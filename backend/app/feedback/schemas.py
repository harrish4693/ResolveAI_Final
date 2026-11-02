from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from app.shared.models import ResolutionType

class FeedbackCreate(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: str | None = Field(None, max_length=1000)

class FeedbackRead(BaseModel):
    id: int
    conversation_id: int
    ticket_id: int
    customer_id: int
    rating: int
    comment: str | None
    resolution_type: ResolutionType
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
