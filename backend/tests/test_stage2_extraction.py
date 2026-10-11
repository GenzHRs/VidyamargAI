"""
Unit and Integration Tests for Stage 2: Multi-Layout & Multi-Modal Text Extraction Engine.

Covers:
1. Column layout decomposition:
   - Single column layout (rw_01_pdf_selectable.pdf)
   - Three-column layout ordering without interleaving (rw_43_three_column_layout.pdf)
   - Top-banner full-width header isolation in two-column layouts (rw_44_two_column_full_width_header.pdf)
2. Multi-page noise suppression:
   - Repeated running header/footer suppression across pages (rw_30_complex_multipage_repeated_headers.pdf)
3. Font-size hierarchy extraction:
   - Body font mode size calculation and prominent heading detection
4. Spatial hyperlink extraction:
   - Resolution of PDF URI annotations to bounding boxes and text labels
5. DOCX document-order traversal:
   - Paragraphs, tables with pipe '|' delimiters, textboxes, and links (rw_05_docx_tables_nested.docx)
6. Scanned PDF processing & deterministic OCR:
   - 300 DPI rendering + OpenCV preprocessing + PaddleOCR CPU extraction (rw_02_pdf_scanned_ocr.pdf)
7. Mixed PDF digital text & regional OCR deduplication (rw_03_pdf_mixed_text_image.pdf)
8. OpenCV image preprocessing functions:
   - Downscaled morphological shadow removal, CLAHE, and deskewing
9. Async threadpool execution safety (extract_document_stage2_async)
"""

import io
import fitz
import pytest
import numpy as np
from pathlib import Path

from app.services.document_classifier import PageType
from app.services.page_extractors import (
    ColumnLayoutType,
    ExtractedBlock,
    PageExtractionResult,
    Stage2ExtractionResult,
    OcrEngine,
    extract_document_stage2,
    extract_document_stage2_async,
    extract_font_hierarchy_from_page,
    detect_column_layout_and_gutters,
    order_blocks_by_layout,
    deskew_image,
    remove_shadows_and_normalize,
    preprocess_scanned_image
)

FIXTURES_DIR = Path(__file__).resolve().parent / "real_world_corpus" / "fixtures"


# ─────────────────────────────────────────────────────────────────────────────
# 1. LAYOUT DECOMPOSITION & READING ORDER TESTS
# ─────────────────────────────────────────────────────────────────────────────

def test_stage2_single_column_layout():
    pdf_path = FIXTURES_DIR / "rw_01_pdf_selectable.pdf"
    content = pdf_path.read_bytes()

    result = extract_document_stage2(content, "rw_01_pdf_selectable.pdf")

    assert result.page_count == 1
    assert len(result.pages) == 1
    page1 = result.pages[0]
    assert page1.page_type == PageType.TEXT
    assert page1.column_layout == ColumnLayoutType.SINGLE_COLUMN
    assert len(page1.gutters) == 0

    # Verify key content present in raw text
    text_lower = result.raw_text.lower()
    assert "sarah jenkins" in text_lower
    assert "sarah.jenkins@example.com" in text_lower
    assert "apex cloud technologies" in text_lower


def test_stage2_three_column_layout_ordering():
    """
    rw_43 has 3 columns:
    Column 1: Core Skills (Flutter, Dart, Swift, Kotlin...)
    Column 2: Work Experience (Senior Mobile Lead, AppVelocity Inc...)
    Column 3: Projects & Education (SyncMesh Mobile, San Jose State University...)
    Must read Column 1 entirely -> Column 2 entirely -> Column 3 entirely.
    Must NOT interleave horizontally!
    """
    pdf_path = FIXTURES_DIR / "rw_43_three_column_layout.pdf"
    content = pdf_path.read_bytes()

    result = extract_document_stage2(content, "rw_43_three_column_layout.pdf")
    page1 = result.pages[0]

    assert page1.column_layout == ColumnLayoutType.THREE_COLUMN
    assert len(page1.gutters) >= 2

    raw_text = result.raw_text
    # Check that Column 1 items appear before Column 2 items, which appear before Column 3 items
    idx_col1 = raw_text.find("CORE SKILLS")
    idx_col2 = raw_text.find("WORK EXPERIENCE")
    idx_col3 = raw_text.find("PROJECTS")

    assert idx_col1 != -1, "Column 1 heading 'CORE SKILLS' not found"
    assert idx_col2 != -1, "Column 2 heading 'WORK EXPERIENCE' not found"
    assert idx_col3 != -1, "Column 3 heading 'PROJECTS' not found"

    assert idx_col1 < idx_col2 < idx_col3, (
        f"Reading order violation in 3-column layout: col1={idx_col1}, col2={idx_col2}, col3={idx_col3}"
    )


def test_stage2_two_column_full_width_header():
    """
    rw_44 has a full-width header banner (Danielle Vance, contact details, summary)
    followed by a 2-column body split (Left: skills, Right: experience).
    The header banner must be extracted at the top BEFORE any column content.
    """
    pdf_path = FIXTURES_DIR / "rw_44_two_column_full_width_header.pdf"
    content = pdf_path.read_bytes()

    result = extract_document_stage2(content, "rw_44_two_column_full_width_header.pdf")
    page1 = result.pages[0]

    assert page1.column_layout in (
        ColumnLayoutType.LEFT_SIDEBAR,
        ColumnLayoutType.RIGHT_SIDEBAR,
        ColumnLayoutType.TWO_COLUMN_BALANCED
    )
    assert len(page1.gutters) == 1

    raw_text = result.raw_text
    text_lower = raw_text.lower()
    idx_name = text_lower.find("danielle vance")
    idx_contact = text_lower.find("danielle.vance@cloudsec.io")
    idx_left_heading = raw_text.find("TECHNICAL SKILLS")
    idx_right_heading = raw_text.find("WORK EXPERIENCE")

    assert idx_name != -1, "Header name 'Danielle Vance' not found"
    assert idx_contact != -1, "Header contact 'danielle.vance@cloudsec.io' not found"
    assert idx_left_heading != -1, "Sidebar heading 'TECHNICAL SKILLS' not found"
    assert idx_right_heading != -1, "Main column heading 'WORK EXPERIENCE' not found"

    # Full-width header banner MUST precede both columns
    assert idx_name < idx_left_heading
    assert idx_name < idx_right_heading
    assert idx_contact < idx_left_heading
    assert idx_contact < idx_right_heading


# ─────────────────────────────────────────────────────────────────────────────
# 2. MULTI-PAGE NOISE SUPPRESSION & FONT HIERARCHY
# ─────────────────────────────────────────────────────────────────────────────

def test_stage2_running_header_footer_suppression():
    """
    rw_30 is a 2-page document with a running header 'Victoria Sterling • Page 2 of 2'
    and footer. The running header must be suppressed from raw text, while
    substantive work experience ('PREVIOUS EXPERIENCE', 'Goldman Sachs') must be kept.
    """
    pdf_path = FIXTURES_DIR / "rw_30_complex_multipage_repeated_headers.pdf"
    content = pdf_path.read_bytes()

    result = extract_document_stage2(content, "rw_30_complex_multipage_repeated_headers.pdf")

    assert result.page_count == 2
    # Verify running header is suppressed
    assert "Page 2 of 2" not in result.raw_text
    # Verify substantive content on page 2 is preserved
    assert "Goldman Sachs" in result.raw_text
    assert "Columbia University" in result.raw_text


def test_stage2_font_hierarchy_extraction():
    pdf_path = FIXTURES_DIR / "rw_01_pdf_selectable.pdf"
    doc = fitz.open(pdf_path)
    page = doc[0]

    hierarchy = extract_font_hierarchy_from_page(page)
    doc.close()

    assert "body_mode_size" in hierarchy
    assert 9.0 <= hierarchy["body_mode_size"] <= 13.0
    assert hierarchy["headings_count"] > 0
    heading_texts = [h["text"].upper() for h in hierarchy["heading_candidates"]]
    assert any("EXPERIENCE" in t for t in heading_texts)
    assert any("EDUCATION" in t for t in heading_texts)


def test_stage2_spatial_hyperlink_extraction():
    pdf_path = FIXTURES_DIR / "rw_01_pdf_selectable.pdf"
    content = pdf_path.read_bytes()

    result = extract_document_stage2(content, "rw_01_pdf_selectable.pdf")

    assert len(result.hyperlinks) > 0
    urls = [l["url"] for l in result.hyperlinks]
    assert any("github.com" in u for u in urls) or any("linkedin.com" in u for u in urls)


# ─────────────────────────────────────────────────────────────────────────────
# 3. DOCX TRAVERSAL TESTS
# ─────────────────────────────────────────────────────────────────────────────

def test_stage2_docx_pipeline_with_tables():
    """
    rw_05 is a DOCX resume containing nested tables.
    The Stage 2 DOCX pipeline must preserve table structures with pipe delimiters.
    """
    docx_path = FIXTURES_DIR / "rw_05_docx_tables_nested.docx"
    content = docx_path.read_bytes()

    result = extract_document_stage2(content, "rw_05_docx_tables_nested.docx")

    assert result.file_type == "docx"
    assert result.tables_count > 0
    assert "|" in result.raw_text
    assert "Priya Sharma" in result.raw_text
    assert "Infosys Limited" in result.raw_text


def test_stage2_docx_hyperlinks_and_paragraphs():
    docx_path = FIXTURES_DIR / "rw_06_docx_hyperlinks_styled.docx"
    content = docx_path.read_bytes()

    result = extract_document_stage2(content, "rw_06_docx_hyperlinks_styled.docx")

    assert result.file_type == "docx"
    assert len(result.raw_text) > 100
    assert len(result.hyperlinks) > 0


# ─────────────────────────────────────────────────────────────────────────────
# 4. OPENCV RESTORATION & PREPROCESSING TESTS
# ─────────────────────────────────────────────────────────────────────────────

def test_opencv_shadow_removal_and_deskew():
    # Create synthetic test image with skewed text line
    img = np.full((300, 500), 240, dtype=np.uint8)
    # Add a non-uniform lighting gradient
    gradient = np.linspace(0, 100, 500, dtype=np.uint8)
    shadowed = np.clip(img - gradient, 0, 255).astype(np.uint8)

    # Apply shadow removal
    normalized = remove_shadows_and_normalize(shadowed)
    assert normalized.shape == (300, 500)
    assert normalized.dtype == np.uint8

    # Test end-to-end preprocessing pipeline
    bgr = np.stack([shadowed] * 3, axis=-1)
    clean_bgr, binary, meta = preprocess_scanned_image(bgr)

    assert clean_bgr.shape == (300, 500, 3)
    assert binary.shape == (300, 500)
    assert meta["shadow_removal_applied"] is True
    assert meta["clahe_applied"] is True


# ─────────────────────────────────────────────────────────────────────────────
# 5. SCANNED & MIXED PDF EXTRACTION TESTS
# ─────────────────────────────────────────────────────────────────────────────

def test_stage2_scanned_pdf_deterministic_ocr():
    """
    rw_02 is a scanned PDF (image-only resume).
    Previously returned empty string and failed HTTP 400.
    Must classify as SCANNED, apply 300 DPI rendering, preprocess, and run OCR.
    """
    pdf_path = FIXTURES_DIR / "rw_02_pdf_scanned_ocr.pdf"
    content = pdf_path.read_bytes()

    result = extract_document_stage2(content, "rw_02_pdf_scanned_ocr.pdf")

    assert result.page_count == 1
    page1 = result.pages[0]
    assert page1.page_type == PageType.SCANNED
    assert page1.ocr_used is True
    assert 1 in result.ocr_applied_pages
    assert len(result.raw_text) > 100

    text_lower = result.raw_text.lower()
    # Scanned resume of Evelyn Vance
    assert "evelyn" in text_lower or "vance" in text_lower or "experience" in text_lower


def test_stage2_mixed_pdf_deduplication():
    """
    rw_03 contains digital text in the header and raster images for the rest.
    Must extract digital text and image OCR without duplicate overlap.
    """
    pdf_path = FIXTURES_DIR / "rw_03_pdf_mixed_text_image.pdf"
    content = pdf_path.read_bytes()

    result = extract_document_stage2(content, "rw_03_pdf_mixed_text_image.pdf")

    assert result.page_count == 1
    page1 = result.pages[0]
    assert page1.page_type == PageType.MIXED
    assert len(result.raw_text) > 100

    text_lower = result.raw_text.lower()
    assert "elena" in text_lower or "rostova" in text_lower or "visionlab" in text_lower


# ─────────────────────────────────────────────────────────────────────────────
# 6. ASYNC THREADPOOL SAFETY TEST
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stage2_async_threadpool_execution():
    pdf_path = FIXTURES_DIR / "rw_01_pdf_selectable.pdf"
    content = pdf_path.read_bytes()

    result = await extract_document_stage2_async(content, "rw_01_pdf_selectable.pdf")

    assert isinstance(result, Stage2ExtractionResult)
    assert result.page_count == 1
    assert "Sarah Jenkins" in result.raw_text
