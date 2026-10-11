"""
Unit and Integration Tests for Stage 1: Intake, Validation, and Routing
Validates:
1. Intake validation: size limits, magic bytes, zip-bomb defense, encrypted PDF defense, SHA-256.
2. Route by type: PDF -> page-level classifier; DOCX -> DOCX pipeline.
3. PDF Page Classifier:
   - TEXT page classification
   - SCANNED page classification
   - MIXED page classification
   - Broken font encoding (CID garbage) page classification as SCANNED
"""

import io
import fitz
import pytest
from pathlib import Path

from app.services.document_classifier import (
    PageType,
    DocumentRoute,
    validate_document_intake,
    classify_pdf_page,
    classify_pdf_document,
    route_document
)

FIXTURES_DIR = Path(__file__).resolve().parent / "real_world_corpus" / "fixtures"


# ─────────────────────────────────────────────────────────────────────────────
# 1. INTAKE VALIDATION TESTS
# ─────────────────────────────────────────────────────────────────────────────

def test_validation_empty_file():
    res = validate_document_intake("resume.pdf", b"")
    assert res.is_valid is False
    assert "empty" in res.error_message.lower()


def test_validation_oversized_file():
    huge_bytes = b"0" * (11 * 1024 * 1024)  # 11 MB
    res = validate_document_intake("resume.pdf", huge_bytes)
    assert res.is_valid is False
    assert "exceeds" in res.error_message.lower() or "10 mb" in res.error_message.lower()


def test_validation_unsupported_extension():
    res = validate_document_intake("malware.exe", b"MZ\x90\x00\x03")
    assert res.is_valid is False
    assert "unsupported" in res.error_message.lower()


def test_validation_pdf_magic_bytes_mismatch():
    fake_pdf = b"NOT_A_REAL_PDF_HEADER"
    res = validate_document_intake("resume.pdf", fake_pdf)
    assert res.is_valid is False
    assert "signature mismatch" in res.error_message.lower() or "corrupted" in res.error_message.lower()


def test_validation_encrypted_pdf_rejection():
    enc_path = FIXTURES_DIR / "rw_40_edge_encrypted.pdf"
    assert enc_path.exists()
    content = enc_path.read_bytes()
    res = validate_document_intake("rw_40_edge_encrypted.pdf", content)
    assert res.is_valid is False
    assert "password" in res.error_message.lower() or "encrypted" in res.error_message.lower()


def test_validation_valid_pdf_sha256():
    pdf_path = FIXTURES_DIR / "rw_01_pdf_selectable.pdf"
    content = pdf_path.read_bytes()
    res = validate_document_intake("rw_01_pdf_selectable.pdf", content)
    assert res.is_valid is True
    assert res.error_message is None
    assert len(res.file_hash) == 64
    assert res.route == DocumentRoute.PDF_PIPELINE


# ─────────────────────────────────────────────────────────────────────────────
# 2. PDF PAGE CLASSIFIER TESTS
# ─────────────────────────────────────────────────────────────────────────────

def test_page_classifier_text_page():
    pdf_path = FIXTURES_DIR / "rw_01_pdf_selectable.pdf"
    doc = fitz.open(pdf_path)
    page_res = classify_pdf_page(doc[0], 0)
    doc.close()

    assert page_res.page_type == PageType.TEXT
    assert page_res.char_count > 200
    assert page_res.word_count > 40
    assert page_res.image_area_ratio < 0.20
    assert page_res.garbage_ratio < 0.05
    assert "clean digital text" in page_res.classification_reason.lower()


def test_page_classifier_scanned_page():
    pdf_path = FIXTURES_DIR / "rw_02_pdf_scanned_ocr.pdf"
    doc = fitz.open(pdf_path)
    page_res = classify_pdf_page(doc[0], 0)
    doc.close()

    assert page_res.page_type == PageType.SCANNED
    assert page_res.char_count < 40
    assert page_res.image_count >= 1
    assert "image-dominated" in page_res.classification_reason.lower() or "insufficient" in page_res.classification_reason.lower()


def test_page_classifier_mixed_page():
    pdf_path = FIXTURES_DIR / "rw_03_pdf_mixed_text_image.pdf"
    doc = fitz.open(pdf_path)
    page_res = classify_pdf_page(doc[0], 0)
    doc.close()

    assert page_res.page_type == PageType.MIXED
    assert page_res.char_count >= 50
    assert page_res.image_area_ratio >= 0.20
    assert "hybrid" in page_res.classification_reason.lower()


def test_page_classifier_broken_cid_font_encoding_marked_scanned():
    """
    Synthesizes a PDF whose text layer consists of broken (cid:..) glyph codes.
    Even though char_count > 100, the classifier must identify the garbage
    and label the page SCANNED so OCR/vision is triggered.
    """
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    # Insert broken CID strings mimicking unmappable PDF fonts
    garbage_stream = "(cid:12)(cid:45)(cid:88)(cid:99) (cid:102)(cid:103) (cid:14) " * 20
    page.insert_text((50, 50), garbage_stream, fontsize=10)

    page_res = classify_pdf_page(page, 0)
    doc.close()

    assert page_res.page_type == PageType.SCANNED
    assert page_res.garbage_ratio >= 0.20
    assert "broken font encoding" in page_res.classification_reason.lower()


# ─────────────────────────────────────────────────────────────────────────────
# 3. ROUTE DISPATCHER TESTS
# ─────────────────────────────────────────────────────────────────────────────

def test_route_pdf_document():
    pdf_path = FIXTURES_DIR / "rw_01_pdf_selectable.pdf"
    doc_res = route_document("rw_01_pdf_selectable.pdf", pdf_path.read_bytes())
    assert doc_res.route == DocumentRoute.PDF_PIPELINE
    assert doc_res.file_type == "pdf"
    assert doc_res.page_count >= 1
    assert doc_res.pages[0].page_type == PageType.TEXT
    assert doc_res.needs_ocr is False


def test_route_docx_document():
    docx_path = FIXTURES_DIR / "rw_04_docx_paragraphs.docx"
    doc_res = route_document("rw_04_docx_paragraphs.docx", docx_path.read_bytes())
    assert doc_res.route == DocumentRoute.DOCX_PIPELINE
    assert doc_res.file_type == "docx"
    assert doc_res.page_count == 1
    assert doc_res.pages[0].page_type == PageType.TEXT


def test_route_image_document():
    png_path = FIXTURES_DIR / "rw_12_image_png.png"
    doc_res = route_document("rw_12_image_png.png", png_path.read_bytes())
    assert doc_res.route == DocumentRoute.IMAGE_PIPELINE
    assert doc_res.overall_type == "scanned"
    assert doc_res.needs_ocr is True
    assert doc_res.needs_vision is True
