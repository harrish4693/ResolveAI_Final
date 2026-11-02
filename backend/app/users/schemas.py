"""
ResolveAIV2 — User Schemas
"""

from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.shared.models import UserRole


class UserBase(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    avatar_url: str | None = None


class UserCreate(UserBase):
    password: str = Field(min_length=8)


class UserUpdate(BaseModel):
    full_name: str | None = Field(None, min_length=1, max_length=255)
    avatar_url: str | None = None


class UserPasswordUpdate(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class UserResponse(UserBase):
    id: int
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
