"""
ResolveAIV2 — User Model
"""

from sqlalchemy import Boolean, String, ForeignKey, UniqueConstraint, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime

from app.database import Base
from app.shared.models import TimestampMixin, UserRole


class User(TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(String(20), nullable=False, default=UserRole.CUSTOMER)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(50), default="default", nullable=False, server_default="default")

    # Relationships
    conversations = relationship("Conversation", back_populates="customer", lazy="select")
    tickets = relationship("Ticket", back_populates="customer", lazy="select")
    notifications = relationship("Notification", back_populates="user", lazy="select")
    feedbacks = relationship("Feedback", back_populates="customer", lazy="select")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email='{self.email}', role='{self.role}')>"

class OAuthAccount(TimestampMixin, Base):
    __tablename__ = "oauth_accounts"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Relationships
    user = relationship("User", backref="oauth_accounts", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("provider", "provider_subject", name="uix_provider_subject"),
    )

class OAuthState(TimestampMixin, Base):
    __tablename__ = "oauth_states"

    # Holds state / nonce for the initial oauth request
    state_token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    nonce: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Used later for the short-lived exchange flow
    exchange_code: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
