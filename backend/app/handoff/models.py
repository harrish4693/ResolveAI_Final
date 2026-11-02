"""
ResolveAIV2 — Handoff Model (First-Class Domain Object)

The Handoff is the bridge between AI support and human support.
It is the single artifact that carries ALL context across that boundary.
"""

from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.shared.models import TimestampMixin, HandoffStatus, Priority


class Handoff(TimestampMixin, Base):
    """First-class domain object for AI-to-human escalation."""
    __tablename__ = "handoffs"
    __table_args__ = (
        Index("ix_handoffs_status_assigned", "status", "assigned_expert_id"),
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

    # ── Core Handoff Data ──
    escalation_reason: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[Priority] = mapped_column(String(10), nullable=False, default=Priority.MEDIUM)
    category: Mapped[str] = mapped_column(String(100), nullable=False, default="general")

    # ── AI Context Snapshot ──
    ai_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    ai_analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Full AnalysisResult
    collected_information: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Entities gathered
    rag_evidence: Mapped[list | None] = mapped_column(JSON, nullable=True)  # Knowledge articles used
    ai_actions_taken: Mapped[list | None] = mapped_column(JSON, nullable=True)  # What AI tried

    # ── Lifecycle ──
    status: Mapped[HandoffStatus] = mapped_column(
        String(20), nullable=False, default=HandoffStatus.WAITING, index=True
    )
    assigned_expert_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("experts.id"), nullable=True, index=True
    )

    # ── Timestamps ──
    assigned_at: Mapped[datetime | None] = mapped_column(nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Relationships
    conversation = relationship("Conversation", back_populates="handoff", lazy="selectin")
    ticket = relationship("Ticket")
    customer = relationship("User")
    assigned_expert = relationship("Expert", back_populates="handoffs")
    assignment = relationship("ExpertAssignment", back_populates="handoff", uselist=False)

    @property
    def channel(self) -> str:
        if hasattr(self, "_channel") and self._channel:
            return self._channel
        if self.conversation and self.conversation.channel:
            return getattr(self.conversation.channel, "value", str(self.conversation.channel))
        return "text"

    @channel.setter
    def channel(self, val: str):
        self._channel = val

    def __repr__(self) -> str:
        return (
            f"<Handoff(id={self.id}, status='{self.status}', "
            f"priority='{self.priority}', reason='{self.escalation_reason[:40]}...')>"
        )


class ExpertAssignment(TimestampMixin, Base):
    """Tracks the expert assignment for a handoff."""
    __tablename__ = "expert_assignments"

    handoff_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("handoffs.id"), nullable=False, unique=True
    )
    expert_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("experts.id"), nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="accepted"
    )  # accepted / completed / transferred

    accepted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Relationships
    handoff = relationship("Handoff", back_populates="assignment")
    expert = relationship("Expert", back_populates="assignments")

    def __repr__(self) -> str:
        return f"<ExpertAssignment(id={self.id}, handoff={self.handoff_id}, expert={self.expert_id})>"
