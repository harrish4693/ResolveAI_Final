"""
ResolveAIV2 — Conversation & Message Models

Conversations track both `status` (customer-facing lifecycle) and
`workflow_state` (internal processing position).
"""

from sqlalchemy import ForeignKey, Integer, String, Text, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.shared.models import (
    TimestampMixin,
    ConversationStatus,
    WorkflowState,
    ConversationChannel,
    SenderType,
    MessageType,
)

from datetime import datetime


class Conversation(TimestampMixin, Base):
    __tablename__ = "conversations"

    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )

    # Dual state tracking
    status: Mapped[ConversationStatus] = mapped_column(
        String(20), nullable=False, default=ConversationStatus.ACTIVE
    )
    workflow_state: Mapped[WorkflowState] = mapped_column(
        String(30), nullable=False, default=WorkflowState.IDLE
    )

    channel: Mapped[ConversationChannel] = mapped_column(
        String(10), nullable=False, default=ConversationChannel.TEXT
    )

    preferred_language: Mapped[str | None] = mapped_column(
        String(20), nullable=True, default=None
    )

    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Relationships
    customer = relationship("User", back_populates="conversations")
    messages = relationship(
        "ConversationMessage",
        back_populates="conversation",
        order_by="ConversationMessage.created_at",
        lazy="selectin",
    )
    ticket = relationship("Ticket", back_populates="conversation", uselist=False)
    handoff = relationship("Handoff", back_populates="conversation", uselist=False)
    feedback = relationship("Feedback", back_populates="conversation", uselist=False)

    def __repr__(self) -> str:
        return (
            f"<Conversation(id={self.id}, customer_id={self.customer_id}, "
            f"status='{self.status}', workflow='{self.workflow_state}')>"
        )


class ConversationMessage(TimestampMixin, Base):
    __tablename__ = "conversation_messages"

    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("conversations.id"), nullable=False, index=True
    )

    sender_type: Mapped[SenderType] = mapped_column(String(20), nullable=False)
    sender_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )

    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_type: Mapped[MessageType] = mapped_column(
        String(20), nullable=False, default=MessageType.TEXT
    )
    audio_url: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Internal metadata (AI analysis, etc.) — never exposed to customers
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")

    def __repr__(self) -> str:
        preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"<Message(id={self.id}, sender='{self.sender_type}', text='{preview}')>"


class ProcessedUtterance(TimestampMixin, Base):
    """Tracks processed voice utterances to ensure idempotency.

    DB-level uniqueness on (utterance_id, customer_id, conversation_id)
    prevents duplicate voice turn processing even across WebSocket
    reconnects or concurrent requests.
    """
    __tablename__ = "processed_utterances"

    utterance_id: Mapped[str] = mapped_column(String(100), nullable=False)
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("conversations.id"), nullable=False, index=True
    )

    __table_args__ = (
        UniqueConstraint(
            "utterance_id", "customer_id", "conversation_id",
            name="uq_processed_utterance",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ProcessedUtterance(conversation_id={self.conversation_id}, "
            f"customer_id={self.customer_id}, utterance_id='{self.utterance_id}')>"
        )

