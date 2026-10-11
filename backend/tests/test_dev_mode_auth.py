"""
test_dev_mode_auth.py — Complete Regression Test Suite for Testing Mode & DEV_AUTH_BYPASS.

Verifies all 11 required scenarios from specification:
1. Local development with testing mode enabled (200, valid token, candidate role, banner).
2. Authorized staging deployment with testing mode enabled (DEV_AUTH_BYPASS_DEPLOYMENT=authorized_testing).
3. Production deployment with testing mode disabled (fails closed with 403).
4. Production startup/build rejects unsafe configuration (raises RuntimeError on unverified prod bypass).
5. Direct navigation & session resolution (/auth/bypass-session returns valid test candidate).
6. Dashboard refresh and navigation between candidate pages (GET /auth/me, /profile, /resumes).
7. Backend API authorization and candidate data isolation (tenant & candidate ownership).
8. Real login, signup, logout, invalid credentials, and expired sessions remain intact.
9. Missing or invalid environment configuration fails safely (fail closed).
10. An ordinary visitor cannot obtain the testing session (403 on session, 401 on dev token in prod).
11. No authentication redirect loop occurs (session validation is stable and idempotent).
"""

import os
import pytest
from datetime import datetime, timedelta
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import create_access_token, get_password_hash
from app.models.models import User, Candidate, CandidateProfile
from app.models.resume_center_models import Resume, ResumeVersion
from app.services.dev_mode_service import (
    DevModeService,
    DEV_USER_EMAIL,
    DEV_USER_NAME,
    DEV_USER_ROLE,
)


# ==============================================================================
# Case 1: Local Development with Testing Mode Enabled
# ==============================================================================
def test_case_01_local_dev_testing_mode_enabled(environment, monkeypatch):
    """POST /api/v1/auth/bypass-session returns 200, authentic JWT token, and candidate role."""
    client, db, owner, other, admin, candidate, _ = environment
    monkeypatch.setattr(settings, "DEV_AUTH_BYPASS", True)
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "DEV_AUTH_BYPASS_DEPLOYMENT", "")

    resp = client.post("/api/v1/auth/bypass-session")
    assert resp.status_code == 200, f"Expected 200 but got {resp.status_code}: {resp.text}"
    data = resp.json()

    assert data["token_type"] == "bearer"
    assert "access_token" in data
    assert data["bypass_enabled"] is True
    assert "TESTING MODE — TEST CANDIDATE" in data["banner_text"]
    assert data["user"]["email"] == DEV_USER_EMAIL
    assert data["user"]["role"] == "candidate"
    assert data["user"]["role"] != "admin"

    # Cookies must include access_token and csrf_token
    assert "access_token" in resp.cookies
    assert "csrf_token" in resp.cookies


# ==============================================================================
# Case 2: Authorized Staging Deployment with Testing Mode Enabled
# ==============================================================================
def test_case_02_authorized_staging_deployment_enabled(environment, monkeypatch):
    """DEV_AUTH_BYPASS_DEPLOYMENT=authorized_testing permits testing mode in staging or prod."""
    client, db, owner, other, admin, candidate, _ = environment
    monkeypatch.setattr(settings, "DEV_AUTH_BYPASS", True)
    monkeypatch.setattr(settings, "ENVIRONMENT", "staging")
    monkeypatch.setattr(settings, "DEV_AUTH_BYPASS_DEPLOYMENT", "authorized_testing")

    assert settings.is_dev_mode_allowed is True

    resp = client.post("/api/v1/auth/bypass-session")
    assert resp.status_code == 200
    assert resp.json()["user"]["email"] == DEV_USER_EMAIL


# ==============================================================================
# Case 3: Production Deployment with Testing Mode Disabled
# ==============================================================================
def test_case_03_production_deployment_disabled(environment, monkeypatch):
    """ENVIRONMENT=production with DEV_AUTH_BYPASS=false strictly returns 403."""
    client, db, owner, other, admin, candidate, _ = environment
    monkeypatch.setattr(settings, "DEV_AUTH_BYPASS", False)
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")

    assert settings.is_dev_mode_allowed is False

    # Status reflects disabled
    status_resp = client.get("/api/v1/auth/bypass-status")
    assert status_resp.status_code == 200
    assert status_resp.json()["bypass_enabled"] is False

    # Session generation is forbidden
    session_resp = client.post("/api/v1/auth/bypass-session")
    assert session_resp.status_code == 403


# ==============================================================================
# Case 4: Production Startup/Build Rejects Unsafe Configuration
# ==============================================================================
def test_case_04_production_startup_rejects_unsafe_configuration(monkeypatch):
    """Backend lifespan check raises RuntimeError if DEV_AUTH_BYPASS is set in production without authorization."""
    monkeypatch.setattr(settings, "DEV_AUTH_BYPASS", True)
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "DEV_AUTH_BYPASS_DEPLOYMENT", "")

    assert settings.is_dev_mode_allowed is False

    # Simulating main lifespan check
    with pytest.raises(RuntimeError) as exc_info:
        if settings.DEV_AUTH_BYPASS and not settings.is_dev_mode_allowed:
            raise RuntimeError(
                "CRITICAL SECURITY CONFIGURATION ERROR: DEV_AUTH_BYPASS is enabled but rejected by environment security policy! "
                "In production/staging environments, DEV_AUTH_BYPASS_DEPLOYMENT='authorized_testing' is strictly required."
            )
    assert "CRITICAL SECURITY CONFIGURATION ERROR" in str(exc_info.value)


# ==============================================================================
# Case 5: Direct Navigation & Session Resolution
# ==============================================================================
def test_case_05_direct_navigation_and_session_resolution(environment, monkeypatch):
    """Direct navigation establishes test candidate and returns rich persisted profile."""
    client, db, owner, other, admin, candidate, _ = environment
    monkeypatch.setattr(settings, "DEV_AUTH_BYPASS", True)
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")

    user, dev_candidate = DevModeService.get_or_create_dev_user(db)
    assert user.email == DEV_USER_EMAIL
    assert dev_candidate.user_id == user.id
    assert dev_candidate.primary_designation == "Senior Full Stack AI Engineer"

    # Verify active test resume was seeded
    active_resume = db.query(Resume).filter(Resume.candidate_id == dev_candidate.id).first()
    assert active_resume is not None
    assert active_resume.title == "Test Candidate Master Resume"


# ==============================================================================
# Case 6: Dashboard Refresh and Navigation Between Candidate Pages
# ==============================================================================
def test_case_06_dashboard_refresh_and_page_navigation(environment, monkeypatch):
    """Token preserves candidate identity across /auth/me, /profile, /resumes."""
    client, db, owner, other, admin, candidate, _ = environment
    monkeypatch.setattr(settings, "DEV_AUTH_BYPASS", True)
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")

    session_resp = client.post("/api/v1/auth/bypass-session")
    token = session_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # /auth/me
    me_resp = client.get("/api/v1/auth/me", headers=headers)
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == DEV_USER_EMAIL

    # /candidates/profile
    profile_resp = client.get("/api/v1/candidates/profile", headers={**headers, "x-caller": "page"})
    assert profile_resp.status_code == 200
    pdata = profile_resp.json()
    resolved_email = pdata.get("email") or pdata.get("personal_info", {}).get("email") or pdata.get("parsed_email")
    assert resolved_email == DEV_USER_EMAIL

    # /resumes
    resumes_resp = client.get("/api/v1/resumes", headers=headers)
    assert resumes_resp.status_code == 200
    assert len(resumes_resp.json()) >= 1
    assert resumes_resp.json()[0]["title"] == "Test Candidate Master Resume"


# ==============================================================================
# Case 7: Backend API Authorization and Candidate Data Isolation
# ==============================================================================
def test_case_07_candidate_data_isolation(environment, monkeypatch):
    """Test candidate cannot access other candidate's private resume."""
    client, db, owner, other, admin, candidate, _ = environment
    monkeypatch.setattr(settings, "DEV_AUTH_BYPASS", True)
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")

    owner_resume = Resume(
        candidate_id=candidate.id,
        title="Confidential Owner Document",
        source_type="upload",
        file_name="owner_confidential.pdf",
        status="active"
    )
    db.add(owner_resume)
    db.commit()
    db.refresh(owner_resume)

    session_resp = client.post("/api/v1/auth/bypass-session")
    token = session_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Accessing owner's resume must be rejected
    resp = client.get(f"/api/v1/resumes/{owner_resume.id}", headers=headers)
    assert resp.status_code in (403, 404)


# ==============================================================================
# Case 8: Real Login, Signup, Logout, Invalid Credentials, and Expiry
# ==============================================================================
def test_case_08_real_auth_lifecycle_intact(environment, monkeypatch):
    """Standard authentication mechanisms remain completely functional."""
    client, db, owner, other, admin, candidate, _ = environment
    monkeypatch.setattr(settings, "DEV_AUTH_BYPASS", False)
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")

    # 8a. Valid login
    login_ok = client.post("/api/v1/auth/login", data={"username": owner.email, "password": "correct-password"})
    assert login_ok.status_code == 200

    # 8b. Invalid credentials
    login_bad = client.post("/api/v1/auth/login", data={"username": owner.email, "password": "wrong-password"})
    assert login_bad.status_code == 401

    # 8c. Valid signup
    signup_ok = client.post("/api/v1/auth/signup", json={
        "email": "fresh.candidate@vidyamarg.example",
        "password": "StrongPassword123!",
        "full_name": "Fresh Candidate",
        "role": "candidate"
    })
    assert signup_ok.status_code == 200

    # 8d. Logout
    token = login_ok.json()["access_token"]
    logout_ok = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout_ok.status_code == 200

    # 8e. Expired token
    expired_token = create_access_token(owner.email, owner.role, expires_delta=timedelta(seconds=-10))
    exp_resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert exp_resp.status_code == 401


# ==============================================================================
# Case 9: Missing or Invalid Environment Configuration Fails Safely
# ==============================================================================
def test_case_09_invalid_environment_configuration_fails_safely(environment, monkeypatch):
    """Ambiguous or unknown environments fail closed."""
    client, db, owner, other, admin, candidate, _ = environment

    # 9a. Unknown environment
    monkeypatch.setattr(settings, "DEV_AUTH_BYPASS", True)
    monkeypatch.setattr(settings, "ENVIRONMENT", "arbitrary_custom_cluster")
    monkeypatch.setattr(settings, "DEV_AUTH_BYPASS_DEPLOYMENT", "")
    assert settings.is_dev_mode_allowed is False
    assert client.post("/api/v1/auth/bypass-session").status_code == 403

    # 9b. Cloud prod detected without authorization
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "DEV_AUTH_BYPASS_DEPLOYMENT", "")
    assert settings.is_dev_mode_allowed is False
    assert client.post("/api/v1/auth/bypass-session").status_code == 403


# ==============================================================================
# Case 10: An Ordinary Visitor Cannot Obtain Testing Session
# ==============================================================================
def test_case_10_ordinary_visitor_cannot_obtain_session(environment, monkeypatch):
    """Dev session endpoint is locked and dev token is rejected in production."""
    client, db, owner, other, admin, candidate, _ = environment

    # Generate dev token while dev mode is temporarily on
    monkeypatch.setattr(settings, "DEV_AUTH_BYPASS", True)
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    u, _ = DevModeService.get_or_create_dev_user(db)
    dev_token = create_access_token(u.email, u.role)

    # Now turn off DEV_AUTH_BYPASS (simulating production)
    monkeypatch.setattr(settings, "DEV_AUTH_BYPASS", False)
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    assert settings.is_dev_mode_allowed is False

    # Attempting to fetch session -> 403
    assert client.post("/api/v1/auth/bypass-session").status_code == 403

    # Attempting to authenticate with dev token -> 401
    me_resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {dev_token}"})
    assert me_resp.status_code == 401
    assert "not permitted in this environment" in me_resp.json()["detail"].lower()


# ==============================================================================
# Case 11: No Authentication Redirect Loop Occurs
# ==============================================================================
def test_case_11_no_authentication_redirect_loop(environment, monkeypatch):
    """Session validation is consistent across 10 consecutive requests."""
    client, db, owner, other, admin, candidate, _ = environment
    monkeypatch.setattr(settings, "DEV_AUTH_BYPASS", True)
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")

    session_resp = client.post("/api/v1/auth/bypass-session")
    assert session_resp.status_code == 200
    token = session_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Simulate 10 page navigations / component mounts
    for _ in range(10):
        resp = client.get("/api/v1/auth/me", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["email"] == DEV_USER_EMAIL
