from datetime import datetime
from pydantic import BaseModel, ConfigDict
from app.shared.models import TicketStatus, Priority


class TicketOut(BaseModel):
    id: int
    customer_id: int
    conversation_id: int
    subject: str
    status: TicketStatus
    priority: Priority
    category: str | None = None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None
    resolved_by: str | None = None

    model_config = ConfigDict(from_attributes=True)
