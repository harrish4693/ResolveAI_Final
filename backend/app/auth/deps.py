"""
ResolveAIV2 — Auth Dependencies

FastAPI dependencies for extracting the current user from JWT
and enforcing RBAC (Role-Based Access Control).
"""

from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import verify_token
from app.database import get_db
from app.shared.exceptions import AuthenticationError, ForbiddenError
from app.shared.models import UserRole
from app.users.models import User

# OAuth2 scheme for Swagger UI auth support
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> User:
    """Dependency: Extract and verify user from JWT access token."""
    try:
        payload = verify_token(token, expected_type="access")
        user_id = int(payload.get("sub"))
    except Exception as e:
        raise AuthenticationError(f"Could not validate credentials: {str(e)}")

    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        raise AuthenticationError("User not found")
    if not user.is_active:
        raise AuthenticationError("Inactive user")

    return user


def require_role(allowed_roles: list[UserRole]):
    """Dependency factory: Enforce role-based access control."""
    async def role_checker(current_user: Annotated[User, Depends(get_current_user)]) -> User:
        if current_user.role not in allowed_roles:
            raise ForbiddenError(f"Operation requires one of roles: {', '.join(allowed_roles)}")
        return current_user
    return role_checker


# Convenience dependencies
require_customer = require_role([UserRole.CUSTOMER, UserRole.ADMIN])
require_expert = require_role([UserRole.EXPERT, UserRole.ADMIN])
require_admin = require_role([UserRole.ADMIN])
