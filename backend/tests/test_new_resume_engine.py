"""
Unit and Integration Tests for VidyamargAI New Resume Extraction Engine.
Validates extraction of Jayavarapu Siva Tejachary PDF and sample bundle documents.
"""
from pathlib import Path
import pytest

from app.services.resume_extractor_engine import (
    validate_resume_upload,
    extract_document_content,
    extract_structured_with_ai,
    extract_pdf_layout_aware,
    extract_docx_content,
    heuristic_comprehensive_parse
)
from app.api.routers.resume_center import convert_to_template_payload

INPUTS_DIR = Path(__file__).resolve().parent / ".." / "app" / "resume_engine" / "validation" / "inputs"


def test_user_resume_pdf_extraction():
    pdf_path = INPUTS_DIR / "Jayavarapu-Siva-Tejachary-AIML.pdf"
    assert pdf_path.exists(), f"File {pdf_path} not found"
    content = pdf_path.read_bytes()

    # 1. Validation
    is_valid, err, fhash, ext = validate_resume_upload(pdf_path.name, content)
    assert is_valid is True
    assert err == ""
    assert ext == ".pdf"
    assert len(fhash) == 64

    # 2. Document content extraction
    doc_res = extract_document_content(pdf_path.name, content, ext)
    assert len(doc_res["raw_text"]) > 200
    assert doc_res["page_count"] >= 1
    assert "layout_info" in doc_res

    # 3. Structured data extraction
    structured = extract_structured_with_ai(
        doc_res["raw_text"], content, doc_res["layout_info"]
    )
    pi = structured["personal_info"]
    assert "JAYAVARAPU SIVA TEJACHARY" in pi["full_name"].upper()
    assert "j.shivachary@gmail.com" in pi["email"].lower()
    assert "9866862016" in pi["phone"]
    assert "linkedin.com" in (pi["linkedin"] or "").lower()
    assert "github.com" in (pi["github"] or "").lower()

    # Work experience
    exps = structured["work_experience"]
    assert len(exps) >= 1
    exp0 = exps[0]
    assert "Avataa" in exp0["employer"]
    assert "AI/ML Engineer" in exp0["designation"]
    assert len(exp0["responsibilities"]) >= 3

    # Education
    edus = structured["education"]
    assert len(edus) >= 1
    edu0 = edus[0]
    assert "Chalapathi" in edu0["institution"]
    assert "Computer Science" in edu0["degree"]
    assert "7.9" in edu0["gpa"]

    # Projects
    projs = structured["projects"]
    assert len(projs) >= 3
    proj_names = [p["name"] for p in projs]
    assert any("RAG" in name for name in proj_names)
    assert any("Document AI" in name for name in proj_names)
    assert any("Screening" in name for name in proj_names)

    # Skills
    skills = structured["skills"]
    assert len(skills["all_raw_skills"]) >= 15
    assert "Python" in skills["all_raw_skills"]
    assert "FastAPI" in skills["all_raw_skills"]

    # 4. Conversion to template payload for LaTeX rendering
    payload = convert_to_template_payload(structured)
    assert payload["personal_info"]["full_name"] == pi["full_name"]
    assert len(payload["work_experience"]) >= 1
    assert len(payload["education"]) >= 1
    assert len(payload["projects"]) >= 3


def test_docx_template_extraction():
    docx_path = INPUTS_DIR / "colorful_resume_templates_bundle" / "01_DOCX_Vibrant_Coral_Creative_Resume.docx"
    if not docx_path.exists():
        docx_path = INPUTS_DIR / "resume_templates_test_bundle" / "01_Modern_Tech_Software_Engineer.docx"
    assert docx_path.exists()

    content = docx_path.read_bytes()
    is_valid, err, fhash, ext = validate_resume_upload(docx_path.name, content)
    assert is_valid is True
    assert ext == ".docx"

    doc_res = extract_document_content(docx_path.name, content, ext)
    assert len(doc_res["raw_text"]) > 100

    structured = extract_structured_with_ai(
        doc_res["raw_text"], content, doc_res["layout_info"]
    )
    assert structured["personal_info"]["full_name"] is not None
    assert len(structured["work_experience"]) > 0 or len(structured["skills"]["all_raw_skills"]) > 0


def test_validation_error_cases():
    # Empty file
    assert validate_resume_upload("resume.pdf", b"")[0] is False
    # Non-PDF invalid signature
    assert validate_resume_upload("resume.pdf", b"NOT_A_PDF")[0] is False
    # Oversized
    huge = b"0" * (11 * 1024 * 1024)
    assert validate_resume_upload("resume.pdf", huge)[0] is False
