import pytest
from datetime import datetime, timedelta
import jwt
from app.core.config import settings
from app.core.security import create_access_token, get_password_hash, hash_token
from app.models.models import User, Candidate, UserRefreshToken, OTP

def test_login_sets_cookies_and_tokens(environment):
    client, db, owner, other, admin, candidate, _ = environment
    response = client.post(
        "/api/v1/auth/login",
        data={"username": owner.email, "password": "correct-password"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == owner.email
    assert data["role"] == "candidate"
    assert "access_token" in data
    assert "refresh_token" in data
    assert "csrf_token" in data

    # Check cookies
    cookies = response.cookies
    assert "access_token" in cookies
    assert "refresh_token" in cookies
    assert "csrf_token" in cookies

def test_cookie_authentication_with_csrf_protection(environment):
    client, db, owner, other, admin, candidate, _ = environment
    # 1. Login to get cookies
    login_resp = client.post(
        "/api/v1/auth/login",
        data={"username": owner.email, "password": "correct-password"}
    )
    assert login_resp.status_code == 200
    csrf_token = login_resp.json()["csrf_token"]

    # 2. GET request using cookie auth works without CSRF header (safe method)
    get_resp = client.get("/api/v1/auth/me")
    assert get_resp.status_code == 200
    assert get_resp.json()["email"] == owner.email

    # 3. Mutating POST without CSRF header is rejected with 403
    post_no_csrf = client.put(
        "/api/v1/users/me/preferences",
        json={"theme": "dark"}
    )
    assert post_no_csrf.status_code == 403
    assert "CSRF token validation failed" in post_no_csrf.json()["detail"]

    # 4. Mutating POST with mismatched CSRF header is rejected with 403
    post_bad_csrf = client.put(
        "/api/v1/users/me/preferences",
        headers={"X-CSRF-Token": "invalid-csrf-token"},
        json={"theme": "dark"}
    )
    assert post_bad_csrf.status_code == 403

    # 5. Mutating POST with valid matching CSRF header succeeds
    post_valid = client.put(
        "/api/v1/users/me/preferences",
        headers={"X-CSRF-Token": csrf_token},
        json={"theme": "dark"}
    )
    assert post_valid.status_code == 200
    assert post_valid.json()["theme"] == "dark"

def test_logout_clears_cookies_and_revokes_session(environment):
    client, db, owner, other, admin, candidate, _ = environment
    login_resp = client.post(
        "/api/v1/auth/login",
        data={"username": owner.email, "password": "correct-password"}
    )
    data = login_resp.json()
    refresh_token = data["refresh_token"]

    # Verify session token in DB
    token_hash = hash_token(refresh_token)
    db_session = db.query(UserRefreshToken).filter(UserRefreshToken.token_hash == token_hash).first()
    assert db_session is not None

    # Call logout
    logout_resp = client.post("/api/v1/auth/logout")
    assert logout_resp.status_code == 200

    # Verify session revoked in DB
    db.expire_all()
    db_session_after = db.query(UserRefreshToken).filter(UserRefreshToken.token_hash == token_hash).first()
    assert db_session_after is None

def test_token_expiry(environment):
    client, db, owner, other, admin, candidate, _ = environment
    # Generate an expired token
    expired_token = create_access_token(
        subject=owner.email,
        role=owner.role,
        expires_delta=timedelta(seconds=-10)
    )
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert resp.status_code == 401
    assert "Could not validate credentials" in resp.json()["detail"]

def test_session_revocation_on_password_reset(environment):
    client, db, owner, other, admin, candidate, _ = environment
    # Add active session
    raw_refresh = "active-session-token-xyz"
    db.add(UserRefreshToken(
        user_id=owner.id,
        token_hash=hash_token(raw_refresh),
        expires_at=datetime.utcnow() + timedelta(days=1)
    ))
    # Add valid OTP
    otp_code = "123456"
    otp_entry = OTP(
        email=owner.email,
        otp=hash_token(f"{owner.email}:{otp_code}:{settings.SECRET_KEY}"),
        expiry_time=datetime.utcnow() + timedelta(minutes=10),
        used=False
    )
    db.add(otp_entry)
    db.commit()

    # Reset password
    resp = client.post(
        "/api/v1/auth/reset-password",
        json={
            "email": owner.email,
            "code": otp_code,
            "new_password": "new-valid-password-123"
        }
    )
    assert resp.status_code == 200
    assert resp.json()["message"] == "Password updated successfully"

    # Verify session was revoked
    db.expire_all()
    sessions = db.query(UserRefreshToken).filter(UserRefreshToken.user_id == owner.id).all()
    assert len(sessions) == 0

def test_candidate_admin_access_separation(environment):
    client, db, owner, other, admin, candidate, _ = environment
    owner_token = create_access_token(owner.email, "candidate")
    admin_token = create_access_token(admin.email, "admin")

    # Candidate attempting removed admin endpoint -> 404
    candidate_resp = client.get(
        "/api/v1/admin/dashboard",
        headers={"Authorization": f"Bearer {owner_token}"}
    )
    assert candidate_resp.status_code == 404

    # Admin accessing removed admin endpoint -> 404
    admin_resp = client.get(
        "/api/v1/admin/dashboard",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert admin_resp.status_code == 404

def test_reset_password_does_not_leak_email_existence(environment):
    client, db, owner, other, admin, candidate, _ = environment
    # Non-existent email with dummy code
    resp = client.post(
        "/api/v1/auth/reset-password",
        json={
            "email": "nonexistent_email_12345@example.com",
            "code": "999999",
            "new_password": "some-new-password-123"
        }
    )
    # Must return 400 and generic message, NOT 404 "Email not registered"
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid or expired verification code"
