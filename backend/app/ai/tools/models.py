from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Enum, UniqueConstraint
from app.database import Base
import enum

class ToolExecutionStatus(enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    AWAITING_CONFIRMATION = "awaiting_confirmation"

class ToolExecution(Base):
    __tablename__ = "tool_executions"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    customer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    expert_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    tool_name = Column(String, nullable=False)
    input_hash = Column(String, nullable=False)
    tool_args = Column(String, nullable=False, default="{}")
    
    status = Column(Enum(ToolExecutionStatus), default=ToolExecutionStatus.PENDING, nullable=False)
    result_summary = Column(String, nullable=True)
    error_code = Column(String, nullable=True)
    
    requires_confirmation = Column(Boolean, default=False)
    confirmed = Column(Boolean, default=False)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("conversation_id", "tool_name", "input_hash", name="uq_tool_execution_idempotency"),
    )
