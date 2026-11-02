"""
ResolveAIV2 — Feedback Model
"""

from sqlalchemy import Boolean, ForeignKey, Integer, Text, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.shared.models import TimestampMixin, ResolutionType


class Feedback(TimestampMixin, Base):
    __tablename__ = "feedback"
    __table_args__ = (
        UniqueConstraint("conversation_id", "customer_id", name="uix_feedback_conversation_customer"),
    )

    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("conversations.id"), nullable=False, unique=True
    )
    ticket_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tickets.id"), nullable=False
    )
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )

    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_helpful: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    resolution_type: Mapped[ResolutionType] = mapped_column(String(30), nullable=False)

    # Relationships
    conversation = relationship("Conversation", back_populates="feedback")
    customer = relationship("User", back_populates="feedbacks")

    def __repr__(self) -> str:
        return f"<Feedback(id={self.id}, rating={self.rating}, helpful={self.is_helpful})>"
