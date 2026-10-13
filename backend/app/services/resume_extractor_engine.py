"""
VidyamargAI Universal Resume Extraction Engine.

Powered by the Offline High-Fidelity Resume Engine (v3.0.0):
- Pure deterministic layout and text analysis with Computer Modern bold detection
- Strict document-order table and paragraph traversal
- True reading order reconstruction and multi-column gutter decomposition
- Offline Name, Contact, Experience, Education, Projects, and Skills NER
- Zero-hallucination policy: Missing values remain null; uncalibrated scores flagged for review
- 100% offline execution: No external LLM or network dependency required.
"""

from __future__ import annotations

import io
import os
import re
import json
import hashlib
import logging
import tempfile
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union

from app.resume_engine.resume_extract.pipeline import extract as v3_extract
from app.resume_engine.resume_extract.application_mapping import map_result as v3_map_result
from app.resume_engine.resume_extract.ingest import detect_type as v3_detect_type
from app.resume_engine.resume_extract.config import load_config as v3_load_config

logger = logging.getLogger("app.resume_extractor")


# ─────────────────────────────────────────────────────────────────────────────
# 1. FILE VALIDATION & INTAKE INTEGRITY
# ─────────────────────────────────────────────────────────────────────────────

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
SUPPORTED_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".txt", ".rtf", ".odt", ".html", ".htm",
    ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".pptx", ".tex"
}


def validate_resume_upload(
    filename: str,
    content: bytes,
    content_type: Optional[str] = None
) -> Tuple[bool, str, str, str]:
    """
    Validates uploaded resume payload for format, security bounds, and content validity.
    Returns:
        (is_valid: bool, error_message: str, sha256_hash: str, normalized_ext: str)
    """
    if not content or len(content) == 0:
        return False, "Uploaded file is empty (0 bytes).", "", ""

    if len(content) > MAX_FILE_SIZE_BYTES:
        return False, f"File size exceeds maximum allowed limit of 10 MB ({len(content) / (1024*1024):.1f} MB).", "", ""

    ext = Path(filename).suffix.lower() if filename else ""
    if not ext and content_type:
        mime_map = {
            "application/pdf": ".pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
            "application/msword": ".doc",
            "text/plain": ".txt",
            "application/rtf": ".rtf",
            "text/html": ".html",
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/tiff": ".tiff",
        }
        ext = mime_map.get(content_type, "")

    if not ext:
        if content.startswith(b"%PDF-"):
            ext = ".pdf"
        elif content.startswith(b"PK\x03\x04"):
            ext = ".docx"
        elif content.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
            ext = ".doc"
        elif content.startswith(b"{\\rtf"):
            ext = ".rtf"
        else:
            ext = ".pdf"

    if ext not in SUPPORTED_EXTENSIONS:
        return False, f"Unsupported file extension '{ext}'. Supported formats: PDF, DOCX, DOC, TXT, RTF, ODT, HTML, PNG, JPG.", "", ""

    # Magic-byte and security integrity checks
    if ext == ".pdf":
        if not content.startswith(b"%PDF-"):
            return False, "Invalid PDF signature or corrupted file header.", "", ""
        # Check for encrypted PDF
        try:
            import fitz
            doc = fitz.open(stream=content, filetype="pdf")
            if doc.is_encrypted:
                doc.close()
                return False, "PDF is password-protected or encrypted. Please remove password and re-upload.", "", ""
            if len(doc) == 0:
                doc.close()
                return False, "PDF document contains 0 pages.", "", ""
            doc.close()
        except Exception as e:
            return False, f"Corrupted PDF document: {str(e)}", "", ""

    elif ext in (".docx", ".pptx", ".odt"):
        try:
            import zipfile
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                total_uncompressed = sum(info.file_size for info in zf.infolist())
                if total_uncompressed > 50 * 1024 * 1024:
                    return False, "Decompression limit exceeded (possible zip bomb).", "", ""
                if len(content) > 0 and (total_uncompressed / len(content)) > 100:
                    return False, "Excessive compression ratio detected.", "", ""
        except Exception as e:
            return False, f"Corrupted {ext.upper().lstrip('.')} archive: {str(e)}", "", ""

    file_hash = hashlib.sha256(content).hexdigest()
    return True, "", file_hash, ext


# ─────────────────────────────────────────────────────────────────────────────
# 2. DOCUMENT PARSING & HIGH-FIDELITY EXTRACTION
# ─────────────────────────────────────────────────────────────────────────────

def _safe_run_v3_extract(content: bytes, filename: str, ext: str) -> Dict[str, Any]:
    """
    Executes the v3 resume engine against in-memory content using a temporary file.
    Guarantees clean resource release and deterministic error handling.
    """
    # For images (.png, .jpg, .tiff), convert to PDF first so PyMuPDF reads it
    if ext in (".png", ".jpg", ".jpeg", ".tiff", ".tif"):
        try:
            import fitz
            img_doc = fitz.open(stream=content)
            content = img_doc.convert_to_pdf()
            img_doc.close()
            ext = ".pdf"
            filename = Path(filename).stem + ".pdf"
        except Exception as e:
            logger.warning(f"Image-to-PDF conversion warning: {e}")

    # For legacy DOC without LibreOffice, or other text formats:
    suffix = ext if ext else ".pdf"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        res = v3_extract(tmp_path)
        return res
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def extract_document_content(
    filename: str,
    content: bytes,
    ext: str
) -> Dict[str, Any]:
    """
    Universal entry point for layout-aware document extraction.
    Returns:
        {
            "raw_text": str,
            "page_count": int,
            "layout_info": {
                "format": str,
                "sha256": str,
                "hyperlinks": List[Dict[str, Any]],
                "extraction_result": Dict[str, Any]  # Cached v3 result
            }
        }
    """
    v3_res = _safe_run_v3_extract(content, filename, ext)

    # Extract all discovered hyperlinks
    hyperlinks: List[Dict[str, Any]] = []
    c = v3_res.get("structured", {}).get("contact", {})
    for link_item in c.get("links", []):
        url = link_item.get("value") if isinstance(link_item, dict) else str(link_item)
        if url:
            hyperlinks.append({
                "url": url,
                "label": url,
                "source_format": ext.lstrip("."),
                "source_page": 1,
                "extraction_method": "resume_engine_v3"
            })

    raw_text = v3_res.get("raw_text") or v3_res.get("source_text") or ""
    page_count = v3_res.get("source", {}).get("pages") or 1

    # Extract tables count
    tables_count = 0
    if ext in (".docx", ".doc"):
        try:
            import docx
            doc = docx.Document(io.BytesIO(content))
            tables_count = len(doc.tables)
        except Exception:
            pass
    elif ext == ".pdf":
        try:
            import fitz
            doc = fitz.open(stream=content, filetype="pdf")
            for page in doc:
                try:
                    tables_count += len(page.find_tables().tables)
                except Exception:
                    pass
            doc.close()
        except Exception:
            pass

    return {
        "raw_text": raw_text,
        "page_count": max(1, int(page_count)),
        "layout_info": {
            "format": ext.lstrip("."),
            "sha256": v3_res.get("source", {}).get("sha256", ""),
            "ocr": v3_res.get("source", {}).get("ocr", False),
            "ocr_pages": v3_res.get("source", {}).get("ocr_pages", []),
            "hyperlinks": hyperlinks,
            "tables_count": tables_count,
            "extraction_result": v3_res
        }
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. SCHEMA TRANSFORMATION: V3 TO VIDYAMARGAI CANONICAL PROFILE
# ─────────────────────────────────────────────────────────────────────────────

def _map_v3_to_canonical_schema(v3_res: Dict[str, Any], raw_text: str = "") -> Dict[str, Any]:
    """
    Converts full v3 extraction result into VidyamargAI's canonical database
    and template payload schema with zero hallucination.
    """
    try:
        mapped_wrapper = v3_map_result(v3_res)
        profile = mapped_wrapper.get("profile", {})
    except Exception as e:
        logger.warning(f"Application mapper warning: {e}. Falling back to structured raw dict.")
        profile = {}

    s = v3_res.get("structured", {})
    c_prof = profile.get("contact", {})
    c_raw = s.get("contact", {})

    # 1. Personal Info
    full_name = c_prof.get("full_name")
    if not full_name:
        name_obj = c_raw.get("name")
        full_name = name_obj.get("value") if isinstance(name_obj, dict) else str(name_obj or "")

    emails = c_prof.get("emails") or []
    email = emails[0] if emails else ""
    if not email:
        raw_emails = c_raw.get("emails") or []
        if raw_emails:
            e0 = raw_emails[0]
            email = e0.get("value") if isinstance(e0, dict) else str(e0 or "")

    phones = c_prof.get("phones") or []
    phone = ""
    if phones:
        p0 = phones[0]
        if isinstance(p0, dict):
            phone = p0.get("normalized") or p0.get("raw") or ""
        else:
            phone = str(p0)
    if not phone:
        raw_phones = c_raw.get("phones") or []
        if raw_phones:
            p0 = raw_phones[0]
            phone = p0.get("normalized") or p0.get("value") or ""
    if not phone and raw_text:
        phone_match = re.search(
            r"(?:\+?\d{1,3}[-.\s]*)?\(?\d{3}\)?[-.\s]*\d{3}[-.\s]*\d{4}|\b\+?1[-.\s]*\d{3}[-.\s]*\d{3,4}\b|\b\d{3}[-.\s]+\d{4}\b",
            raw_text
        )
        if phone_match:
            phone = phone_match.group(0).strip()

    locations = c_prof.get("locations") or []
    location = locations[0] if locations else ""
    city, state = None, None
    if not location and raw_text:
        for line in raw_text.splitlines()[:6]:
            m = re.search(r"([A-Za-z\s]+),\s*([A-Z]{2}\b|[A-Za-z]+)", line)
            if m:
                loc_cand = m.group(0).strip()
                if not any(k in loc_cand.lower() for k in ("http", "github", "linkedin", "email", "@")):
                    location = loc_cand
                    break
    if location:
        parts = [p.strip() for p in location.split(",") if p.strip()]
        if len(parts) >= 1:
            city = parts[0]
        if len(parts) >= 2:
            state = parts[1].split()[0] if parts[1] else None

    links = c_prof.get("links") or []
    raw_links = [l.get("value") if isinstance(l, dict) else str(l) for l in c_raw.get("links", [])]
    all_links = list(dict.fromkeys(links + raw_links))

    linkedin_url = next((l for l in all_links if "linkedin.com" in l.lower()), None)
    github_url = next((l for l in all_links if "github.com" in l.lower()), None)
    portfolio_url = next((l for l in all_links if l != linkedin_url and l != github_url and ("http" in l or "www" in l)), None)

    headline = c_prof.get("headline")

    personal_info = {
        "full_name": full_name or None,
        "first_name": full_name.split()[0] if full_name else None,
        "last_name": full_name.split()[-1] if full_name and len(full_name.split()) > 1 else None,
        "middle_name": " ".join(full_name.split()[1:-1]) if full_name and len(full_name.split()) > 2 else None,
        "email": email or None,
        "phone": phone or None,
        "location": location or None,
        "city": city,
        "state": state,
        "country": None,
        "linkedin": linkedin_url,
        "linkedin_url": linkedin_url,
        "github": github_url,
        "github_url": github_url,
        "portfolio": portfolio_url,
        "portfolio_url": portfolio_url,
        "website": portfolio_url,
        "professional_title": headline
    }

    # 2. Professional Summary
    summary_parts = []
    for sum_item in profile.get("summary") or s.get("summary") or []:
        if isinstance(sum_item, dict):
            txt = sum_item.get("text") or sum_item.get("value") or ""
        else:
            txt = str(sum_item)
        if txt.strip():
            summary_parts.append(txt.strip())
    summary_text = "\n\n".join(summary_parts)

    # 3. Work Experience
    experiences: List[Dict[str, Any]] = []
    exp_source = profile.get("experience") or s.get("experience") or []
    for exp in exp_source:
        if not isinstance(exp, dict):
            continue
        emp = exp.get("employer") or exp.get("company")
        if isinstance(emp, dict):
            emp = emp.get("value")
        desig = exp.get("title") or exp.get("designation")
        if isinstance(desig, dict):
            desig = desig.get("value")
        loc = exp.get("location")
        if isinstance(loc, dict):
            loc = loc.get("value")

        if not emp and desig and " - " in desig:
            parts = desig.split(" - ", 1)
            desig = parts[0].strip()
            emp = parts[1].strip()

        dates = exp.get("dates") or {}
        s_date, e_date = "", ""
        is_current = False
        if isinstance(dates, dict):
            if "start" in dates and isinstance(dates["start"], dict):
                s_date = dates["start"].get("raw") or dates["start"].get("normalized") or ""
            elif isinstance(dates.get("start"), str):
                s_date = dates["start"]
            elif "value" in dates and isinstance(dates["value"], dict):
                s_date = dates["value"].get("start") or ""
                e_date = dates["value"].get("end") or ""

            if "end" in dates and isinstance(dates["end"], dict):
                e_date = dates["end"].get("raw") or dates["end"].get("normalized") or ""
            elif isinstance(dates.get("end"), str):
                e_date = dates["end"]

            is_current = bool(re.search(r"present|current|now", str(e_date), re.I)) or dates.get("ongoing_as_reported", False)

        bullets = []
        raw_bullets = exp.get("bullets") or exp.get("responsibilities") or []
        for b in raw_bullets:
            if isinstance(b, dict):
                btxt = b.get("text") or b.get("value") or ""
            else:
                btxt = str(b)
            # Clean leading bullet symbols
            btxt = re.sub(r"^[\s•·∙○●▪■►▸▶◆◇★☆✦✧✓✔\-\*–—\x95\x85]+\s*", "", btxt).strip()
            if btxt:
                bullets.append(btxt)

        if not bullets and exp.get("text"):
            for l in exp["text"].splitlines():
                l_strip = l.strip()
                if l_strip.startswith(("-", "•", "*", "–", "—")):
                    c_txt = re.sub(r"^[\s•·∙○●▪■►▸▶◆◇★☆✦✧✓✔\-\*–—\x95\x85]+\s*", "", l_strip).strip()
                    if c_txt:
                        bullets.append(c_txt)

        experiences.append({
            "employer": emp or "",
            "company": emp or "",
            "designation": desig or "",
            "title": desig or "",
            "location": loc or "",
            "start_date": s_date or "",
            "end_date": e_date or "",
            "is_current": is_current,
            "responsibilities": bullets,
            "bullets": bullets,
            "description": exp.get("description") or ""
        })

    # 4. Education
    educations: List[Dict[str, Any]] = []
    edu_source = profile.get("education") or s.get("education") or []
    for edu in edu_source:
        if not isinstance(edu, dict):
            continue
        inst = edu.get("institution")
        if isinstance(inst, dict):
            inst = inst.get("value")
        deg = edu.get("degree")
        if isinstance(deg, dict):
            deg = deg.get("value")
        loc = edu.get("location")
        if isinstance(loc, dict):
            loc = loc.get("value")

        dates = edu.get("dates") or {}
        s_date, e_date = "", ""
        if isinstance(dates, dict):
            if "start" in dates and isinstance(dates["start"], dict):
                s_date = dates["start"].get("raw") or ""
            elif isinstance(dates.get("start"), str):
                s_date = dates["start"]
            elif "value" in dates and isinstance(dates["value"], dict):
                s_date = dates["value"].get("start") or ""
                e_date = dates["value"].get("end") or ""

            if "end" in dates and isinstance(dates["end"], dict):
                e_date = dates["end"].get("raw") or ""
            elif isinstance(dates.get("end"), str):
                e_date = dates["end"]

        grad_obj = edu.get("graduation") or {}
        grad_yr = grad_obj.get("raw") if isinstance(grad_obj, dict) else (grad_obj or e_date)

        gpa_obj = edu.get("gpa") or {}
        gpa_val = ""
        if isinstance(gpa_obj, dict):
            if "score" in gpa_obj:
                scale = gpa_obj.get("scale") or "4.0"
                gpa_val = f"{gpa_obj['score']}/{scale}"
            elif "value" in gpa_obj:
                gpa_val = str(gpa_obj["value"])
        elif isinstance(gpa_obj, str):
            gpa_val = gpa_obj

        educations.append({
            "institution": inst or "",
            "degree": deg or "",
            "field_of_study": deg or "",
            "location": loc or "",
            "start_date": s_date or "",
            "end_date": e_date or "",
            "graduation_year": grad_yr or "",
            "gpa": gpa_val
        })

    # 5. Projects
    projects: List[Dict[str, Any]] = []
    proj_source = profile.get("projects") or s.get("projects") or []
    for pr in proj_source:
        if not isinstance(pr, dict):
            continue
        pname = pr.get("name")
        if isinstance(pname, dict):
            pname = pname.get("value")

        tech_list = []
        raw_tech = pr.get("technologies") or []
        for t in raw_tech:
            if isinstance(t, dict):
                tval = t.get("value") or ""
            else:
                tval = str(t)
            if tval.strip():
                tech_list.append(tval.strip())

        dates = pr.get("dates") or {}
        s_date, e_date = "", ""
        if isinstance(dates, dict):
            if "start" in dates and isinstance(dates["start"], dict):
                s_date = dates["start"].get("raw") or ""
            elif isinstance(dates.get("start"), str):
                s_date = dates["start"]
            elif "value" in dates and isinstance(dates["value"], dict):
                s_date = dates["value"].get("start") or ""
                e_date = dates["value"].get("end") or ""

            if "end" in dates and isinstance(dates["end"], dict):
                e_date = dates["end"].get("raw") or ""
            elif isinstance(dates.get("end"), str):
                e_date = dates["end"]

        bullets = []
        for b in pr.get("bullets") or pr.get("responsibilities") or []:
            btxt = b.get("text") or b.get("value") if isinstance(b, dict) else str(b)
            btxt = re.sub(r"^[\s•·∙○●▪■►▸▶◆◇★☆✦✧✓✔\-\*–—\x95\x85]+\s*", "", btxt).strip()
            if btxt:
                bullets.append(btxt)

        projects.append({
            "name": pname or "",
            "technologies": tech_list,
            "start_date": s_date or "",
            "end_date": e_date or "",
            "description": pr.get("description") or "",
            "responsibilities": bullets,
            "bullets": bullets
        })

    # 6. Skills
    skills_dict: Dict[str, List[str]] = {
        "programming_languages": [],
        "frameworks_libraries": [],
        "databases": [],
        "cloud_platforms": [],
        "developer_tools": [],
        "ai_ml_technologies": [],
        "soft_skills": [],
        "domain_knowledge": [],
        "other_skills": [],
        "all_raw_skills": []
    }

    seen_skills = set()
    skills_source = profile.get("skills") or s.get("skills") or []
    for g in skills_source:
        cat_name = (g.get("category") or "Technical Skills").lower()
        items = g.get("items") or []
        for it in items:
            clean_it = str(it).strip()
            if clean_it and clean_it.lower() not in seen_skills:
                seen_skills.add(clean_it.lower())
                skills_dict["all_raw_skills"].append(clean_it)

                # Categorize into standard groups
                if any(k in cat_name for k in ("program", "language", "coding")):
                    skills_dict["programming_languages"].append(clean_it)
                elif any(k in cat_name for k in ("framework", "library")):
                    skills_dict["frameworks_libraries"].append(clean_it)
                elif any(k in cat_name for k in ("database", "sql", "datastore")):
                    skills_dict["databases"].append(clean_it)
                elif any(k in cat_name for k in ("cloud", "devops", "platform", "aws", "azure", "docker")):
                    skills_dict["cloud_platforms"].append(clean_it)
                elif any(k in cat_name for k in ("tool", "platform", "git")):
                    skills_dict["developer_tools"].append(clean_it)
                elif any(k in cat_name for k in ("ai", "ml", "learning", "intelligence", "nlp", "vision")):
                    skills_dict["ai_ml_technologies"].append(clean_it)
                elif any(k in cat_name for k in ("soft", "competenc", "leadership")):
                    skills_dict["soft_skills"].append(clean_it)
                else:
                    skills_dict["other_skills"].append(clean_it)

    # Parse explicit skill category lines in raw_text if present (e.g. Languages: Python, Go)
    for line in (raw_text or "").splitlines():
        line_clean = line.strip()
        if not line_clean:
            continue
        m = re.match(r"^(Languages?|Frameworks?(?:\s*&\s*Libraries)?|Databases?|Cloud(?:\s*&\s*Tools)?|Tools?|DevOps|Platforms?)[:\s]+(.+)$", line_clean, re.I)
        if m:
            cat_header = m.group(1).lower()
            items_str = m.group(2)
            for it in re.split(r"[,|•·;]\s*", items_str):
                it_clean = it.strip()
                if it_clean and it_clean.lower() not in seen_skills:
                    seen_skills.add(it_clean.lower())
                    skills_dict["all_raw_skills"].append(it_clean)
                    if any(k in cat_header for k in ("lang", "program")):
                        skills_dict["programming_languages"].append(it_clean)
                    elif any(k in cat_header for k in ("cloud", "devops", "tool")):
                        skills_dict["cloud_platforms"].append(it_clean)
                    elif any(k in cat_header for k in ("database", "sql")):
                        skills_dict["databases"].append(it_clean)
                    elif any(k in cat_header for k in ("framework", "library")):
                        skills_dict["frameworks_libraries"].append(it_clean)
                    else:
                        skills_dict["developer_tools"].append(it_clean)

    # Enrich from fields skills NER
    for f_sk in v3_res.get("fields", {}).get("skills", []):
        sk_val = f_sk.get("value") if isinstance(f_sk, dict) else str(f_sk)
        if sk_val and sk_val.lower() not in seen_skills:
            seen_skills.add(sk_val.lower())
            skills_dict["all_raw_skills"].append(sk_val)
            lower_v = sk_val.lower()
            if lower_v in ("python", "go", "bash", "c++", "c", "java", "javascript", "typescript", "rust", "ruby", "php", "swift", "kotlin", "sql", "julia", "r"):
                skills_dict["programming_languages"].append(sk_val)
            elif lower_v in ("docker", "kubernetes", "terraform", "aws", "gcp", "azure", "prometheus", "grafana", "helm", "ansible"):
                skills_dict["cloud_platforms"].append(sk_val)
            elif lower_v in ("postgresql", "redis", "mysql", "mongodb", "sqlite", "elasticsearch"):
                skills_dict["databases"].append(sk_val)
            elif lower_v in ("fastapi", "react", "django", "flask", "pytorch", "tensorflow", "node.js", "next.js"):
                skills_dict["frameworks_libraries"].append(sk_val)
            else:
                skills_dict["other_skills"].append(sk_val)

    # 7. Certifications & Other Sections
    certifications = []
    for cert in profile.get("certifications") or s.get("certifications") or []:
        if isinstance(cert, dict):
            cname = cert.get("name") or cert.get("text") or ""
        else:
            cname = str(cert)
        if cname.strip():
            certifications.append({"name": cname.strip()})

    languages = []
    other_secs = profile.get("other_sections") or s.get("other_sections") or []
    for sec in other_secs:
        if isinstance(sec, dict) and "language" in sec.get("type", "").lower():
            for item in sec.get("items", []):
                languages.append(item.get("text") if isinstance(item, dict) else str(item))

    # 8. Custom Sections Preservation
    custom_sections: List[Dict[str, Any]] = []
    for sec in v3_res.get("sections", []):
        h = sec.get("original_heading")
        canon = sec.get("canonical")
        if canon == "custom" or (h and canon not in ("preamble", "contact", "summary", "experience", "education", "skills", "projects", "certifications")):
            title = h or canon or "Custom Section"
            custom_sections.append({
                "section_title": title,
                "title": title,
                "content": sec.get("text", "").strip()
            })

    for sec in v3_res.get("structured", {}).get("other_sections", []):
        title = sec.get("original_heading") or sec.get("canonical") or "Custom Section"
        if not any(c["section_title"] == title for c in custom_sections):
            custom_sections.append({
                "section_title": title,
                "title": title,
                "content": sec.get("text", "").strip()
            })

    custom_heading_patterns = [
        r"Open Source (?:Contributions?|Projects?)",
        r"Volunteer(?:ing)? (?:Work|Experience)?",
        r"Patents?(?: and Inventions)?",
        r"Publications?",
        r"Awards?(?: and Honors)?",
        r"Leadership(?: Experience)?",
        r"Speaking(?: Engagements)?",
        r"Interests?(?: and Activities)?",
    ]
    for pat in custom_heading_patterns:
        m = re.search(rf"^(?:[\s#*-]*)(({pat})\b[^\n]*)\n+(.+?)(?=\n\s*(?:[A-Z][a-zA-Z\s]{{2,30}}\n|$)|\Z)", raw_text or "", re.M | re.S | re.I)
        if m:
            heading_text = m.group(1).strip()
            content_text = m.group(3).strip()
            heading_clean = heading_text.lstrip("#*- ").rstrip(":")
            if not any(heading_clean.lower() in c["section_title"].lower() for c in custom_sections):
                custom_sections.append({
                    "section_title": heading_clean,
                    "title": heading_clean,
                    "content": content_text
                })

    # Review flags & quality
    review_issues = v3_res.get("needs_review") or s.get("review") or []
    warnings = [r.get("reason", "") for r in review_issues if isinstance(r, dict)]

    missing_fields = []
    if not personal_info["full_name"]: missing_fields.append("full_name")
    if not personal_info["email"]: missing_fields.append("email")
    if not personal_info["phone"]: missing_fields.append("phone")
    if not skills_dict["all_raw_skills"]: missing_fields.append("skills")
    if not experiences: missing_fields.append("work_experience")
    if not educations: missing_fields.append("education")

    # Overall Confidence Calculation
    quality = v3_res.get("quality", {})
    completeness_status = quality.get("completeness", {}).get("status", "pass")
    confidence_score = 0.95 if completeness_status == "pass" else 0.85
    if missing_fields:
        confidence_score -= (0.05 * len(missing_fields))
    confidence_score = max(0.5, min(1.0, round(confidence_score, 2)))

    return {
        "personal_info": personal_info,
        "professional_summary": summary_text,
        "work_experience": experiences,
        "education": educations,
        "projects": projects,
        "skills": skills_dict,
        "certifications": certifications,
        "languages": languages,
        "custom_sections": custom_sections,
        "confidence_score": confidence_score,
        "missing_fields": missing_fields,
        "extraction_warnings": warnings,
        "needs_review": review_issues,
        "v3_result": v3_res  # Lossless reference
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. STRUCTURED EXTRACTION ORCHESTRATION
# ─────────────────────────────────────────────────────────────────────────────

def extract_structured_with_ai(
    raw_text: str,
    pdf_bytes: Optional[bytes] = None,
    layout_info: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Offline deterministic structured extraction engine.
    Uses cached v3 parsing result if available; otherwise runs fresh v3 extraction.
    Never hallucinates, never calls external paid LLMs.
    """
    cached_res = (layout_info or {}).get("extraction_result")
    if cached_res:
        return _map_v3_to_canonical_schema(cached_res, raw_text)

    # If no cached result, extract from pdf_bytes or raw_text
    if pdf_bytes:
        v3_res = _safe_run_v3_extract(pdf_bytes, "resume.pdf", ".pdf")
        return _map_v3_to_canonical_schema(v3_res, raw_text)
    else:
        text_bytes = raw_text.encode("utf-8")
        v3_res = _safe_run_v3_extract(text_bytes, "resume.txt", ".txt")
        return _map_v3_to_canonical_schema(v3_res, raw_text)


def heuristic_comprehensive_parse(
    raw_text: str,
    layout_info: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Offline heuristic parse alias routing directly to the v3 deterministic engine."""
    return extract_structured_with_ai(raw_text, None, layout_info)


# ─────────────────────────────────────────────────────────────────────────────
# 5. PUBLIC CONVENIENCE ALIASES
# ─────────────────────────────────────────────────────────────────────────────

def extract_pdf_layout_aware(content: bytes) -> Dict[str, Any]:
    return extract_document_content("resume.pdf", content, ".pdf")


def extract_docx_content(content: bytes) -> Dict[str, Any]:
    return extract_document_content("resume.docx", content, ".docx")
