"""
ResolveAIV2 — Shared Base Model & Enums

Contains the base mixin (id, timestamps) and all application enums.
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# ═══════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════


class UserRole(str, enum.Enum):
    """User roles for RBAC."""
    CUSTOMER = "customer"
    EXPERT = "expert"
    ADMIN = "admin"


class ConversationStatus(str, enum.Enum):
    """Customer-facing lifecycle state."""
    ACTIVE = "active"
    WAITING = "waiting"        # Waiting for expert assignment
    RESOLVED = "resolved"
    CLOSED = "closed"


class ResolutionType(str, enum.Enum):
    """Authoritative source of conversation resolution."""
    AI = "ai"
    HUMAN = "human"
    AI_ESCALATED_TO_HUMAN = "ai_escalated_to_human"


class WorkflowState(str, enum.Enum):
    """Internal workflow processing state."""
    IDLE = "idle"
    UNDERSTANDING = "understanding"
    SEARCHING_KNOWLEDGE = "searching_knowledge"
    DECIDING = "deciding"
    ASKING_USER = "asking_user"
    
    # M9 Agentic Tool States
    TOOL_REQUESTED = "tool_requested"
    VALIDATING_TOOL = "validating_tool"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    EXECUTING_TOOL = "executing_tool"
    OBSERVING_RESULT = "observing_result"
    RESPONDING = "responding"
    TOOL_FAILURE = "tool_failure"
    RETRY = "retry"
    
    RESOLVING = "resolving"
    ESCALATING = "escalating"
    WAITING_FOR_EXPERT = "waiting_for_expert"
    WITH_EXPERT = "with_expert"
    RESOLVED = "resolved"


class TicketStatus(str, enum.Enum):
    """Ticket lifecycle state."""
    OPEN = "open"
    AI_PROCESSING = "ai_processing"
    WAITING_FOR_USER = "waiting_for_user"
    ESCALATED = "escalated"
    ASSIGNED = "assigned"
    HUMAN_HANDLING = "human_handling"
    RESOLVED = "resolved"


class Priority(str, enum.Enum):
    """Issue priority levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class HandoffStatus(str, enum.Enum):
    """Handoff lifecycle."""
    WAITING = "waiting"
    ASSIGNED = "assigned"
    RESOLVED = "resolved"


class SenderType(str, enum.Enum):
    """Who sent a message."""
    CUSTOMER = "customer"
    AI = "ai"
    EXPERT = "expert"
    SYSTEM = "system"


class MessageType(str, enum.Enum):
    """Type of message content."""
    TEXT = "text"
    VOICE = "voice"
    SYSTEM = "system"


class ConversationChannel(str, enum.Enum):
    """How the conversation was initiated."""
    TEXT = "text"
    VOICE = "voice"
    CHAT = "chat"


class AssignmentStatus(str, enum.Enum):
    """Expert assignment lifecycle."""
    ACCEPTED = "accepted"
    COMPLETED = "completed"
    TRANSFERRED = "transferred"


class NotificationType(str, enum.Enum):
    """Types of notifications."""
    EXPERT_ASSIGNED = "expert_assigned"
    EXPERT_JOINED = "expert_joined"
    TICKET_UPDATED = "ticket_updated"
    TICKET_RESOLVED = "ticket_resolved"
    NEW_MESSAGE = "new_message"
    HANDOFF_STATUS = "handoff_status"
    SYSTEM = "system"


# ═══════════════════════════════════════════════════════════
# Base Model Mixin
# ═══════════════════════════════════════════════════════════


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    """Mixin that adds id, created_at, and updated_at to every model."""

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
        nullable=False,
    )
