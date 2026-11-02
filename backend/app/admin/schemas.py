"""
ResolveAIV2 — Admin Autonomy Schemas
"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class AutonomyUpdateRequest(BaseModel):
    mode: str = Field(..., description="Autonomy mode: conservative, balanced, high_automation")
    tenant_id: Optional[str] = Field(None, description="Target tenant ID")
    auto_resolve_min_confidence: Optional[float] = Field(None, ge=60.0, le=95.0)
    auto_resolve_max_risk: Optional[float] = Field(None, ge=0.05, le=0.40)
    confirm_min_confidence: Optional[float] = Field(None, ge=35.0, le=80.0)
    confirm_max_risk: Optional[float] = Field(None, ge=0.20, le=0.70)
    frustration_escalation_threshold: Optional[float] = Field(None, ge=0.30, le=0.90)
    max_attempts_before_escalate: Optional[int] = Field(None, ge=1, le=5)
    policy_overrides: Optional[Dict[str, Any]] = None


class ModeDescription(BaseModel):
    mode: str
    title: str
    description: str
    safety_summary: str


class AutonomyConfigResponse(BaseModel):
    mode: str
    tenant_id: str
    auto_resolve_min_confidence: float
    auto_resolve_max_risk: float
    confirm_min_confidence: float
    confirm_max_risk: float
    frustration_escalation_threshold: float
    max_attempts_before_escalate: int
    policy_overrides: Dict[str, Any] = {}
    allowed_bounds: Dict[str, List[float]]
    modes_info: List[ModeDescription]
    recent_audit_trail: List[Dict[str, Any]] = []
    safety_invariants: List[str]
