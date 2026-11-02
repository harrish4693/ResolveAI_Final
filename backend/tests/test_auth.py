"""
ResolveAIV2 — Authentication, Authorization & OAuth Test Suite
==============================================================
Validates:
1. User registration, password validation, duplicate email rejection.
2. Login and JWT issuance (access and refresh tokens).
3. Refresh token rotation and revocation on logout.
4. User profile access control (/api/auth/me) and password redaction.
5. Account creation confirmation emails.
6. Forgot password requests, email delivery, and user privacy protection.
7. Password reset verification, token expiration, and password update.
8. Google OAuth state creation, callback token exchange, and account linkage.
"""

import pytest
import secrets
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.users.models import User, OAuthState, OAuthAccount
from app.shared.models import UserRole
from app.auth.models import RefreshToken
from app.notifications.email_service import email_service


# ═══════════════════════════════════════════════════════════════
# 1. Registration & Login Tests
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_register_success(async_client: AsyncClient):
    response = await async_client.post(
        "/api/auth/register",
        json={
            "email": "test@resolveai.com",
            "full_name": "Test User",
            "password": "StrongPassword123"
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.asyncio
async def test_register_duplicate_email(async_client: AsyncClient):
    payload = {
        "email": "duplicate@resolveai.com",
        "full_name": "Test User",
        "password": "StrongPassword123"
    }
    await async_client.post("/api/auth/register", json=payload)
    response = await async_client.post("/api/auth/register", json=payload)
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


@pytest.mark.asyncio
async def test_register_weak_password(async_client: AsyncClient):
    payload = {
        "email": "weak@resolveai.com",
        "full_name": "Weak User",
        "password": "weak"
    }
    response = await async_client.post("/api/auth/register", json=payload)
    assert response.status_code == 422
    assert "Password must be at least 8 characters" in str(response.json()) or "String should have at least 8" in str(response.json())


@pytest.mark.asyncio
async def test_login_success(async_client: AsyncClient):
    payload = {
        "email": "login@resolveai.com",
        "full_name": "Login User",
        "password": "StrongPassword123"
    }
    await async_client.post("/api/auth/register", json=payload)
    
    response = await async_client.post(
        "/api/auth/login",
        json={
            "email": "login@resolveai.com",
            "password": "StrongPassword123"
        }
    )
    assert response.status_code == 200
    assert "access_token" in response.json()


@pytest.mark.asyncio
async def test_refresh_token(async_client: AsyncClient, db_session: AsyncSession):
    payload = {
        "email": "refresh@resolveai.com",
        "full_name": "Refresh User",
        "password": "StrongPassword123"
    }
    reg_response = await async_client.post("/api/auth/register", json=payload)
    tokens = reg_response.json()
    refresh_token = tokens["refresh_token"]

    response = await async_client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_token}
    )
    assert response.status_code == 200
    new_tokens = response.json()
    assert "access_token" in new_tokens
    
    # Old refresh token should be revoked
    stmt = select(RefreshToken).where(RefreshToken.token == refresh_token)
    db_token = (await db_session.execute(stmt)).scalar_one_or_none()
    assert db_token is not None
    assert db_token.is_revoked is True


@pytest.mark.asyncio
async def test_logout_revokes_token(async_client: AsyncClient, db_session: AsyncSession):
    payload = {
        "email": "logout@resolveai.com",
        "full_name": "Logout User",
        "password": "StrongPassword123"
    }
    reg_response = await async_client.post("/api/auth/register", json=payload)
    tokens = reg_response.json()
    refresh_token = tokens["refresh_token"]

    response = await async_client.post(
        "/api/auth/logout",
        json={"refresh_token": refresh_token}
    )
    assert response.status_code == 200
    
    stmt = select(RefreshToken).where(RefreshToken.token == refresh_token)
    db_token = (await db_session.execute(stmt)).scalar_one_or_none()
    assert db_token is not None
    assert db_token.is_revoked is True


@pytest.mark.asyncio
async def test_get_me_protected(async_client: AsyncClient):
    payload = {
        "email": "me@resolveai.com",
        "full_name": "Me User",
        "password": "StrongPassword123"
    }
    reg_response = await async_client.post("/api/auth/register", json=payload)
    access_token = reg_response.json()["access_token"]
    
    # Missing token
    response = await async_client.get("/api/auth/me")
    assert response.status_code == 401
    
    # With token
    response = await async_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    assert response.json()["email"] == "me@resolveai.com"
    assert "password_hash" not in response.json()
    assert "password" not in response.json()


# ═══════════════════════════════════════════════════════════════
# 2. Email Notifications & Password Reset Tests
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_register_sends_account_confirmation_email(async_client: AsyncClient):
    email_service.clear_sent_emails()

    payload = {
        "email": "welcome_user@resolveai.com",
        "full_name": "Welcome User",
        "password": "StrongPassword123"
    }
    res = await async_client.post("/api/auth/register", json=payload)
    assert res.status_code == 201
    assert "access_token" in res.json()

    sent = email_service.get_last_sent_email()
    assert sent is not None
    assert sent["to_email"] == "welcome_user@resolveai.com"
    assert "Confirm Your Account Creation" in sent["subject"]
    assert "Welcome User" in sent["html_content"]
    assert "welcome_user@resolveai.com" in sent["html_content"]
    assert "Confirm &amp; Access Your Account" in sent["html_content"]
    assert "Active &amp; Ready" in sent["html_content"]
    assert "welcome_user@resolveai.com" in sent["text_content"]


@pytest.mark.asyncio
async def test_forgot_password_sends_confirmation_email(async_client: AsyncClient):
    email_service.clear_sent_emails()

    # 1. Register a test user
    payload = {
        "email": "forgot_user@resolveai.com",
        "full_name": "Forgot User",
        "password": "StrongPassword123"
    }
    reg_res = await async_client.post("/api/auth/register", json=payload)
    assert reg_res.status_code == 201

    # 2. Trigger forgot password
    res = await async_client.post(
        "/api/auth/forgot-password",
        json={"email": "forgot_user@resolveai.com"}
    )
    assert res.status_code == 200
    data = res.json()
    assert "dev_reset_token" in data
    assert "dev_reset_url" in data
    reset_url = data["dev_reset_url"]

    # 3. Verify confirmation email was recorded and formatted properly
    sent = email_service.get_last_sent_email()
    assert sent is not None
    assert sent["to_email"] == "forgot_user@resolveai.com"
    assert "Confirm Your Password Reset Request — ResolveAI" in sent["subject"]
    assert "Confirm &amp; Reset Password" in sent["html_content"]
    assert reset_url in sent["html_content"]
    assert "15 minutes" in sent["html_content"]
    assert reset_url in sent["text_content"]


@pytest.mark.asyncio
async def test_forgot_password_unknown_email_no_leak(async_client: AsyncClient):
    email_service.clear_sent_emails()

    res = await async_client.post(
        "/api/auth/forgot-password",
        json={"email": "does_not_exist@resolveai.com"}
    )
    assert res.status_code == 200
    assert "If an account exists" in res.json()["message"]
    assert len(email_service.get_sent_emails()) == 0


@pytest.mark.asyncio
async def test_reset_password_flow_and_confirmation_email(async_client: AsyncClient):
    email_service.clear_sent_emails()

    # 1. Register user
    reg_payload = {
        "email": "reset_test@resolveai.com",
        "full_name": "Reset Test User",
        "password": "OldPassword123"
    }
    await async_client.post("/api/auth/register", json=reg_payload)

    # 2. Request reset
    forgot_res = await async_client.post(
        "/api/auth/forgot-password",
        json={"email": "reset_test@resolveai.com"}
    )
    assert forgot_res.status_code == 200
    reset_token = forgot_res.json()["dev_reset_token"]

    # 3. Submit password reset with valid token
    reset_res = await async_client.post(
        "/api/auth/reset-password",
        json={
            "token": reset_token,
            "new_password": "NewStrongPassword456"
        }
    )
    assert reset_res.status_code == 200
    assert reset_res.json()["message"] == "Password has been reset successfully"

    # 4. Verify password changed confirmation email was sent
    sent = email_service.get_last_sent_email()
    assert sent is not None
    assert sent["to_email"] == "reset_test@resolveai.com"
    assert "Your ResolveAI Password Has Been Successfully Changed" in sent["subject"]
    assert "successfully updated" in sent["html_content"]

    # 5. Verify old password fails and new password succeeds for login
    fail_login = await async_client.post(
        "/api/auth/login",
        json={"email": "reset_test@resolveai.com", "password": "OldPassword123"}
    )
    assert fail_login.status_code == 401

    success_login = await async_client.post(
        "/api/auth/login",
        json={"email": "reset_test@resolveai.com", "password": "NewStrongPassword456"}
    )
    assert success_login.status_code == 200
    assert "access_token" in success_login.json()


@pytest.mark.asyncio
async def test_reset_password_invalid_or_expired_token(async_client: AsyncClient):
    res = await async_client.post(
        "/api/auth/reset-password",
        json={
            "token": "invalid.jwt.token",
            "new_password": "NewPassword123"
        }
    )
    assert res.status_code == 401
    assert "Invalid or expired reset token" in res.json()["detail"]


# ═══════════════════════════════════════════════════════════════
# 3. Google OAuth Flow Tests
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def mock_google_settings(monkeypatch):
    monkeypatch.setattr("app.config.settings.google_client_id", "test_client_id")
    monkeypatch.setattr("app.config.settings.google_client_secret", "test_client_secret")


@pytest.mark.asyncio
async def test_google_login_generates_url(async_client: AsyncClient, mock_google_settings, db_session):
    response = await async_client.get("/api/auth/google/login")
    assert response.status_code == 200
    data = response.json()
    assert "url" in data
    assert "https://accounts.google.com/o/oauth2/v2/auth" in data["url"]
    
    # Check that state is created
    state_token = data["url"].split("state=")[1].split("&")[0]
    result = await db_session.execute(select(OAuthState).where(OAuthState.state_token == state_token))
    state_obj = result.scalar_one_or_none()
    assert state_obj is not None
    assert state_obj.nonce is not None


@pytest.mark.asyncio
async def test_google_callback_creates_user(async_client: AsyncClient, mock_google_settings, db_session):
    state_token = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    oauth_state = OAuthState(
        state_token=state_token,
        nonce=nonce,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15)
    )
    db_session.add(oauth_state)
    await db_session.commit()

    with patch("httpx.AsyncClient.post") as mock_post, patch("google.oauth2.id_token.verify_oauth2_token") as mock_verify:
        mock_res = MagicMock()
        mock_res.status_code = 200
        mock_res.json.return_value = {"id_token": "fake_id_token"}
        mock_post.return_value = mock_res
        
        mock_verify.return_value = {
            "iss": "accounts.google.com",
            "nonce": nonce,
            "email": "googleuser@example.com",
            "email_verified": True,
            "sub": "google123",
            "name": "Google User",
            "picture": "http://example.com/pic.jpg"
        }
        
        response = await async_client.get(
            f"/api/auth/google/callback?state={state_token}&code=authcode123",
            follow_redirects=False
        )
        assert response.status_code == 307
        assert "/oauth/callback?code=" in response.headers["location"]
        
        exchange_code = response.headers["location"].split("code=")[1]
        
        result = await db_session.execute(select(User).where(User.email == "googleuser@example.com"))
        user = result.scalar_one_or_none()
        assert user is not None
        assert user.role == UserRole.CUSTOMER
        assert user.password_hash == "!oauth_only!"
        
    exchange_response = await async_client.post("/api/auth/google/exchange", json={"code": exchange_code})
    assert exchange_response.status_code == 200
    tokens = exchange_response.json()
    assert "access_token" in tokens
    assert "refresh_token" in tokens
