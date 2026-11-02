from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class AnalysisSchema(BaseModel):
    intent: str = Field(description="e.g., PAYMENT_ISSUE, LOGIN_ISSUE, DELIVERY_ISSUE, SECURITY_ISSUE, GENERAL_QUERY")
    sentiment: str = Field(description="positive, negative, or neutral")
    priority: str = Field(description="LOW, MEDIUM, HIGH, or CRITICAL")
    language: str = Field(description="detect the language (e.g., English, Tamil, Tanglish, Hindi, Hinglish)")
    entities: Dict[str, Any] = Field(description="a key-value map of important entities extracted (e.g., transaction_id: 'TXN123')", default_factory=dict)
    emotion: Optional[str] = Field(description="frustrated | confused | urgent | calm | satisfied | uncertain", default="calm")
    emotion_confidence: Optional[float] = Field(description="confidence score between 0.0 and 1.0", default=0.85)

class VoiceTurnSchema(BaseModel):
    intent: str = Field(description="e.g., PAYMENT_ISSUE, LOGIN_ISSUE, DELIVERY_ISSUE, SECURITY_ISSUE, GENERAL_QUERY")
    sentiment: str = Field(description="positive, negative, or neutral")
    priority: str = Field(description="LOW, MEDIUM, HIGH, or CRITICAL")
    language: str = Field(description="English, Tamil, Tanglish, Hindi, or Hinglish")
    emotion: str = Field(description="frustrated, confused, urgent, calm, satisfied, or uncertain", default="calm")
    emotion_confidence: float = Field(description="confidence score between 0.0 and 1.0", default=0.85)
    entities: Dict[str, Any] = Field(description="extracted entities like order_id, transaction_id, etc.", default_factory=dict)
    decision: str = Field(description="RESOLVE | ASK_USER | USE_TOOL | ESCALATE")
    spoken_response: str = Field(description="1 or 2 short conversational sentences (under 35 words). Empathetic, acknowledges customer concern first, zero formatting, natural code-mixed phrasing.")
    tool_name: Optional[str] = Field(description="tool name if decision is USE_TOOL, else null", default=None)
    tool_args: Dict[str, Any] = Field(description="tool arguments if USE_TOOL", default_factory=dict)
    reason: str = Field(description="brief internal reasoning", default="")


class DecisionSchema(BaseModel):
    decision: str = Field(description="RESOLVE | ASK_USER | USE_TOOL | ESCALATE")
    response_text: str = Field(description="The message to send to the customer (if resolving, asking, or escalating).")
    tool_name: Optional[str] = Field(description="name of the tool if decision is USE_TOOL, else null", default=None)
    tool_args: Dict[str, Any] = Field(description="arguments for the tool if decision is USE_TOOL, else empty object", default_factory=dict)
    reason: str = Field(description="Internal reasoning for this decision.")
    confidence: float = Field(description="Confidence score between 0.0 and 1.0", default=1.0)

class MemoryItemSchema(BaseModel):
    type: str = Field(description="ISSUE_HISTORY, RESOLUTION, PREFERENCE, or FACT")
    content: str = Field(description="concise summary of the fact")
    importance: str = Field(description="HIGH, MEDIUM, or LOW")
    confidence: str = Field(description="HIGH or MEDIUM")

class MemoryExtractionSchema(BaseModel):
    memories: List[MemoryItemSchema] = Field(description="List of extracted memories")

class SemanticValidationSchema(BaseModel):
    status: str = Field(description="VALID or FAIL")
    violation_type: Optional[str] = Field(description="UNSUPPORTED_CLAIM or CONTRADICTION or null")
    reason: Optional[str] = Field(description="Explanation of why it failed, or null if valid")
