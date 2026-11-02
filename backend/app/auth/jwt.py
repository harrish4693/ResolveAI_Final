"""
ResolveAIV2 — JWT Utilities

Handles creating and verifying JSON Web Tokens (access and refresh).
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from app.config import settings
from app.shared.exceptions import AuthenticationError


import uuid

def create_access_token(subject: str | int, role: str, expires_delta: timedelta | None = None) -> str:
    """Create a short-lived JWT access token."""
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    
    to_encode = {"exp": expire, "sub": str(subject), "role": role, "type": "access", "jti": str(uuid.uuid4())}
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return encoded_jwt


def create_refresh_token(subject: str | int, role: str) -> str:
    """Create a longer-lived JWT refresh token."""
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    to_encode = {"exp": expire, "sub": str(subject), "role": role, "type": "refresh", "jti": str(uuid.uuid4())}
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return encoded_jwt


def verify_token(token: str, expected_type: str = "access") -> dict[str, Any]:
    """Verify a JWT token and return its payload. Raises AuthenticationError on failure."""
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        
        # Verify token type (don't accept refresh token where access token is expected)
        if payload.get("type") != expected_type:
            raise AuthenticationError("Invalid token type")
            
        # Verify subject exists
        if payload.get("sub") is None:
            raise AuthenticationError("Invalid token payload: missing subject")
            
        return payload
    except JWTError:
        raise AuthenticationError("Could not validate credentials")
