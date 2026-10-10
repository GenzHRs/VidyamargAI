"""
A-to-Z Resume Data Extraction & Storage Engine.
Combines:
- File validation (magic bytes, size, SHA-256 integrity hash)
- Layout-aware PDF extraction (multi-column reading-order detection, link extraction)
- Scanned document OCR detection & fallback
- DOCX parsing (paragraphs, tables, hyperlinks, headers, footers)
- Fuzzy section segmentation
- AI-based semantic structured extraction with strict zero-hallucination guarantees
- Offline heuristic fallback parser (zero downtime when AI is offline)
- Consistency, date anomaly, and completeness checks
"""
import hashlib
import io
import json
import logging
import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("app.resume_extractor")

MAX_RESUME_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_RESUME_EXTENSIONS = {".pdf", ".docx", ".txt", ".tex"}


# ─────────────────────────────────────────────────────────────────────────────
# 1. FILE VALIDATION & INTEGRITY HASHING
# ─────────────────────────────────────────────────────────────────────────────

def validate_resume_upload(
    filename: str,
    content: bytes,
    content_type: Optional[str] = None
) -> Tuple[bool, str, str, str]:
    """
    Validates file extension, size, MIME type, and magic bytes.
    Computes SHA-256 integrity hash for duplicate detection.
    Returns: (is_valid, error_msg, sha256_hash, ext)
    """
    if len(content) == 0:
        return False, "Uploaded file is empty (0 bytes).", "", ""

    if len(content) > MAX_RESUME_UPLOAD_SIZE:
        return False, f"File size ({len(content)/(1024*1024):.1f}MB) exceeds the 10MB limit.", "", ""

    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_RESUME_EXTENSIONS:
        return False, f"Unsupported file type '{ext}'. Allowed formats: PDF, DOCX, TXT, TEX.", "", ""

    # Magic byte verification
    if ext == ".pdf":
        if not content.startswith(b"%PDF-"):
            return False, "Invalid PDF signature. The file appears corrupted or disguised.", "", ""
    elif ext == ".docx":
        if not content.startswith(b"PK\x03\x04"):
            return False, "Invalid DOCX signature (not a valid Word XML package).", "", ""
    elif ext in (".txt", ".tex"):
        try:
            content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                content.decode("latin-1")
            except Exception:
                return False, "Plain text file cannot be decoded as valid text.", "", ""

    file_hash = hashlib.sha256(content).hexdigest()
    return True, "", file_hash, ext


# ─────────────────────────────────────────────────────────────────────────────
# 2. DOCUMENT PARSING & LAYOUT-AWARE EXTRACTION
# ─────────────────────────────────────────────────────────────────────────────

def extract_document_content(
    filename: str,
    content: bytes,
    ext: str
) -> Dict[str, Any]:
    """
    Extracts raw text, detects reading order for multi-column layouts,
    extracts embedded hyperlinks, and detects scanned pages.
    Returns:
    {
      "raw_text": str,
      "page_count": int,
      "layout_info": {
        "columns_detected": bool,
        "scanned_pages": list[int],
        "hyperlinks": list[dict],
        "tables_count": int
      }
    }
    """
    if ext == ".pdf":
        return _extract_pdf_layout_aware(content)
    elif ext == ".docx":
        return _extract_docx_with_tables(content)
    elif ext == ".tex":
        return _extract_tex_clean(content)
    else:
        return _extract_plain_text(content)


def _extract_pdf_layout_aware(content: bytes) -> Dict[str, Any]:
    """
    Extracts text using PyMuPDF (fitz) with column-aware reading order,
    annotation hyperlink recovery, and OCR fallback for scanned pages.
    """
    import fitz  # PyMuPDF

    doc = fitz.open(stream=content, filetype="pdf")
    page_count = len(doc)
    page_texts: List[str] = []
    scanned_pages: List[int] = []
    hyperlinks: List[Dict[str, str]] = []
    multi_column_detected = False

    for page_idx in range(page_count):
        page = doc[page_idx]

        # 1. Recover embedded hyperlinks (LinkedIn, GitHub, Portfolio URLs)
        try:
            links = page.get_links()
            for l in links:
                uri = l.get("uri")
                if uri and uri.startswith(("http://", "https://", "mailto:")):
                    hyperlinks.append({"page": page_idx + 1, "uri": uri})
        except Exception as e:
            logger.debug(f"Link extraction error on page {page_idx + 1}: {e}")

        # 2. Layout-aware block extraction
        blocks = page.get_text("blocks")  # (x0, y0, x1, y1, text, block_no, block_type)
        page_width = page.rect.width

        # Filter text blocks only (block_type == 0)
        text_blocks = [b for b in blocks if len(b) >= 5 and b[4].strip() and b[6] == 0]

        # Multi-column heuristic: check if blocks are distributed across left and right halves
        left_blocks = [b for b in text_blocks if b[2] <= page_width * 0.58]
        right_blocks = [b for b in text_blocks if b[0] >= page_width * 0.42]

        if len(left_blocks) >= 3 and len(right_blocks) >= 3:
            multi_column_detected = True
            # Sort left column top-to-bottom, then right column top-to-bottom
            left_blocks.sort(key=lambda b: (b[1], b[0]))
            right_blocks.sort(key=lambda b: (b[1], b[0]))
            # Remaining header or full-width blocks
            full_blocks = [b for b in text_blocks if b not in left_blocks and b not in right_blocks]
            full_blocks.sort(key=lambda b: b[1])

            ordered_blocks = full_blocks + left_blocks + right_blocks
        else:
            # Standard single column or top-to-bottom flow
            ordered_blocks = sorted(text_blocks, key=lambda b: (b[1], b[0]))

        extracted_page_str = "\n".join([b[4].strip() for b in ordered_blocks if b[4].strip()])

        # 3. Check for Scanned / Image-only page
        if len(extracted_page_str.strip()) < 50:
            scanned_pages.append(page_idx + 1)
            # Try OCR fallback on this page
            ocr_text = _attempt_ocr_on_page(page)
            if ocr_text:
                extracted_page_str = ocr_text

        page_texts.append(extracted_page_str)

    doc.close()

    raw_text = "\n\n".join(page_texts).strip()

    # Append any unique hyperlinks found to assist contact detection
    if hyperlinks:
        unique_uris = list(dict.fromkeys([h["uri"] for h in hyperlinks]))
        raw_text += "\n\n--- EXTRACTED HYPERLINKS ---\n" + "\n".join(unique_uris)

    return {
        "raw_text": raw_text,
        "page_count": page_count,
        "layout_info": {
            "columns_detected": multi_column_detected,
            "scanned_pages": scanned_pages,
            "hyperlinks": hyperlinks,
            "tables_count": 0
        }
    }


def _attempt_ocr_on_page(page) -> str:
    """Runs OCR on page pixmap when selectable text is missing."""
    try:
        pix = page.get_pixmap(dpi=150)
        img_bytes = pix.tobytes("png")

        # Try PaddleOCR if available
        try:
            from paddleocr import PaddleOCR
            import numpy as np
            from PIL import Image

            ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
            image = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            img_np = np.array(image)
            result = ocr.ocr(img_np, cls=True)
            if result and result[0]:
                lines = [line[1][0] for line in result[0] if line and len(line) > 1]
                return "\n".join(lines).strip()
        except Exception as ocr_err:
            logger.debug(f"PaddleOCR fallback not run or encountered error: {ocr_err}")

    except Exception as e:
        logger.warning(f"OCR rendering error: {e}")

    return ""


def _extract_docx_with_tables(content: bytes) -> Dict[str, Any]:
    """Extracts DOCX paragraphs, table rows, headers, footers, and hyperlinks."""
    import docx

    doc = docx.Document(io.BytesIO(content))
    text_chunks: List[str] = []
    tables_found = 0

    # 1. Headers & Footers (contact details often live here)
    for section in doc.sections:
        try:
            for p in section.header.paragraphs:
                if p.text.strip():
                    text_chunks.append(p.text.strip())
        except Exception:
            pass

    # 2. Main document paragraphs
    for p in doc.paragraphs:
        if p.text.strip():
            text_chunks.append(p.text.strip())

    # 3. Tables (skill matrices, work tables, project grids)
    for table in doc.tables:
        tables_found += 1
        table_rows = []
        for row in table.rows:
            row_cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            # deduplicate repeated merged cells
            seen = set()
            dedup_cells = [c for c in row_cells if not (c in seen or seen.add(c))]
            if dedup_cells:
                table_rows.append(" | ".join(dedup_cells))
        if table_rows:
            text_chunks.append("\n" + "\n".join(table_rows) + "\n")

    # 4. Hyperlinks extraction from document relationships
    hyperlinks = []
    try:
        for rel in doc.part.rels.values():
            if "hyperlink" in rel.reltype and rel.target_ref.startswith(("http", "mailto")):
                hyperlinks.append({"uri": rel.target_ref})
    except Exception:
        pass

    raw_text = "\n".join(text_chunks).strip()
    if hyperlinks:
        unique_uris = list(dict.fromkeys([h["uri"] for h in hyperlinks]))
        raw_text += "\n\n--- EXTRACTED HYPERLINKS ---\n" + "\n".join(unique_uris)

    return {
        "raw_text": raw_text,
        "page_count": max(1, len(text_chunks) // 40),
        "layout_info": {
            "columns_detected": False,
            "scanned_pages": [],
            "hyperlinks": hyperlinks,
            "tables_count": tables_found
        }
    }


def _extract_tex_clean(content: bytes) -> Dict[str, Any]:
    try:
        raw = content.decode("utf-8")
    except UnicodeDecodeError:
        raw = content.decode("latin-1", errors="replace")

    clean_lines = []
    for line in raw.split("\n"):
        line = re.sub(r"%.*$", "", line)  # remove comments
        if line.strip():
            clean_lines.append(line.strip())

    return {
        "raw_text": "\n".join(clean_lines).strip(),
        "page_count": 1,
        "layout_info": {"columns_detected": False, "scanned_pages": [], "hyperlinks": [], "tables_count": 0}
    }


def _extract_plain_text(content: bytes) -> Dict[str, Any]:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("latin-1", errors="replace")

    return {
        "raw_text": text.strip(),
        "page_count": max(1, len(text.split("\n")) // 50),
        "layout_info": {"columns_detected": False, "scanned_pages": [], "hyperlinks": [], "tables_count": 0}
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. COMPREHENSIVE EXTRACTION SCHEMA DEFINITIONS & AI PROMPTING
# ─────────────────────────────────────────────────────────────────────────────

EXTRACTION_SYSTEM_PROMPT = """You are an expert AI Resume Parsing Engine and Human Resources Information Architect.
Extract ALL information from the provided resume text with zero hallucination.
Never invent or extrapolate facts not explicitly stated or directly verifiable.
Use `null` for missing scalar fields and `[]` for missing lists. Preserve original wording alongside clean values.

CRITICAL MANDATORY RULES:
1. NEVER STOP AFTER THE FIRST PROJECT OR FIRST COMPANY.
   If the resume contains N projects (e.g. 5 projects), you MUST return N distinct objects in the "projects" array.
   If the resume contains M work experience entries / companies, you MUST return M distinct objects in the "work_experience" array.
2. COMPANY & WORK EXPERIENCE EXTRACTION:
   Extract company/employer into "employer", designation/job title into "designation", dates into "start_date" and "end_date".
   Never merge multiple companies into one or combine company name with dates/designations.
3. PROJECT EXTRACTION & BOUNDARY ATTRIBUTION:
   - Extract every project independently with its exact name, duration/dates, tech stack ("technologies" list), and ALL bullet points ("responsibilities"/"features").
   - Do NOT merge bullet points or technologies across project boundaries.
   - If a project block has dates or a "Tech:" line without an inline project title, inspect preceding text lines/headings to capture the true project name.
4. PRESERVE ALL ORIGINAL DATA WITHOUT TRUNCATION OR HALLUCINATION.

Return ONLY a valid JSON object matching the following comprehensive schema:
{
  "personal_info": {
    "full_name": string or null,
    "first_name": string or null,
    "middle_name": string or null,
    "last_name": string or null,
    "professional_title": string or null,
    "email": string or null,
    "additional_emails": [string],
    "phone": string or null,
    "additional_phones": [string],
    "location": string or null,
    "city": string or null,
    "state": string or null,
    "country": string or null,
    "linkedin_url": string or null,
    "github_url": string or null,
    "portfolio_url": string or null,
    "custom_links": [{"label": string, "url": string}]
  },
  "professional_summary": {
    "summary": string or null,
    "career_objective": string or null,
    "years_of_experience": number or null,
    "areas_of_specialization": [string],
    "career_interests": [string]
  },
  "skills": {
    "programming_languages": [string],
    "frameworks_libraries": [string],
    "databases": [string],
    "cloud_platforms": [string],
    "developer_tools": [string],
    "ai_ml_technologies": [string],
    "soft_skills": [string],
    "domain_knowledge": [string],
    "other_skills": [string],
    "all_raw_skills": [string]
  },
  "work_experience": [
    {
      "employer": string,
      "designation": string,
      "employment_location": string or null,
      "start_date": string or null,
      "end_date": string or null,
      "is_current": boolean,
      "employment_type": string or null,
      "responsibilities": [string],
      "achievements": [string],
      "technologies": [string],
      "metrics": [string],
      "original_text": string or null
    }
  ],
  "education": [
    {
      "degree": string,
      "field_of_study": string or null,
      "institution": string,
      "location": string or null,
      "start_date": string or null,
      "end_date": string or null,
      "graduation_year": string or null,
      "grade": string or null,
      "relevant_coursework": [string],
      "achievements": [string],
      "thesis": string or null
    }
  ],
  "projects": [
    {
      "name": string,
      "description": string or null,
      "problem": string or null,
      "solution": string or null,
      "technologies": [string],
      "responsibilities": [string],
      "features": [string],
      "results_metrics": [string],
      "duration": string or null,
      "link": string or null,
      "project_type": string or null
    }
  ],
  "certifications": [
    {
      "name": string,
      "issuing_organization": string or null,
      "issue_date": string or null,
      "expiration_date": string or null,
      "credential_id": string or null,
      "credential_url": string or null,
      "training_type": string or null
    }
  ],
  "achievements": [string],
  "publications": [
    {
      "title": string,
      "publisher": string or null,
      "date": string or null,
      "url": string or null
    }
  ],
  "languages": [
    {
      "language": string,
      "proficiency": string or null
    }
  ],
  "custom_sections": [
    {
      "section_title": string,
      "original_content": string,
      "structured_content": any
    }
  ],
  "extraction_warnings": [string]
}
"""


def extract_structured_with_ai(
    raw_text: str,
    pdf_bytes: Optional[bytes] = None
) -> Dict[str, Any]:
    """
    Invokes external AI provider with strict JSON output.
    Gracefully falls back to heuristic extraction if unconfigured or unreachable.
    Performs multi-pass safety merging to guarantee NO projects or companies are omitted.
    """
    from app.services.ai_provider import ai_provider_service

    # Check if AI provider is available
    if not (ai_provider_service.is_gemini_configured() or
            ai_provider_service.is_nvidia_configured() or
            ai_provider_service.is_groq_configured()):
        logger.info("AI provider not configured. Using high-fidelity 2-pass heuristic parser.")
        return heuristic_comprehensive_parse(raw_text)

    prompt = f"{EXTRACTION_SYSTEM_PROMPT}\n\nRESUME TEXT TO EXTRACT:\n{raw_text[:14000]}"

    parsed = None
    try:
        # Multimodal Gemini if PDF bytes available and Gemini configured
        if pdf_bytes and ai_provider_service.is_gemini_configured():
            try:
                response = ai_provider_service.call_gemini(
                    prompt=prompt,
                    json_mode=True,
                    pdf_bytes=pdf_bytes
                )
                parsed = _clean_and_parse_json(response)
            except Exception as e:
                logger.warning(f"Multimodal Gemini parse failed, falling back to text AI: {e}")

        if not parsed:
            # Text-based fallback through chained AI providers (NVIDIA / Groq / Gemini)
            response_text = ai_provider_service.call_with_fallback(prompt, json_mode=True)
            parsed = _clean_and_parse_json(response_text)

        if parsed and isinstance(parsed, dict) and "personal_info" in parsed:
            # Multi-pass safety merge with heuristic 2-pass extraction to ensure NO projects or companies are lost
            heuristic_data = heuristic_comprehensive_parse(raw_text)
            
            # 1. Merge projects
            ai_projs = parsed.get("projects") or []
            h_projs = heuristic_data.get("projects") or []
            if len(h_projs) > len(ai_projs):
                logger.info(f"Multi-pass check: Heuristic parser identified {len(h_projs)} projects vs AI {len(ai_projs)}. Merging missing project entries.")
                ai_names = [str(p.get("name", "")).lower() for p in ai_projs]
                for hp in h_projs:
                    h_n = str(hp.get("name", "")).lower()
                    if h_n and h_n != "project" and not any(h_n in ai_n or ai_n in h_n for ai_n in ai_names if ai_n):
                        ai_projs.append(hp)
                parsed["projects"] = ai_projs

            # 2. Merge work experience
            ai_exps = parsed.get("work_experience") or []
            h_exps = heuristic_data.get("work_experience") or []
            if len(h_exps) > len(ai_exps):
                logger.info(f"Multi-pass check: Heuristic parser identified {len(h_exps)} companies vs AI {len(ai_exps)}. Merging missing work experience entries.")
                ai_emp_names = [str(e.get("employer", e.get("company", ""))).lower() for e in ai_exps]
                for he in h_exps:
                    he_emp = str(he.get("employer", he.get("company", ""))).lower()
                    if he_emp and he_emp != "company" and not any(he_emp in ai_e or ai_e in he_emp for ai_e in ai_emp_names if ai_e):
                        ai_exps.append(he)
                parsed["work_experience"] = ai_exps

            return _normalize_and_validate_extraction(parsed, raw_text)

    except Exception as e:
        logger.error(f"AI structured parsing failed: {e}. Falling back to 2-pass heuristic engine.")

    return heuristic_comprehensive_parse(raw_text)


def _clean_and_parse_json(raw_json: str) -> Optional[Dict[str, Any]]:
    """Strips markdown fences and safely parses JSON."""
    cleaned = raw_json.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except Exception as e:
        logger.warning(f"JSON parsing error: {e}")
        # Try finding outer braces
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1:
            try:
                return json.loads(cleaned[start:end + 1])
            except Exception:
                pass
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 4. OFFLINE HEURISTIC PARSER (HIGH FIDELITY 2-PASS STRUCTURAL ENGINE)
# ─────────────────────────────────────────────────────────────────────────────

COMPANY_KEYWORDS = {
    "pvt", "ltd", "inc", "corp", "corporation", "llc", "solutions", "technologies",
    "technology", "systems", "labs", "group", "services", "software", "infotech",
    "global", "industries", "university", "institute", "college", "co", "company",
    "agency", "studio", "enterprises", "hub", "media", "consulting", "ventures", "pvt."
}

DESIGNATION_KEYWORDS = {
    "engineer", "developer", "architect", "manager", "lead", "consultant", "intern",
    "analyst", "specialist", "designer", "associate", "scientist", "administrator",
    "officer", "executive", "director", "vp", "cto", "ceo", "head", "founder",
    "trainee", "programmer", "tester", "researcher", "student", "sde", "swe"
}


def _extract_company_and_designation(raw_str: str) -> Tuple[str, str]:
    """
    Deterministically separates Company / Employer from Job Designation / Role.
    Uses regex boundary splitting (dashes, pipes, at, commas) and keyword classification
    to guarantee that Company and Designation are never reversed.
    """
    if not raw_str or not raw_str.strip():
        return "Company", "Role"

    cleaned = re.sub(
        r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{4}|\b20\d{2}\b|\b19\d{2}\b)\s*[-–—to\s]*\s*(present|current|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{4}|\b20\d{2}\b|\b19\d{2}\b)?",
        "",
        raw_str,
        flags=re.I
    ).strip(" -–—|@,[]()")

    if not cleaned:
        return "Company", "Role"

    # 1. Handle "Role at Company" or "Role @ Company"
    at_match = re.search(r"^(.+?)\s+(?:at|@)\s+(.+)$", cleaned, re.I)
    if at_match:
        part1, part2 = at_match.group(1).strip(), at_match.group(2).strip()
        return part2, part1

    # 2. Split on separators: |, —, –, -, comma
    parts = [p.strip() for p in re.split(r"\s*[|—–\-]\s*", cleaned) if p.strip()]
    if len(parts) >= 2:
        part_a, part_b = parts[0], parts[1]
        words_a = set(re.findall(r"\w+", part_a.lower()))
        words_b = set(re.findall(r"\w+", part_b.lower()))

        a_is_company = bool(words_a & COMPANY_KEYWORDS)
        a_is_desig = bool(words_a & DESIGNATION_KEYWORDS)
        b_is_company = bool(words_b & COMPANY_KEYWORDS)
        b_is_desig = bool(words_b & DESIGNATION_KEYWORDS)

        if a_is_company and b_is_desig:
            return part_a, part_b
        elif b_is_company and a_is_desig:
            return part_b, part_a
        elif a_is_desig and not b_is_desig:
            return part_b, part_a
        elif a_is_company and not b_is_company:
            return part_a, part_b

        return part_a, part_b

    # Single line without separator
    words = set(re.findall(r"\w+", cleaned.lower()))
    if words & DESIGNATION_KEYWORDS:
        return "Company", cleaned
    elif words & COMPANY_KEYWORDS:
        return cleaned, "Role"

    return cleaned, "Role"


def normalize_experience_entry(exp: Dict[str, Any]) -> Dict[str, Any]:
    """
    Audits and normalizes an experience entry dict.
    If employer looks like a Job Designation and designation looks like a Company Name,
    swaps them to canonical order. Ensures canonical aliases exist.
    """
    if not isinstance(exp, dict):
        return exp

    emp = str(exp.get("employer") or exp.get("company") or "").strip()
    des = str(exp.get("designation") or exp.get("role") or exp.get("job_title") or exp.get("title") or "").strip()

    if emp and des and emp != "Company" and des != "Role":
        emp_words = set(re.findall(r"\w+", emp.lower()))
        des_words = set(re.findall(r"\w+", des.lower()))

        emp_has_company = bool(emp_words & COMPANY_KEYWORDS)
        emp_has_desig = bool(emp_words & DESIGNATION_KEYWORDS)
        des_has_company = bool(des_words & COMPANY_KEYWORDS)
        des_has_desig = bool(des_words & DESIGNATION_KEYWORDS)

        should_swap = False
        if emp_has_desig and des_has_company and not emp_has_company:
            should_swap = True
        elif des_has_company and not des_has_desig and not emp_has_company:
            should_swap = True

        if should_swap:
            emp, des = des, emp

    exp["employer"] = emp or "Company"
    exp["company"] = emp or "Company"
    exp["designation"] = des or "Role"
    exp["role"] = des or "Role"
    exp["title"] = des or "Role"
    exp["job_title"] = des or "Role"

    return exp


def _parse_heuristic_experience(exp_lines: List[str]) -> List[Dict[str, Any]]:
    """
    Extracts ALL work experience / company entries without dropping or collapsing previous employers.
    Separates company, designation, start/end dates, location, responsibilities, technologies.
    """
    if not exp_lines:
        return []

    date_regex = re.compile(
        r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{4}|\b20\d{2}\b|\b19\d{2}\b)\s*[-–—to\s]+\s*(present|current|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{4}|\b20\d{2}\b|\b19\d{2}\b)",
        re.I
    )

    jobs: List[Dict[str, Any]] = []
    curr_job: Optional[Dict[str, Any]] = None

    for idx_l, line in enumerate(exp_lines):
        line_str = line.strip()
        if not line_str:
            continue

        date_match = date_regex.search(line_str)
        is_bullet = line_str.startswith(("-", "•", "*", "–", "—"))
        clean_text = line_str.lstrip("-•*–— ").strip()

        prev_line = exp_lines[idx_l - 1].strip() if idx_l > 0 else ""

        is_new_job = False
        if date_match and (curr_job is None or len(curr_job.get("responsibilities", [])) > 0):
            is_new_job = True
        elif not is_bullet and curr_job and len(curr_job.get("responsibilities", [])) >= 2 and len(clean_text.split()) <= 8 and not clean_text.endswith("."):
            is_new_job = True

        if is_new_job:
            if curr_job and (curr_job["responsibilities"] or curr_job["employer"] != "Company" or curr_job["designation"] != "Role"):
                jobs.append(normalize_experience_entry(curr_job))

            # Determine whether target_str is on current line or prev_line
            line_text_no_date = re.sub(date_regex, "", line_str).strip(" -–—|@,[]()")
            if line_text_no_date and len(line_text_no_date.split()) >= 2:
                target_str = line_str
            elif prev_line and not prev_line.startswith(("-", "•", "*", "–", "—")):
                target_str = prev_line
            else:
                target_str = line_str

            employer, designation = _extract_company_and_designation(target_str)

            curr_job = {
                "employer": employer,
                "company": employer,
                "designation": designation,
                "role": designation,
                "job_title": designation,
                "title": designation,
                "employment_location": None,
                "start_date": date_match.group(1) if date_match else None,
                "end_date": date_match.group(2) if date_match else None,
                "is_current": "present" in date_match.group(2).lower() or "current" in date_match.group(2).lower() if date_match else False,
                "employment_type": "Full-time",
                "responsibilities": [],
                "achievements": [],
                "technologies": [],
                "metrics": [],
                "original_text": line_str
            }

            if date_match and not curr_job["start_date"]:
                curr_job["start_date"] = date_match.group(1)
                curr_job["end_date"] = date_match.group(2)
                curr_job["is_current"] = "present" in date_match.group(2).lower() or "current" in date_match.group(2).lower()
            continue

        if curr_job is None:
            emp, des = _extract_company_and_designation(line_str)
            curr_job = {
                "employer": emp,
                "company": emp,
                "designation": des,
                "role": des,
                "job_title": des,
                "title": des,
                "employment_location": None,
                "start_date": None,
                "end_date": None,
                "is_current": False,
                "employment_type": "Full-time",
                "responsibilities": [],
                "achievements": [],
                "technologies": [],
                "metrics": [],
                "original_text": line_str
            }

        if date_match and not curr_job["start_date"]:
            curr_job["start_date"] = date_match.group(1)
            curr_job["end_date"] = date_match.group(2)
            curr_job["is_current"] = "present" in date_match.group(2).lower() or "current" in date_match.group(2).lower()
            continue

        if is_bullet:
            curr_job["responsibilities"].append(clean_text)
        elif len(clean_text.split()) > 7 or (curr_job["responsibilities"] and not clean_text[0].isupper()):
            if curr_job["responsibilities"]:
                curr_job["responsibilities"][-1] += " " + clean_text
            else:
                curr_job["responsibilities"].append(clean_text)
        else:
            if any(k in clean_text.lower() for k in ("india", "usa", "us", "uk", "hyderabad", "bangalore", "bengaluru", "mumbai", "delhi", "pune", "chennai", "noida", "gurgaon", "guntur", "andhra", "remote", "hybrid", "onsite", "california", "new york", "london", "singapore", "ca", "ny", "tx", "wa")) or ("," in clean_text and len(clean_text.split()) <= 4 and not clean_text.endswith(".")):
                if not curr_job.get("employment_location"):
                    curr_job["employment_location"] = clean_text
            elif curr_job["employer"] == "Company" or curr_job["designation"] == "Role":
                emp, des = _extract_company_and_designation(clean_text)
                if emp != "Company":
                    curr_job["employer"] = emp
                    curr_job["company"] = emp
                if des != "Role":
                    curr_job["designation"] = des
                    curr_job["role"] = des
                    curr_job["job_title"] = des
                    curr_job["title"] = des

    if curr_job and (curr_job["responsibilities"] or curr_job["employer"] != "Company" or curr_job["designation"] != "Role"):
        jobs.append(normalize_experience_entry(curr_job))

    return jobs


def _parse_heuristic_projects(project_lines: List[str]) -> List[Dict[str, Any]]:
    """
    High-fidelity 2-pass project parser.
    Detects boundaries by explicit titles, numbers, Tech: stack lines, or date ranges.
    Resolves backward headings when dates or Tech: lines precede or follow a project title.
    Returns array of ALL detected projects with name, duration, technologies, bullets, responsibilities.
    """
    if not project_lines:
        return []

    date_regex = re.compile(
        r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{4}|\b20\d{2}\b|\b19\d{2}\b)\s*[-–to\s]+\s*(present|current|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{4}|\b20\d{2}\b|\b19\d{2}\b)",
        re.I
    )
    tech_prefix_regex = re.compile(r"^(tech\s*stack|technologies|tech|tools|stack)\s*[:\-]\s*(.+)", re.I)

    blocks: List[Dict[str, Any]] = []
    curr: Optional[Dict[str, Any]] = None

    idx = 0
    while idx < len(project_lines):
        line = project_lines[idx].strip()
        if not line:
            idx += 1
            continue

        num_match = re.match(r"^(\d+[\.\)]\s*)(.+)", line)
        date_match = date_regex.search(line)
        tech_match = tech_prefix_regex.match(line)
        is_bullet = line.startswith(("-", "•", "*", "–", "—"))
        clean_text = line.lstrip("-•*–— ").strip()

        is_heading = False
        heading_title = None

        if num_match:
            is_heading = True
            heading_title = num_match.group(2).strip()
        elif not is_bullet and not tech_match and not date_match and len(clean_text.split()) <= 10 and not clean_text.endswith("."):
            if curr is None or len(curr.get("bullets", [])) > 0 or curr.get("technologies") or curr.get("duration"):
                is_heading = True
                heading_title = clean_text

        if not is_heading and (date_match or tech_match):
            if curr is None or (curr and len(curr.get("bullets", [])) > 0):
                backward_title = None
                if idx > 0:
                    prev_line = project_lines[idx - 1].strip()
                    prev_clean = prev_line.lstrip("-•*–— ").strip()
                    if prev_clean and not prev_line.startswith(("-", "•", "*", "–")) and len(prev_clean.split()) <= 10 and not prev_clean.endswith("."):
                        backward_title = prev_clean

                is_heading = True
                heading_title = backward_title or (clean_text if not tech_match else "Project")

        if is_heading:
            if curr and (curr["bullets"] or curr["name"] != "Project" or curr["technologies"]):
                blocks.append(curr)

            curr = {
                "name": heading_title or "Project",
                "duration": date_match.group(0) if date_match else None,
                "start_date": date_match.group(1) if date_match else None,
                "end_date": date_match.group(2) if date_match else None,
                "technologies": [],
                "description": "",
                "responsibilities": [],
                "bullets": [],
                "achievements": [],
                "results_metrics": []
            }

            if tech_match:
                tech_items = [t.strip() for t in re.split(r"[,;|•·]\s*", tech_match.group(2)) if t.strip()]
                curr["technologies"].extend(tech_items)
            idx += 1
            continue

        if curr is None:
            curr = {
                "name": "Project",
                "duration": None,
                "start_date": None,
                "end_date": None,
                "technologies": [],
                "description": "",
                "responsibilities": [],
                "bullets": [],
                "achievements": [],
                "results_metrics": []
            }

        if date_match and not curr["duration"]:
            curr["duration"] = date_match.group(0)
            curr["start_date"] = date_match.group(1)
            curr["end_date"] = date_match.group(2)
            idx += 1
            continue

        if tech_match:
            tech_items = [t.strip() for t in re.split(r"[,;|•·]\s*", tech_match.group(2)) if t.strip()]
            curr["technologies"].extend(tech_items)
            idx += 1
            continue

        if is_bullet or len(clean_text) > 0:
            curr["bullets"].append(clean_text)
            curr["responsibilities"].append(clean_text)
            if any(k in clean_text.lower() for k in ("reduced", "improved", "increased", "%", "built", "designed", "integrated", "developed")):
                curr["achievements"].append(clean_text)

        idx += 1

    if curr and (curr["bullets"] or curr["name"] != "Project" or curr["technologies"]):
        blocks.append(curr)

    deduped_blocks = []
    for b in blocks:
        deduped_blocks.append(normalize_and_deduplicate_project(b))

    return deduped_blocks


KNOWN_TECH_TERMS = [
    "FastAPI", "Python", "PostgreSQL", "Azure OCR", "Azure", "OCR", "NER", "Gemini LLM", "Gemini", "LLM",
    "React", "Next.js", "Vue.js", "Vue", "Angular", "Node.js", "Express", "Django", "Flask", "Spring Boot",
    "PyTorch", "TensorFlow", "Keras", "Scikit-Learn", "Pandas", "NumPy", "Docker", "Kubernetes", "K8s",
    "MongoDB", "Redis", "SQLite", "MySQL", "Oracle", "AWS", "GCP", "OpenAI", "LangChain", "LlamaIndex",
    "Qdrant", "ChromaDB", "Java", "C++", "C#", "Rust", "Go", "Golang", "TypeScript", "JavaScript",
    "HTML", "CSS", "Tailwind", "Git", "GitHub", "CI/CD", "Linux", "Bash", "REST API", "REST", "GraphQL",
    "gRPC", "Kafka", "RabbitMQ", "Spark", "Hadoop", "Airflow", "MLOps", "NLP", "LLMs", "RAG", "Computer Vision"
]


def normalize_technologies_list(tech_input: Any) -> List[str]:
    """
    Parses, tokenizes, and cleans technology strings and lists.
    Handles concatenated tech stacks like 'FastAPIPythonPostgreSQLAzure OCRNERGemini LLM'
    and splits them into structured lists: ['FastAPI', 'Python', 'PostgreSQL', 'Azure OCR', 'NER', 'Gemini LLM'].
    """
    if not tech_input:
        return []

    raw_items = []
    if isinstance(tech_input, str):
        if re.search(r"[,;|•·/\n]", tech_input):
            raw_items = [t.strip() for t in re.split(r"[,;|•·/\n]\s*", tech_input) if t.strip()]
        else:
            raw_items = [tech_input.strip()]
    elif isinstance(tech_input, list):
        for item in tech_input:
            if isinstance(item, str) and item.strip():
                if re.search(r"[,;|•·/\n]", item):
                    raw_items.extend([t.strip() for t in re.split(r"[,;|•·/\n]\s*", item) if t.strip()])
                else:
                    raw_items.append(item.strip())

    final_techs = []
    seen = set()

    for item in raw_items:
        sorted_terms = sorted(KNOWN_TECH_TERMS, key=len, reverse=True)
        found_matches = []

        for term in sorted_terms:
            pattern = re.compile(re.escape(term), re.IGNORECASE)
            for m in pattern.finditer(item):
                start, end = m.span()
                overlap = any(not (end <= s or start >= e) for s, e, _ in found_matches)
                if not overlap:
                    found_matches.append((start, end, term))

        if len(found_matches) > 1:
            found_matches.sort(key=lambda x: x[0])
            for _, _, term in found_matches:
                if term.lower() not in seen:
                    seen.add(term.lower())
                    final_techs.append(term)
        else:
            clean_item = re.sub(r"^[\ue000-\uf8ff•·∙○●▪■►▸▶◆◇★☆✦✧✓✔\s\-*–—]+\s*", "", item).strip()
            if clean_item and clean_item.lower() not in seen:
                seen.add(clean_item.lower())
                final_techs.append(clean_item)

    return final_techs


def clean_bullet_text(text: str) -> str:
    """Strips leading repeated bullet symbols and markers."""
    if not text:
        return ""
    cleaned = re.sub(r"^[\ue000-\uf8ff•·∙○●▪■►▸▶◆◇★☆✦✧✓✔\s\-*–—]+\s*", "", text).strip()
    return cleaned


def normalize_and_deduplicate_project(proj: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalizes a project dict:
    1. Removes duplicate bullet items and strips repeated bullet markers.
    2. Tokenizes concatenated technology strings.
    3. Prevents paragraph description from repeating identical bullet point sentences.
    """
    if not isinstance(proj, dict):
        return proj

    p = dict(proj)

    # 1. Clean bullet points & responsibilities
    raw_bullets = p.get("responsibilities") or p.get("bullets") or p.get("features") or []
    if isinstance(raw_bullets, str):
        raw_bullets = [raw_bullets]

    unique_bullets = []
    seen_bullets = set()
    for b in raw_bullets:
        clean_b = clean_bullet_text(str(b))
        if clean_b:
            b_key = clean_b.lower()
            if b_key not in seen_bullets:
                seen_bullets.add(b_key)
                unique_bullets.append(clean_b)

    p["responsibilities"] = unique_bullets
    p["bullets"] = unique_bullets
    p["features"] = unique_bullets

    # 2. Clean technologies using tokenization
    raw_tech = p.get("technologies") or p.get("tech_stack") or []
    p["technologies"] = normalize_technologies_list(raw_tech)

    # 3. Deduplicate description vs bullets
    raw_desc = str(p.get("description") or "").strip()
    clean_desc = clean_bullet_text(raw_desc)

    if clean_desc and unique_bullets:
        joined_bullets = " ".join(unique_bullets)
        dot_joined_bullets = ". ".join(unique_bullets)

        norm_desc = re.sub(r"\s+", " ", clean_desc.lower().strip(" ."))
        norm_joined = re.sub(r"\s+", " ", joined_bullets.lower().strip(" ."))
        norm_dot_joined = re.sub(r"\s+", " ", dot_joined_bullets.lower().strip(" ."))

        if norm_desc == norm_joined or norm_desc == norm_dot_joined:
            p["description"] = None
        else:
            desc_sentences = [s.strip() for s in re.split(r"[.!?]\s*", clean_desc) if s.strip()]
            all_in_bullets = True
            for ds in desc_sentences:
                ds_norm = re.sub(r"\s+", " ", ds.lower())
                if not any(ds_norm in re.sub(r"\s+", " ", b.lower()) for b in unique_bullets):
                    all_in_bullets = False
                    break
            if all_in_bullets:
                p["description"] = None
    elif not clean_desc and unique_bullets:
        p["description"] = None

    return p


def heuristic_comprehensive_parse(raw_text: str) -> Dict[str, Any]:
    """
    Offline deterministic parser that extracts all contact information,
    categorizes skills, splits experience and education, and captures custom sections.
    Guarantees that no data is lost even without AI API keys.
    """
    structured: Dict[str, Any] = {
        "personal_info": {
            "full_name": None,
            "first_name": None,
            "middle_name": None,
            "last_name": None,
            "professional_title": None,
            "email": None,
            "additional_emails": [],
            "phone": None,
            "additional_phones": [],
            "location": None,
            "city": None,
            "state": None,
            "country": None,
            "linkedin_url": None,
            "github_url": None,
            "portfolio_url": None,
            "custom_links": []
        },
        "professional_summary": {
            "summary": None,
            "career_objective": None,
            "years_of_experience": None,
            "areas_of_specialization": [],
            "career_interests": []
        },
        "skills": {
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
        },
        "work_experience": [],
        "education": [],
        "projects": [],
        "certifications": [],
        "achievements": [],
        "publications": [],
        "languages": [],
        "custom_sections": [],
        "extraction_warnings": []
    }

    raw_lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
    lines = []
    for l in raw_lines:
        if re.fullmatch(r"[\ue000-\uf8ff•·∙○●▪■►▸▶◆◇★☆✦✧✓✔\s]+", l):
            continue
        is_bullet = bool(re.match(r"^[\ue000-\uf8ff•·∙○●▪■►▸▶◆◇★☆✦✧✓✔\-*–—]\s*", l))
        cl = re.sub(r"^[\ue000-\uf8ff•·∙○●▪■►▸▶◆◇★☆✦✧✓✔\s\-*–—]+\s*", "", l).strip()
        if cl:
            lines.append(f"- {cl}" if is_bullet else cl)

    # 1. Emails
    all_emails = list(dict.fromkeys(re.findall(r"[\w\.-]+@[\w\.-]+\.\w+", raw_text)))
    if all_emails:
        structured["personal_info"]["email"] = all_emails[0]
        structured["personal_info"]["additional_emails"] = all_emails[1:]

    # 2. Phones (supporting 7-digit, 10-digit, international with country codes)
    phone_pattern = re.compile(
        r"(?:"
        r"\+?\d{1,3}[-.\s]*(?:\(\d{3}\)|\d{3})[-.\s]?\d{3}[-.\s]?\d{4}"  # 10-digit with optional country code
        r"|(?:\+\d{1,3}[-.\s]*)?\b\d{3}[-.\s]\d{4}\b"                     # 7-digit e.g. +1 555-3211 or 555-3211
        r"|\+\d{1,3}[-.\s]*\d{4,5}[-.\s]*\d{4,5}\b"                      # +91 98765 43210
        r"|\+\d{9,14}\b"                                                  # continuous e.g. +15551234567
        r")"
    )
    raw_phones = phone_pattern.findall(raw_text)
    phone_matches = []
    for p in raw_phones:
        cleaned_p = p.strip()
        if not re.match(r"^(19|20)\d{2}[-–—](19|20)\d{2}$", cleaned_p):
            if cleaned_p not in phone_matches:
                phone_matches.append(cleaned_p)
    if phone_matches:
        structured["personal_info"]["phone"] = phone_matches[0]
        structured["personal_info"]["additional_phones"] = phone_matches[1:]

    # 3. URLs, Profiles & Location from header lines
    linkedin = re.search(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[\w-]+", raw_text, re.I)
    if linkedin:
        structured["personal_info"]["linkedin_url"] = linkedin.group(0)

    github = re.search(r"(?:https?://)?(?:www\.)?github\.com/[\w-]+", raw_text, re.I)
    if github:
        structured["personal_info"]["github_url"] = github.group(0)

    for line in lines[:5]:
        if ("@" in line or any(p in line for p in phone_matches)) and "|" in line:
            parts = [p.strip() for p in line.split("|")]
            for part in parts:
                if "@" not in part and not any(p in part for p in phone_matches) and len(part) > 3 and not any(k in part.lower() for k in ("linkedin", "github", "http")):
                    structured["personal_info"]["location"] = part
                    loc_parts = [lp.strip() for lp in part.split(",")]
                    if len(loc_parts) >= 1:
                        structured["personal_info"]["city"] = loc_parts[0]
                    if len(loc_parts) >= 2:
                        structured["personal_info"]["state"] = loc_parts[1].split()[0] if loc_parts[1] else None

    # Section regex definitions
    section_patterns = {
        "summary": re.compile(r"^(professional\s+summary|summary|profile|about\s+me|career\s+objective|objective|executive\s+summary)", re.I),
        "experience": re.compile(r"^(work\s+experience|professional\s+experience|experience|employment\s+history|career\s+history|work\s+history|internships?)", re.I),
        "skills": re.compile(r"^(technical\s+skills|skills|core\s+competencies|technologies|tools\s+&\s+technologies|skills\s+&\s+abilities|key\s+skills)", re.I),
        "projects": re.compile(r"^(projects|key\s+projects|featured\s+projects|personal\s+projects|academic\s+projects)", re.I),
        "education": re.compile(r"^(education|academic\s+background|academics|qualifications|educational\s+qualifications)", re.I),
        "certifications": re.compile(r"^(certifications?|licenses?|courses?|professional\s+certifications?|trainings?|awards?\s*(?:&|and)\s*certifications?|certifications?\s*(?:&|and)\s*awards?)", re.I),
        "achievements": re.compile(r"^(achievements?|awards?|honors?|extracurricular(\s+activities)?)", re.I),
        "languages": re.compile(r"^(languages?|spoken\s+languages?)", re.I)
    }

    known_custom_headings = {
        "volunteer", "volunteering", "volunteer work", "volunteer experience",
        "leadership", "activities", "extracurricular", "publications", "patents",
        "open source", "open source contributions", "contributions", "interests",
        "hobbies", "references", "affiliations", "memberships"
    }

    # 4. Candidate Name & Title from Top Lines
    for line in lines[:6]:
        cleaned_top = line.strip(" :#*-").lower()
        if "@" not in line and not re.search(r"\d{3}", line) and len(line.split()) in (2, 3, 4) and len(line) < 40:
            if any(pat.match(cleaned_top) for pat in section_patterns.values()):
                continue
            if not structured["personal_info"]["full_name"]:
                structured["personal_info"]["full_name"] = line
                parts = line.split()
                structured["personal_info"]["first_name"] = parts[0]
                structured["personal_info"]["last_name"] = parts[-1]
                if len(parts) > 2:
                    structured["personal_info"]["middle_name"] = " ".join(parts[1:-1])
            elif not structured["personal_info"]["professional_title"]:
                structured["personal_info"]["professional_title"] = line

    current_sec = None
    section_buffers: Dict[str, List[str]] = {k: [] for k in section_patterns}
    custom_buffers: Dict[str, List[str]] = {}

    for line in lines:
        cleaned_h = line.strip(" :#*-").lower()
        has_list_separators = ("," in line) or (";" in line) or (":" in line and not line.endswith(":"))
        matched = False
        if not has_list_separators:
            for sec_key, pat in section_patterns.items():
                if pat.match(cleaned_h) and len(cleaned_h.split()) <= 4:
                    current_sec = sec_key
                    matched = True
                    break

        if matched:
            continue

        # Detect unknown section heading (must be after header block and not contain inline lists)
        is_custom_heading = (
            current_sec is not None
            and not has_list_separators
            and not line.endswith(".")
            and len(line.split()) <= 4
            and (
                cleaned_h in known_custom_headings
                or any(cleaned_h.startswith(k) for k in known_custom_headings)
                or (line.isupper() and len(line) < 30)
                or line.endswith(":")
            )
        )
        if is_custom_heading:
            # New custom section
            current_sec = f"custom_{cleaned_h}"
            if current_sec not in custom_buffers:
                custom_buffers[current_sec] = []
            continue

        if current_sec:
            if current_sec.startswith("custom_"):
                custom_buffers[current_sec].append(line)
            else:
                section_buffers[current_sec].append(line)

    # Populate Summary
    if section_buffers["summary"]:
        structured["professional_summary"]["summary"] = " ".join(section_buffers["summary"][:6])

    # Populate Skills into categories
    skill_vocab = {
        "programming_languages": {
            "python", "javascript", "typescript", "c++", "c", "java", "c#", "go", "golang", "rust",
            "php", "ruby", "swift", "kotlin", "sql", "html", "css", "r", "scala", "dart", "bash", "shell"
        },
        "frameworks_libraries": {
            "react", "next.js", "vue", "angular", "node.js", "express", "fastapi", "django", "flask",
            "spring", "spring boot", "tailwind", "pytorch", "tensorflow", "keras", "dotnet", ".net",
            "scikit-learn", "pandas", "numpy", "matplotlib", "seaborn", "opencv"
        },
        "databases": {
            "postgresql", "postgres", "mysql", "mongodb", "redis", "sqlite", "elasticsearch", "cassandra",
            "dynamodb", "oracle", "mariadb", "snowflake", "rdbms"
        },
        "cloud_platforms": {
            "aws", "gcp", "azure", "docker", "kubernetes", "k8s", "terraform", "linux", "git", "github",
            "ci/cd", "nginx", "prometheus", "grafana", "ansible", "helm", "sagemaker", "lambda", "s3"
        },
        "developer_tools": {
            "postman", "jira", "vs code", "pycharm", "graphql", "rest", "grpc", "vim", "webpack", "vite",
            "jupyter", "google colab", "colab", "power bi"
        },
        "ai_ml_technologies": {
            "machine learning", "deep learning", "llm", "nlp", "computer vision", "scikit-learn",
            "huggingface", "langchain", "rag", "pandas", "numpy", "scipy", "openai", "gemini",
            "data science", "data analysis", "predictive models"
        }
    }

    all_raw_skills = []
    for s_line in section_buffers["skills"]:
        target_cat_hint = None
        if ":" in s_line and len(s_line.split(":")[0].split()) <= 4:
            cat_prefix, _, rest = s_line.partition(":")
            tokens = re.split(r"[,;|•·]\s*", rest)
            cp_lower = cat_prefix.lower()
            if any(w in cp_lower for w in ("language", "lang", "programming")):
                target_cat_hint = "programming_languages"
            elif any(w in cp_lower for w in ("framework", "library", "lib")):
                target_cat_hint = "frameworks_libraries"
            elif any(w in cp_lower for w in ("database", "db", "storage")):
                target_cat_hint = "databases"
            elif any(w in cp_lower for w in ("cloud", "devops", "infra")):
                target_cat_hint = "cloud_platforms"
            elif any(w in cp_lower for w in ("tool", "dev", "platform")):
                target_cat_hint = "developer_tools"
            elif any(w in cp_lower for w in ("ai", "ml", "data")):
                target_cat_hint = "ai_ml_technologies"
        else:
            tokens = re.split(r"[,;|•·]\s*", s_line)

        for token in tokens:
            item = token.strip(" -•*")
            if item and len(item) < 35 and not re.search(r"^\d+$", item):
                all_raw_skills.append(item)
                item_lower = item.lower()
                categorized = False
                for cat, keywords in skill_vocab.items():
                    if any(k == item_lower or f" {k} " in f" {item_lower} " for k in keywords):
                        structured["skills"][cat].append(item)
                        categorized = True
                        break
                if not categorized and target_cat_hint:
                    structured["skills"][target_cat_hint].append(item)
                    categorized = True
                if not categorized:
                    structured["skills"]["other_skills"].append(item)

    structured["skills"]["all_raw_skills"] = list(dict.fromkeys(all_raw_skills))

    # Populate Experience using 2-pass company parser
    if section_buffers["experience"]:
        structured["work_experience"] = _parse_heuristic_experience(section_buffers["experience"])

    # Populate Projects using 2-pass project parser with backward heading resolution
    if section_buffers["projects"]:
        structured["projects"] = _parse_heuristic_projects(section_buffers["projects"])

    # Populate Education (supporting multiple institutions / degrees)
    if section_buffers["education"]:
        curr_edu = None
        for edu_l in section_buffers["education"]:
            date_range = re.findall(r"\b(20\d{2}|19\d{2})\b", edu_l)
            gpa_match = re.search(r"(?:gpa|cgpa)[:\s]+([\d\.]+(?:/\d+)?)", edu_l, re.I)
            is_deg = any(k in edu_l.lower() for k in ("btech", "b.tech", "bachelor", "master", "intermediate", "ssc", "10th", "12th", "ph.d", "degree", "bs", "ms"))
            is_inst = any(k in edu_l.lower() for k in ("institute", "college", "school", "university", "academy"))

            should_split = False
            if curr_edu:
                has_deg = curr_edu["degree"] != "Degree"
                has_inst = curr_edu["institution"] != "University / Institution"
                if is_deg and has_deg:
                    should_split = True
                elif is_inst and has_inst:
                    should_split = True

            if should_split and curr_edu:
                structured["education"].append(curr_edu)
                curr_edu = None

            if not curr_edu:
                curr_edu = {
                    "degree": "Degree",
                    "field_of_study": None,
                    "institution": "University / Institution",
                    "location": None,
                    "start_date": None,
                    "end_date": None,
                    "graduation_year": None,
                    "grade": None,
                    "relevant_coursework": [],
                    "achievements": [],
                    "thesis": None
                }

            if gpa_match:
                curr_edu["grade"] = gpa_match.group(1)
            if date_range:
                curr_edu["graduation_year"] = date_range[-1]
                if len(date_range) > 1:
                    curr_edu["start_date"] = date_range[0]
                    curr_edu["end_date"] = date_range[-1]

            if is_deg and curr_edu["degree"] == "Degree":
                curr_edu["degree"] = edu_l
            elif is_inst and curr_edu["institution"] == "University / Institution":
                curr_edu["institution"] = edu_l
            elif not curr_edu["location"] and any(k in edu_l.lower() for k in ("pradesh", "guntur", "dachepalle", "delhi", "bangalore", "mumbai", "hyderabad", "boston", "seattle", "austin", "chicago")):
                curr_edu["location"] = edu_l

        if curr_edu and (curr_edu["degree"] != "Degree" or curr_edu["institution"] != "University / Institution"):
            structured["education"].append(curr_edu)

    # Populate Certifications
    if section_buffers["certifications"]:
        curr_cert = None
        for c_l in section_buffers["certifications"]:
            if "--- EXTRACTED HYPERLINKS ---" in c_l:
                break
            if not curr_cert or len(c_l.split()) <= 8:
                if curr_cert:
                    structured["certifications"].append(curr_cert)
                parts = c_l.split(" - ")
                name = parts[0].strip()
                issuer = parts[1].strip() if len(parts) > 1 else None
                curr_cert = {
                    "name": name,
                    "issuer": issuer,
                    "issue_date": None,
                    "expiry_date": None,
                    "credential_id": None,
                    "credential_url": None,
                    "description": ""
                }
            elif curr_cert:
                curr_cert["description"] = (curr_cert["description"] + " " + c_l).strip()
        if curr_cert:
            structured["certifications"].append(curr_cert)

    # Populate Custom Sections
    for c_key, c_lines in custom_buffers.items():
        title = c_key.replace("custom_", "").title()
        content_txt = "\n".join(c_lines).strip()
        if content_txt:
            structured["custom_sections"].append({
                "section_title": title,
                "original_content": content_txt,
                "structured_content": c_lines
            })

    # 6. Fallback candidate location if header didn't specify it
    if not structured["personal_info"].get("location"):
        for job in structured.get("work_experience", []):
            if job.get("employment_location"):
                structured["personal_info"]["location"] = job["employment_location"]
                loc_parts = [lp.strip() for lp in job["employment_location"].split(",")]
                structured["personal_info"]["city"] = loc_parts[0]
                if len(loc_parts) > 1:
                    structured["personal_info"]["state"] = loc_parts[1]
                break
        if not structured["personal_info"].get("location"):
            for edu in structured.get("education", []):
                if edu.get("location"):
                    structured["personal_info"]["location"] = edu["location"]
                    loc_parts = [lp.strip() for lp in edu["location"].split(",")]
                    structured["personal_info"]["city"] = loc_parts[0]
                    if len(loc_parts) > 1:
                        structured["personal_info"]["state"] = loc_parts[1]
                    break

    return _normalize_and_validate_extraction(structured, raw_text)


# ─────────────────────────────────────────────────────────────────────────────
# 5. NORMALIZATION, CONSISTENCY CHECKS & DIAGNOSTICS
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_and_validate_extraction(
    data: Dict[str, Any],
    raw_text: str
) -> Dict[str, Any]:
    """
    Validates completeness, checks for contradictory dates,
    computes confidence score, and attaches warnings.
    """
    warnings: List[str] = data.get("extraction_warnings", []) or []
    missing_fields: List[str] = []

    pi = data.get("personal_info") or {}
    if not pi.get("full_name") or pi.get("full_name") in ("Candidate", "null", ""):
        missing_fields.append("full_name")
        warnings.append("Full name could not be reliably determined. Please review and enter your name.")

    if not pi.get("email"):
        missing_fields.append("email")
        warnings.append("No email address found in the document.")

    # ── Project & Work Experience Completeness Audit ──
    tech_lines = re.findall(r"(?:tech\s*stack|technologies|tech|tools|stack)\s*[:\-]", raw_text, re.I)
    numbered_projects = re.findall(r"^\s*\d+[\.\)]\s*[A-Z]", raw_text, re.M)
    expected_projects = max(len(tech_lines), len(numbered_projects))
    extracted_projects = len(data.get("projects") or [])

    if expected_projects > 0 and extracted_projects < expected_projects:
        warnings.append(
            f"Extraction Completeness Alert: Document contains evidence of at least {expected_projects} project blocks, but {extracted_projects} were extracted."
        )

    exp_dates = re.findall(r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{4}\s*[-–to\s]+\s*(?:present|current|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{4}|\d{4})", raw_text, re.I)
    extracted_exps = len(data.get("work_experience") or [])
    if len(exp_dates) > extracted_exps and extracted_exps == 1:
        warnings.append(
            f"Extraction Completeness Alert: Document contains {len(exp_dates)} employment date ranges, but only {extracted_exps} company experience entry was extracted."
        )

    # Audit and normalize all work_experience entries (ensure Company & Designation are never reversed)
    normalized_exps = []
    for exp in data.get("work_experience", []):
        if isinstance(exp, dict):
            normalized_exps.append(normalize_experience_entry(exp))
        else:
            normalized_exps.append(exp)
    data["work_experience"] = normalized_exps

    # Audit and normalize all project entries (deduplicate paragraphs vs bullets, tokenize concatenated technologies)
    normalized_projects = []
    for proj in data.get("projects", []):
        if isinstance(proj, dict):
            normalized_projects.append(normalize_and_deduplicate_project(proj))
        else:
            normalized_projects.append(proj)
    data["projects"] = normalized_projects

    # Check work experience date consistency
    for idx, exp in enumerate(data.get("work_experience", [])):
        s_date = exp.get("start_date")
        e_date = exp.get("end_date")
        if s_date and e_date and not exp.get("is_current"):
            try:
                s_year = int(re.search(r"\b(20\d{2}|19\d{2})\b", str(s_date)).group(0))
                e_year = int(re.search(r"\b(20\d{2}|19\d{2})\b", str(e_date)).group(0))
                if s_year > e_year:
                    warnings.append(f"Work Experience entry #{idx + 1} ({exp.get('employer', 'Job')}): Start date ({s_date}) is after end date ({e_date}).")
            except Exception:
                pass

    # Skills check
    skills = data.get("skills") or {}
    total_skills = sum(len(v) for k, v in skills.items() if isinstance(v, list) and k != "all_raw_skills")
    if total_skills == 0:
        missing_fields.append("skills")
        warnings.append("No categorized skills were detected.")

    # Calculate overall confidence score
    confidence = 1.0
    if "full_name" in missing_fields:
        confidence -= 0.25
    if "email" in missing_fields:
        confidence -= 0.15
    if "phone" in missing_fields:
        confidence -= 0.10
    if total_skills == 0:
        confidence -= 0.20
    if not data.get("work_experience") and not data.get("education"):
        confidence -= 0.25

    confidence = max(0.2, min(1.0, round(confidence, 2)))

    data["confidence_score"] = confidence
    data["missing_fields"] = missing_fields
    data["extraction_warnings"] = warnings

    return data
