from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime
from app.shared.models import HandoffStatus, Priority

class HandoffBase(BaseModel):
    conversation_id: int
    category: str
    escalation_reason: str
    priority: Priority

class HandoffCreate(HandoffBase):
    pass

class HandoffRead(HandoffBase):
    id: int
    assigned_expert_id: Optional[int] = None
    status: HandoffStatus
    resolution_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    # Resolution Failure Prediction & Proactive Escalation Context
    failure_risk_level: Optional[str] = None  # "LOW", "MODERATE", "HIGH", "VERY_HIGH"
    failure_probability: Optional[float] = None
    predicted_difficulty: Optional[str] = None
    warning_signals: Optional[list[str]] = None
    observed_failure_count: Optional[int] = None
    has_prior_solution_failed: Optional[bool] = None
    suggested_next_action: Optional[str] = None
    priority_rationale: Optional[str] = None
    incident_id: Optional[str] = None
    priority_rank: Optional[int] = None
    channel: Optional[str] = "text"

    model_config = ConfigDict(from_attributes=True)


class HandoffAssignRequest(BaseModel):
    pass

class HandoffResolveRequest(BaseModel):
    resolution_message: str

class HandoffTransferRequest(BaseModel):
    expert_id: Optional[int] = None

class HandoffStats(BaseModel):
    queue_size: int
    active_chats: int
    resolved_count: int
    average_csat: Optional[float] = None


class LanguageContextRead(BaseModel):
    detected_language: Optional[str] = None
    is_code_mixed: Optional[bool] = False
    code_mix_type: Optional[str] = None
    normalized_message: Optional[str] = None
    original_message: Optional[str] = None
    negation_detected: Optional[bool] = False
    normalized_search_query: Optional[str] = None


class AIContextRead(BaseModel):
    intent: str = "Unknown"
    sentiment: str = "Neutral"
    summary: str = "No AI summary available"
    language_context: Optional[LanguageContextRead] = None
    confidence_score: Optional[float] = None
    autonomy_mode: Optional[str] = None


class CustomerContextRead(BaseModel):
    id: int
    name: Optional[str] = None
    email: str
    account_status: str = "Active"


class ActiveTicketRead(BaseModel):
    id: int
    category: str
    priority: str
    reason: str
    channel: Optional[str] = "text"


class TicketHistoryItem(BaseModel):
    id: int
    status: str
    created_at: str


class IncidentContextRead(BaseModel):
    incident_id: str
    title: str
    description: str
    category: str
    status: str = "candidate"
    severity: str = "MEDIUM"
    confidence: float
    related_ticket_count: int
    related_tickets: list[dict] = []
    time_window_start: Optional[str] = None
    time_window_end: Optional[str] = None
    evidence: list[str] = []
    is_spike: bool = False
    spike_ratio: Optional[float] = None


class FailureRiskRead(BaseModel):
    risk_level: str = "LOW"  # LOW, MODERATE, HIGH, VERY_HIGH
    probability: float = 0.0
    predicted_difficulty: str = "LOW"  # LOW, MODERATE, HIGH, COMPLEX
    signals: list[str] = []
    observed_failure_count: int = 0
    has_prior_solution_failed: bool = False
    suggested_action: Optional[str] = None
    priority_rationale: Optional[str] = None


class HandoffContextResponse(BaseModel):
    customer: CustomerContextRead
    active_ticket: ActiveTicketRead
    ai_context: AIContextRead
    ticket_history: list[TicketHistoryItem]
    language_context: Optional[LanguageContextRead] = None
    confidence_score: Optional[float] = None
    incident_context: Optional[IncidentContextRead] = None
    failure_risk: Optional[FailureRiskRead] = None



