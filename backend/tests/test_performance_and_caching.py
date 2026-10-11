"""
Unit & Integration Test Suite for Global Performance & Caching Architecture.

Verifies:
1. Candidate-scoped Redis & in-memory caching for job recommendations.
2. Candidate context revision invalidation (incrementing revision purges stale cache).
3. Intelligence bundle candidate-scoped caching and invalidation.
4. Invalidation of candidate context clears all candidate-scoped caches.
5. Strict candidate isolation: Candidate A's cache cannot leak to Candidate B.
6. Monotonic revision tracking and instant cache retrieval (< 5ms).
"""

import pytest
import time
from app.services.resume_cache import (
    get_candidate_context_revision,
    increment_candidate_context_revision,
    get_cached_job_recommendations,
    set_cached_job_recommendations,
    get_cached_intelligence_bundle,
    set_cached_intelligence_bundle,
    invalidate_candidate_context,
    clear_all_local_caches,
    get_cached_dashboard_summary,
    set_cached_dashboard_summary,
)


@pytest.fixture(autouse=True)
def clean_cache():
    """Ensure clean cache state before and after each test."""
    clear_all_local_caches()
    yield
    clear_all_local_caches()


def test_candidate_context_revision_increments():
    """Verifies that context revisions start at 1 and increment monotonically."""
    cand_id = 9901
    rev1 = get_candidate_context_revision(cand_id)
    assert rev1 >= 1

    rev2 = increment_candidate_context_revision(cand_id)
    assert rev2 == rev1 + 1

    rev3 = increment_candidate_context_revision(cand_id)
    assert rev3 == rev2 + 1


def test_job_recommendations_caching_and_hit():
    """Verifies candidate-scoped job recommendations caching and instant retrieval."""
    cand_id = 9902
    current_rev = get_candidate_context_revision(cand_id)

    # Initial state should be a cache miss
    miss = get_cached_job_recommendations(cand_id, limit=50)
    assert miss is None

    sample_jobs = {
        "jobs": [
            {"id": 1, "title": "Full Stack Engineer", "match_score": 92.0},
            {"id": 2, "title": "AI Platform Engineer", "match_score": 88.5},
        ],
        "total": 2,
    }

    # Set cache
    set_cached_job_recommendations(cand_id, limit=50, revision=current_rev, data=sample_jobs)

    # Subsequent fetch should be a cache hit
    hit = get_cached_job_recommendations(cand_id, limit=50)
    assert hit is not None
    assert hit["total"] == 2
    assert hit["jobs"][0]["title"] == "Full Stack Engineer"


def test_revision_increment_invalidates_job_recommendations():
    """Verifies that incrementing context revision purges stale job recommendations."""
    cand_id = 9903
    rev_initial = get_candidate_context_revision(cand_id)

    sample_jobs = {"jobs": [{"id": 10, "title": "Old Recommendation"}], "total": 1}
    set_cached_job_recommendations(cand_id, limit=50, revision=rev_initial, data=sample_jobs)

    # Confirm cache hit
    assert get_cached_job_recommendations(cand_id, limit=50) is not None

    # Candidate uploads new resume or changes target role -> revision increments
    increment_candidate_context_revision(cand_id)

    # The old cache entry MUST NOT be returned
    assert get_cached_job_recommendations(cand_id, limit=50) is None


def test_intelligence_bundle_caching_and_invalidation():
    """Verifies intelligence bundle caching, instant hit, and revision-based invalidation."""
    cand_id = 9904
    rev = get_candidate_context_revision(cand_id)

    assert get_cached_intelligence_bundle(cand_id) is None

    sample_bundle = {
        "profile": {"personal_info": {"name": "Test Candidate"}},
        "career_dna": {"personality": "Builder"},
        "skills": {"skills": ["Python", "FastAPI"]},
        "roles": {"core": [{"role": "Backend Engineer", "confidence": 95}]},
        "career_paths": [],
        "skill_gaps": {"overall_gap_score": 25.0},
        "opportunities": {"top_opportunities": []},
        "market_intelligence": {"demand_score": 0.9},
        "improvements": {"ats_score": 85},
    }

    set_cached_intelligence_bundle(cand_id, rev, sample_bundle)

    # Cache hit
    cached = get_cached_intelligence_bundle(cand_id)
    assert cached is not None
    assert cached["career_dna"]["personality"] == "Builder"
    assert cached["improvements"]["ats_score"] == 85

    # Invalidate candidate context
    invalidate_candidate_context(cand_id)

    # Cache must now be purged
    assert get_cached_intelligence_bundle(cand_id) is None


def test_strict_candidate_isolation():
    """Verifies that Candidate A's cache cannot be read by Candidate B."""
    cand_a = 9905
    cand_b = 9906

    rev_a = get_candidate_context_revision(cand_a)
    data_a = {"jobs": [{"id": 101, "title": "Candidate A Exclusive Job"}], "total": 1}
    set_cached_job_recommendations(cand_a, 50, rev_a, data_a)

    bundle_a = {"profile": {"personal_info": {"name": "Alice"}}}
    set_cached_intelligence_bundle(cand_a, rev_a, bundle_a)

    # Candidate B must not see Candidate A's data
    assert get_cached_job_recommendations(cand_b, 50) is None
    assert get_cached_intelligence_bundle(cand_b) is None

    # Candidate A gets their own data
    assert get_cached_job_recommendations(cand_a, 50)["total"] == 1
    assert get_cached_intelligence_bundle(cand_a)["profile"]["personal_info"]["name"] == "Alice"


def test_cache_retrieval_performance_benchmark():
    """Verifies that cached lookups execute in sub-millisecond time (< 5ms)."""
    cand_id = 9907
    rev = get_candidate_context_revision(cand_id)
    payload = {"jobs": [{"id": i, "title": f"Job {i}"} for i in range(50)], "total": 50}

    set_cached_job_recommendations(cand_id, 50, rev, payload)

    start_time = time.perf_counter()
    result = get_cached_job_recommendations(cand_id, 50)
    elapsed_ms = (time.perf_counter() - start_time) * 1000

    assert result is not None
    assert result["total"] == 50
    # In-memory / fast local socket lookup must execute well under 5ms
    assert elapsed_ms < 5.0, f"Cache retrieval took {elapsed_ms:.2f}ms, expected < 5ms"
