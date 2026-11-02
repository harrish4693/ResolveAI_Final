"""
ResolveAIV2 — Conversation Memory Models
"""

from sqlalchemy import ForeignKey, Integer, String, Text, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
import enum

from app.database import Base
from app.shared.models import TimestampMixin

class MemoryType(str, enum.Enum):
    ISSUE_HISTORY = "ISSUE_HISTORY"
    RESOLUTION = "RESOLUTION"
    PREFERENCE = "PREFERENCE"
    SUMMARY = "SUMMARY"

class MemorySourceType(str, enum.Enum):
    CUSTOMER = "CUSTOMER"
    AI = "AI"
    SYSTEM = "SYSTEM"
    TOOL = "TOOL"

class MemoryImportance(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

class MemoryConfidence(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

class ConversationMemory(TimestampMixin, Base):
    __tablename__ = "conversation_memories"

    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    
    # Nullable if the memory transcends a single conversation (e.g., persistent preference)
    conversation_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("conversations.id"), nullable=True, index=True
    )

    memory_type: Mapped[MemoryType] = mapped_column(String(50), nullable=False)
    source_type: Mapped[MemorySourceType] = mapped_column(String(50), nullable=False)
    
    content: Mapped[str] = mapped_column(Text, nullable=False)
    
    importance: Mapped[MemoryImportance] = mapped_column(
        String(20), nullable=False, default=MemoryImportance.MEDIUM
    )
    confidence: Mapped[MemoryConfidence] = mapped_column(
        String(20), nullable=False, default=MemoryConfidence.MEDIUM
    )
    
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    customer = relationship("User")
    conversation = relationship("Conversation")

    def __repr__(self) -> str:
        return f"<ConversationMemory(id={self.id}, customer_id={self.customer_id}, type='{self.memory_type}')>"
