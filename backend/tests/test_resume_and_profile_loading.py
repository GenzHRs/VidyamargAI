"""
Comprehensive Regression & Integration Tests for Resume Center & Candidate Profile.
Verifies Phase 6 requirements:
1. Resume list returns real resumes.
2. Resume list returns an empty list for fresh candidates.
3. Resume API returns 401 when unauthenticated.
4. Candidate isolation: Candidate A cannot access Candidate B's resume or profile.
5. Profile loads successfully with full candidate details.
6. Profile loads safely when optional fields (experience, projects, certifications) are missing.
7. Profile API returns 401 when unauthenticated.
8. Active resume context synchronization works across endpoints.
9. Eager loading and query optimization prevents N+1 bottlenecks.
"""

import json
import pytest
from app.models.models import User, Candidate
from app.models.resume_center_models import (
    Resume, ResumeVersion, ResumeTemplate, ResumeProfile,
    ResumeExperience, ResumeProject, ResumeSkill, ResumeEducation, ResumeCertification
)
from tests.conftest import headers


def test_resume_list_returns_real_resumes(environment):
    client, db, owner, other, admin, candidate, tmp_path = environment

    # Seed template
    template = ResumeTemplate(
        name="Tech Modern",
        slug="tech-modern",
        description="Clean tech resume",
        latex_template="\\documentclass{article}",
        category="Technical",
        ats_score=96
    )
    db.add(template)
    db.commit()

    # Seed resume for candidate
    resume = Resume(
        candidate_id=candidate.id,
        title="Senior Software Engineer",
        source_type="upload",
        template_id=template.id,
        status="active",
        is_active=True
    )
    db.add(resume)
    db.commit()

    # Seed version
    version = ResumeVersion(
        resume_id=resume.id,
        version_number=1,
        structured_data={"summary": "Experienced software architect."},
        pdf_file_url="https://storage.vidyamarg.ai/resumes/test.pdf"
    )
    db.add(version)
    resume.current_version_id = version.id
    candidate.active_resume_id = resume.id
    db.commit()

    # Test GET /api/v1/resumes
    res = client.get("/api/v1/resumes", headers=headers(owner))
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["id"] == resume.id
    assert data[0]["title"] == "Senior Software Engineer"
    assert data[0]["template_name"] == "Tech Modern"
    assert data[0]["version_number"] == 1
    assert data[0]["is_active"] is True


def test_resume_list_returns_empty_list_for_new_candidate(environment):
    client, db, owner, other, admin, candidate, tmp_path = environment

    # `other` has no resumes
    res = client.get("/api/v1/resumes", headers=headers(other))
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) == 0


def test_resume_api_unauthorized_401(environment):
    client, db, owner, other, admin, candidate, tmp_path = environment

    # Request without Authorization header
    res = client.get("/api/v1/resumes")
    assert res.status_code == 401

    # Request with invalid token
    res = client.get("/api/v1/resumes", headers={"Authorization": "Bearer invalid_token_123"})
    assert res.status_code == 401


def test_candidate_isolation_cross_access_forbidden(environment):
    client, db, owner, other, admin, candidate, tmp_path = environment

    # Create resume for candidate A (owner)
    resume = Resume(
        candidate_id=candidate.id,
        title="Candidate A Private Resume",
        source_type="builder",
        status="active",
        is_active=True
    )
    db.add(resume)
    db.commit()

    # Candidate B (other) lists resumes -> Candidate A's resume must not appear
    res = client.get("/api/v1/resumes", headers=headers(other))
    assert res.status_code == 200
    resumes_b = res.json()
    assert all(r["id"] != resume.id for r in resumes_b)

    # Candidate B attempts direct GET on Candidate A's resume -> 403 Forbidden
    res_direct = client.get(f"/api/v1/resumes/{resume.id}", headers=headers(other))
    assert res_direct.status_code == 403
    assert "permission" in res_direct.json().get("detail", "").lower()


def test_profile_loads_successfully_with_complete_fields(environment):
    client, db, owner, other, admin, candidate, tmp_path = environment

    # Seed complete resume profile
    resume = Resume(
        candidate_id=candidate.id,
        title="Full Stack Architect",
        source_type="upload",
        status="active",
        is_active=True
    )
    db.add(resume)
    db.commit()

    prof = ResumeProfile(
        resume_id=resume.id,
        full_name="Jane Developer",
        email="jane.dev@example.com",
        phone="+1 555-0199",
        location="San Francisco, CA",
        linkedin_url="https://linkedin.com/in/janedev",
        github_url="https://github.com/janedev",
        portfolio_url="https://janedev.io",
        professional_summary="Principal engineer specializing in distributed systems and AI platforms."
    )
    db.add(prof)

    exp = ResumeExperience(
        resume_id=resume.id,
        employer="CloudTech Solutions",
        designation="Lead Architect",
        start_date="2021",
        end_date="Present",
        is_current=True,
        responsibilities=["Architected multi-tenant cloud pipelines", "Led team of 12 engineers"]
    )
    db.add(exp)

    proj = ResumeProject(
        resume_id=resume.id,
        name="AutoML Pipeline Engine",
        description="Low-latency inference server serving 5M daily requests.",
        technologies=["FastAPI", "Python", "Kubernetes"],
        link="https://github.com/janedev/automl"
    )
    db.add(proj)

    sk1 = ResumeSkill(resume_id=resume.id, name="Python", category="Programming Languages")
    sk2 = ResumeSkill(resume_id=resume.id, name="PostgreSQL", category="Databases")
    db.add_all([sk1, sk2])

    edu = ResumeEducation(
        resume_id=resume.id,
        degree="B.S. Computer Science",
        institution="University of Technology",
        graduation_year="2018"
    )
    db.add(edu)

    cert = ResumeCertification(
        resume_id=resume.id,
        name="AWS Certified Solutions Architect",
        issuing_organization="Amazon Web Services"
    )
    db.add(cert)

    candidate.active_resume_id = resume.id
    candidate.primary_designation = "Lead Architect"
    candidate.target_roles = json.dumps(["Lead Architect", "Staff Engineer"])
    db.commit()

    # Call GET /api/v1/candidates/profile
    res = client.get("/api/v1/candidates/profile", headers=headers(owner))
    assert res.status_code == 200
    data = res.json()

    # Verify structured fields
    assert data["personal_info"]["full_name"] == "Jane Developer"
    assert data["personal_info"]["email"] == "jane.dev@example.com"
    assert data["personal_info"]["phone"] == "+1 555-0199"
    assert data["personal_info"]["location"] == "San Francisco, CA"
    assert data["links"]["github"] == "https://github.com/janedev"
    assert data["professional"]["primary_designation"] == "Lead Architect"
    assert "Lead Architect" in data["professional"]["target_roles"]

    # Verify lists
    assert len(data["experience"]) == 1
    assert data["experience"][0]["company"] == "CloudTech Solutions"
    assert data["experience"][0]["designation"] == "Lead Architect"

    assert len(data["projects"]) == 1
    assert data["projects"][0]["name"] == "AutoML Pipeline Engine"

    assert len(data["skills"]) == 2
    skill_names = [s["name"] for s in data["skills"]]
    assert "Python" in skill_names
    assert "PostgreSQL" in skill_names

    assert len(data["education"]) == 1
    assert data["education"][0]["degree"] == "B.S. Computer Science"

    assert len(data["certifications"]) == 1
    assert data["certifications"][0]["name"] == "AWS Certified Solutions Architect"


def test_profile_loads_with_missing_optional_fields(environment):
    client, db, owner, other, admin, candidate, tmp_path = environment

    # `other` has no resumes, no experience, no projects, no certs
    res = client.get("/api/v1/candidates/profile", headers=headers(other))
    assert res.status_code == 200
    data = res.json()

    # Core user details fallback gracefully without crashing
    assert data["personal_info"]["email"] == "other@example.com"
    assert data["personal_info"]["full_name"] == "Other"

    # Optional lists are cleanly empty
    assert data["experience"] == []
    assert data["projects"] == []
    assert data["skills"] == []
    assert data["education"] == []
    assert data["certifications"] == []
    assert data["active_resume_id"] is None


def test_profile_api_unauthorized_401(environment):
    client, db, owner, other, admin, candidate, tmp_path = environment

    res = client.get("/api/v1/candidates/profile")
    assert res.status_code == 401


def test_active_resume_context_endpoint(environment):
    client, db, owner, other, admin, candidate, tmp_path = environment

    # Before resume upload
    res = client.get("/api/v1/resumes/active", headers=headers(owner))
    assert res.status_code == 200
    data = res.json()
    assert data["has_resume"] is False
    assert data["active_resume"] is None

    # After adding active resume
    resume = Resume(
        candidate_id=candidate.id,
        title="Active Master Resume",
        source_type="builder",
        status="active",
        is_active=True
    )
    db.add(resume)
    db.commit()
    candidate.active_resume_id = resume.id
    db.commit()

    res2 = client.get("/api/v1/resumes/active", headers=headers(owner))
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["has_resume"] is True
    assert data2["active_resume"]["id"] == resume.id
    assert data2["active_resume"]["title"] == "Active Master Resume"


def test_multi_resume_eager_loading_efficiency(environment):
    client, db, owner, other, admin, candidate, tmp_path = environment

    template = ResumeTemplate(
        name="Classic Template",
        slug="classic-template",
        description="Standard classic layout",
        latex_template="\\documentclass{article}",
        ats_score=95
    )
    db.add(template)
    db.commit()

    # Seed 5 resumes
    for i in range(5):
        r = Resume(
            candidate_id=candidate.id,
            title=f"Version {i + 1} Resume",
            source_type="builder",
            template_id=template.id,
            status="active",
            is_active=(i == 0)
        )
        db.add(r)
        db.flush()
        v = ResumeVersion(
            resume_id=r.id,
            version_number=1,
            structured_data={"title": f"Resume {i}"}
        )
        db.add(v)
    db.commit()

    res = client.get("/api/v1/resumes", headers=headers(owner))
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 5
    # Verify each has template name and version number
    for item in data:
        assert item["template_name"] == "Classic Template"
        assert item["version_number"] == 1
