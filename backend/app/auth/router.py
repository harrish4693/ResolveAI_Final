"""
ResolveAIV2 — Auth Router
"""

import logging
import urllib.parse
from typing import Annotated

from fastapi import APIRouter, Depends, status, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import jwt as jwt_utils
from app.auth import password as pwd_utils
from app.auth.deps import get_current_user
from app.auth.models import RefreshToken
from app.auth.schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    ResetPasswordRequest,
    Token,
)
from pydantic import BaseModel
from app.auth.oauth import generate_oauth_login_url, handle_oauth_callback, exchange_oauth_code_for_user
from app.config import settings
from app.database import get_db
from app.notifications.email_service import email_service
from app.shared.exceptions import AuthenticationError, ConflictError, ValidationError
from app.users.models import User
from app.users.schemas import UserCreate, UserResponse
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(user_in: UserCreate, db: Annotated[AsyncSession, Depends(get_db)]):
    """Register a new customer and return JWT tokens."""
    # Check if user exists
    stmt = select(User).where(User.email == user_in.email)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise ConflictError("A user with this email already exists")

    if not pwd_utils.validate_password_strength(user_in.password):
        raise ValidationError("Password must be at least 8 characters long and contain uppercase, lowercase, and numeric characters.")

    # Create user
    user = User(
        email=user_in.email,
        full_name=user_in.full_name,
        password_hash=pwd_utils.get_password_hash(user_in.password),
        avatar_url=user_in.avatar_url,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Generate tokens
    role_str = user.role if isinstance(user.role, str) else user.role.value
    access_token = jwt_utils.create_access_token(user.id, role_str)
    refresh_token = jwt_utils.create_refresh_token(user.id, role_str)
    
    # Extract expiration from the refresh token for DB storage
    payload = jwt_utils.verify_token(refresh_token, expected_type="refresh")
    expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    
    # Store refresh token in database
    db_token = RefreshToken(
        user_id=user.id,
        token=refresh_token,
        expires_at=expires_at,
    )
    db.add(db_token)
    await db.commit()

    # Send account creation confirmation email
    try:
        await email_service.send_account_confirmation_email(
            to_email=user.email,
            user_name=user.full_name or "there",
            login_url=f"{settings.frontend_url}/login",
        )
    except Exception as exc:
        logger.error("Failed to send account creation confirmation email to %s: %s", user.email, exc)

    return Token(access_token=access_token, refresh_token=refresh_token)


@router.post("/login", response_model=Token)
async def login(login_data: LoginRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    """Authenticate and return JWT tokens."""
    stmt = select(User).where(User.email == login_data.email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not pwd_utils.verify_password(login_data.password, user.password_hash):
        raise AuthenticationError("Incorrect email or password")
    
    if not user.is_active:
        raise AuthenticationError("User account is inactive")

    role_str = user.role if isinstance(user.role, str) else user.role.value
    access_token = jwt_utils.create_access_token(user.id, role_str)
    refresh_token = jwt_utils.create_refresh_token(user.id, role_str)

    payload = jwt_utils.verify_token(refresh_token, expected_type="refresh")
    expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    
    db_token = RefreshToken(
        user_id=user.id,
        token=refresh_token,
        expires_at=expires_at,
    )
    db.add(db_token)
    await db.commit()

    return Token(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=Token)
async def refresh_token(refresh_data: RefreshRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    """Exchange a valid refresh token for a new access+refresh token pair."""
    try:
        payload = jwt_utils.verify_token(refresh_data.refresh_token, expected_type="refresh")
        user_id = int(payload.get("sub"))
    except AuthenticationError:
        raise AuthenticationError("Invalid refresh token")

    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise AuthenticationError("User not found or inactive")

    # Verify refresh token exists in DB and is not revoked
    stmt = select(RefreshToken).where(RefreshToken.token == refresh_data.refresh_token)
    result = await db.execute(stmt)
    db_token = result.scalar_one_or_none()
    
    if not db_token or db_token.is_revoked:
        raise AuthenticationError("Invalid or revoked refresh token")

    role_str = user.role if isinstance(user.role, str) else user.role.value
    access_token = jwt_utils.create_access_token(user.id, role_str)
    new_refresh_token = jwt_utils.create_refresh_token(user.id, role_str)

    payload = jwt_utils.verify_token(new_refresh_token, expected_type="refresh")
    expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    
    # Store the new token, revoke the old one to implement token rotation
    db_token.is_revoked = True
    new_db_token = RefreshToken(
        user_id=user.id,
        token=new_refresh_token,
        expires_at=expires_at,
    )
    db.add(new_db_token)
    await db.commit()

    return Token(access_token=access_token, refresh_token=new_refresh_token)


@router.post("/logout")
async def logout(refresh_data: RefreshRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    """
    Logout revokes the provided refresh token.
    """
    stmt = select(RefreshToken).where(RefreshToken.token == refresh_data.refresh_token)
    result = await db.execute(stmt)
    db_token = result.scalar_one_or_none()
    
    if db_token:
        db_token.is_revoked = True
        await db.commit()
        
    return {"message": "Logged out successfully"}


@router.post("/forgot-password")
async def forgot_password(
    req: ForgotPasswordRequest, 
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Generate a password reset token and send a confirmation email."""
    stmt = select(User).where(User.email == req.email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        # Don't leak whether the email exists
        return {"message": "If an account exists, a password reset confirmation email has been sent"}

    # Generate a short-lived reset token (encoded as a standard JWT)
    from datetime import timedelta
    expires_in_minutes = 15
    reset_token = jwt_utils.create_access_token(
        subject=user.id, 
        role="reset", 
        expires_delta=timedelta(minutes=expires_in_minutes)
    )

    reset_url = f"{settings.frontend_url}/reset-password?token={reset_token}"
    
    # Send password reset confirmation email
    email_record = await email_service.send_password_reset_email(
        to_email=user.email,
        user_name=user.full_name or "there",
        reset_url=reset_url,
        expires_in_minutes=expires_in_minutes,
    )

    if not settings.email_enabled:
        # Development mode: log the token to the console and return dev inspection payload
        logger.warning(
            f"\n{'='*50}\n"
            f"PASSWORD RESET REQUESTED FOR: {user.email}\n"
            f"RESET URL: {reset_url}\n"
            f"{'='*50}\n"
        )

        return {
            "message": "Password reset confirmation email generated",
            "dev_reset_url": reset_url,
            "dev_reset_token": reset_token,
            "email_preview": {
                "to": user.email,
                "subject": email_record["subject"],
                "delivery_mode": email_record["delivery_mode"],
            }
        }
    else:
        logger.info(f"Delivered password reset confirmation email to {user.email}")
        return {"message": "If an account exists, a password reset confirmation email has been sent"}


@router.post("/reset-password")
async def reset_password(
    req: ResetPasswordRequest, 
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Reset the password using a valid reset token."""
    try:
        # We overloaded the access token logic for the reset token
        payload = jwt_utils.verify_token(req.token, expected_type="access")
        if payload.get("role") != "reset":
            raise AuthenticationError("Invalid token type for password reset")
            
        user_id = int(payload.get("sub"))
    except AuthenticationError:
        raise AuthenticationError("Invalid or expired reset token")

    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise AuthenticationError("User not found")

    if not pwd_utils.validate_password_strength(req.new_password):
        raise ValidationError("Password must be at least 8 characters long and contain uppercase, lowercase, and numeric characters.")

    user.password_hash = pwd_utils.get_password_hash(req.new_password)
    await db.commit()

    # Send confirmation email notifying user of password change
    try:
        await email_service.send_password_changed_email(
            to_email=user.email,
            user_name=user.full_name or "there",
        )
    except Exception as e:
        logger.error("Failed to send password changed notification email: %s", e)

    return {"message": "Password has been reset successfully"}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: Annotated[User, Depends(get_current_user)]):
    """Get the current authenticated user's profile."""
    return current_user

class ExchangeRequest(BaseModel):
    code: str

@router.get("/google/login")
async def google_login(db: Annotated[AsyncSession, Depends(get_db)]):
    """Initiates Google OAuth flow."""
    url = await generate_oauth_login_url(db)
    return {"url": url}

@router.get("/google/callback")
async def google_callback(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    state: str | None = None,
    code: str | None = None,
    error: str | None = None,
):
    """Handles Google OAuth callback, generates exchange code, and redirects frontend."""
    if error:
        logger.warning(f"Google OAuth callback provider error: {error}")
        return RedirectResponse(url=f"{settings.frontend_url}/login?error=Google+login+cancelled+or+failed")

    if not state or not code:
        logger.warning("Google OAuth callback missing state or code")
        return RedirectResponse(url=f"{settings.frontend_url}/login?error=Invalid+or+missing+OAuth+parameters")

    try:
        exchange_code = await handle_oauth_callback(db, state, code)
        redirect_url = f"{settings.frontend_url}/oauth/callback?code={exchange_code}"
        return RedirectResponse(url=redirect_url)
    except Exception as exc:
        logger.warning(f"OAuth callback failed: {exc}")
        detail = getattr(exc, "detail", "Invalid or expired OAuth state")
        safe_detail = urllib.parse.quote_plus(str(detail))
        return RedirectResponse(url=f"{settings.frontend_url}/login?error={safe_detail}")

@router.post("/google/exchange", response_model=Token)
async def google_exchange(
    req: ExchangeRequest,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Exchanges short-lived code for ResolveAI JWT tokens."""
    user = await exchange_oauth_code_for_user(db, req.code)
    
    role_str = user.role if isinstance(user.role, str) else user.role.value
    access_token = jwt_utils.create_access_token(user.id, role_str)
    refresh_token = jwt_utils.create_refresh_token(user.id, role_str)

    payload = jwt_utils.verify_token(refresh_token, expected_type="refresh")
    expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    
    db_token = RefreshToken(
        user_id=user.id,
        token=refresh_token,
        expires_at=expires_at,
    )
    db.add(db_token)
    await db.commit()

    return Token(access_token=access_token, refresh_token=refresh_token)
