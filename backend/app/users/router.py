"""
ResolveAIV2 — Users Router
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import password as pwd_utils
from app.auth.deps import get_current_user
from app.database import get_db
from app.shared.exceptions import AuthenticationError
from app.users.models import User
from app.users.schemas import UserPasswordUpdate, UserResponse, UserUpdate

router = APIRouter()


@router.put("/me", response_model=UserResponse)
async def update_me(
    user_update: UserUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Update current user profile."""
    if user_update.full_name is not None:
        current_user.full_name = user_update.full_name
    if user_update.avatar_url is not None:
        current_user.avatar_url = user_update.avatar_url
        
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.put("/me/password")
async def update_password(
    pwd_update: UserPasswordUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Change current user password."""
    if not pwd_utils.verify_password(pwd_update.current_password, current_user.password_hash):
        raise AuthenticationError("Incorrect current password")
        
    current_user.password_hash = pwd_utils.get_password_hash(pwd_update.new_password)
    await db.commit()
    
    return {"message": "Password updated successfully"}
