from datetime import datetime
from typing import List, Any
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator
from app.shared.models import (
    ConversationStatus,
    WorkflowState,
    ConversationChannel,
    SenderType,
    MessageType,
)


class ConversationMessageOut(BaseModel):
    id: int
    conversation_id: int
    sender_type: SenderType
    sender_id: int | None = None
    content: str
    message_type: MessageType
    audio_url: str | None = None
    metadata_: dict | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationMessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000, description="Message content")
    is_internal: bool = False


class ConversationCreate(BaseModel):
    initial_message: str | None = Field(None, max_length=5000, description="Initial message (optional for voice calls)")
    subject: str | None = Field(None, max_length=500, description="Optional subject")
    channel: ConversationChannel = ConversationChannel.TEXT
    preferred_language: str | None = None

    @field_validator("channel", mode="before")
    @classmethod
    def normalize_channel(cls, v: Any) -> ConversationChannel:
        if isinstance(v, ConversationChannel):
            return v
        if isinstance(v, str):
            val = v.lower().strip()
            if val in ("voice", "call"):
                return ConversationChannel.VOICE
            return ConversationChannel.TEXT
        return ConversationChannel.TEXT

    @model_validator(mode="after")
    def validate_text_initial_message(self) -> "ConversationCreate":
        channel_val = getattr(self.channel, "value", self.channel)
        if channel_val in ("text", "chat", ConversationChannel.TEXT):
            if not self.initial_message or not self.initial_message.strip():
                raise ValueError("Initial message is required for text conversations.")
        return self


class ConversationUpdate(BaseModel):
    preferred_language: str | None = None
    subject: str | None = None


class ConversationOut(BaseModel):
    id: int
    customer_id: int
    status: ConversationStatus
    workflow_state: WorkflowState
    channel: ConversationChannel
    preferred_language: str | None = None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("channel", mode="before")
    @classmethod
    def normalize_channel(cls, v: Any) -> ConversationChannel:
        if isinstance(v, ConversationChannel):
            return v
        if isinstance(v, str):
            val = v.lower().strip()
            if val in ("voice", "call"):
                return ConversationChannel.VOICE
            return ConversationChannel.TEXT
        return ConversationChannel.TEXT
