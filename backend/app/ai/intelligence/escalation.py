"""
Capability 5: Resolution vs Escalation Intelligence

Determines whether the AI should resolve autonomously, ask for confirmation,
or escalate to a human expert based on multi-dimensional analysis.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum

from app.ai.intelligence.confidence import ResolutionConfidenceScorer, ConfidenceScore

logger = logging.getLogger(__name__)


class EscalationDecision(str, Enum):
    RESOLVE = "RESOLVE"
    CONFIRM = "CONFIRM"
    ESCALATE = "ESCALATE"


@dataclass
class EscalationContext:
    """Context prepared for human expert when escalating."""
    reason: str = ""
    confidence_score: float = 0.0
    issue_summary: str = ""
    customer_sentiment: str = "NEUTRAL"
    ai_actions_taken: List[str] = field(default_factory=list)
    collected_entities: Dict[str, Any] = field(default_factory=dict)
    recommended_specialization: str = "General Support"
    priority: str = "MEDIUM"


@dataclass
class EscalationResult:
    """Result of escalation decision analysis."""
    decision: EscalationDecision = EscalationDecision.ESCALATE
    confidence: ConfidenceScore = field(default_factory=ConfidenceScore)
    context: EscalationContext = field(default_factory=EscalationContext)
    reasoning: str = ""


class EscalationDecisionEngine:
    """
    Analyzes whether the AI should resolve, confirm, or escalate.
    Combines confidence scoring with business rules.
    """

    # Issues that ALWAYS require human review
    ALWAYS_ESCALATE_INTENTS = {"SECURITY_ISSUE"}
    
    # Issues that always require confirmation before action
    ALWAYS_CONFIRM_INTENTS = {"REFUND_ISSUE", "UPDATE_ISSUE"}

    # Priority -> escalation weight map
    PRIORITY_ESCALATION_WEIGHT = {
        "CRITICAL": 1.0,
        "HIGH": 0.6,
        "MEDIUM": 0.3,
        "LOW": 0.1,
    }

    # Specialization mapping
    INTENT_TO_SPECIALIZATION = {
        "PAYMENT_ISSUE": "Payments/Finance",
        "SECURITY_ISSUE": "Security",
        "DELIVERY_ISSUE": "Delivery/Logistics",
        "LOGIN_ISSUE": "Account/Auth",
        "REFUND_ISSUE": "Payments/Finance",
        "UPDATE_ISSUE": "Account/Auth",
    }

    def __init__(self):
        self.confidence_scorer = ResolutionConfidenceScorer()

    def evaluate(self, analysis: Dict[str, Any], context: Dict[str, Any]) -> EscalationResult:
        """
        Evaluate whether to resolve, confirm, or escalate.
        
        Args:
            analysis: AI analysis result
            context: Conversation context including history, memories, RAG results
        
        Returns:
            EscalationResult with decision, confidence score, and escalation context.
        """
        intent = str(analysis.get("intent", "GENERAL_QUERY")).upper()
        priority = str(analysis.get("priority", "LOW")).upper()
        sentiment = str(analysis.get("sentiment", "NEUTRAL")).upper()

        # Step 1: Score confidence
        confidence = self.confidence_scorer.score(analysis, context)

        # Step 2: Apply hard rules
        from app.ai.intelligence.escalation_keywords import is_supervisor_demand, is_fraud_or_security
        orig_msg = str(analysis.get("original_message", "")).lower()
        if is_supervisor_demand(orig_msg):
            return self._build_result(
                EscalationDecision.ESCALATE,
                confidence,
                analysis,
                context,
                "Explicit customer request for human support",
            )

        if is_fraud_or_security(orig_msg) or (intent in self.ALWAYS_ESCALATE_INTENTS and priority == "CRITICAL"):
            return self._build_result(
                EscalationDecision.ESCALATE,
                confidence,
                analysis,
                context,
                "Security-sensitive issue or fraud report requires human review",
            )

        if priority == "CRITICAL":
            return self._build_result(
                EscalationDecision.ESCALATE,
                confidence,
                analysis,
                context,
                "CRITICAL priority always escalated",
            )

        if intent in self.ALWAYS_CONFIRM_INTENTS:
            return self._build_result(
                EscalationDecision.CONFIRM if confidence.overall >= 40 else EscalationDecision.ESCALATE,
                confidence,
                analysis,
                context,
                f"Intent {intent} requires confirmation",
            )

        # Step 3: Confidence-based decision
        decision = EscalationDecision(confidence.recommendation)

        # Step 4: Sentiment override — frustrated customers get escalated faster
        if sentiment == "NEGATIVE" and confidence.overall < 60:
            decision = EscalationDecision.ESCALATE

        # Step 5: Repeated attempt detection
        attempt_count = context.get("attempt_count", 0)
        if attempt_count >= 3:
            decision = EscalationDecision.ESCALATE

        return self._build_result(
            decision, confidence, analysis, context,
            f"Confidence-based: {confidence.overall}%, sentiment: {sentiment}",
        )

    def _build_result(
        self,
        decision: EscalationDecision,
        confidence: ConfidenceScore,
        analysis: Dict[str, Any],
        context: Dict[str, Any],
        reasoning: str,
    ) -> EscalationResult:
        intent = analysis.get("intent", "GENERAL_QUERY")
        
        esc_context = EscalationContext(
            reason=reasoning,
            confidence_score=confidence.overall,
            issue_summary=analysis.get("original_message", "")[:200],
            customer_sentiment=analysis.get("sentiment", "NEUTRAL"),
            collected_entities=analysis.get("entities", {}),
            recommended_specialization=self.INTENT_TO_SPECIALIZATION.get(intent, "General Support"),
            priority=analysis.get("priority", "MEDIUM"),
        )

        return EscalationResult(
            decision=decision,
            confidence=confidence,
            context=esc_context,
            reasoning=reasoning,
        )
