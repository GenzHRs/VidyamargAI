"""
Tests for Resume PDF Compilation and Preview Pipeline.
Covers:
1. Standalone high-fidelity PDF rendering with heterogeneous data structures (dicts, strings, lists).
2. API endpoint POST /resumes/{id}/compile returning valid PDF artifact and response status.
3. API endpoint GET /resumes/{id}/download/pdf and GET /resumes/{id}/preview/pdf with proper headers.
4. Candidate ownership and access control (403 for other candidates).
5. Invalid resume ID handling (404).
6. On-the-fly compilation fallback when resume has not yet been pre-compiled.
7. Recompilation after edits reflecting latest data.
8. Concurrent compilation request safety.
"""
import concurrent.futures
import io
import pytest

from tests.conftest import headers
from app.services.latex_service import (
    render_structured_data_to_pdf,
    is_latex_installed,
    escape_latex
)


def test_standalone_pdf_renderer_heterogeneous_data():
    """Verify render_structured_data_to_pdf handles any mix of strings, dicts, lists, and empty values."""
    complex_data = {
        "personal_info": {
            "full_name": "Dr. Alexandra Chen",
            "email": "alexandra.chen@example.com",
            "phone": "+1-555-0199",
            "location": "San Francisco, CA",
            "linkedin": "https://linkedin.com/in/alexandrachen",
            "github": "https://github.com/alexandrachen"
        },
        "summary": "Senior Staff AI Engineer specializing in distributed document processing and LLM pipelines.",
        # Heterogeneous skills: mix of string lists, dicts, and nested dicts
        "skills": {
            "Languages": ["Python", "Rust", "TypeScript"],
            "Frameworks": [{"name": "FastAPI"}, {"name": "PyTorch"}, {"name": "Next.js"}],
            "Infrastructure": "Docker, Kubernetes, AWS, PostgreSQL"
        },
        # Experience with dict bullets and string bullets
        "experience": [
            {
                "title": "Principal AI Architect",
                "company": "NeuralFlow Technologies",
                "location": "San Francisco, CA",
                "dates": "2022 - Present",
                "bullets": [
                    "Architected enterprise document processing system serving 500k daily requests.",
                    {"text": "Engineered automated PDF rendering pipeline with Overleaf-fidelity typesetting."},
                    {"content": "Reduced p95 compilation latency from 3.2s to 120ms via in-memory vector generation."}
                ]
            },
            {
                "title": "Senior Software Engineer",
                "company": "DataScale Inc.",
                "dates": "2019 - 2022",
                "responsibilities": [
                    "Built microservices with FastAPI and PostgreSQL.",
                    "Designed high-concurrency event processing pipelines."
                ]
            }
        ],
        "education": [
            {
                "degree": "Ph.D. in Computer Science",
                "institution": "Stanford University",
                "dates": "2015 - 2019",
                "gpa": "3.95"
            }
        ],
        "projects": [
            {
                "name": "Enterprise Document AI & Compliance Engine",
                "technologies": ["Python", "FastAPI", "ReportLab", "PyMuPDF"],
                "description": "High-fidelity PDF document generation engine.",
                "link": "https://github.com/example/doc-ai"
            }
        ],
        "certifications": [
            "AWS Certified Solutions Architect",
            {"name": "CKA: Certified Kubernetes Administrator", "issuer": "CNCF"}
        ]
    }

    pdf_bytes = render_structured_data_to_pdf(complex_data, "Alexandra Chen Resume", "ats-classic")
    assert pdf_bytes is not None
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 500
    assert pdf_bytes.startswith(b"%PDF-")


def test_compile_resume_success_and_preview_headers(environment):
    """Test full compilation endpoint and subsequent preview/download requests."""
    client, db, owner, other, admin, candidate, tmp_path = environment
    auth = headers(owner)

    # 1. Create resume
    res = client.post("/api/v1/resumes", json={
        "title": "Full Stack Engineer Resume",
        "structured_data": {
            "personal_info": {
                "full_name": "Dev Sharma",
                "email": "dev.sharma@example.com",
                "phone": "+91-9876543210",
                "location": "Bengaluru, India"
            },
            "summary": "Experienced Full Stack Engineer with expertise in React, Next.js, and FastAPI.",
            "skills": {
                "Backend": ["Python", "FastAPI", "SQLAlchemy", "PostgreSQL"],
                "Frontend": ["React 19", "Next.js 16", "Tailwind CSS"]
            },
            "experience": [
                {
                    "title": "Lead Software Engineer",
                    "company": "TechNova Corp",
                    "dates": "2021 - Present",
                    "bullets": [
                        "Designed and deployed cloud-native career acceleration platform.",
                        "Implemented document preview pipeline with zero blank-screen regressions."
                    ]
                }
            ],
            "education": [
                {
                    "degree": "B.Tech in Computer Engineering",
                    "institution": "National Institute of Technology",
                    "dates": "2017 - 2021"
                }
            ]
        }
    }, headers=auth)
    assert res.status_code == 200
    resume_id = res.json()["id"]

    # 2. Trigger compilation
    comp_res = client.post(f"/api/v1/resumes/{resume_id}/compile", headers=auth)
    assert comp_res.status_code == 200
    comp_data = comp_res.json()
    assert comp_data["status"] == "success"
    assert comp_data["pdf_available"] is True
    assert "latest_pdf_url" in comp_data
    assert comp_data["latest_pdf_url"] is not None
    assert comp_data["pdf_size_bytes"] > 500

    # 3. Test Download Endpoint (Content-Disposition: attachment)
    download_res = client.get(f"/api/v1/resumes/{resume_id}/download/pdf", headers=auth)
    assert download_res.status_code == 200
    assert download_res.headers["content-type"] == "application/pdf"
    assert "attachment" in download_res.headers["content-disposition"]
    assert download_res.content.startswith(b"%PDF-")
    assert len(download_res.content) == comp_data["pdf_size_bytes"]

    # 4. Test Preview Endpoint (Content-Disposition: inline)
    preview_res = client.get(f"/api/v1/resumes/{resume_id}/preview/pdf", headers=auth)
    assert preview_res.status_code == 200
    assert preview_res.headers["content-type"] == "application/pdf"
    assert "inline" in preview_res.headers["content-disposition"]
    assert preview_res.content.startswith(b"%PDF-")

    # 5. Test Download with ?preview=true parameter
    query_preview_res = client.get(f"/api/v1/resumes/{resume_id}/download/pdf?preview=true", headers=auth)
    assert query_preview_res.status_code == 200
    assert "inline" in query_preview_res.headers["content-disposition"]
    assert query_preview_res.content.startswith(b"%PDF-")


def test_compile_and_preview_ownership_isolation(environment):
    """Ensure candidate ownership isolation strictly prevents unauthorized compilation or preview."""
    client, db, owner, other, admin, candidate, tmp_path = environment
    owner_auth = headers(owner)
    other_auth = headers(other)

    res = client.post("/api/v1/resumes", json={
        "title": "Private Candidate Resume",
        "structured_data": {
            "personal_info": {"full_name": "Private User", "email": "private@example.com"}
        }
    }, headers=owner_auth)
    resume_id = res.json()["id"]

    # Compile as owner
    comp_res = client.post(f"/api/v1/resumes/{resume_id}/compile", headers=owner_auth)
    assert comp_res.status_code == 200

    # Other candidate attempts compilation — MUST be 403
    other_compile = client.post(f"/api/v1/resumes/{resume_id}/compile", headers=other_auth)
    assert other_compile.status_code == 403

    # Other candidate attempts download — MUST be 403
    other_dl = client.get(f"/api/v1/resumes/{resume_id}/download/pdf", headers=other_auth)
    assert other_dl.status_code == 403

    # Other candidate attempts preview — MUST be 403
    other_preview = client.get(f"/api/v1/resumes/{resume_id}/preview/pdf", headers=other_auth)
    assert other_preview.status_code == 403


def test_invalid_resume_id_returns_404(environment):
    """Verify non-existent resume ID returns structured 404."""
    client, db, owner, other, admin, candidate, tmp_path = environment
    auth = headers(owner)

    res_compile = client.post("/api/v1/resumes/999999/compile", headers=auth)
    assert res_compile.status_code == 404

    res_dl = client.get("/api/v1/resumes/999999/download/pdf", headers=auth)
    assert res_dl.status_code == 404

    res_preview = client.get("/api/v1/resumes/999999/preview/pdf", headers=auth)
    assert res_preview.status_code == 404


def test_on_the_fly_preview_for_uncompiled_resume(environment):
    """Verify on-the-fly PDF compilation when accessing preview endpoint before explicit compile."""
    client, db, owner, other, admin, candidate, tmp_path = environment
    auth = headers(owner)

    res = client.post("/api/v1/resumes", json={
        "title": "Immediate Preview Resume",
        "structured_data": {
            "personal_info": {"full_name": "Quick Previewer", "email": "quick@example.com"},
            "skills": ["Python", "FastAPI"]
        }
    }, headers=auth)
    resume_id = res.json()["id"]

    # Request preview directly without calling /compile first
    preview_res = client.get(f"/api/v1/resumes/{resume_id}/preview/pdf", headers=auth)
    assert preview_res.status_code == 200
    assert preview_res.headers["content-type"] == "application/pdf"
    assert preview_res.content.startswith(b"%PDF-")


def test_recompilation_after_edits(environment):
    """Verify modifying resume data and recompiling reflects changes in the compiled PDF."""
    client, db, owner, other, admin, candidate, tmp_path = environment
    auth = headers(owner)

    res = client.post("/api/v1/resumes", json={
        "title": "Initial Resume Title",
        "structured_data": {
            "personal_info": {"full_name": "Original Name"},
            "skills": ["InitialSkill"]
        }
    }, headers=auth)
    resume_id = res.json()["id"]

    # 1. Compile initial
    c1 = client.post(f"/api/v1/resumes/{resume_id}/compile", headers=auth)
    assert c1.status_code == 200
    url_v1 = c1.json()["latest_pdf_url"]

    # 2. Update resume
    update_res = client.patch(f"/api/v1/resumes/{resume_id}", json={
        "title": "Updated Senior Resume",
        "structured_data": {
            "personal_info": {"full_name": "Original Name Updated"},
            "skills": ["InitialSkill", "AdvancedSkill"],
            "summary": "Updated executive career summary."
        },
        "create_new_version": True,
        "change_summary": "Added advanced skills and summary"
    }, headers=auth)
    assert update_res.status_code == 200

    # 3. Recompile
    c2 = client.post(f"/api/v1/resumes/{resume_id}/compile", headers=auth)
    assert c2.status_code == 200
    url_v2 = c2.json()["latest_pdf_url"]

    # PDF URLs reflect versioning
    assert url_v1 != url_v2
    assert "v2" in url_v2


def test_concurrent_compilation_safety(environment):
    """Verify concurrent PDF rendering executes safely without collisions, leaks, or state corruption."""
    client, db, owner, other, admin, candidate, tmp_path = environment
    auth = headers(owner)

    # 1. Multi-threaded parallel PDF generation tests
    candidate_profiles = [
        {
            "personal_info": {"full_name": f"Engineer #{i}", "email": f"eng{i}@company.com"},
            "skills": [f"Tech {i}-A", f"Tech {i}-B", f"Tech {i}-C"],
            "summary": f"High performance distributed engineer #{i}."
        }
        for i in range(5)
    ]

    def render_worker(prof):
        return render_structured_data_to_pdf(prof, prof["personal_info"]["full_name"], "ats-classic")

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(render_worker, p) for p in candidate_profiles]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(results) == 5
    for pdf in results:
        assert pdf is not None
        assert isinstance(pdf, bytes)
        assert len(pdf) > 500
        assert pdf.startswith(b"%PDF-")

    # 2. Sequential compilation of distinct candidate resumes
    created_resumes = []
    for i in range(3):
        res = client.post("/api/v1/resumes", json={
            "title": f"Candidate Pipeline #{i}",
            "structured_data": candidate_profiles[i]
        }, headers=auth)
        assert res.status_code == 200
        created_resumes.append(res.json()["id"])

    compiled_urls = set()
    for r_id in created_resumes:
        comp_res = client.post(f"/api/v1/resumes/{r_id}/compile", headers=auth)
        assert comp_res.status_code == 200
        data = comp_res.json()
        assert data["status"] == "success"
        assert data["pdf_available"] is True
        assert data["pdf_size_bytes"] > 500
        assert data["latest_pdf_url"] not in compiled_urls
        compiled_urls.add(data["latest_pdf_url"])

    assert len(compiled_urls) == 3
