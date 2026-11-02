"""
ResolveAIV2 — Notification Model
"""

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.shared.models import TimestampMixin, NotificationType


class Notification(TimestampMixin, Base):
    __tablename__ = "notifications"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )

    type: Mapped[NotificationType] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Polymorphic reference to related entity
    reference_type: Mapped[str | None] = mapped_column(String(50), nullable=True)  # conversation / ticket / handoff
    reference_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Relationships
    user = relationship("User", back_populates="notifications")

    def __repr__(self) -> str:
        return f"<Notification(id={self.id}, type='{self.type}', read={self.is_read})>"
