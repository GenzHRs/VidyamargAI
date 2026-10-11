"""
Document Intake, Validation, and Routing Module for VidyamargAI.

Stage 1 implementation:
1. Validation:
   - Size limit (10MB)
   - Magic bytes verification (%PDF-, PK\x03\x04 for docx)
   - Extension whitelist
   - Zip-bomb defense (ratio check & uncompressed limit)
   - Encrypted PDF rejection with explicit human-readable error
   - Deterministic SHA-256 fingerprinting
2. Routing:
   - Route by file format: PDF -> page-level classifier; DOCX -> DOCX pipeline
3. Page-Level Classifier (per page, not per file):
   - Computes text char count and word count
   - Computes fraction of page area covered by images
   - Computes ratio of garbage / unmappable characters (broken font encodings `(cid:..)`, `\ufffd`, private use area glyphs)
   - Assigns deterministic labels: TEXT, SCANNED, or MIXED
   - Pages with garbage/broken font layers are classified as SCANNED
"""

import io
import re
import zipfile
import hashlib
import logging
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple, Union
from pydantic import BaseModel, Field
import fitz  # PyMuPDF

logger = logging.getLogger("app.document_classifier")

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_UNCOMPRESSED_ZIP_SIZE = 100 * 1024 * 1024  # 100 MB
MAX_COMPRESSION_RATIO = 100.0

ALLOWED_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".txt", ".rtf", ".odt",
    ".html", ".htm", ".pptx", ".png", ".jpg", ".jpeg",
    ".tiff", ".tif", ".tex"
}


class PageType(str, Enum):
    TEXT = "TEXT"
    SCANNED = "SCANNED"
    MIXED = "MIXED"


class DocumentRoute(str, Enum):
    PDF_PIPELINE = "PDF_PIPELINE"
    DOCX_PIPELINE = "DOCX_PIPELINE"
    IMAGE_PIPELINE = "IMAGE_PIPELINE"
    RICH_TEXT_PIPELINE = "RICH_TEXT_PIPELINE"


class PageClassificationResult(BaseModel):
    page_number: int = Field(description="1-indexed page number")
    page_type: PageType = Field(description="TEXT, SCANNED, or MIXED")
    char_count: int = Field(description="Total extractable text characters")
    word_count: int = Field(description="Total extractable words")
    image_area_ratio: float = Field(description="Fraction of page area covered by images (0.0 to 1.0)")
    garbage_ratio: float = Field(description="Fraction of text consisting of unmappable/garbage glyphs (0.0 to 1.0)")
    garbage_details: Dict[str, int] = Field(default_factory=dict, description="Counts of specific garbage patterns")
    image_count: int = Field(default=0, description="Number of distinct image objects on page")
    classification_reason: str = Field(description="Deterministic reasoning for label assignment")


class DocumentClassificationResult(BaseModel):
    file_type: str = Field(description="File extension without dot, e.g. pdf, docx")
    route: DocumentRoute = Field(description="Pipeline route assigned to document")
    page_count: int = Field(description="Total pages in document")
    pages: List[PageClassificationResult] = Field(default_factory=list, description="Per-page classifications")
    overall_type: str = Field(description="Summary document type: text, scanned, or mixed")
    has_scanned_pages: bool = Field(default=False)
    has_mixed_pages: bool = Field(default=False)
    needs_ocr: bool = Field(default=False)
    needs_vision: bool = Field(default=False)


class IntakeValidationResult(BaseModel):
    is_valid: bool
    error_message: Optional[str] = None
    file_hash: str = ""
    normalized_ext: str = ""
    file_size_bytes: int = 0
    route: Optional[DocumentRoute] = None


# ─────────────────────────────────────────────────────────────────────────────
# 1. INTAKE VALIDATION
# ─────────────────────────────────────────────────────────────────────────────

def validate_document_intake(
    filename: str,
    content: bytes,
    content_type: Optional[str] = None
) -> IntakeValidationResult:
    """
    Strict intake validation:
    - Zero-byte rejection
    - 10MB size limit
    - Whitelisted extensions
    - Magic bytes signature matching
    - Zip-bomb defense (ratio & size checks on docx/odt/pptx)
    - Encrypted PDF rejection with human-readable error message
    - Deterministic SHA-256 fingerprinting
    """
    file_size = len(content) if content else 0

    if not content or file_size == 0:
        return IntakeValidationResult(
            is_valid=False,
            error_message="Uploaded file is empty (0 bytes). Please upload a valid resume document.",
            file_size_bytes=0
        )

    if file_size > MAX_FILE_SIZE:
        mb = file_size / (1024 * 1024)
        return IntakeValidationResult(
            is_valid=False,
            error_message=f"File size ({mb:.1f} MB) exceeds maximum allowed limit of 10 MB.",
            file_size_bytes=file_size
        )

    file_hash = hashlib.sha256(content).hexdigest()

    # Determine extension
    ext = ""
    if filename and "." in filename:
        ext = "." + filename.rsplit(".", 1)[-1].lower()

    if not ext or ext not in ALLOWED_EXTENSIONS:
        return IntakeValidationResult(
            is_valid=False,
            error_message=f"Unsupported file format '{ext or 'unknown'}'. Supported formats: PDF, DOCX, DOC, TXT, RTF, ODT, HTML, PPTX, PNG, JPG.",
            file_hash=file_hash,
            normalized_ext=ext,
            file_size_bytes=file_size
        )

    # Magic Bytes & Structural Validation
    if ext == ".pdf":
        if not content.startswith(b"%PDF-"):
            return IntakeValidationResult(
                is_valid=False,
                error_message="File header signature mismatch: Corrupted or invalid PDF document.",
                file_hash=file_hash,
                normalized_ext=ext,
                file_size_bytes=file_size
            )

        # Check encryption / password protection
        try:
            doc = fitz.open(stream=content, filetype="pdf")
            if doc.is_encrypted or doc.needs_pass:
                doc.close()
                return IntakeValidationResult(
                    is_valid=False,
                    error_message="Password-protected or encrypted PDFs are not supported. Please remove the password and re-upload.",
                    file_hash=file_hash,
                    normalized_ext=ext,
                    file_size_bytes=file_size
                )
            if len(doc) == 0:
                doc.close()
                return IntakeValidationResult(
                    is_valid=False,
                    error_message="PDF contains 0 pages.",
                    file_hash=file_hash,
                    normalized_ext=ext,
                    file_size_bytes=file_size
                )
            doc.close()
        except Exception as e:
            return IntakeValidationResult(
                is_valid=False,
                error_message=f"Corrupted PDF file could not be parsed: {str(e)}",
                file_hash=file_hash,
                normalized_ext=ext,
                file_size_bytes=file_size
            )

        route = DocumentRoute.PDF_PIPELINE

    elif ext in {".docx", ".pptx", ".odt"}:
        if not content.startswith(b"PK\x03\x04"):
            return IntakeValidationResult(
                is_valid=False,
                error_message=f"File header mismatch: Corrupted or invalid {ext.upper()} archive.",
                file_hash=file_hash,
                normalized_ext=ext,
                file_size_bytes=file_size
            )

        # Zip bomb defense
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                uncompressed_total = sum(zinfo.file_size for zinfo in zf.infolist())
                compressed_total = max(1, sum(zinfo.compress_size for zinfo in zf.infolist()))

                if uncompressed_total > MAX_UNCOMPRESSED_ZIP_SIZE:
                    return IntakeValidationResult(
                        is_valid=False,
                        error_message="File rejected: Uncompressed archive size exceeds maximum safe limit (100 MB).",
                        file_hash=file_hash,
                        normalized_ext=ext,
                        file_size_bytes=file_size
                    )

                ratio = uncompressed_total / compressed_total
                if ratio > MAX_COMPRESSION_RATIO:
                    return IntakeValidationResult(
                        is_valid=False,
                        error_message=f"File rejected: Suspicious compression ratio ({ratio:.1f}x) indicative of a zip-bomb.",
                        file_hash=file_hash,
                        normalized_ext=ext,
                        file_size_bytes=file_size
                    )

                if ext == ".docx":
                    namelist = zf.namelist()
                    if "[Content_Types].xml" not in namelist or not any(n.startswith("word/") for n in namelist):
                        return IntakeValidationResult(
                            is_valid=False,
                            error_message="Invalid DOCX structure: Missing standard OpenXML wordprocessing schema.",
                            file_hash=file_hash,
                            normalized_ext=ext,
                            file_size_bytes=file_size
                        )
        except Exception as ze:
            return IntakeValidationResult(
                is_valid=False,
                error_message=f"Corrupted {ext.upper()} document archive: {str(ze)}",
                file_hash=file_hash,
                normalized_ext=ext,
                file_size_bytes=file_size
            )

        route = DocumentRoute.DOCX_PIPELINE if ext == ".docx" else DocumentRoute.RICH_TEXT_PIPELINE

    elif ext in {".png", ".jpg", ".jpeg", ".tiff", ".tif"}:
        route = DocumentRoute.IMAGE_PIPELINE
    else:
        route = DocumentRoute.RICH_TEXT_PIPELINE

    return IntakeValidationResult(
        is_valid=True,
        error_message=None,
        file_hash=file_hash,
        normalized_ext=ext,
        file_size_bytes=file_size,
        route=route
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. PDF PAGE CLASSIFIER (PER-PAGE)
# ─────────────────────────────────────────────────────────────────────────────

def _calculate_image_coverage(page: fitz.Page) -> Tuple[float, int]:
    """
    Calculates the fraction of page area covered by images (0.0 to 1.0)
    and the total count of distinct image objects.
    Uses union bounding boxes to avoid double-counting overlapping image rects.
    """
    page_rect = page.rect
    page_area = max(1.0, page_rect.width * page_rect.height)
    image_list = page.get_images(full=True)
    if not image_list:
        return 0.0, 0

    image_rects: List[fitz.Rect] = []
    for img_info in image_list:
        xref = img_info[0]
        rects = page.get_image_rects(xref)
        for r in rects:
            # Intersect with page boundary
            clipped = r & page_rect
            if not clipped.is_empty and clipped.width > 5 and clipped.height > 5:
                image_rects.append(clipped)

    if not image_rects:
        # Fallback: if image rects cannot be determined by xref, inspect drawing list
        return (0.0, len(image_list))

    # Approximate union area by sorting and merging or grid coverage
    # For speed and precision: compute covered area across merged boxes
    total_covered_area = 0.0
    # Merge overlapping rectangles
    merged: List[fitz.Rect] = []
    for r in sorted(image_rects, key=lambda x: (x.y0, x.x0)):
        combined = False
        for i, m in enumerate(merged):
            if (r & m).is_valid and not (r & m).is_empty:
                merged[i] = m | r
                combined = True
                break
        if not combined:
            merged.append(r)

    total_covered_area = sum(m.width * m.height for m in merged)
    coverage_ratio = min(1.0, total_covered_area / page_area)
    return round(coverage_ratio, 3), len(image_list)


def _calculate_garbage_ratio(text: str) -> Tuple[float, Dict[str, int]]:
    """
    Analyzes extractable text to detect broken font encodings, CID replacements,
    and unmappable unicode glyphs.
    Returns (garbage_ratio, details_dict).
    """
    if not text or not text.strip():
        return 0.0, {}

    raw_len = len(text)
    details: Dict[str, int] = {}

    # 1. Broken CID font encoding tags e.g. "(cid:12)", "(cid:142)"
    cid_matches = re.findall(r"\(cid:\d+\)", text)
    cid_chars_count = sum(len(m) for m in cid_matches)
    if cid_matches:
        details["cid_font_tags"] = len(cid_matches)
        details["cid_tag_chars"] = cid_chars_count

    # 2. Unicode replacement character
    replacement_chars = text.count("\ufffd")
    if replacement_chars:
        details["unicode_replacement_chars"] = replacement_chars

    # 3. Private Use Area (PUA) glyphs: E000 - F8FF
    pua_chars = len(re.findall(r"[\ue000-\uf8ff]", text))
    if pua_chars:
        details["private_use_area_chars"] = pua_chars

    # 4. Non-printable control characters (excluding newline \n, tab \t, carriage return \r)
    control_chars = len(re.findall(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", text))
    if control_chars:
        details["unprintable_control_chars"] = control_chars

    total_garbage = cid_chars_count + replacement_chars + pua_chars + control_chars
    garbage_ratio = min(1.0, total_garbage / max(1, raw_len))
    return round(garbage_ratio, 3), details


def classify_pdf_page(page: fitz.Page, page_index: int = 0) -> PageClassificationResult:
    """
    Inspects a single PDF page and assigns a deterministic classification:
    - TEXT: High extractable text, low image coverage, low garbage ratio.
    - SCANNED: Little/no text, or high image coverage, or broken/garbage font layer.
    - MIXED: Substantial extractable text AND substantial image regions.
    """
    page_num = page_index + 1
    text = page.get_text("text") or ""
    clean_text = text.strip()
    char_count = len(clean_text)
    word_count = len(clean_text.split())

    image_area_ratio, image_count = _calculate_image_coverage(page)
    garbage_ratio, garbage_details = _calculate_garbage_ratio(text)

    # ── Classification Decision Matrix ──

    # Rule 1: Broken / unmappable font encoding (e.g. text is full of CID tags or replacement glyphs)
    if garbage_ratio >= 0.20:
        return PageClassificationResult(
            page_number=page_num,
            page_type=PageType.SCANNED,
            char_count=char_count,
            word_count=word_count,
            image_area_ratio=image_area_ratio,
            garbage_ratio=garbage_ratio,
            garbage_details=garbage_details,
            image_count=image_count,
            classification_reason=f"Broken font encoding: {garbage_ratio*100:.1f}% unmappable garbage characters (requires OCR/vision re-extraction)"
        )

    # Rule 2: Pure scan or raster image without text layer
    if char_count < 40 and image_area_ratio >= 0.30:
        return PageClassificationResult(
            page_number=page_num,
            page_type=PageType.SCANNED,
            char_count=char_count,
            word_count=word_count,
            image_area_ratio=image_area_ratio,
            garbage_ratio=garbage_ratio,
            garbage_details=garbage_details,
            image_count=image_count,
            classification_reason=f"Image-dominated page ({image_area_ratio*100:.1f}% area covered) with negligible text ({char_count} chars)"
        )

    # Rule 3: Negligible text count (e.g. blank page or tiny watermarks)
    if char_count < 25:
        return PageClassificationResult(
            page_number=page_num,
            page_type=PageType.SCANNED,
            char_count=char_count,
            word_count=word_count,
            image_area_ratio=image_area_ratio,
            garbage_ratio=garbage_ratio,
            garbage_details=garbage_details,
            image_count=image_count,
            classification_reason=f"Insufficient text layer ({char_count} chars, {word_count} words)"
        )

    # Rule 4: Mixed layout (hybrid text layer + large images/scanned sections)
    if char_count >= 50 and image_area_ratio >= 0.20:
        return PageClassificationResult(
            page_number=page_num,
            page_type=PageType.MIXED,
            char_count=char_count,
            word_count=word_count,
            image_area_ratio=image_area_ratio,
            garbage_ratio=garbage_ratio,
            garbage_details=garbage_details,
            image_count=image_count,
            classification_reason=f"Hybrid page: {char_count} text characters coexisting with {image_area_ratio*100:.1f}% image coverage"
        )

    # Rule 5: Standard digital text layout
    return PageClassificationResult(
        page_number=page_num,
        page_type=PageType.TEXT,
        char_count=char_count,
        word_count=word_count,
        image_area_ratio=image_area_ratio,
        garbage_ratio=garbage_ratio,
        garbage_details=garbage_details,
        image_count=image_count,
        classification_reason=f"Clean digital text layer ({char_count} chars, {word_count} words, {image_area_ratio*100:.1f}% images)"
    )


def classify_pdf_document(doc_or_bytes: Union[fitz.Document, bytes]) -> DocumentClassificationResult:
    """
    Classifies all pages in a PDF document and produces document-level summary.
    """
    doc_opened_internally = False
    if isinstance(doc_or_bytes, bytes):
        doc = fitz.open(stream=doc_or_bytes, filetype="pdf")
        doc_opened_internally = True
    else:
        doc = doc_or_bytes

    page_results: List[PageClassificationResult] = []
    try:
        for idx in range(len(doc)):
            p = doc[idx]
            page_results.append(classify_pdf_page(p, idx))
    finally:
        if doc_opened_internally:
            doc.close()

    total_pages = len(page_results)
    scanned_count = sum(1 for p in page_results if p.page_type == PageType.SCANNED)
    mixed_count = sum(1 for p in page_results if p.page_type == PageType.MIXED)
    text_count = sum(1 for p in page_results if p.page_type == PageType.TEXT)

    if scanned_count == total_pages:
        overall = "scanned"
    elif scanned_count > 0 or mixed_count > 0:
        overall = "mixed"
    else:
        overall = "text"

    return DocumentClassificationResult(
        file_type="pdf",
        route=DocumentRoute.PDF_PIPELINE,
        page_count=total_pages,
        pages=page_results,
        overall_type=overall,
        has_scanned_pages=(scanned_count > 0),
        has_mixed_pages=(mixed_count > 0),
        needs_ocr=(scanned_count > 0 or mixed_count > 0),
        needs_vision=(scanned_count > 0 or mixed_count > 0)
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3. ROUTE DISPATCHER
# ─────────────────────────────────────────────────────────────────────────────

def route_document(filename: str, content: bytes) -> DocumentClassificationResult:
    """
    Dispatches document to its appropriate pipeline classifier based on format:
    - PDF: Executes per-page PDF classifier
    - DOCX: Executes DOCX structure inspection
    - Image: Returns single-page scanned classification
    """
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext == ".pdf":
        return classify_pdf_document(content)

    elif ext == ".docx":
        # DOCX Pipeline route
        import docx
        doc = docx.Document(io.BytesIO(content))
        p_count = len(doc.paragraphs)
        tbl_count = len(doc.tables)
        # Check embedded images in docx
        img_count = 0
        try:
            for rel in doc.part.rels.values():
                if "image" in rel.target_ref.lower():
                    img_count += 1
        except Exception:
            pass

        text_len = sum(len(p.text) for p in doc.paragraphs)
        page_res = PageClassificationResult(
            page_number=1,
            page_type=PageType.MIXED if (img_count > 0 and text_len < 100) else PageType.TEXT,
            char_count=text_len,
            word_count=sum(len(p.text.split()) for p in doc.paragraphs),
            image_area_ratio=0.5 if img_count > 0 and text_len < 100 else 0.0,
            garbage_ratio=0.0,
            image_count=img_count,
            classification_reason=f"DOCX document with {p_count} paragraphs, {tbl_count} tables, {img_count} embedded images"
        )

        return DocumentClassificationResult(
            file_type="docx",
            route=DocumentRoute.DOCX_PIPELINE,
            page_count=1,
            pages=[page_res],
            overall_type="mixed" if (img_count > 0 and text_len < 100) else "text",
            has_scanned_pages=False,
            has_mixed_pages=(img_count > 0 and text_len < 100),
            needs_ocr=(img_count > 0 and text_len < 100),
            needs_vision=(img_count > 0 and text_len < 100)
        )

    elif ext in {".png", ".jpg", ".jpeg", ".tiff", ".tif"}:
        return DocumentClassificationResult(
            file_type=ext.lstrip("."),
            route=DocumentRoute.IMAGE_PIPELINE,
            page_count=1,
            pages=[PageClassificationResult(
                page_number=1,
                page_type=PageType.SCANNED,
                char_count=0,
                word_count=0,
                image_area_ratio=1.0,
                garbage_ratio=0.0,
                image_count=1,
                classification_reason="Pure raster image upload"
            )],
            overall_type="scanned",
            has_scanned_pages=True,
            has_mixed_pages=False,
            needs_ocr=True,
            needs_vision=True
        )

    else:
        return DocumentClassificationResult(
            file_type=ext.lstrip("."),
            route=DocumentRoute.RICH_TEXT_PIPELINE,
            page_count=1,
            pages=[PageClassificationResult(
                page_number=1,
                page_type=PageType.TEXT,
                char_count=len(content.decode("utf-8", errors="ignore")),
                word_count=len(content.decode("utf-8", errors="ignore").split()),
                image_area_ratio=0.0,
                garbage_ratio=0.0,
                image_count=0,
                classification_reason="Rich text format"
            )],
            overall_type="text",
            has_scanned_pages=False,
            has_mixed_pages=False,
            needs_ocr=False,
            needs_vision=False
        )
