"""
Capability 7: Resolution Failure Prediction

Predicts when the current resolution approach is likely to fail,
enabling early escalation before customer frustration builds.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class FailureLikelihood(str, Enum):
    LOW = "LOW"           # < 30% chance of failure
    MODERATE = "MODERATE"  # 30-60%
    HIGH = "HIGH"          # 60-85%
    VERY_HIGH = "VERY_HIGH"  # > 85%


@dataclass
class ResolutionAttempt:
    """Tracks a single resolution attempt."""
    approach: str = ""          # e.g., "rag_lookup", "tool_execution", "ask_user"
    success: bool = False
    error_message: str = ""
    duration_seconds: float = 0.0


@dataclass
class FailurePrediction:
    """Result of failure prediction analysis."""
    likelihood: FailureLikelihood = FailureLikelihood.LOW
    probability: float = 0.0    # 0.0 - 1.0
    should_escalate_early: bool = False
    reasons: List[str] = field(default_factory=list)
    frustration_level: float = 0.0  # 0.0 - 1.0
    recommendation: str = ""
    predicted_difficulty: str = "LOW"  # LOW, MODERATE, HIGH, COMPLEX
    observed_failure_count: int = 0
    has_prior_solution_failed: bool = False
    suggested_action: str = ""



class ResolutionAttemptTracker:
    """
    Tracks resolution attempts for a conversation to detect patterns
    that indicate likely failure.
    """

    def __init__(self):
        self._attempts: Dict[int, List[ResolutionAttempt]] = {}  # conversation_id -> attempts

    def track_attempt(self, conversation_id: int, approach: str, success: bool,
                      error_message: str = "", duration_seconds: float = 0.0):
        """Track a resolution attempt."""
        if conversation_id not in self._attempts:
            self._attempts[conversation_id] = []

        self._attempts[conversation_id].append(ResolutionAttempt(
            approach=approach,
            success=success,
            error_message=error_message,
            duration_seconds=duration_seconds,
        ))

    def get_attempts(self, conversation_id: int) -> List[ResolutionAttempt]:
        """Get all attempts for a conversation."""
        return self._attempts.get(conversation_id, [])

    def get_attempt_count(self, conversation_id: int) -> int:
        return len(self._attempts.get(conversation_id, []))

    def get_failure_count(self, conversation_id: int) -> int:
        attempts = self._attempts.get(conversation_id, [])
        return sum(1 for a in attempts if not a.success)

    def get_success_rate(self, conversation_id: int) -> float:
        attempts = self._attempts.get(conversation_id, [])
        if not attempts:
            return 0.5  # Unknown
        successes = sum(1 for a in attempts if a.success)
        return successes / len(attempts)

    def clear(self, conversation_id: int):
        """Clear tracking for a conversation."""
        self._attempts.pop(conversation_id, None)


class FrustrationDetector:
    """
    Detects customer frustration from conversation patterns
    and message content.
    """

    # Frustration signals in text
    FRUSTRATION_KEYWORDS = {
        "angry", "frustrated", "upset", "terrible", "worst", "horrible",
        "ridiculous", "unacceptable", "useless", "waste", "pathetic",
        "can't believe", "fed up", "sick of", "enough", "already told",
        "how many times", "still not", "nothing works", "keeps happening",
    }

    # Escalation request signals
    ESCALATION_SIGNALS = {
        "talk to someone", "human", "supervisor", "manager",
        "real person", "escalate", "agent", "representative",
    }

    def estimate_frustration(
        self,
        message: str,
        history: List[Dict[str, Any]],
        attempt_count: int = 0,
    ) -> float:
        """
        Estimate customer frustration level (0.0 - 1.0).
        
        Factors:
        - Explicit frustration keywords
        - Conversation length
        - Repeated attempts
        - Escalation requests
        """
        score = 0.0
        text_lower = message.lower()

        # 1. Frustration keywords
        keyword_hits = sum(1 for kw in self.FRUSTRATION_KEYWORDS if kw in text_lower)
        score += min(keyword_hits * 0.15, 0.4)

        # 2. Escalation requests
        escalation_hits = sum(1 for kw in self.ESCALATION_SIGNALS if kw in text_lower)
        score += min(escalation_hits * 0.2, 0.3)

        # 3. Conversation length (long conversations indicate unresolved issues)
        msg_count = len(history)
        if msg_count > 10:
            score += 0.3
        elif msg_count > 6:
            score += 0.15
        elif msg_count > 3:
            score += 0.05

        # 4. Failed attempts
        if attempt_count >= 3:
            score += 0.3
        elif attempt_count >= 2:
            score += 0.15
        elif attempt_count >= 1:
            score += 0.05

        # 5. ALL CAPS detection (shouting)
        upper_words = sum(1 for w in message.split() if w.isupper() and len(w) > 2)
        if upper_words >= 3:
            score += 0.2

        # 6. Excessive punctuation (!!! or ???)
        if re.search(r'[!?]{3,}', message):
            score += 0.1

        return min(1.0, score)


import re

class FailurePredictor:
    """
    Predicts the probability that the current resolution approach will fail.
    Combines multiple signals for an ensemble prediction.
    """

    def __init__(self):
        self.frustration_detector = FrustrationDetector()

    def predict(
        self,
        analysis: Dict[str, Any],
        context: Dict[str, Any],
        attempt_tracker: Optional[ResolutionAttemptTracker] = None,
        conversation_id: int = 0,
    ) -> FailurePrediction:
        """
        Predict failure probability for the current resolution.
        
        Args:
            analysis: AI analysis result
            context: Conversation context
            attempt_tracker: Optional tracker with historical attempts
            conversation_id: Current conversation ID
        
        Returns:
            FailurePrediction with probability, likelihood, and recommendations.
        """
        reasons: List[str] = []
        probability = 0.0

        # 1. Intent complexity
        intent = analysis.get("intent", "GENERAL_QUERY")
        complexity_risk = self._assess_intent_complexity(intent)
        probability += complexity_risk * 0.2
        if complexity_risk > 0.6:
            reasons.append(f"Complex intent: {intent}")

        # 2. Missing entities
        entities = analysis.get("entities", {})
        decision_state = analysis.get("decision_state", "")
        if decision_state == "ASK_USER":
            probability += 0.15
            reasons.append("Waiting for additional information")

        # 3. Attempt history
        attempt_count = 0
        failure_count = 0
        if attempt_tracker:
            attempt_count = attempt_tracker.get_attempt_count(conversation_id)
            failure_count = attempt_tracker.get_failure_count(conversation_id)
        else:
            attempt_count = context.get("attempt_count", 0)
            failure_count = context.get("observed_failure_count", 0)

        if attempt_count > 0:
            failure_rate = failure_count / attempt_count
            probability += failure_rate * 0.25
            if failure_rate > 0.5:
                reasons.append(f"High failure rate: {failure_rate:.0%}")

        # 4. Customer frustration
        history = context.get("history", [])
        latest_message = analysis.get("original_message", "")
        frustration = self.frustration_detector.estimate_frustration(
            latest_message, history, attempt_count
        )
        probability += frustration * 0.25
        if frustration > 0.5:
            reasons.append(f"Customer frustration: {frustration:.0%}")

        # 5. RAG quality
        rag_results = context.get("rag_results", [])
        if not rag_results:
            probability += 0.1
            reasons.append("No knowledge base results")
        elif rag_results:
            best_score = max((r.get("score", 0) for r in rag_results), default=0)
            if best_score < 0.1:
                probability += 0.1
                reasons.append("Low knowledge base relevance")

        # 6. Sentiment analysis
        sentiment = analysis.get("sentiment", "NEUTRAL")
        if sentiment == "NEGATIVE":
            probability += 0.1
            reasons.append("Negative sentiment detected")

        # 7. Customer reporting prior suggested solution failed (observed failure vs predicted risk)
        has_prior_solution_failed = bool(context.get("has_prior_solution_failed", False))
        latest_lower = latest_message.lower() if isinstance(latest_message, str) else ""
        prior_failed_phrases = [
            "didn't work", "did not work", "not working", "still not working",
            "doesn't work", "does not work", "failed again", "tried that",
            "solution didn't work", "solution failed", "still having this issue",
            "already tried", "tried already"
        ]
        if any(phrase in latest_lower for phrase in prior_failed_phrases):
            has_prior_solution_failed = True

        if has_prior_solution_failed:
            probability += 0.2
            reasons.append("Customer reported previous solution did not work")

        # 8. Recurring complaint in previous tickets
        ticket_history = context.get("ticket_history", [])
        if ticket_history and isinstance(ticket_history, list):
            same_issue_count = sum(
                1 for t in ticket_history
                if isinstance(t, dict) and (
                    t.get("category") == analysis.get("category") or
                    t.get("intent") == intent or
                    (intent and intent.replace("_", " ").lower() in str(t.get("subject", "")).lower())
                )
            )
            if same_issue_count > 0:
                probability += min(same_issue_count * 0.1, 0.2)
                reasons.append(f"Recurring complaint: {same_issue_count} prior ticket(s) with matching issue")

        # Clamp probability
        probability = min(1.0, max(0.0, probability))

        # Determine likelihood
        if probability >= 0.85:
            likelihood = FailureLikelihood.VERY_HIGH
        elif probability >= 0.6:
            likelihood = FailureLikelihood.HIGH
        elif probability >= 0.3:
            likelihood = FailureLikelihood.MODERATE
        else:
            likelihood = FailureLikelihood.LOW

        # Should we escalate early?
        should_escalate = (
            probability >= 0.6
            or frustration >= 0.7
            or failure_count >= 3
        )

        # Build recommendation & suggested action
        if should_escalate:
            recommendation = "Escalate to human expert immediately"
            suggested_action = "Escalate to human expert with context"
        elif has_prior_solution_failed:
            recommendation = "Review previous solution failure and prepare human handoff"
            suggested_action = "Investigate previous solution failure and verify customer state"
        elif decision_state == "ASK_USER":
            recommendation = "Ask targeted clarification before attempting resolution"
            suggested_action = "Ask targeted clarification for missing details"
        elif likelihood in (FailureLikelihood.HIGH, FailureLikelihood.VERY_HIGH):
            recommendation = "Monitor closely; prepare escalation context"
            suggested_action = "Prepare escalation context and review account history"
        elif likelihood == FailureLikelihood.MODERATE:
            recommendation = "Monitor resolution progress; verify knowledge relevance"
            suggested_action = "Check additional knowledge and confirm parameters"
        else:
            recommendation = "Continue with AI resolution"
            suggested_action = "Continue standard automated resolution workflow"

        # Determine predicted difficulty
        if complexity_risk >= 0.7 or probability >= 0.6:
            predicted_difficulty = "COMPLEX"
        elif complexity_risk >= 0.4 or probability >= 0.4:
            predicted_difficulty = "HIGH"
        elif complexity_risk >= 0.3 or probability >= 0.25:
            predicted_difficulty = "MODERATE"
        else:
            predicted_difficulty = "LOW"

        return FailurePrediction(
            likelihood=likelihood,
            probability=round(probability, 3),
            should_escalate_early=should_escalate,
            reasons=reasons,
            frustration_level=round(frustration, 3),
            recommendation=recommendation,
            predicted_difficulty=predicted_difficulty,
            observed_failure_count=failure_count,
            has_prior_solution_failed=has_prior_solution_failed,
            suggested_action=suggested_action,
        )

    def _assess_intent_complexity(self, intent: str) -> float:
        complexity_map = {
            "GREETING": 0.0,
            "GENERAL_QUERY": 0.2,
            "DELIVERY_ISSUE": 0.3,
            "PAYMENT_ISSUE": 0.4,
            "LOGIN_ISSUE": 0.4,
            "REFUND_ISSUE": 0.7,
            "UPDATE_ISSUE": 0.5,
            "SECURITY_ISSUE": 0.9,
        }
        return complexity_map.get(intent, 0.5)


# Global singleton instance for application-wide attempt tracking across turns
global_attempt_tracker = ResolutionAttemptTracker()
