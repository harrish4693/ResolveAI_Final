"""
ResolveAIV2 — Ticket Model
"""

from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.shared.models import TimestampMixin, TicketStatus, Priority


class Ticket(TimestampMixin, Base):
    __tablename__ = "tickets"

    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("conversations.id"), nullable=False, unique=True
    )

    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[TicketStatus] = mapped_column(
        String(20), nullable=False, default=TicketStatus.OPEN
    )
    priority: Mapped[Priority] = mapped_column(
        String(10), nullable=False, default=Priority.MEDIUM
    )
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)

    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(50), nullable=True)  # "ai" or user_id

    # Relationships
    customer = relationship("User", back_populates="tickets")
    conversation = relationship("Conversation", back_populates="ticket")

    def __repr__(self) -> str:
        return f"<Ticket(id={self.id}, status='{self.status}', priority='{self.priority}')>"
