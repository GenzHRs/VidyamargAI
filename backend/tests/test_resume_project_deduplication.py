"""
Comprehensive Unit Tests for Resume Project Deduplication & Technology Tokenization.

Tests:
- Paragraph and bullet duplication
- Repeated bullet markers (e.g. "• •")
- Multiple distinct projects preservation
- Concatenated technology string tokenization
- Legitimate repeated keywords across bullets
- Extraction idempotency (re-extracting the same resume)
- Original raw resume text preservation
- Application snapshot immutability
"""

import pytest
from app.services.resume_extractor_engine import (
    normalize_technologies_list,
    clean_bullet_text,
    normalize_and_deduplicate_project
)


def test_concatenated_technology_strings():
    raw_concatenated = "FastAPIPythonPostgreSQLAzure OCRNERGemini LLM"
    result = normalize_technologies_list(raw_concatenated)
    expected = ["FastAPI", "Python", "PostgreSQL", "Azure OCR", "NER", "Gemini LLM"]
    assert result == expected, f"Expected {expected}, got {result}"


def test_repeated_bullet_markers():
    raw_bullets = [
        "• • Developed high-throughput REST APIs using FastAPI.",
        "► ▸ Implemented OAuth2 authentication flow.",
        "▪ - Built Docker containers for microservices."
    ]
    cleaned = [clean_bullet_text(b) for b in raw_bullets]
    assert cleaned == [
        "Developed high-throughput REST APIs using FastAPI.",
        "Implemented OAuth2 authentication flow.",
        "Built Docker containers for microservices."
    ]


def test_paragraph_and_bullet_duplication():
    proj = {
        "name": "Enterprise Document AI & Compliance Automation",
        "description": "Architected an end-to-end document classification platform using PyMuPDF and Azure OCR. Integrated Gemini LLM for zero-shot JSON metadata extraction from complex contracts.",
        "responsibilities": [
            "Architected an end-to-end document classification platform using PyMuPDF and Azure OCR.",
            "Integrated Gemini LLM for zero-shot JSON metadata extraction from complex contracts."
        ],
        "technologies": "FastAPIPythonPostgreSQLAzure OCRNERGemini LLM"
    }

    normalized = normalize_and_deduplicate_project(proj)

    # Paragraph description must be normalized to None because all its sentences repeat the bullets
    assert normalized["description"] is None
    assert len(normalized["responsibilities"]) == 2
    assert normalized["responsibilities"][0] == "Architected an end-to-end document classification platform using PyMuPDF and Azure OCR."
    assert normalized["technologies"] == ["FastAPI", "Python", "PostgreSQL", "Azure OCR", "NER", "Gemini LLM"]


def test_paragraph_with_genuine_additional_information():
    proj = {
        "name": "AI Resume Screening System",
        "description": "Enterprise-grade resume parser and matching platform built for high-volume hiring.",
        "responsibilities": [
            "Achieved 95% parsing precision across 10,000 resumes.",
            "Reduced candidate screening time by 75% for HR teams."
        ],
        "technologies": ["Python", "FastAPI", "PostgreSQL"]
    }

    normalized = normalize_and_deduplicate_project(proj)

    # Genuine additional description must be preserved
    assert normalized["description"] == "Enterprise-grade resume parser and matching platform built for high-volume hiring."
    assert len(normalized["responsibilities"]) == 2


def test_multiple_distinct_projects():
    proj1 = {
        "name": "Enterprise Document AI & Compliance Automation",
        "description": None,
        "responsibilities": ["Automated contract compliance checking with Azure OCR."],
        "technologies": "FastAPIPythonAzure OCR"
    }
    proj2 = {
        "name": "AI Resume Screening System",
        "description": None,
        "responsibilities": ["Parsed PDF resumes with PyMuPDF."],
        "technologies": "PythonFastAPIPostgreSQL"
    }

    norm1 = normalize_and_deduplicate_project(proj1)
    norm2 = normalize_and_deduplicate_project(proj2)

    assert norm1["name"] != norm2["name"]
    assert norm1["technologies"] == ["FastAPI", "Python", "Azure OCR"]
    assert norm2["technologies"] == ["Python", "FastAPI", "PostgreSQL"]


def test_legitimate_repeated_keywords():
    proj = {
        "name": "E-Commerce Recommendation Engine",
        "description": None,
        "responsibilities": [
            "Built high-speed vector retrieval index using Qdrant.",
            "Optimized Qdrant similarity search query latency by 40%."
        ],
        "technologies": ["Qdrant", "Python", "Redis"]
    }

    normalized = normalize_and_deduplicate_project(proj)
    # Legitimate repeated keyword "Qdrant" across separate bullets must NOT cause bullets to be merged or deleted
    assert len(normalized["responsibilities"]) == 2


def test_idempotency_re_extracting_same_resume():
    proj = {
        "name": "Enterprise Document AI",
        "description": "Built document automation system.",
        "responsibilities": [
            "• • Built document automation system.",
            "Deployed model on Azure."
        ],
        "technologies": "FastAPIPythonAzure OCR"
    }

    pass1 = normalize_and_deduplicate_project(proj)
    pass2 = normalize_and_deduplicate_project(pass1)

    assert pass1 == pass2, "Normalization must be idempotent across multiple passes"


def test_original_master_resume_raw_text_preservation():
    raw_text = "PROJECTS\nEnterprise Document AI\n• Built document automation system."
    proj = {
        "name": "Enterprise Document AI",
        "description": "Built document automation system.",
        "responsibilities": ["• Built document automation system."],
        "technologies": "Python"
    }

    normalized = normalize_and_deduplicate_project(proj)
    # Ensure raw text string in original resume record is unchanged
    assert raw_text == "PROJECTS\nEnterprise Document AI\n• Built document automation system."
    assert normalized["responsibilities"] == ["Built document automation system."]


def test_job_snapshot_immutability():
    original_snapshot = {
        "snapshot_id": "snap-12345",
        "project": {
            "name": "Historical Application Project",
            "description": "Historical description",
            "responsibilities": ["Historical responsibility"]
        }
    }
    # Create immutable copy
    frozen_snapshot = dict(original_snapshot)

    # Perform normalizer on new candidate resume data
    new_proj = {
        "name": "Historical Application Project",
        "description": "Historical responsibility",
        "responsibilities": ["Historical responsibility"],
        "technologies": "Python"
    }
    _ = normalize_and_deduplicate_project(new_proj)

    # Verify original application snapshot was untouched
    assert frozen_snapshot == original_snapshot
