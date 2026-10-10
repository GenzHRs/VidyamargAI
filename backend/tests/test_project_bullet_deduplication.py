"""
Regression Test Suite for Project Bullet Deduplication in LaTeX and PDF Renderers.

Verifies:
- AI Super Assistant with 5 unique bullets repeated across responsibilities, features, bullets
- Smart Multi-Restaurant Delivery Optimization System
- LaTeX output contains each unique bullet string EXACTLY ONCE
- ReportLab vector PDF output contains each unique bullet string EXACTLY ONCE
- PDF text extraction via PyMuPDF confirms single-occurrence of each bullet
- Distinct additional overview description text remains intact
- Multiple projects remain completely separate
- Repeated extraction/canonicalization is strictly idempotent
- Both renderers produce consistent project content
"""

import pytest
import io
import fitz  # PyMuPDF
from app.services.project_normalizer import (
    canonicalize_project,
    canonicalize_projects_list,
    clean_bullet_text,
    normalize_technologies_list
)
from app.services.latex_service import (
    render_resume_to_latex,
    render_structured_data_to_pdf,
    escape_latex
)
from app.api.routers.resume_center import convert_to_template_payload


AI_SUPER_ASSISTANT_BULLETS = [
    "Built an AI-powered automation assistant for food ordering, ride booking, and music playback.",
    "Implemented intent detection using NVIDIA API and LLM + RAG.",
    "Developed a context-aware recommendation system.",
    "Added predictive user behavior modeling.",
    "Implemented Android automation using Kotlin AccessibilityService."
]

DELIVERY_OPTIMIZATION_BULLETS = [
    "Engineered dynamic routing algorithm reducing average delivery latency by 28%.",
    "Implemented real-time dispatch queueing with Redis Pub/Sub and Celery workers.",
    "Developed order batching system aggregating multi-restaurant pickups within 1.5km radius."
]


def create_ai_super_assistant_raw_project():
    return {
        "name": "AI Super Assistant",
        "title": "AI Super Assistant",
        "description": "Built an AI-powered automation assistant for food ordering, ride booking, and music playback. Implemented intent detection using NVIDIA API and LLM + RAG.",
        "technologies": ["Kotlin", "Android", "AccessibilityService", "NVIDIA API", "Python", "RAG"],
        "responsibilities": list(AI_SUPER_ASSISTANT_BULLETS),
        "bullets": list(AI_SUPER_ASSISTANT_BULLETS),
        "features": list(AI_SUPER_ASSISTANT_BULLETS)
    }


def create_delivery_optimization_raw_project():
    return {
        "name": "Smart Multi-Restaurant Delivery Optimization System",
        "title": "Smart Multi-Restaurant Delivery Optimization System",
        "description": "Multi-restaurant delivery routing platform.",
        "technologies": ["Python", "FastAPI", "Redis", "PostgreSQL", "Celery"],
        "responsibilities": list(DELIVERY_OPTIMIZATION_BULLETS),
        "bullets": list(DELIVERY_OPTIMIZATION_BULLETS),
        "features": list(DELIVERY_OPTIMIZATION_BULLETS)
    }


def test_canonicalize_ai_super_assistant_bullets_count():
    raw_p = create_ai_super_assistant_raw_project()
    canon_p = canonicalize_project(raw_p)

    assert len(canon_p["bullets"]) == 5, f"Expected 5 unique bullets, got {len(canon_p['bullets'])}"
    assert canon_p["features"] == []
    for expected_bullet in AI_SUPER_ASSISTANT_BULLETS:
        assert expected_bullet in canon_p["bullets"]


def test_convert_to_template_payload_does_not_double_bullets():
    extracted = {
        "personal_info": {"full_name": "Test Candidate"},
        "projects": [
            create_ai_super_assistant_raw_project(),
            create_delivery_optimization_raw_project()
        ]
    }
    payload = convert_to_template_payload(extracted)
    projects = payload.get("projects", [])
    assert len(projects) == 2

    ai_proj = projects[0]
    assert len(ai_proj["bullets"]) == 5, f"Expected 5 bullets, got {len(ai_proj['bullets'])}"
    assert ai_proj["features"] == []

    deliv_proj = projects[1]
    assert len(deliv_proj["bullets"]) == 3, f"Expected 3 bullets, got {len(deliv_proj['bullets'])}"


def test_latex_renderer_contains_each_unique_bullet_exactly_once():
    data = {
        "personal_info": {
            "name": "Arjun Sharma",
            "email": "arjun@example.com",
            "phone": "+91 9876543210"
        },
        "summary": "Full Stack & AI Engineer.",
        "skills": {"Languages": ["Python", "Kotlin"], "Frameworks": ["FastAPI", "PyTorch"]},
        "projects": [
            create_ai_super_assistant_raw_project(),
            create_delivery_optimization_raw_project()
        ]
    }

    latex_code = render_resume_to_latex(data)

    # Check AI Super Assistant bullets in LaTeX output (with LaTeX escaping)
    for bullet in AI_SUPER_ASSISTANT_BULLETS:
        escaped_b = escape_latex(bullet)
        count = latex_code.count(escaped_b)
        assert count == 1, f"Bullet occurred {count} times in LaTeX (expected 1): '{escaped_b}'"

    # Check Delivery Optimization bullets in LaTeX output (with LaTeX escaping)
    for bullet in DELIVERY_OPTIMIZATION_BULLETS:
        escaped_b = escape_latex(bullet)
        count = latex_code.count(escaped_b)
        assert count == 1, f"Bullet occurred {count} times in LaTeX (expected 1): '{escaped_b}'"


def test_reportlab_pdf_output_contains_each_unique_bullet_exactly_once():
    data = {
        "personal_info": {
            "name": "Arjun Sharma",
            "email": "arjun@example.com",
            "phone": "+91 9876543210"
        },
        "summary": "Full Stack & AI Engineer.",
        "skills": {"Languages": ["Python", "Kotlin"]},
        "projects": [
            create_ai_super_assistant_raw_project(),
            create_delivery_optimization_raw_project()
        ]
    }

    pdf_bytes = render_structured_data_to_pdf(data, "Arjun Sharma Resume", template_slug="classic-ats")
    assert pdf_bytes.startswith(b"%PDF")

    # Extract text using PyMuPDF
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    extracted_text = ""
    for page in doc:
        extracted_text += page.get_text() + "\n"
    doc.close()

    # Verify AI Super Assistant bullets
    for bullet in AI_SUPER_ASSISTANT_BULLETS:
        count = extracted_text.count(bullet)
        assert count == 1, f"Bullet occurred {count} times in ReportLab PDF extracted text (expected 1): '{bullet}'"

    # Verify Delivery Optimization bullets
    for bullet in DELIVERY_OPTIMIZATION_BULLETS:
        count = extracted_text.count(bullet)
        assert count == 1, f"Bullet occurred {count} times in ReportLab PDF extracted text (expected 1): '{bullet}'"


def test_distinct_additional_description_text_remains_intact():
    proj_with_distinct_desc = {
        "name": "AI Super Assistant",
        "description": "Architected as a flagship distributed Android assistant communicating with an on-device Kotlin AccessibilityService engine.",
        "technologies": ["Kotlin", "Android", "Python"],
        "responsibilities": list(AI_SUPER_ASSISTANT_BULLETS),
        "bullets": list(AI_SUPER_ASSISTANT_BULLETS),
        "features": list(AI_SUPER_ASSISTANT_BULLETS)
    }

    canon = canonicalize_project(proj_with_distinct_desc)

    # Distinct description must be preserved
    assert canon["description"] == proj_with_distinct_desc["description"]
    assert len(canon["bullets"]) == 5

    # When rendered to ReportLab PDF, description is present
    data = {
        "personal_info": {"name": "Test User"},
        "projects": [canon]
    }
    pdf_bytes = render_structured_data_to_pdf(data, "Test", template_slug="classic-ats")
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    text = "".join(page.get_text() for page in doc)
    doc.close()

    assert proj_with_distinct_desc["description"] in text
    for b in AI_SUPER_ASSISTANT_BULLETS:
        assert text.count(b) == 1


def test_multiple_projects_remain_separate_and_unmerged():
    p1 = create_ai_super_assistant_raw_project()
    p2 = create_delivery_optimization_raw_project()

    canon_list = canonicalize_projects_list([p1, p2])
    assert len(canon_list) == 2
    assert canon_list[0]["name"] == "AI Super Assistant"
    assert canon_list[1]["name"] == "Smart Multi-Restaurant Delivery Optimization System"
    assert len(canon_list[0]["bullets"]) == 5
    assert len(canon_list[1]["bullets"]) == 3


def test_repeated_canonicalization_is_strictly_idempotent():
    p = create_ai_super_assistant_raw_project()
    pass1 = canonicalize_project(p)
    pass2 = canonicalize_project(pass1)
    pass3 = canonicalize_project(pass2)

    assert pass1 == pass2
    assert pass2 == pass3
    assert len(pass3["bullets"]) == 5
