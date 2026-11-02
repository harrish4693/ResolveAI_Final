"""
Capability 9: Adaptive Autonomy Engine

Dynamically adjusts AI autonomy level based on confidence, risk,
authorization, and customer history. Three levels:
  - AUTOMATIC: AI resolves without human intervention
  - CONFIRMATION_REQUIRED: AI proposes, customer confirms
  - ESCALATE: Route to human expert
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum

from app.ai.intelligence.confidence import ResolutionConfidenceScorer, ConfidenceScore

logger = logging.getLogger(__name__)


class AutonomyLevel(str, Enum):
    AUTOMATIC = "AUTOMATIC"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
    ESCALATE = "ESCALATE"


class AutonomyMode(str, Enum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    HIGH_AUTOMATION = "high_automation"


@dataclass
class AutonomyThresholds:
    """Configurable thresholds for autonomy level determination."""
    auto_resolve_min_confidence: float = 75.0
    auto_resolve_max_risk: float = 0.25
    confirm_min_confidence: float = 45.0
    confirm_max_risk: float = 0.55
    frustration_escalation_threshold: float = 0.7
    max_attempts_before_escalate: int = 3


MODE_THRESHOLDS: Dict[AutonomyMode, AutonomyThresholds] = {
    AutonomyMode.CONSERVATIVE: AutonomyThresholds(
        auto_resolve_min_confidence=85.0,
        auto_resolve_max_risk=0.15,
        confirm_min_confidence=60.0,
        confirm_max_risk=0.40,
        frustration_escalation_threshold=0.50,
        max_attempts_before_escalate=2,
    ),
    AutonomyMode.BALANCED: AutonomyThresholds(
        auto_resolve_min_confidence=75.0,
        auto_resolve_max_risk=0.25,
        confirm_min_confidence=45.0,
        confirm_max_risk=0.55,
        frustration_escalation_threshold=0.70,
        max_attempts_before_escalate=3,
    ),
    AutonomyMode.HIGH_AUTOMATION: AutonomyThresholds(
        auto_resolve_min_confidence=65.0,
        auto_resolve_max_risk=0.35,
        confirm_min_confidence=40.0,
        confirm_max_risk=0.60,
        frustration_escalation_threshold=0.80,
        max_attempts_before_escalate=4,
    ),
}

# Validation bounds for administrator threshold overrides
THRESHOLD_BOUNDS = {
    "auto_resolve_min_confidence": (60.0, 95.0),
    "auto_resolve_max_risk": (0.05, 0.40),
    "confirm_min_confidence": (35.0, 80.0),
    "confirm_max_risk": (0.20, 0.70),
    "frustration_escalation_threshold": (0.30, 0.90),
    "max_attempts_before_escalate": (1, 5),
}


@dataclass
class AutonomyConfigDTO:
    """Data transfer object for tenant-scoped autonomy configuration."""
    mode: AutonomyMode = AutonomyMode.BALANCED
    thresholds: AutonomyThresholds = field(default_factory=AutonomyThresholds)
    policy_overrides: Dict[str, Any] = field(default_factory=dict)
    tenant_id: str = "default"

    @classmethod
    def default(cls, tenant_id: str = "default") -> "AutonomyConfigDTO":
        return cls(
            mode=AutonomyMode.BALANCED,
            thresholds=MODE_THRESHOLDS[AutonomyMode.BALANCED],
            policy_overrides={},
            tenant_id=tenant_id,
        )

    @classmethod
    def for_mode(
        cls,
        mode: AutonomyMode | str,
        tenant_id: str = "default",
        custom_overrides: Optional[Dict[str, Any]] = None,
    ) -> "AutonomyConfigDTO":
        if isinstance(mode, str):
            try:
                mode_enum = AutonomyMode(mode.lower())
            except ValueError:
                raise ValueError(f"Invalid autonomy mode '{mode}'. Must be one of: {[m.value for m in AutonomyMode]}")
        else:
            mode_enum = mode

        base_thresholds = MODE_THRESHOLDS[mode_enum]
        threshold_dict = {
            "auto_resolve_min_confidence": base_thresholds.auto_resolve_min_confidence,
            "auto_resolve_max_risk": base_thresholds.auto_resolve_max_risk,
            "confirm_min_confidence": base_thresholds.confirm_min_confidence,
            "confirm_max_risk": base_thresholds.confirm_max_risk,
            "frustration_escalation_threshold": base_thresholds.frustration_escalation_threshold,
            "max_attempts_before_escalate": base_thresholds.max_attempts_before_escalate,
        }

        overrides = custom_overrides or {}
        # Validate and apply overrides within safety bounds
        for key, val in overrides.items():
            if key in THRESHOLD_BOUNDS:
                min_b, max_b = THRESHOLD_BOUNDS[key]
                if not (min_b <= float(val) <= max_b):
                    raise ValueError(
                        f"Override {key}={val} violates safety bounds ({min_b} to {max_b})"
                    )
                threshold_dict[key] = int(val) if key == "max_attempts_before_escalate" else float(val)

        return cls(
            mode=mode_enum,
            thresholds=AutonomyThresholds(**threshold_dict),
            policy_overrides=overrides,
            tenant_id=tenant_id,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode.value if hasattr(self.mode, "value") else str(self.mode),
            "tenant_id": self.tenant_id,
            "auto_resolve_min_confidence": self.thresholds.auto_resolve_min_confidence,
            "auto_resolve_max_risk": self.thresholds.auto_resolve_max_risk,
            "confirm_min_confidence": self.thresholds.confirm_min_confidence,
            "confirm_max_risk": self.thresholds.confirm_max_risk,
            "frustration_escalation_threshold": self.thresholds.frustration_escalation_threshold,
            "max_attempts_before_escalate": self.thresholds.max_attempts_before_escalate,
            "policy_overrides": self.policy_overrides,
        }


@dataclass
class AutonomyDecision:
    """Result of autonomy level determination."""
    level: AutonomyLevel = AutonomyLevel.ESCALATE
    confidence_score: float = 0.0
    risk_score: float = 0.0
    reasoning: str = ""
    factors: Dict[str, Any] = field(default_factory=dict)
    mode: str = "balanced"


class AutonomyLevelDeterminer:
    """
    Determines the appropriate autonomy level for each interaction.
    
    Level 1 (AUTOMATIC): Low-risk, high-confidence, informational queries.
    Level 2 (CONFIRMATION_REQUIRED): Moderate risk/confidence, tool execution needed.
    Level 3 (ESCALATE): High risk, low confidence, complex/sensitive issues.
    """

    def __init__(
        self,
        thresholds: Optional[AutonomyThresholds] = None,
        mode: AutonomyMode | str = AutonomyMode.BALANCED,
    ):
        if isinstance(mode, str):
            try:
                self.mode = AutonomyMode(mode.lower())
            except ValueError:
                self.mode = AutonomyMode.BALANCED
        else:
            self.mode = mode

        self.thresholds = thresholds or MODE_THRESHOLDS.get(self.mode, AutonomyThresholds())
        self.scorer = ResolutionConfidenceScorer()

    def determine_level(
        self,
        analysis: Dict[str, Any],
        context: Dict[str, Any],
        mode: Optional[AutonomyMode | str] = None,
    ) -> AutonomyDecision:
        """
        Determine the appropriate autonomy level considering configured autonomy mode.
        """
        active_mode = self.mode
        if mode is not None:
            if isinstance(mode, str):
                try:
                    active_mode = AutonomyMode(mode.lower())
                except ValueError:
                    active_mode = self.mode
            else:
                active_mode = mode

        # Score confidence
        confidence = self.scorer.score(analysis, context)
        risk_score = 1.0 - confidence.factors.risk_level  # Invert: higher = riskier

        intent = str(analysis.get("intent", "GENERAL_QUERY")).upper()
        priority = str(analysis.get("priority", "LOW")).upper()
        sentiment = str(analysis.get("sentiment", "NEUTRAL")).upper()
        decision_state = analysis.get("decision_state", "")
        tool_name = analysis.get("tool_name", "")

        factors = {
            "intent": intent,
            "priority": priority,
            "sentiment": sentiment,
            "confidence": confidence.overall,
            "risk": round(risk_score, 3),
            "tool_required": bool(tool_name),
            "autonomy_mode": active_mode.value,
        }

        # Hard Rule 1: CRITICAL priority → always escalate unconditionally
        if priority == "CRITICAL":
            return AutonomyDecision(
                level=AutonomyLevel.ESCALATE,
                confidence_score=confidence.overall,
                risk_score=risk_score,
                reasoning="CRITICAL priority requires mandatory expert escalation",
                factors=factors,
                mode=active_mode.value,
            )

        # Hard Rule 2: Security issues → always escalate unconditionally
        if intent == "SECURITY_ISSUE":
            return AutonomyDecision(
                level=AutonomyLevel.ESCALATE,
                confidence_score=confidence.overall,
                risk_score=risk_score,
                reasoning="Security issues require mandatory human review",
                factors=factors,
                mode=active_mode.value,
            )

        # Effective thresholds for active mode
        effective_thresholds = self.thresholds if active_mode == self.mode else MODE_THRESHOLDS.get(active_mode, self.thresholds)

        # Hard Rule 3: Too many attempts → escalate
        attempt_count = context.get("attempt_count", 0)
        if attempt_count >= effective_thresholds.max_attempts_before_escalate:
            return AutonomyDecision(
                level=AutonomyLevel.ESCALATE,
                confidence_score=confidence.overall,
                risk_score=risk_score,
                reasoning=f"Maximum resolution attempts ({attempt_count}) reached for {active_mode.value} mode",
                factors=factors,
                mode=active_mode.value,
            )

        # Hard Rule 4: Restricted / Irreversible tool actions strictly require confirmation
        RESTRICTED_TOOLS = {"create_refund_request", "update_account", "create_support_ticket", "update_ticket_info"}
        if tool_name in RESTRICTED_TOOLS or decision_state == "AWAITING_CONFIRMATION":
            return AutonomyDecision(
                level=AutonomyLevel.CONFIRMATION_REQUIRED,
                confidence_score=confidence.overall,
                risk_score=risk_score,
                reasoning=f"Restricted tool '{tool_name}' requires customer confirmation",
                factors=factors,
                mode=active_mode.value,
            )

        # Hard Rule 4b: Sensitive intents that always require confirmation (aligned with escalation engine)
        ALWAYS_CONFIRM_INTENTS = {"REFUND_ISSUE", "UPDATE_ISSUE"}
        orig_text = str(analysis.get("original_message", "")).lower()
        norm_text = str(analysis.get("normalized_message", "")).lower()
        is_policy_inquiry = any(k in orig_text or k in norm_text for k in [
            "policy", "rule", "terms", "how does", "what is", "how to", "procedure",
            "process", "pathi", "enna", "eppadi", "evlo", "evvalavu", "naatkal", "kulla", "days"
        ])
        if intent in ALWAYS_CONFIRM_INTENTS and not is_policy_inquiry:
            req_level = AutonomyLevel.CONFIRMATION_REQUIRED if confidence.overall >= 40 else AutonomyLevel.ESCALATE
            return AutonomyDecision(
                level=req_level,
                confidence_score=confidence.overall,
                risk_score=risk_score,
                reasoning=f"Intent {intent} requires customer confirmation or human review",
                factors=factors,
                mode=active_mode.value,
            )

        # Hard Rule 5: Observed or high failure risk influences escalation
        failure_risk = analysis.get("failure_risk", {})
        if isinstance(failure_risk, dict):
            if failure_risk.get("should_escalate_early") or failure_risk.get("has_prior_solution_failed"):
                return AutonomyDecision(
                    level=AutonomyLevel.ESCALATE,
                    confidence_score=confidence.overall,
                    risk_score=risk_score,
                    reasoning="High failure risk or prior solution failure mandates expert escalation",
                    factors=factors,
                    mode=active_mode.value,
                )
            if active_mode == AutonomyMode.CONSERVATIVE and (
                failure_risk.get("probability", 0.0) >= 0.45 or
                failure_risk.get("likelihood") in ("MODERATE", "HIGH", "VERY_HIGH")
            ):
                return AutonomyDecision(
                    level=AutonomyLevel.CONFIRMATION_REQUIRED,
                    confidence_score=confidence.overall,
                    risk_score=risk_score,
                    reasoning="Conservative mode: elevated failure risk requires clarification or human review",
                    factors=factors,
                    mode=active_mode.value,
                )

        # Mode-Aware Threshold Determination
        min_auto_conf = effective_thresholds.auto_resolve_min_confidence
        max_auto_risk = effective_thresholds.auto_resolve_max_risk
        min_conf_conf = effective_thresholds.confirm_min_confidence
        max_conf_risk = effective_thresholds.confirm_max_risk

        # In High Automation, only ELIGIBLE routine / low-risk requests can use the relaxed auto-threshold
        ROUTINE_LOW_RISK_INTENTS = {"GREETING", "GENERAL_QUERY", "DELIVERY_ISSUE"}
        if active_mode == AutonomyMode.HIGH_AUTOMATION and intent not in ROUTINE_LOW_RISK_INTENTS:
            # Sensitive or complex intents remain held to standard balanced thresholds
            min_auto_conf = max(min_auto_conf, 75.0)
            max_auto_risk = min(max_auto_risk, 0.25)

        # Threshold-based evaluation
        if confidence.overall >= min_auto_conf and risk_score <= max_auto_risk:
            level = AutonomyLevel.AUTOMATIC
            reasoning = f"Autonomous resolution approved ({active_mode.value} mode, conf {confidence.overall:.0f}%, risk {risk_score:.2f})"
        elif confidence.overall >= min_conf_conf and risk_score <= max_conf_risk:
            level = AutonomyLevel.CONFIRMATION_REQUIRED
            reasoning = f"Confirmation or clarification preferred ({active_mode.value} mode, conf {confidence.overall:.0f}%, risk {risk_score:.2f})"
        else:
            level = AutonomyLevel.ESCALATE
            reasoning = f"Low confidence ({confidence.overall:.0f}%) or elevated risk ({risk_score:.2f}) under {active_mode.value} policy"

        # Sentiment Overrides
        if sentiment == "NEGATIVE":
            if active_mode == AutonomyMode.CONSERVATIVE:
                # Conservative mode: any negative sentiment with non-exceptional confidence downgrades
                if level == AutonomyLevel.AUTOMATIC and confidence.overall < 90:
                    level = AutonomyLevel.CONFIRMATION_REQUIRED
                    reasoning += "; conservative sentiment protection"
            else:
                if level == AutonomyLevel.AUTOMATIC and confidence.overall < 80:
                    level = AutonomyLevel.CONFIRMATION_REQUIRED
                    reasoning += "; negative sentiment downgrade"

        return AutonomyDecision(
            level=level,
            confidence_score=confidence.overall,
            risk_score=risk_score,
            reasoning=reasoning,
            factors=factors,
            mode=active_mode.value,
        )


class AutonomyAdapter:
    """
    Adapts autonomy thresholds over time based on resolution outcomes.
    Provides per-intent threshold adjustment and learning from history.
    """

    def __init__(self):
        self._outcomes: Dict[str, List[bool]] = {}  # intent -> [success, success, fail, ...]
        self._threshold_adjustments: Dict[str, float] = {}

    def record_outcome(self, intent: str, was_successful: bool):
        """Record the outcome of an autonomous resolution."""
        if intent not in self._outcomes:
            self._outcomes[intent] = []
        self._outcomes[intent].append(was_successful)

        # Recalculate threshold adjustment
        outcomes = self._outcomes[intent]
        if len(outcomes) >= 5:  # Need minimum sample
            success_rate = sum(1 for o in outcomes if o) / len(outcomes)
            if success_rate > 0.9:
                self._threshold_adjustments[intent] = -5.0  # Lower threshold (more autonomy)
            elif success_rate < 0.5:
                self._threshold_adjustments[intent] = 10.0  # Raise threshold (less autonomy)
            else:
                self._threshold_adjustments[intent] = 0.0

    def get_adjusted_thresholds(self, intent: str) -> AutonomyThresholds:
        """Get thresholds adjusted for a specific intent's track record."""
        base = AutonomyThresholds()
        adjustment = self._threshold_adjustments.get(intent, 0.0)
        
        return AutonomyThresholds(
            auto_resolve_min_confidence=base.auto_resolve_min_confidence + adjustment,
            confirm_min_confidence=base.confirm_min_confidence + adjustment,
            auto_resolve_max_risk=base.auto_resolve_max_risk,
            confirm_max_risk=base.confirm_max_risk,
        )

    def get_success_rate(self, intent: str) -> Optional[float]:
        """Get the historical success rate for an intent."""
        outcomes = self._outcomes.get(intent, [])
        if not outcomes:
            return None
        return sum(1 for o in outcomes if o) / len(outcomes)

