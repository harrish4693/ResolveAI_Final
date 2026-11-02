"""
M12.5 — AI Response Validation Models

Structured data models for the validation pipeline.
These models define the context passed to the validator and the result it produces.
"""

import enum
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime


class ValidationStatus(str, enum.Enum):
    """Outcome of the validation pipeline."""
    VALID = "VALID"
    REGENERATE = "REGENERATE"
    ASK_CLARIFICATION = "ASK_CLARIFICATION"
    ESCALATE = "ESCALATE"


class CheckResult(str, enum.Enum):
    """Result of an individual validation check."""
    PASS_ = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass
class ValidationViolation:
    """A single violation detected by the validator."""
    check_name: str          # e.g. "TOOL_TRUTHFULNESS", "SECURITY"
    violation_type: str      # e.g. "FABRICATED_TOOL_RESULT", "CROSS_CUSTOMER_LEAK"
    reason: str              # Human-readable explanation
    severity: str = "HIGH"   # HIGH, MEDIUM, LOW


@dataclass
class ValidationChecks:
    """Individual check outcomes."""
    structural: CheckResult = CheckResult.SKIP
    security: CheckResult = CheckResult.SKIP
    tool_truthfulness: CheckResult = CheckResult.SKIP
    action_truthfulness: CheckResult = CheckResult.SKIP
    contradiction: CheckResult = CheckResult.SKIP
    memory_consistency: CheckResult = CheckResult.SKIP
    intent_alignment: CheckResult = CheckResult.SKIP
    grounding: CheckResult = CheckResult.SKIP
    response_quality: CheckResult = CheckResult.SKIP
    language_consistency: CheckResult = CheckResult.SKIP

    def to_dict(self) -> Dict[str, str]:
        return {
            "structural": self.structural.value,
            "security": self.security.value,
            "tool_truthfulness": self.tool_truthfulness.value,
            "action_truthfulness": self.action_truthfulness.value,
            "contradiction": self.contradiction.value,
            "memory_consistency": self.memory_consistency.value,
            "intent_alignment": self.intent_alignment.value,
            "grounding": self.grounding.value,
            "response_quality": self.response_quality.value,
            "language_consistency": self.language_consistency.value,
        }


@dataclass
class ValidationResult:
    """Output of the validation pipeline."""
    status: ValidationStatus
    violations: List[ValidationViolation] = field(default_factory=list)
    checks: ValidationChecks = field(default_factory=ValidationChecks)
    reasons: List[str] = field(default_factory=list)
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "violations": [
                {"check_name": v.check_name, "violation_type": v.violation_type, "reason": v.reason, "severity": v.severity}
                for v in self.violations
            ],
            "checks": self.checks.to_dict(),
            "reasons": self.reasons,
            "confidence": self.confidence,
        }

    @property
    def correction_instructions(self) -> str:
        """Build internal correction instructions for regeneration (never shown to customer)."""
        if not self.violations:
            return ""
        lines = ["Correct the following issues in your response:"]
        for v in self.violations:
            lines.append(f"- [{v.check_name}] {v.reason}")
        return "\n".join(lines)


@dataclass
class ToolResultContext:
    """Structured representation of a tool execution result."""
    tool_name: str
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error_code: Optional[str] = None


@dataclass
class ResponseValidationContext:
    """
    All context the validator needs to evaluate a draft response.
    Constructed by ConversationService from server-derived authoritative data.
    """
    conversation_id: int
    customer_id: int
    user_message: str
    conversation_history: List[Dict[str, Any]] = field(default_factory=list)
    detected_intent: str = ""
    detected_language: str = "en"
    sentiment: str = "neutral"
    memory_context: List[str] = field(default_factory=list)
    rag_context: List[Dict[str, Any]] = field(default_factory=list)
    tool_results: List[ToolResultContext] = field(default_factory=list)
    agent_decision: str = ""
    draft_response: str = ""

    # Server-derived authorization data for security validation
    authorized_order_ids: List[str] = field(default_factory=list)
    authorized_ticket_ids: List[str] = field(default_factory=list)
    internal_notes: List[str] = field(default_factory=list)
    preferred_language: Optional[str] = None

    # Regeneration tracking
    attempt_number: int = 1
    previous_violations: List[str] = field(default_factory=list)
