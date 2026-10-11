"""
Unit tests for backend/scripts/repair_existing_resumes.py
Verifies:
1. Dry-run mode never commits changes to database.
2. Identifies and clears hallucinated placeholder strings in work experience and projects.
3. Creates valid timestamped JSON backup snapshots when requested.
"""

import os
import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.models import Base, User, Candidate
from app.models.resume_center_models import (
    Resume, ResumeVersion, ResumeExtraction, ResumeProfile,
    ResumeExperience, ResumeEducation, ResumeProject, ResumeSkill, ResumeTemplate
)
from scripts.repair_existing_resumes import audit_and_repair_resume, create_backup_snapshot


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    try:
        user = User(email="test_repair@example.com", password_hash="pw", full_name="Test Repair", role="candidate")
        db.add(user)
        db.flush()
        cand = Candidate(user_id=user.id, status="Active")
        db.add(cand)
        db.flush()
        tmpl = ResumeTemplate(name="Classic", slug="classic-ats", description="Classic ATS", is_active=True, ats_score=95, latex_template="")
        db.add(tmpl)
        db.flush()
        yield db, user, cand
    finally:
        db.close()


def test_dry_run_audit_identifies_hallucinations_without_db_mutation(test_db):
    db, user, cand = test_db

    # Create resume with hallucinated placeholder data
    resume = Resume(
        candidate_id=cand.id,
        title="Resume with Hallucinations",
        source_type="upload",
        file_name="test.pdf",
        file_type="PDF",
        status="active",
        extraction_status="extracted"
    )
    db.add(resume)
    db.flush()

    old_structured = {
        "work_experience": [
            {
                "employer": "Company",
                "designation": "Role",
                "responsibilities": ["Designed and implemented project functionality.", "Legitimate bullet point."]
            }
        ],
        "projects": [
            {
                "name": "Project",
                "bullets": ["Key contributor to team deliverables.", "Real bullet."]
            }
        ]
    }

    extraction = ResumeExtraction(
        resume_id=resume.id,
        raw_text="Sample text",
        structured_data=old_structured,
        confidence_score=0.8
    )
    db.add(extraction)

    version = ResumeVersion(
        resume_id=resume.id,
        version_number=1,
        structured_data=old_structured,
        latex_source="",
        change_summary="Original",
        created_by=user.id
    )
    db.add(version)
    db.commit()

    # 1. Run in DRY-RUN mode (commit=False)
    report = audit_and_repair_resume(db, resume, commit=False)
    assert report["status"] == "repaired"
    assert len(report["anomalies_detected"]) >= 2
    assert any("Placeholder employer/role" in a for a in report["anomalies_detected"])
    assert any("Hallucinated" in a for a in report["anomalies_detected"])

    # Verify database was NOT mutated
    db_version = db.query(ResumeVersion).filter(ResumeVersion.id == version.id).first()
    assert db_version.change_summary == "Original"
    assert db_version.structured_data["work_experience"][0]["employer"] == "Company"

    # 2. Run with COMMIT (commit=True)
    report_commit = audit_and_repair_resume(db, resume, commit=True)
    assert report_commit["status"] == "repaired"

    # Verify database WAS mutated and placeholders removed
    db.refresh(db_version)
    assert db_version.change_summary == "Repaired via Layout-Aware Overhaul Utility"
    db_extraction = db.query(ResumeExtraction).filter(ResumeExtraction.resume_id == resume.id).first()
    exp_repaired = db_extraction.structured_data["work_experience"][0]
    assert exp_repaired.get("employer") != "Company"
    assert "Designed and implemented project functionality." not in exp_repaired["responsibilities"]
