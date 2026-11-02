"""
Capability 1: Resolution Confidence Scoring

Multi-factor confidence scorer that evaluates whether the AI can safely resolve
a customer issue. Outputs a 0-100 confidence score with factor breakdown.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ConfidenceFactors:
    """Individual confidence factor scores (0.0 - 1.0)."""
    intent_clarity: float = 0.0
    context_completeness: float = 0.0
    knowledge_availability: float = 0.0
    tool_availability: float = 0.0
    historical_success: float = 0.0
    risk_level: float = 1.0  # 1.0 = lowest risk, 0.0 = highest risk


@dataclass
class ConfidenceScore:
    """Aggregated confidence result."""
    overall: float = 0.0  # 0-100
    factors: ConfidenceFactors = field(default_factory=ConfidenceFactors)
    recommendation: str = "ESCALATE"  # RESOLVE | CONFIRM | ESCALATE
    reasoning: str = ""


class ResolutionConfidenceScorer:
    """
    Scores the AI's confidence in resolving a customer issue.

    Used by the Adaptive Autonomy Engine to determine whether to auto-resolve,
    ask for confirmation, or escalate to a human expert.
    """

    # Intents the system can handle well
    HIGH_CLARITY_INTENTS = {
        "PAYMENT_ISSUE", "DELIVERY_ISSUE", "LOGIN_ISSUE",
        "GENERAL_QUERY", "GREETING",
    }
    
    # Intents that need special handling
    MODERATE_INTENTS = {"REFUND_ISSUE", "UPDATE_ISSUE"}
    
    # Intents that require escalation
    ESCALATION_INTENTS = {"SECURITY_ISSUE"}

    # Required entities per intent
    REQUIRED_ENTITIES = {
        "PAYMENT_ISSUE": ["transaction_id"],
        "DELIVERY_ISSUE": ["order_id"],
    }

    # High-risk tool operations
    HIGH_RISK_TOOLS = {"create_refund_request", "update_account"}
    MEDIUM_RISK_TOOLS = {"create_support_ticket", "update_ticket_info"}

    def score(self, analysis: Dict[str, Any], context: Dict[str, Any]) -> ConfidenceScore:
        """
        Score the AI's confidence in resolving this issue.
        
        Args:
            analysis: The AI analysis result (intent, entities, sentiment, etc.)
            context: Conversation context (history, rag results, memories, etc.)
        
        Returns:
            ConfidenceScore with overall score, factor breakdown, and recommendation.
        """
        factors = ConfidenceFactors()

        # 1. Intent Clarity
        factors.intent_clarity = self._score_intent_clarity(analysis)

        # 2. Context Completeness (entities available vs required)
        factors.context_completeness = self._score_context_completeness(analysis)

        # 3. Knowledge Availability (RAG results)
        factors.knowledge_availability = self._score_knowledge(context)

        # 4. Tool Availability
        factors.tool_availability = self._score_tool_availability(analysis, context)

        # 5. Historical Success (memory-based)
        factors.historical_success = self._score_historical(context)

        # 6. Risk Level (inverted: 1.0 = safe, 0.0 = risky)
        factors.risk_level = self._score_risk(analysis, context)

        # Aggregate
        overall = self._aggregate(factors)
        recommendation = self._recommend(overall, factors)
        reasoning = self._build_reasoning(factors, overall, recommendation)

        return ConfidenceScore(
            overall=overall,
            factors=factors,
            recommendation=recommendation,
            reasoning=reasoning,
        )

    def _score_intent_clarity(self, analysis: Dict[str, Any]) -> float:
        intent = analysis.get("intent", "GENERAL_QUERY")
        if intent in self.HIGH_CLARITY_INTENTS:
            return 0.9
        if intent in self.MODERATE_INTENTS:
            return 0.6
        if intent in self.ESCALATION_INTENTS:
            return 0.3
        return 0.5  # Unknown intent

    def _score_context_completeness(self, analysis: Dict[str, Any]) -> float:
        intent = analysis.get("intent", "")
        entities = analysis.get("entities", {})
        required = self.REQUIRED_ENTITIES.get(intent, [])

        if not required:
            return 1.0  # No specific entities needed

        fulfilled = sum(1 for r in required if r in entities)
        return fulfilled / len(required)

    def _score_knowledge(self, context: Dict[str, Any]) -> float:
        rag_results = context.get("rag_results", [])
        if not rag_results:
            return 0.2  # No knowledge available
        
        # Check best match score
        best_score = max((r.get("score", 0) for r in rag_results), default=0)
        if best_score > 0.5:
            return 1.0
        if best_score > 0.2:
            return 0.7
        if best_score > 0.05:
            return 0.5
        return 0.3

    def _score_tool_availability(self, analysis: Dict[str, Any], context: Dict[str, Any]) -> float:
        decision_state = analysis.get("decision_state", "")
        tool_name = analysis.get("tool_name")

        if decision_state == "USE_TOOL" and tool_name:
            return 0.9  # Tool is available and selected
        if decision_state == "RESOLVE":
            return 1.0  # No tool needed
        if decision_state == "ASK_USER":
            return 0.7  # Waiting for info
        return 0.5

    def _score_historical(self, context: Dict[str, Any]) -> float:
        memories = context.get("relevant_memories", [])
        if not memories:
            return 0.5  # Neutral - no history

        # Check for positive resolution history
        positive_signals = sum(
            1 for m in memories
            if any(kw in str(m).lower() for kw in ["resolved", "fixed", "completed", "successful"])
        )
        negative_signals = sum(
            1 for m in memories
            if any(kw in str(m).lower() for kw in ["failed", "escalated", "unresolved", "complaint"])
        )

        if positive_signals > negative_signals:
            return 0.8
        if negative_signals > positive_signals:
            return 0.3
        return 0.5

    def _score_risk(self, analysis: Dict[str, Any], context: Dict[str, Any]) -> float:
        intent = analysis.get("intent", "")
        priority = analysis.get("priority", "LOW")
        tool_name = analysis.get("tool_name", "")
        sentiment = analysis.get("sentiment", "NEUTRAL")

        risk = 1.0  # Start safe

        # Priority risk
        if priority == "CRITICAL":
            risk -= 0.5
        elif priority == "HIGH":
            risk -= 0.3
        elif priority == "MEDIUM":
            risk -= 0.1

        # Tool risk
        if tool_name in self.HIGH_RISK_TOOLS:
            risk -= 0.3
        elif tool_name in self.MEDIUM_RISK_TOOLS:
            risk -= 0.15

        # Sentiment risk
        if sentiment == "NEGATIVE":
            risk -= 0.1

        # Security issues are always high risk
        if intent == "SECURITY_ISSUE":
            risk -= 0.4

        return max(0.0, min(1.0, risk))

    def _aggregate(self, factors: ConfidenceFactors) -> float:
        """Weighted average of all factors, scaled to 0-100."""
        weights = {
            "intent_clarity": 0.20,
            "context_completeness": 0.20,
            "knowledge_availability": 0.20,
            "tool_availability": 0.10,
            "historical_success": 0.10,
            "risk_level": 0.20,
        }
        
        total = (
            factors.intent_clarity * weights["intent_clarity"]
            + factors.context_completeness * weights["context_completeness"]
            + factors.knowledge_availability * weights["knowledge_availability"]
            + factors.tool_availability * weights["tool_availability"]
            + factors.historical_success * weights["historical_success"]
            + factors.risk_level * weights["risk_level"]
        )
        return round(total * 100, 2)

    def _recommend(self, overall: float, factors: ConfidenceFactors) -> str:
        """Determine recommendation based on overall score and critical factors."""
        # Hard escalation rules
        if factors.risk_level < 0.3:
            return "ESCALATE"
        if factors.intent_clarity < 0.4:
            return "ESCALATE"

        # Score-based recommendation
        if overall >= 70:
            return "RESOLVE"
        if overall >= 45:
            return "CONFIRM"
        return "ESCALATE"

    def _build_reasoning(self, factors: ConfidenceFactors, overall: float, recommendation: str) -> str:
        parts = [f"Overall confidence: {overall}%"]
        if factors.intent_clarity < 0.5:
            parts.append("Low intent clarity")
        if factors.context_completeness < 0.5:
            parts.append("Missing required context")
        if factors.knowledge_availability < 0.3:
            parts.append("Insufficient knowledge base coverage")
        if factors.risk_level < 0.5:
            parts.append("Elevated risk level")
        parts.append(f"Recommendation: {recommendation}")
        return "; ".join(parts)
