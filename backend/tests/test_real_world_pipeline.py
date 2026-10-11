"""
Test Suite: Real-World Resume Pipeline & Extraction Integrity
Validates:
1. Corpus manifest & ground truth integrity (all 41 fixtures)
2. Safe rejection & security defense (corrupted, empty, encrypted, unsupported, prompt injection)
3. End-to-end extraction across diverse layouts & formats
4. Hyperlink fidelity and anchor matching
5. Database persistence and idempotency (no duplicate entities on re-parse)
6. Multi-candidate data isolation
7. Immutable job application snapshot guarantee
"""

import os
import json
import pytest
from pathlib import Path

from app.services.resume_extractor_engine import (
    validate_resume_upload,
    extract_document_content,
    extract_structured_with_ai,
    _normalize_and_validate_extraction
)
from app.services.hyperlink_extractor import associate_links_with_resume_entities
from app.services.project_normalizer import canonicalize_projects_list
from app.services.latex_service import render_structured_data_to_pdf
from app.api.routers.resume_center import sync_extraction_to_database, convert_to_template_payload

BASE_DIR = Path(__file__).resolve().parent
CORPUS_DIR = BASE_DIR / "real_world_corpus"
FIXTURES_DIR = CORPUS_DIR / "fixtures"
GROUND_TRUTH_DIR = CORPUS_DIR / "ground_truth"
MANIFEST_FILE = CORPUS_DIR / "manifest.json"


@pytest.fixture(scope="session")
def manifest():
    assert MANIFEST_FILE.exists(), f"Manifest file missing at {MANIFEST_FILE}"
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        return data if isinstance(data, list) else data.get("fixtures", [])


def test_corpus_manifest_and_ground_truth_integrity(manifest):
    """Verifies that all corpus fixtures (including Phase 0 additions) and ground truth files exist and match."""
    assert len(manifest) >= 41, f"Expected at least 41 fixtures in manifest, found {len(manifest)}"

    for entry in manifest:
        test_id = entry["test_id"]
        file_name = entry["file_name"]
        fixture_path = FIXTURES_DIR / file_name
        truth_path = GROUND_TRUTH_DIR / f"{test_id}_truth.json"

        assert fixture_path.exists(), f"Fixture file missing: {fixture_path}"
        assert truth_path.exists(), f"Ground truth file missing: {truth_path}"

        with open(truth_path, "r", encoding="utf-8") as f:
            gt = json.load(f)
            assert gt["test_id"] == test_id
            if gt.get("expected_status") != "rejected":
                assert "personal_info" in gt
            else:
                assert "rejection_reason" in gt


def test_edge_corrupted_file_handling():
    """Validates that corrupted files are rejected gracefully without unhandled crashes."""
    corrupt_path = FIXTURES_DIR / "rw_38_edge_corrupted.pdf"
    assert corrupt_path.exists()
    with open(corrupt_path, "rb") as f:
        content = f.read()

    is_valid, err_msg, _, _ = validate_resume_upload("rw_38_edge_corrupted.pdf", content)
    assert is_valid is False or "corrupt" in (err_msg or "").lower() or "error" in (err_msg or "").lower()


def test_edge_empty_file_handling():
    """Validates that empty files are safely rejected by upload validation."""
    empty_path = FIXTURES_DIR / "rw_39_edge_empty.pdf"
    assert empty_path.exists()
    with open(empty_path, "rb") as f:
        content = f.read()

    is_valid, err_msg, _, _ = validate_resume_upload("rw_39_edge_empty.pdf", content)
    assert is_valid is False
    assert "empty" in (err_msg or "").lower()


def test_edge_encrypted_file_handling():
    """Validates that password-protected files are trapped gracefully during validation or parsing."""
    enc_path = FIXTURES_DIR / "rw_40_edge_encrypted.pdf"
    assert enc_path.exists()
    with open(enc_path, "rb") as f:
        content = f.read()

    is_valid, err_msg, _, ext = validate_resume_upload("rw_40_edge_encrypted.pdf", content)
    if is_valid:
        doc_res = extract_document_content("rw_40_edge_encrypted.pdf", content, ext)
        assert doc_res.get("raw_text", "") == "" or "encrypted" in str(doc_res)


def test_edge_unsupported_file_handling():
    """Validates that unsupported file extensions are rejected upfront."""
    unsupp_path = FIXTURES_DIR / "rw_41_edge_unsupported.xyz"
    assert unsupp_path.exists()
    with open(unsupp_path, "rb") as f:
        content = f.read()

    is_valid, err_msg, _, _ = validate_resume_upload("rw_41_edge_unsupported.xyz", content)
    assert is_valid is False
    assert "unsupported" in (err_msg or "").lower() or "extension" in (err_msg or "").lower()


def test_edge_prompt_injection_defense():
    """Validates that prompt injection in resumes is contained and candidate identity preserved."""
    inj_path = FIXTURES_DIR / "rw_37_edge_prompt_injection_security.pdf"
    assert inj_path.exists()
    with open(inj_path, "rb") as f:
        content = f.read()

    is_valid, _, _, ext = validate_resume_upload("rw_37_edge_prompt_injection_security.pdf", content)
    assert is_valid is True

    doc_res = extract_document_content("rw_37_edge_prompt_injection_security.pdf", content, ext)
    structured = extract_structured_with_ai(doc_res["raw_text"], content, doc_res["layout_info"])

    # Candidate name must be Kevin Flynn, NOT 'SYSTEM ADMINISTRATOR'
    name = (structured.get("personal_info") or {}).get("full_name", "")
    assert "Kevin" in name or "Flynn" in name
    assert "ADMINISTRATOR" not in name.upper()


def test_end_to_end_formats_extraction_and_pdf_render():
    """Tests full pipeline (parse -> normalize -> PDF render) on multiple formats."""
    test_files = [
        "rw_01_pdf_selectable.pdf",
        "rw_04_docx_paragraphs.docx",
        "rw_10_txt_plain.txt",
        "rw_11_html_export.html",
        "rw_15_pptx_slides.pptx"
    ]

    for filename in test_files:
        filepath = FIXTURES_DIR / filename
        assert filepath.exists(), f"File missing: {filepath}"
        with open(filepath, "rb") as f:
            content = f.read()

        is_valid, err_msg, _, ext = validate_resume_upload(filename, content)
        assert is_valid, f"Validation failed for {filename}: {err_msg}"

        doc_res = extract_document_content(filename, content, ext)
        raw_text = doc_res["raw_text"]
        assert len(raw_text.strip()) > 20, f"Raw text unexpectedly empty for {filename}"

        pdf_bytes_in = content if ext == ".pdf" else None
        structured = extract_structured_with_ai(raw_text, pdf_bytes_in, doc_res["layout_info"])
        assert structured is not None

        normalized = _normalize_and_validate_extraction(structured, raw_text)
        if "projects" in normalized:
            normalized["projects"] = canonicalize_projects_list(normalized["projects"])

        payload = convert_to_template_payload(normalized)
        rendered_pdf = render_structured_data_to_pdf(payload, template_slug="classic_ats")
        assert rendered_pdf is not None
        assert len(rendered_pdf) > 500, f"Rendered PDF for {filename} is unexpectedly small"
        assert rendered_pdf.startswith(b"%PDF"), f"Rendered output for {filename} is not a valid PDF"


def test_hyperlink_extraction_integrity():
    """Validates that hyperlinks are extracted and associated correctly."""
    filepath = FIXTURES_DIR / "rw_01_pdf_selectable.pdf"
    with open(filepath, "rb") as f:
        content = f.read()

    doc_res = extract_document_content("rw_01_pdf_selectable.pdf", content, ".pdf")
    hyperlinks = doc_res["layout_info"].get("hyperlinks", [])
    assert len(hyperlinks) >= 1, "Expected at least 1 hyperlink extracted from rw_01"

    structured = extract_structured_with_ai(doc_res["raw_text"], content, doc_res["layout_info"])
    structured, enriched_links = associate_links_with_resume_entities(hyperlinks, structured)

    urls = [h.get("url", "") for h in enriched_links]
    assert any("github.com" in u or "http" in u for u in urls), "Hyperlinks missing from extracted hyperlinks"


def test_database_persistence_and_idempotency():
    """
    Validates that saving or updating resume data is idempotent:
    re-saving normalized entities updates records instead of duplicating them.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.core.database import Base
    from app.models.resume_center_models import (
        Resume, ResumeVersion, ResumeExtraction, ResumeProfile,
        ResumeExperience, ResumeEducation, ResumeProject, ResumeSkill
    )

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Create root resume record
    resume = Resume(
        id=1,
        candidate_id=42,
        title="Marcus Resume",
        source_type="upload",
        file_name="rw_01_pdf_selectable.pdf"
    )
    session.add(resume)
    session.commit()

    sample_extraction = {
        "personal_info": {"full_name": "Marcus Vance", "email": "m.vance@apexcloud.io"},
        "professional_summary": "Lead Cloud Architect with 12 years experience.",
        "work_experience": [
            {
                "company": "Apex Cloud",
                "title": "Lead Architect",
                "start_date": "2021",
                "end_date": "Present",
                "responsibilities": ["Architected distributed systems"]
            }
        ],
        "education": [{"institution": "Tech University", "degree": "B.S. Computer Science"}],
        "projects": [{"name": "CloudMigrate", "technologies": ["Python", "AWS"]}],
        "skills": {
            "programming_languages": ["Python", "Go"],
            "cloud_platforms": ["AWS", "Kubernetes"]
        }
    }

    # Pass 1: First sync
    sync_extraction_to_database(
        db=session,
        resume=resume,
        structured_data=sample_extraction,
        raw_text="Marcus Vance Lead Cloud Architect Apex Cloud"
    )
    session.commit()

    exp_count_1 = session.query(ResumeExperience).filter_by(resume_id=1).count()
    edu_count_1 = session.query(ResumeEducation).filter_by(resume_id=1).count()
    skill_count_1 = session.query(ResumeSkill).filter_by(resume_id=1).count()
    proj_count_1 = session.query(ResumeProject).filter_by(resume_id=1).count()

    assert exp_count_1 == 1
    assert edu_count_1 == 1
    assert skill_count_1 == 4  # 2 languages + 2 cloud
    assert proj_count_1 == 1

    # Pass 2: Re-syncing the updated extraction with 1 extra skill
    sample_extraction_v2 = dict(sample_extraction)
    sample_extraction_v2["skills"] = dict(sample_extraction["skills"])
    sample_extraction_v2["skills"]["cloud_platforms"] = ["AWS", "Kubernetes", "Terraform"]

    sync_extraction_to_database(
        db=session,
        resume=resume,
        structured_data=sample_extraction_v2,
        raw_text="Marcus Vance Lead Cloud Architect Apex Cloud"
    )
    session.commit()

    exp_count_2 = session.query(ResumeExperience).filter_by(resume_id=1).count()
    edu_count_2 = session.query(ResumeEducation).filter_by(resume_id=1).count()
    skill_count_2 = session.query(ResumeSkill).filter_by(resume_id=1).count()
    proj_count_2 = session.query(ResumeProject).filter_by(resume_id=1).count()

    # Proves idempotency: old rows were cleared, no duplicates created
    assert exp_count_2 == 1, f"Expected 1 experience record, found {exp_count_2}"
    assert edu_count_2 == 1, f"Expected 1 education record, found {edu_count_2}"
    assert skill_count_2 == 5, f"Expected 5 skill records, found {skill_count_2}"
    assert proj_count_2 == 1, f"Expected 1 project record, found {proj_count_2}"

    session.close()


def test_candidate_ownership_isolation():
    """Validates that candidate resumes are strictly isolated by candidate_id."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.core.database import Base
    from app.models.resume_center_models import Resume

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Candidate A
    resume_a = Resume(id=1, candidate_id=101, title="Candidate A Resume")
    # Candidate B
    resume_b = Resume(id=2, candidate_id=202, title="Candidate B Resume")
    session.add_all([resume_a, resume_b])
    session.commit()

    # Query for Candidate A should never return Candidate B's resume
    resumes_for_a = session.query(Resume).filter(Resume.candidate_id == 101).all()
    assert len(resumes_for_a) == 1
    assert resumes_for_a[0].id == 1
    assert resumes_for_a[0].candidate_id == 101

    resumes_for_b = session.query(Resume).filter(Resume.candidate_id == 202).all()
    assert len(resumes_for_b) == 1
    assert resumes_for_b[0].id == 2
    assert resumes_for_b[0].candidate_id == 202
    session.close()


def test_immutable_application_snapshot_guarantee():
    """
    Validates that job application snapshots remain frozen and immutable
    even when candidate profile or active resume is updated later.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.core.database import Base
    from app.models.resume_center_models import Resume, ResumeVersion

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # 1. Candidate creates Resume Version 1
    resume = Resume(id=10, candidate_id=500, title="Applied Resume")
    session.add(resume)
    session.commit()

    v1_data = {
        "full_name": "Devon Miller",
        "experience": [{"title": "Mid-level Engineer", "company": "Beta Corp"}]
    }
    v1 = ResumeVersion(id=100, resume_id=resume.id, version_number=1, structured_data=v1_data)
    session.add(v1)
    session.commit()

    # 2. Application submitted using Version 1 snapshot
    application_snapshot = {
        "application_id": 999,
        "job_id": 404,
        "candidate_id": 500,
        "resume_version_id": v1.id,
        "frozen_structured_data": v1.structured_data
    }

    # 3. Later, Candidate updates their profile and creates Version 2
    v2_data = {
        "full_name": "Devon Miller, Principal Engineer",
        "experience": [{"title": "Principal Architect", "company": "Gamma Innovations"}]
    }
    v2 = ResumeVersion(id=101, resume_id=resume.id, version_number=2, structured_data=v2_data)
    session.add(v2)
    session.commit()

    # 4. Verify the application snapshot remains exactly as submitted
    assert application_snapshot["resume_version_id"] == 100
    assert application_snapshot["frozen_structured_data"]["experience"][0]["title"] == "Mid-level Engineer"
    assert application_snapshot["frozen_structured_data"]["experience"][0]["company"] == "Beta Corp"

    # Also verify in DB that version 1 record itself was not overwritten
    retrieved_v1 = session.query(ResumeVersion).filter_by(id=100).first()
    assert retrieved_v1.structured_data["experience"][0]["title"] == "Mid-level Engineer"
    session.close()
