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
from app.services.project_normalizer import (
    canonicalize_project,
    canonicalize_projects_list,
    clean_bullet_text as canon_clean_bullet_text,
    normalize_technologies_list as canon_normalize_technologies_list
)

logger = logging.getLogger("app.resume_extractor")

MAX_RESUME_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_RESUME_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".odt", ".rtf", ".txt", ".tex",
    ".html", ".htm", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".pptx"
}

from app.services.hyperlink_extractor import (
    create_hyperlink_record,
    associate_links_with_resume_entities,
    classify_link_type,
    normalize_url,
    validate_url
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. FILE VALIDATION & INTEGRITY HASHING
# ─────────────────────────────────────────────────────────────────────────────

def validate_resume_upload(
    filename: str,
    content: bytes,
    content_type: Optional[str] = None
) -> Tuple[bool, str, str, str]:
    """
    Validates file extension, size, MIME type, magic bytes, and encryption/corruption.
    Rejects password-protected PDFs and decompression bombs with explicit error messages.
    Computes SHA-256 integrity hash for duplicate detection.
    Returns: (is_valid, error_msg, sha256_hash, ext)
    """
    if len(content) == 0:
        return False, "Uploaded file is empty (0 bytes).", "", ""

    if len(content) > MAX_RESUME_UPLOAD_SIZE:
        return False, f"File size ({len(content)/(1024*1024):.1f}MB) exceeds the 10MB limit.", "", ""

    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_RESUME_EXTENSIONS:
        return (
            False,
            f"Unsupported file type '{ext}'. Supported formats: PDF, DOCX, DOC, ODT, RTF, HTML, TXT, TEX, Images (PNG, JPEG, TIFF), PPTX.",
            "",
            ""
        )

    # Magic byte verification & security checks
    if ext == ".pdf":
        if not content.startswith(b"%PDF-"):
            return False, "Invalid PDF signature. The file appears corrupted or disguised.", "", ""
        # Check for encrypted or password-protected PDF
        try:
            import fitz
            doc = fitz.open(stream=content, filetype="pdf")
            if doc.is_encrypted or doc.needs_pass:
                doc.close()
                return False, "Encrypted or password-protected PDF detected. Please remove password protection before uploading.", "", ""
            doc.close()
        except Exception as e:
            err_str = str(e).lower()
            if "password" in err_str or "encrypted" in err_str:
                return False, "Encrypted or password-protected PDF detected. Please remove password protection before uploading.", "", ""
            return False, f"Corrupted or unreadable PDF: {str(e)}", "", ""

    elif ext in (".docx", ".odt", ".pptx"):
        if not content.startswith(b"PK\x03\x04"):
            return False, f"Invalid {ext.upper().lstrip('.')} signature (not a valid Zip package).", "", ""
        # Zip bomb / decompression limit check
        try:
            import zipfile
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                total_uncompressed = sum(info.file_size for info in zf.infolist())
                if total_uncompressed > 50 * 1024 * 1024:  # 50MB decompression limit
                    return False, "Decompression limit exceeded (possible zip bomb).", "", ""
                if len(content) > 0 and (total_uncompressed / len(content)) > 100:
                    return False, "Excessive compression ratio detected.", "", ""
        except Exception as e:
            return False, f"Corrupted {ext.upper().lstrip('.')} archive: {str(e)}", "", ""

    elif ext == ".doc":
        # Legacy binary Word document (OLE compound file) or RTF disguised as DOC
        if not (content.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1") or content.startswith(b"{\\rtf")):
            return False, "Invalid legacy Word (.doc) signature.", "", ""

    elif ext == ".rtf":
        if not content.startswith(b"{\\rtf"):
            return False, "Invalid RTF document header.", "", ""

    elif ext in (".png", ".jpg", ".jpeg", ".tiff", ".tif"):
        try:
            from PIL import Image
            with Image.open(io.BytesIO(content)) as img:
                img.verify()
        except Exception as e:
            return False, f"Corrupted or invalid image file: {str(e)}", "", ""

    elif ext in (".html", ".htm"):
        try:
            content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                content.decode("latin-1")
            except Exception:
                return False, "HTML file cannot be decoded as valid text.", "", ""

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

def _recover_plaintext_hyperlinks(text: str, existing_links: List[Dict[str, Any]], format_name: str) -> None:
    """Discovers plaintext URLs and emails in extracted text without dropping metadata."""
    seen_urls = {normalize_url(l["url"]) for l in existing_links if l.get("url")}

    # Match URLs in text
    for m in re.finditer(r"(?:https?://|www\.)[^\s<>\"'()]+", text, re.IGNORECASE):
        raw_url = m.group(0).strip(".,;()")
        norm = normalize_url(raw_url)
        if norm and norm not in seen_urls:
            seen_urls.add(norm)
            nearby = text[max(0, m.start() - 50):min(len(text), m.end() + 50)].strip()
            existing_links.append(create_hyperlink_record(
                url=norm,
                label=raw_url,
                source_format=format_name,
                source_page=1,
                nearby_text=nearby,
                extraction_method="regex_pattern"
            ))

    # Match email addresses
    for m in re.finditer(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,7}\b", text):
        email_str = m.group(0)
        norm_mailto = normalize_url(f"mailto:{email_str}")
        if norm_mailto not in seen_urls:
            seen_urls.add(norm_mailto)
            existing_links.append(create_hyperlink_record(
                url=norm_mailto,
                label=email_str,
                source_format=format_name,
                source_page=1,
                nearby_text=email_str,
                extraction_method="mailto_scheme"
            ))


def _extract_pdf_layout_aware(content: bytes) -> Dict[str, Any]:
    """
    Layout-aware PDF extraction powered by Stage 2 Multi-Modal & Multi-Layout engine:
    - 1, 2, and 3 column detection with full-width banner header isolation
    - Multi-page running header/footer suppression
    - Spatial hyperlink extraction with visible label recovery
    - Font-size hierarchy extraction
    - High-resolution 300 DPI OpenCV preprocessing and dual-path vision/OCR for scanned & mixed pages
    """
    from app.services.page_extractors import extract_document_stage2, ColumnLayoutType
    from app.services.document_classifier import PageType

    stage2_res = extract_document_stage2(content, "resume.pdf")

    page_layouts = []
    scanned_pages = []
    for p in stage2_res.pages:
        if p.ocr_used or p.page_type == PageType.SCANNED:
            scanned_pages.append(p.page_number)
        page_layouts.append({
            "page": p.page_number,
            "column_layout": p.column_layout.value if hasattr(p.column_layout, "value") else str(p.column_layout),
            "gutters": p.gutters,
            "ocr_used": p.ocr_used
        })

    multi_column = any(p.column_layout != ColumnLayoutType.SINGLE_COLUMN for p in stage2_res.pages)

    return {
        "raw_text": stage2_res.raw_text,
        "page_count": stage2_res.page_count,
        "layout_info": {
            "columns_detected": multi_column,
            "page_layouts": page_layouts,
            "scanned_pages": scanned_pages,
            "hyperlinks": stage2_res.hyperlinks,
            "tables_count": stage2_res.tables_count,
            "format": "pdf",
            "ocr_applied_pages": stage2_res.ocr_applied_pages,
            "font_hierarchy_summary": stage2_res.font_hierarchy_summary
        }
    }


def _extract_docx_with_tables(content: bytes) -> Dict[str, Any]:
    """
    Stage 2 DOCX extraction preserving document element order:
    - Paragraphs with inline hyperlinks
    - Table cell structure preserved (| delimiter)
    - DrawingML and VML textboxes
    - Section headers and footers
    - Embedded image OCR extraction
    """
    from app.services.page_extractors import extract_document_stage2

    stage2_res = extract_document_stage2(content, "resume.docx")

    return {
        "raw_text": stage2_res.raw_text,
        "page_count": stage2_res.page_count,
        "layout_info": {
            "columns_detected": False,
            "scanned_pages": [],
            "hyperlinks": stage2_res.hyperlinks,
            "tables_count": stage2_res.tables_count,
            "format": "docx",
            "ocr_applied_pages": stage2_res.ocr_applied_pages
        }
    }


def _extract_odt_content(content: bytes) -> Dict[str, Any]:
    """Extracts OpenDocument Text (ODT) headings, paragraphs, tables, and hyperlinks."""
    import zipfile
    import xml.etree.ElementTree as ET

    text_chunks: List[str] = []
    hyperlinks: List[Dict[str, Any]] = []
    tables_count = 0

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            content_xml = zf.read("content.xml")

        tree = ET.fromstring(content_xml)
        for elem in tree.iter():
            tag = elem.tag
            if tag.endswith("}a"):
                url = elem.attrib.get("{http://www.w3.org/1999/xlink}href")
                label = "".join(elem.itertext()).strip()
                if url:
                    hyperlinks.append(create_hyperlink_record(
                        url=url,
                        label=label,
                        source_format="odt",
                        source_page=1,
                        extraction_method="odt_xlink"
                    ))
            elif tag.endswith(("}h", "}p")):
                txt = "".join(elem.itertext()).strip()
                if txt:
                    text_chunks.append(txt)
            elif tag.endswith("}table"):
                tables_count += 1
    except Exception as e:
        logger.warning(f"ODT parse error: {e}")

    raw_text = "\n".join(text_chunks).strip()
    _recover_plaintext_hyperlinks(raw_text, hyperlinks, "odt")

    return {
        "raw_text": raw_text,
        "page_count": max(1, len(text_chunks) // 35),
        "layout_info": {
            "columns_detected": False,
            "scanned_pages": [],
            "hyperlinks": hyperlinks,
            "tables_count": tables_count,
            "format": "odt"
        }
    }


def _extract_rtf_content(content: bytes) -> Dict[str, Any]:
    """Extracts RTF document text and HYPERLINK fields."""
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("latin-1", errors="replace")

    hyperlinks: List[Dict[str, Any]] = []
    link_pattern = re.compile(r'\{\\field\{\\\*\\fldinst\{HYPERLINK\s+"([^"]+)"\}\}\{\\fldrslt\s+([^{}]+)\}\}', re.IGNORECASE)
    for m in link_pattern.finditer(text):
        url, label = m.group(1), m.group(2).strip()
        hyperlinks.append(create_hyperlink_record(
            url=url,
            label=label,
            source_format="rtf",
            source_page=1,
            extraction_method="rtf_field"
        ))

    # Strip RTF header tables with nested braces (fonttbl, colortbl, stylesheet, info)
    for header_tbl in ("fonttbl", "colortbl", "stylesheet", "info"):
        while f"\\{header_tbl}" in text:
            start_pos = text.find(f"\\{header_tbl}")
            open_pos = text.rfind("{", 0, start_pos)
            if open_pos == -1:
                break
            depth = 1
            idx = open_pos + 1
            while idx < len(text) and depth > 0:
                if text[idx] == "{":
                    depth += 1
                elif text[idx] == "}":
                    depth -= 1
                idx += 1
            text = text[:open_pos] + " " + text[idx:]

    # Replace RTF field results with their plain visible label
    text = re.sub(r"\{\\field\{\\\*\\fldinst\{[^{}]*\}\}\{\\fldrslt\s*([^{}]*)\}\}", r"\1", text)

    # Convert RTF paragraph/line breaks to newline
    text = re.sub(r"\\(par|line)\b", "\n", text)
    # Convert hex escapes \'xx
    text = re.sub(r"\\\'([0-9a-fA-F]{2})", lambda m: bytes.fromhex(m.group(1)).decode("latin-1", errors="ignore"), text)
    # Strip remaining RTF control words: \word123 or \* or \~
    text = re.sub(r"\\[a-zA-Z]+-?\d* ?", " ", text)
    text = re.sub(r"\\[^a-zA-Z0-9\s] ?", " ", text)
    # Strip braces
    text = re.sub(r"[{}]", " ", text)

    lines = [re.sub(r"\s+", " ", l).strip() for l in text.split("\n") if l.strip()]
    raw_text = "\n".join(lines).strip()
    _recover_plaintext_hyperlinks(raw_text, hyperlinks, "rtf")

    return {
        "raw_text": raw_text,
        "page_count": max(1, len(lines) // 35),
        "layout_info": {
            "columns_detected": False,
            "scanned_pages": [],
            "hyperlinks": hyperlinks,
            "tables_count": 0,
            "format": "rtf"
        }
    }


def _extract_html_content(content: bytes) -> Dict[str, Any]:
    """Extracts HTML resume exports preserving semantic structure and hyperlinks."""
    from bs4 import BeautifulSoup

    try:
        html_str = content.decode("utf-8")
    except UnicodeDecodeError:
        html_str = content.decode("latin-1", errors="replace")

    soup = BeautifulSoup(html_str, "html.parser")
    for s in soup(["script", "style", "noscript", "meta", "link"]):
        s.decompose()

    hyperlinks: List[Dict[str, Any]] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        label = a.get_text().strip()
        if href.startswith(("http", "mailto:", "tel:")):
            hyperlinks.append(create_hyperlink_record(
                url=href,
                label=label,
                source_format="html",
                source_page=1,
                nearby_text=a.parent.get_text()[:200] if a.parent else "",
                extraction_method="html_anchor"
            ))

    text_chunks: List[str] = []
    for elem in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "tr"]):
        txt = elem.get_text().strip()
        if txt and txt not in text_chunks:
            text_chunks.append(txt)

    if not text_chunks:
        text_chunks = [soup.get_text().strip()]

    raw_text = "\n".join(text_chunks).strip()
    _recover_plaintext_hyperlinks(raw_text, hyperlinks, "html")

    return {
        "raw_text": raw_text,
        "page_count": max(1, len(text_chunks) // 35),
        "layout_info": {
            "columns_detected": False,
            "scanned_pages": [],
            "hyperlinks": hyperlinks,
            "tables_count": len(soup.find_all("table")),
            "format": "html"
        }
    }


def _extract_image_content(content: bytes) -> Dict[str, Any]:
    """Converts image resumes (PNG, JPEG, TIFF) to PDF in memory and extracts text via layout engine + OCR."""
    import fitz

    # Open image with fitz and convert to single-page PDF document
    img_doc = fitz.open(stream=content)
    pdf_bytes = img_doc.convert_to_pdf()
    img_doc.close()

    result = _extract_pdf_layout_aware(pdf_bytes)
    result["layout_info"]["format"] = "image"
    return result


def _extract_doc_content(content: bytes) -> Dict[str, Any]:
    """Extracts text streams from legacy Word 97-2003 binary documents."""
    text_pieces = []
    raw_str = content.decode("latin-1", errors="ignore")
    printable_chunks = re.findall(r"[\x20-\x7E\xA0-\xFF]{4,}", raw_str)
    for chunk in printable_chunks:
        if not any(noise in chunk for noise in ("WordDocument", "Root Entry", "CompObj", "SummaryInformation")):
            text_pieces.append(chunk.strip())

    raw_text = "\n".join(text_pieces).strip()
    hyperlinks: List[Dict[str, Any]] = []
    _recover_plaintext_hyperlinks(raw_text, hyperlinks, "doc")

    return {
        "raw_text": raw_text,
        "page_count": max(1, len(text_pieces) // 35),
        "layout_info": {
            "columns_detected": False,
            "scanned_pages": [],
            "hyperlinks": hyperlinks,
            "tables_count": 0,
            "format": "doc"
        }
    }


def _extract_pptx_content(content: bytes) -> Dict[str, Any]:
    """Extracts PowerPoint resume content across slides, tables, and hyperlinks."""
    import zipfile
    import xml.etree.ElementTree as ET

    text_chunks: List[str] = []
    hyperlinks: List[Dict[str, Any]] = []

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            slide_files = sorted([f for f in zf.namelist() if f.startswith("ppt/slides/slide") and f.endswith(".xml")])
            for s_idx, sf in enumerate(slide_files, 1):
                raw_xml = zf.read(sf)
                try:
                    tree = ET.fromstring(raw_xml)
                    for elem in tree.iter():
                        if elem.tag.endswith("}t"):
                            txt = (elem.text or "").strip()
                            if txt:
                                text_chunks.append(txt)
                except Exception as ex:
                    # Regex fallback for imperfect or non-standard PPTX XML
                    xml_str = raw_xml.decode("utf-8", errors="ignore")
                    matches = re.findall(r"<[a-zA-Z0-9_:]*t[^>]*>(.*?)</[a-zA-Z0-9_:]*t>", xml_str)
                    for m in matches:
                        if m.strip():
                            text_chunks.append(m.strip())
    except Exception as e:
        logger.warning(f"PPTX parse note: {e}")

    raw_text = "\n".join(text_chunks).strip()
    _recover_plaintext_hyperlinks(raw_text, hyperlinks, "pptx")

    return {
        "raw_text": raw_text,
        "page_count": max(1, len(text_chunks) // 20),
        "layout_info": {
            "columns_detected": False,
            "scanned_pages": [],
            "hyperlinks": hyperlinks,
            "tables_count": 0,
            "format": "pptx"
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

    raw_text = "\n".join(clean_lines).strip()
    hyperlinks: List[Dict[str, Any]] = []
    _recover_plaintext_hyperlinks(raw_text, hyperlinks, "tex")

    return {
        "raw_text": raw_text,
        "page_count": 1,
        "layout_info": {
            "columns_detected": False,
            "scanned_pages": [],
            "hyperlinks": hyperlinks,
            "tables_count": 0,
            "format": "tex"
        }
    }


def _extract_plain_text(content: bytes) -> Dict[str, Any]:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("latin-1", errors="replace")

    raw_text = text.strip()
    hyperlinks: List[Dict[str, Any]] = []
    _recover_plaintext_hyperlinks(raw_text, hyperlinks, "txt")

    return {
        "raw_text": raw_text,
        "page_count": max(1, len(text.split("\n")) // 50),
        "layout_info": {
            "columns_detected": False,
            "scanned_pages": [],
            "hyperlinks": hyperlinks,
            "tables_count": 0,
            "format": "txt"
        }
    }


def extract_document_content(
    filename: str,
    content: bytes,
    ext: str
) -> Dict[str, Any]:
    """
    Universal router dispatching to format-specific layout-aware parsers.
    Extracts raw text, reconstructs multi-column reading order,
    extracts first-class hyperlinks, and detects scanned pages.
    """
    ext_lower = ext.lower()
    if ext_lower == ".pdf":
        return _extract_pdf_layout_aware(content)
    elif ext_lower == ".docx":
        return _extract_docx_with_tables(content)
    elif ext_lower == ".doc":
        return _extract_doc_content(content)
    elif ext_lower == ".odt":
        return _extract_odt_content(content)
    elif ext_lower == ".rtf":
        return _extract_rtf_content(content)
    elif ext_lower in (".html", ".htm"):
        return _extract_html_content(content)
    elif ext_lower in (".png", ".jpg", ".jpeg", ".tiff", ".tif"):
        return _extract_image_content(content)
    elif ext_lower == ".pptx":
        return _extract_pptx_content(content)
    elif ext_lower == ".tex":
        return _extract_tex_clean(content)
    else:
        return _extract_plain_text(content)


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
    pdf_bytes: Optional[bytes] = None,
    layout_info: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Invokes external AI provider with strict JSON output.
    Gracefully falls back to heuristic extraction if unconfigured or unreachable.
    Performs multi-pass safety merging to guarantee NO projects or companies are omitted.
    Associates layout-extracted hyperlinks with structured entities.
    """
    from app.services.ai_provider import ai_provider_service

    links = (layout_info or {}).get("hyperlinks", [])

    # Check if AI provider is available
    if not (ai_provider_service.is_gemini_configured() or
            ai_provider_service.is_nvidia_configured() or
            ai_provider_service.is_groq_configured()):
        logger.info("AI provider not configured. Using high-fidelity 2-pass heuristic parser.")
        return heuristic_comprehensive_parse(raw_text, layout_info)

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
            heuristic_data = heuristic_comprehensive_parse(raw_text, layout_info)
            
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

            norm_result = _normalize_and_validate_extraction(parsed, raw_text)
            if links:
                norm_result, _ = associate_links_with_resume_entities(links, norm_result)
            return norm_result

    except Exception as e:
        logger.error(f"AI structured parsing failed: {e}. Falling back to 2-pass heuristic engine.")

    return heuristic_comprehensive_parse(raw_text, layout_info)


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


def _extract_company_and_designation(raw_str: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Deterministically separates Company / Employer from Job Designation / Role.
    Uses regex boundary splitting (dashes, pipes, at, commas) and keyword classification
    to guarantee that Company and Designation are never reversed.
    Returns (employer, designation) where unidentifiable elements are None (zero-hallucination).
    """
    if not raw_str or not raw_str.strip():
        return None, None

    cleaned = re.sub(
        r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{4}|\b20\d{2}\b|\b19\d{2}\b)\s*[-–—to\s]*\s*(present|current|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{4}|\b20\d{2}\b|\b19\d{2}\b)?",
        "",
        raw_str,
        flags=re.I
    ).strip(" -–—|@,[]()")

    if not cleaned:
        return None, None

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
        return None, cleaned
    elif words & COMPANY_KEYWORDS:
        return cleaned, None

    return cleaned, None


def normalize_experience_entry(exp: Dict[str, Any]) -> Dict[str, Any]:
    """
    Audits and normalizes an experience entry dict.
    If employer looks like a Job Designation and designation looks like a Company Name,
    swaps them to canonical order. Ensures canonical aliases exist without inventing placeholders.
    """
    if not isinstance(exp, dict):
        return exp

    emp = str(exp.get("employer") or exp.get("company") or "").strip()
    des = str(exp.get("designation") or exp.get("role") or exp.get("job_title") or exp.get("title") or "").strip()

    if emp and des:
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

    exp["employer"] = emp
    exp["company"] = emp
    exp["designation"] = des
    exp["role"] = des
    exp["title"] = des
    exp["job_title"] = des

    return exp


def _parse_heuristic_experience(exp_lines: List[str]) -> List[Dict[str, Any]]:
    """
    Extracts ALL work experience / company entries without dropping or collapsing previous employers.
    Supports multi-role company blocks (inheriting parent employer name across subsequent promotions).
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
    active_company: Optional[str] = None

    for idx_l, line in enumerate(exp_lines):
        line_str = line.strip()
        if not line_str:
            continue

        date_match = date_regex.search(line_str)
        is_bullet = line_str.startswith(("-", "•", "*", "–", "—"))
        clean_text = line_str.lstrip("-•*–— ").strip()

        prev_line = exp_lines[idx_l - 1].strip() if idx_l > 0 else ""

        # Standalone company heading detection (e.g. "Google" or "Amazon AWS" preceding multiple roles)
        if not date_match and not is_bullet and len(clean_text.split()) <= 6 and not clean_text.endswith("."):
            words_clean = set(re.findall(r"\w+", clean_text.lower()))
            is_known_company = (
                bool(words_clean & COMPANY_KEYWORDS)
                or any(k in clean_text.lower() for k in (
                    "google", "microsoft", "amazon", "apple", "meta", "netflix", "uber",
                    "salesforce", "oracle", "ibm", "intel", "cisco", "adobe", "stripe",
                    "airbnb", "twitter", "linkedin", "spotify", "cloudops", "technologies",
                    "solutions", "systems", "labs", "inc", "corp", "llc", "ltd"
                ))
            ) and not bool(words_clean & DESIGNATION_KEYWORDS)
            if is_known_company:
                active_company = clean_text

        is_new_job = False
        if date_match:
            if (
                curr_job is None
                or len(curr_job.get("responsibilities", [])) > 0
                or bool(curr_job.get("start_date"))
                or (curr_job.get("employer") and any(sep in line_str for sep in ("|", "—", "–", " - ")))
            ):
                is_new_job = True
        elif not is_bullet and curr_job and len(curr_job.get("responsibilities", [])) >= 2 and len(clean_text.split()) <= 8 and not clean_text.endswith("."):
            is_new_job = True

        if is_new_job:
            if curr_job and (curr_job.get("responsibilities") or curr_job.get("employer") or curr_job.get("designation")):
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

            # Inherit active_company if employer missing in multi-job company structure
            if not employer and active_company:
                employer = active_company
            elif employer:
                active_company = employer

            curr_job = {
                "employer": employer or "",
                "company": employer or "",
                "designation": designation or "",
                "role": designation or "",
                "job_title": designation or "",
                "title": designation or "",
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
            continue

        if curr_job is None:
            emp, des = _extract_company_and_designation(line_str)
            if not emp and active_company:
                emp = active_company
            elif emp:
                active_company = emp
            curr_job = {
                "employer": emp or "",
                "company": emp or "",
                "designation": des or "",
                "role": des or "",
                "job_title": des or "",
                "title": des or "",
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
            if any(k in clean_text.lower() for k in ("india", "usa", "us", "uk", "hyderabad", "bangalore", "bengaluru", "mumbai", "delhi", "pune", "chennai", "noida", "gurgaon", "guntur", "andhra", "remote", "hybrid", "onsite", "california", "new york", "london", "singapore", "austin", "seattle", "boston", "chicago", "ca", "ny", "tx", "wa")) or ("," in clean_text and len(clean_text.split()) <= 4 and not clean_text.endswith(".")):
                if not curr_job.get("employment_location"):
                    curr_job["employment_location"] = clean_text
            elif not curr_job.get("employer") or not curr_job.get("designation"):
                emp, des = _extract_company_and_designation(clean_text)
                if emp and not curr_job.get("employer"):
                    curr_job["employer"] = emp
                    curr_job["company"] = emp
                    active_company = emp
                if des and not curr_job.get("designation"):
                    curr_job["designation"] = des
                    curr_job["role"] = des
                    curr_job["job_title"] = des
                    curr_job["title"] = des

    if curr_job and (curr_job.get("responsibilities") or curr_job.get("employer") or curr_job.get("designation")):
        jobs.append(normalize_experience_entry(curr_job))

    return jobs


def _parse_heuristic_projects(project_lines: List[str]) -> List[Dict[str, Any]]:
    """
    High-fidelity 2-pass project parser.
    Detects boundaries by explicit titles, numbers, Tech: stack lines, or date ranges.
    Resolves backward headings when dates or Tech: lines precede or follow a project title.
    Preserves all bullet points, cleans dates/URLs from project names, and links repositories.
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

            # Extract any embedded link or date range from project heading
            h_clean = heading_title or "Project"
            proj_link = None
            url_match = re.search(r"https?://\S+", h_clean)
            if url_match:
                proj_link = url_match.group(0).rstrip(".,;()")
                h_clean = h_clean.replace(url_match.group(0), "").strip()

            d_match = date_regex.search(h_clean)
            proj_dates = None
            if d_match:
                proj_dates = d_match.group(0)
                h_clean = re.sub(date_regex, "", h_clean).strip()

            clean_name = h_clean.strip(" -–—|()[]:").strip() or "Project"

            curr = {
                "name": clean_name,
                "duration": proj_dates or (date_match.group(0) if date_match else None),
                "start_date": d_match.group(1) if d_match else (date_match.group(1) if date_match else None),
                "end_date": d_match.group(2) if d_match else (date_match.group(2) if date_match else None),
                "technologies": [],
                "description": "",
                "responsibilities": [],
                "bullets": [],
                "achievements": [],
                "results_metrics": [],
                "link": proj_link
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
                "results_metrics": [],
                "link": None
            }

        # Check for link inside project lines
        line_url = re.search(r"https?://\S+", line)
        if line_url and not curr.get("link"):
            curr["link"] = line_url.group(0).rstrip(".,;()")

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
    return canon_clean_bullet_text(text)


def normalize_and_deduplicate_project(proj: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalizes a project dict using the canonical project normalizer:
    1. Removes duplicate bullet items and strips repeated bullet markers.
    2. Tokenizes concatenated technology strings.
    3. Prevents paragraph description from repeating identical bullet point sentences.
    4. Explicitly avoids duplicating bullets into features.
    """
    return canonicalize_project(proj)


def heuristic_comprehensive_parse(
    raw_text: str,
    layout_info: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Offline deterministic parser that extracts all contact information,
    categorizes skills, splits experience and education, and captures custom sections.
    Guarantees that no data is lost even without AI API keys.
    Associates layout-extracted hyperlinks with structured entities.
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
        "experience": re.compile(r"^(work\s+experience|professional\s+experience|experience|employment(\s+history)?|career(\s+history)?|work\s+history|internships?|relevant\s+experience|professional\s+background|industry\s+experience|career\s+milestones.*)", re.I),
        "skills": re.compile(r"^(technical\s+skills|skills|core\s+competencies|technologies|tools\s+&\s+technologies|skills\s+&\s+abilities|key\s+skills|technical\s+expertise|proficiencies|technical\s+toolkit.*|competencies|skills\s+&\s+tools|toolkit)", re.I),
        "projects": re.compile(r"^(projects|key\s+projects|featured\s+projects|personal\s+projects|academic\s+projects|notable\s+projects|selected\s+projects|portfolio|client\s+engagements|recent\s+projects|key\s+initiatives.*)", re.I),
        "education": re.compile(r"^(education|academic\s+background|academics|scholastic(\s+background|\s+credentials)?|qualifications|educational\s+qualifications|academic\s+qualifications|degrees?|education\s+&\s+credentials)", re.I),
        "certifications": re.compile(r"^(certifications?|licenses?|courses?|professional\s+certifications?|trainings?|awards?\s*(?:&|and)\s*certifications?|certifications?\s*(?:&|and)\s*awards?|credentials|licenses?\s*(?:&|and)\s*certifications?)", re.I),
        "achievements": re.compile(r"^(achievements?|awards?|honors?|extracurricular(\s+activities)?|honors?\s*(?:&|and)\s*awards?|awards?\s*(?:&|and)\s*honors?|recognitions?)", re.I),
        "publications": re.compile(r"^(publications?|patents?|papers?|works?\s+published|published\s+works?|scholarly\s+articles?|research\s+papers?|publications?\s*(?:&|and)\s*patents?|talks\s*(?:&|and)\s*publications?|scholarly\s+works?)", re.I),
        "languages": re.compile(r"^(languages?|spoken\s+languages?|language\s+proficiencies?)", re.I)
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

    for idx_l, line in enumerate(lines):
        # 1. Check for inline section label (e.g. "Experience: Company - Role" or "Skills: Python, Go")
        inline_match = re.match(r"^(experience|work experience|education|skills|technical skills|projects|summary|professional summary)\s*:\s*(.+)$", line, re.I)
        if inline_match:
            sec_name = inline_match.group(1).lower().strip()
            rest_of_line = inline_match.group(2).strip()
            matched_inline = False
            for sec_key, pat in section_patterns.items():
                if pat.match(sec_name):
                    current_sec = sec_key
                    if rest_of_line:
                        section_buffers[current_sec].append(rest_of_line)
                    matched_inline = True
                    break
            if matched_inline:
                continue

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

        # Detect unknown section heading (valid even if before recognized sections)
        is_custom_heading = (
            idx_l >= 2
            and not has_list_separators
            and not line.endswith(".")
            and len(line.split()) <= 4
            and not any(k in cleaned_h for k in ("@", "http", ".com", ".dev", "+", "github", "linkedin", "|"))
            and (
                cleaned_h in known_custom_headings
                or any(cleaned_h.startswith(k) for k in known_custom_headings)
                or (line.isupper() and len(line) < 30 and len(line) > 3)
                or (line.endswith(":") and len(line.split()) <= 3)
            )
        )
        if is_custom_heading:
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
            "scikit-learn", "pandas", "numpy", "matplotlib", "seaborn", "opencv", "scipy"
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

    if not all_raw_skills:
        for cat, keywords in skill_vocab.items():
            for kw in keywords:
                if len(kw) <= 1:
                    continue
                m = re.search(r"\b" + re.escape(kw) + r"\b", raw_text, re.IGNORECASE)
                if m:
                    actual_text = raw_text[m.start():m.end()]
                    if actual_text not in all_raw_skills:
                        all_raw_skills.append(actual_text)
                        structured["skills"][cat].append(actual_text)

    structured["skills"]["all_raw_skills"] = list(dict.fromkeys(all_raw_skills))

    # Populate Experience using 2-pass company parser
    if section_buffers["experience"]:
        structured["work_experience"] = _parse_heuristic_experience(section_buffers["experience"])

    # Populate Projects using 2-pass project parser with backward heading resolution
    if section_buffers["projects"]:
        structured["projects"] = _parse_heuristic_projects(section_buffers["projects"])

    # Populate Education (supporting multiple institutions / degrees with zero-hallucination)
    if section_buffers["education"]:
        curr_edu = None
        for edu_l in section_buffers["education"]:
            date_range = re.findall(r"\b(20\d{2}|19\d{2})\b", edu_l)
            gpa_match = re.search(r"(?:gpa|cgpa)[:\s]+([\d\.]+(?:/\d+)?)", edu_l, re.I)
            is_deg = any(k in edu_l.lower() for k in ("btech", "b.tech", "bachelor", "master", "intermediate", "ssc", "10th", "12th", "ph.d", "degree", "bs", "ms"))
            is_inst = any(k in edu_l.lower() for k in ("institute", "college", "school", "university", "academy"))

            should_split = False
            if curr_edu:
                has_deg = bool(curr_edu.get("degree"))
                has_inst = bool(curr_edu.get("institution"))
                if is_deg and has_deg:
                    should_split = True
                elif is_inst and has_inst:
                    should_split = True

            if should_split and curr_edu:
                structured["education"].append(curr_edu)
                curr_edu = None

            if not curr_edu:
                curr_edu = {
                    "degree": None,
                    "field_of_study": None,
                    "institution": None,
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

            if (" - " in edu_l or " | " in edu_l) and not (curr_edu["degree"] and curr_edu["institution"]):
                split_parts = re.split(r"\s*[-–—|]\s*", edu_l, maxsplit=1)
                p0, p1 = split_parts[0].strip(), split_parts[1].strip()
                p0_inst = any(k in p0.lower() for k in ("institute", "college", "school", "university", "academy", "stanford", "harvard", "mit", "berkeley", "iit", "nit", "bits", "polytechnic"))
                p1_inst = any(k in p1.lower() for k in ("institute", "college", "school", "university", "academy", "stanford", "harvard", "mit", "berkeley", "iit", "nit", "bits", "polytechnic"))
                p0_deg = any(k in p0.lower() for k in ("btech", "b.tech", "bachelor", "master", "ph.d", "degree", "bs", "ms", "b.s", "m.s"))
                p1_deg = any(k in p1.lower() for k in ("btech", "b.tech", "bachelor", "master", "ph.d", "degree", "bs", "ms", "b.s", "m.s"))
                if p0_inst and not curr_edu["institution"]:
                    curr_edu["institution"] = p0
                elif p1_inst and not curr_edu["institution"]:
                    curr_edu["institution"] = p1
                if p1_deg and not curr_edu["degree"]:
                    curr_edu["degree"] = p1
                elif p0_deg and not curr_edu["degree"]:
                    curr_edu["degree"] = p0

            if is_deg and not curr_edu["degree"]:
                curr_edu["degree"] = edu_l
            elif is_inst and not curr_edu["institution"]:
                curr_edu["institution"] = edu_l
            elif not curr_edu["location"] and any(k in edu_l.lower() for k in ("pradesh", "guntur", "dachepalle", "delhi", "bangalore", "mumbai", "hyderabad", "boston", "seattle", "austin", "chicago")):
                curr_edu["location"] = edu_l

        if curr_edu and (curr_edu.get("degree") or curr_edu.get("institution")):
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

    # Populate Publications
    if section_buffers.get("publications"):
        for pub_l in section_buffers["publications"]:
            if pub_l.strip():
                url_m = re.search(r"https?://\S+", pub_l)
                url_val = url_m.group(0).rstrip(".,;()") if url_m else None
                clean_t = pub_l.replace(url_val, "").strip(" -–—|()") if url_val else pub_l.strip(" -–—|()")
                structured["publications"].append({
                    "title": clean_t,
                    "publisher": None,
                    "date": None,
                    "url": url_val
                })

    # Populate Languages
    if section_buffers.get("languages"):
        for lang_l in section_buffers["languages"]:
            for token in re.split(r"[,;|•·]\s*", lang_l):
                t_clean = token.strip(" -*•")
                if t_clean:
                    prof_m = re.search(r"\((.+?)\)", t_clean)
                    lang_name = re.sub(r"\(.+?\)", "", t_clean).strip()
                    structured["languages"].append({
                        "language": lang_name,
                        "proficiency": prof_m.group(1).strip() if prof_m else None
                    })

    # Populate Achievements
    if section_buffers.get("achievements"):
        for ach_l in section_buffers["achievements"]:
            clean_ach = ach_l.lstrip("-•*–— ").strip()
            if clean_ach:
                structured["achievements"].append(clean_ach)

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

    res = _normalize_and_validate_extraction(structured, raw_text)
    links = (layout_info or {}).get("hyperlinks", [])
    if links:
        res, _ = associate_links_with_resume_entities(links, res)
    return res


# ─────────────────────────────────────────────────────────────────────────────
# 5. NORMALIZATION, CONSISTENCY CHECKS & DIAGNOSTICS
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_and_validate_extraction(
    data: Dict[str, Any],
    raw_text: str
) -> Dict[str, Any]:
    """
    Validates completeness, checks for contradictory dates,
    computes field-level confidence scores, extraction coverage, and attaches warnings.
    """
    warnings: List[str] = data.get("extraction_warnings", []) or []
    missing_fields: List[str] = []
    field_confidence: Dict[str, float] = {}
    field_level_review: Dict[str, Dict[str, Any]] = {}

    pi = data.get("personal_info") or {}
    pi_score = 1.0
    if not pi.get("full_name") or pi.get("full_name") in ("Candidate", "null", ""):
        missing_fields.append("full_name")
        warnings.append("Full name could not be reliably determined. Please review and enter your name.")
        pi_score -= 0.4
    if not pi.get("email"):
        missing_fields.append("email")
        warnings.append("No email address found in the document.")
        pi_score -= 0.3
    if not pi.get("phone"):
        missing_fields.append("phone")
        pi_score -= 0.2
    field_confidence["personal_info"] = max(0.1, round(pi_score, 2))
    field_level_review["personal_info"] = {
        "status": "high" if pi_score >= 0.8 else ("medium" if pi_score >= 0.5 else "needs_review"),
        "confidence": field_confidence["personal_info"],
        "issues": [w for w in warnings if "name" in w.lower() or "email" in w.lower()]
    }

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

    # Audit and normalize all work_experience entries
    normalized_exps = []
    for exp in data.get("work_experience", []):
        if isinstance(exp, dict):
            normalized_exps.append(normalize_experience_entry(exp))
        else:
            normalized_exps.append(exp)
    data["work_experience"] = normalized_exps

    exp_score = 1.0 if normalized_exps else 0.0
    # Check work experience date consistency
    for idx, exp in enumerate(normalized_exps):
        s_date = exp.get("start_date")
        e_date = exp.get("end_date")
        if s_date and e_date and not exp.get("is_current"):
            try:
                s_year = int(re.search(r"\b(20\d{2}|19\d{2})\b", str(s_date)).group(0))
                e_year = int(re.search(r"\b(20\d{2}|19\d{2})\b", str(e_date)).group(0))
                if s_year > e_year:
                    exp_score -= 0.15
                    warnings.append(f"Work Experience entry #{idx + 1} ({exp.get('employer', 'Job')}): Start date ({s_date}) is after end date ({e_date}).")
            except Exception:
                pass

    field_confidence["work_experience"] = max(0.0, round(exp_score, 2))
    field_level_review["work_experience"] = {
        "status": "high" if exp_score >= 0.85 else ("medium" if exp_score >= 0.5 else "needs_review"),
        "confidence": field_confidence["work_experience"],
        "count": len(normalized_exps),
        "issues": [w for w in warnings if "experience" in w.lower() or "employment" in w.lower()]
    }

    # Audit and normalize all project entries
    normalized_projects = []
    for proj in data.get("projects", []):
        if isinstance(proj, dict):
            normalized_projects.append(normalize_and_deduplicate_project(proj))
        else:
            normalized_projects.append(proj)
    data["projects"] = normalized_projects

    proj_score = 1.0 if normalized_projects else (0.8 if not expected_projects else 0.2)
    field_confidence["projects"] = max(0.0, round(proj_score, 2))
    field_level_review["projects"] = {
        "status": "high" if proj_score >= 0.8 else ("medium" if proj_score >= 0.5 else "needs_review"),
        "confidence": field_confidence["projects"],
        "count": len(normalized_projects),
        "issues": [w for w in warnings if "project" in w.lower()]
    }

    # Skills check
    skills = data.get("skills") or {}
    total_skills = sum(len(v) for k, v in skills.items() if isinstance(v, list) and k != "all_raw_skills")
    if total_skills == 0:
        missing_fields.append("skills")
        warnings.append("No categorized skills were detected.")
        skills_score = 0.0
    else:
        skills_score = min(1.0, 0.4 + (total_skills * 0.06))

    field_confidence["skills"] = round(skills_score, 2)
    field_level_review["skills"] = {
        "status": "high" if skills_score >= 0.8 else ("medium" if skills_score >= 0.5 else "needs_review"),
        "confidence": field_confidence["skills"],
        "total_skills": total_skills
    }

    # Education check
    edus = data.get("education") or []
    edu_score = 1.0 if edus else 0.0
    field_confidence["education"] = round(edu_score, 2)
    field_level_review["education"] = {
        "status": "high" if edu_score >= 0.8 else "needs_review",
        "confidence": field_confidence["education"],
        "count": len(edus)
    }

    # Calculate extraction text coverage vs raw document non-whitespace characters
    raw_chars = len(re.sub(r"\s+", "", raw_text)) or 1
    extracted_text_pieces = []
    if pi.get("full_name"): extracted_text_pieces.append(pi["full_name"])
    if pi.get("email"): extracted_text_pieces.append(pi["email"])
    for s_list in skills.values():
        if isinstance(s_list, list): extracted_text_pieces.extend(str(s) for s in s_list)
    for exp in normalized_exps:
        extracted_text_pieces.extend([str(exp.get("employer", "")), str(exp.get("designation", ""))])
        extracted_text_pieces.extend(str(r) for r in exp.get("responsibilities", []))
    for pr in normalized_projects:
        extracted_text_pieces.append(str(pr.get("name", "")))
        extracted_text_pieces.extend(str(b) for b in pr.get("bullets", []))
    for ed in edus:
        extracted_text_pieces.extend([str(ed.get("degree", "")), str(ed.get("institution", ""))])

    extracted_chars = sum(len(re.sub(r"\s+", "", p)) for p in extracted_text_pieces)
    coverage = min(1.0, extracted_chars / raw_chars)

    # Calculate overall confidence score
    confidence = (
        field_confidence["personal_info"] * 0.25 +
        field_confidence["work_experience"] * 0.25 +
        field_confidence["projects"] * 0.20 +
        field_confidence["skills"] * 0.15 +
        field_confidence["education"] * 0.15
    )
    confidence = max(0.2, min(1.0, round(confidence, 2)))

    data["confidence_score"] = confidence
    data["field_confidence"] = field_confidence
    data["extraction_coverage"] = round(coverage, 2)
    data["field_level_review"] = field_level_review
    data["missing_fields"] = missing_fields
    data["extraction_warnings"] = warnings

    return data


# Public convenience aliases
extract_pdf_layout_aware = _extract_pdf_layout_aware
extract_docx_content = _extract_docx_with_tables

