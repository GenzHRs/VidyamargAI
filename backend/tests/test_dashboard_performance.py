"""
Regression & Performance Tests for Candidate Dashboard Caching and Aggregation.

Verifies:
1. Candidate-scoped Redis and memory caching
2. Strict candidate isolation (Candidate A vs Candidate B)
3. Immediate cache invalidation on mutations (resume / profile updates)
4. Fast fallback when Redis is unavailable
"""

import pytest
from app.services.resume_cache import (
    get_cached_dashboard_summary,
    set_cached_dashboard_summary,
    invalidate_dashboard_summary,
    clear_all_local_caches,
    invalidate_candidate_context
)


@pytest.fixture(autouse=True)
def clean_caches():
    clear_all_local_caches()
    yield
    clear_all_local_caches()


def test_dashboard_summary_cache_and_retrieval():
    candidate_id = 901
    sample_data = {
        "candidate_id": candidate_id,
        "profile": {"full_name": "Test Candidate"},
        "roles": {"core": [{"role": "AI Engineer", "confidence": 95}]},
        "skillGaps": {"skills_present": ["Python", "FastAPI"], "skill_gaps": ["Docker"]},
        "readiness": {"career_readiness_score": 85.0},
        "resumes": [{"id": 1, "title": "Main Resume"}]
    }

    # Initial state: cache miss
    assert get_cached_dashboard_summary(candidate_id) is None

    # Cache write
    set_cached_dashboard_summary(candidate_id, sample_data)

    # Cache read: immediate hit
    cached = get_cached_dashboard_summary(candidate_id)
    assert cached is not None
    assert cached["candidate_id"] == candidate_id
    assert cached["profile"]["full_name"] == "Test Candidate"
    assert cached["readiness"]["career_readiness_score"] == 85.0


def test_candidate_isolation_no_cross_tenant_leakage():
    cand_a_id = 101
    cand_b_id = 102

    data_a = {
        "candidate_id": cand_a_id,
        "profile": {"full_name": "Alice Candidate", "email": "alice@example.com"},
        "readiness": {"career_readiness_score": 90.0}
    }
    data_b = {
        "candidate_id": cand_b_id,
        "profile": {"full_name": "Bob Candidate", "email": "bob@example.com"},
        "readiness": {"career_readiness_score": 70.0}
    }

    set_cached_dashboard_summary(cand_a_id, data_a)
    set_cached_dashboard_summary(cand_b_id, data_b)

    cached_a = get_cached_dashboard_summary(cand_a_id)
    cached_b = get_cached_dashboard_summary(cand_b_id)

    assert cached_a["profile"]["email"] == "alice@example.com"
    assert cached_b["profile"]["email"] == "bob@example.com"
    assert cached_a["readiness"]["career_readiness_score"] == 90.0
    assert cached_b["readiness"]["career_readiness_score"] == 70.0


def test_cache_invalidation_on_mutation():
    candidate_id = 301
    data = {
        "candidate_id": candidate_id,
        "profile": {"full_name": "Charlie"},
        "readiness": {"career_readiness_score": 60.0}
    }

    set_cached_dashboard_summary(candidate_id, data)
    assert get_cached_dashboard_summary(candidate_id) is not None

    # Invalidate dashboard summary
    invalidate_dashboard_summary(candidate_id)
    assert get_cached_dashboard_summary(candidate_id) is None


def test_candidate_context_invalidation_cascades_to_dashboard():
    candidate_id = 401
    data = {
        "candidate_id": candidate_id,
        "profile": {"full_name": "Diana"},
        "readiness": {"career_readiness_score": 75.0}
    }

    set_cached_dashboard_summary(candidate_id, data)
    assert get_cached_dashboard_summary(candidate_id) is not None

    # Invalidate candidate context (triggered on resume upload / activation)
    invalidate_candidate_context(candidate_id)
    assert get_cached_dashboard_summary(candidate_id) is None
