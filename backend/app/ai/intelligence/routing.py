"""
Capability 10: Intelligent Expert Routing

Routes escalated cases to the most appropriate human expert based on
expertise matching, workload balancing, availability, and performance history.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


@dataclass
class ExpertProfile:
    """Profile of a human support expert."""
    expert_id: int = 0
    user_id: int = 0
    name: str = ""
    expertise_areas: List[str] = field(default_factory=list)  # e.g., ["Payments/Finance", "Security"]
    proficiency_levels: Dict[str, int] = field(default_factory=dict)  # area -> 1-5
    current_workload: int = 0
    max_concurrent: int = 5
    is_available: bool = True
    avg_resolution_time_minutes: float = 30.0
    satisfaction_rating: float = 4.0  # 1-5
    total_resolved: int = 0


@dataclass 
class RoutingCase:
    """A case that needs to be routed to an expert."""
    conversation_id: int = 0
    ticket_id: int = 0
    customer_id: int = 0
    category: str = "General Support"
    priority: str = "MEDIUM"
    required_expertise: List[str] = field(default_factory=list)
    customer_sentiment: str = "NEUTRAL"
    escalation_reason: str = ""
    entities: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RoutingScore:
    """Scoring breakdown for an expert-case match."""
    expert_id: int = 0
    expertise_match: float = 0.0
    workload_score: float = 0.0
    availability_score: float = 0.0
    performance_score: float = 0.0
    overall: float = 0.0


@dataclass
class RoutingDecision:
    """Final routing decision."""
    primary_expert_id: Optional[int] = None
    fallback_expert_id: Optional[int] = None
    scores: List[RoutingScore] = field(default_factory=list)
    reasoning: str = ""
    estimated_wait_minutes: float = 0.0


class ExpertMatcher:
    """
    Matches escalated cases to the best available expert based on
    expertise, workload, availability, and performance.
    """

    # Category → expertise area mapping
    CATEGORY_TO_EXPERTISE = {
        "Payments/Finance": ["Payments/Finance", "General Support"],
        "Security": ["Security", "Account/Auth"],
        "Delivery/Logistics": ["Delivery/Logistics", "General Support"],
        "Account/Auth": ["Account/Auth", "Security"],
        "General Support": ["General Support"],
    }

    def match(
        self,
        case: RoutingCase,
        experts: List[ExpertProfile],
    ) -> RoutingDecision:
        """
        Find the best expert match for a case.
        
        Args:
            case: The case to route
            experts: Available expert profiles
        
        Returns:
            RoutingDecision with primary and fallback expert selections.
        """
        if not experts:
            return RoutingDecision(
                reasoning="No experts available in the system",
                estimated_wait_minutes=60.0,
            )

        # Score each expert
        scores: List[RoutingScore] = []
        for expert in experts:
            score = self._score_expert(expert, case)
            scores.append(score)

        # Sort by overall score descending
        scores.sort(key=lambda s: s.overall, reverse=True)

        # Select primary and fallback
        primary = scores[0] if scores else None
        fallback = scores[1] if len(scores) > 1 else None

        # Build decision
        primary_id = primary.expert_id if primary and primary.overall > 0 else None
        fallback_id = fallback.expert_id if fallback and fallback.overall > 0 else None

        if primary_id is None:
            reasoning = "No suitable expert found for this case"
            estimated_wait = 60.0
        else:
            primary_expert = next(e for e in experts if e.expert_id == primary_id)
            reasoning = (
                f"Best match: Expert #{primary_id} "
                f"(expertise: {primary.expertise_match:.0%}, "
                f"workload: {primary.workload_score:.0%}, "
                f"performance: {primary.performance_score:.0%})"
            )
            # Estimate wait time based on workload
            utilization = primary_expert.current_workload / max(primary_expert.max_concurrent, 1)
            estimated_wait = primary_expert.avg_resolution_time_minutes * utilization

        return RoutingDecision(
            primary_expert_id=primary_id,
            fallback_expert_id=fallback_id,
            scores=scores,
            reasoning=reasoning,
            estimated_wait_minutes=round(estimated_wait, 1),
        )

    def _score_expert(self, expert: ExpertProfile, case: RoutingCase) -> RoutingScore:
        """Score a single expert against a case."""
        expertise_match = self._score_expertise(expert, case)
        workload_score = self._score_workload(expert)
        availability_score = self._score_availability(expert)
        performance_score = self._score_performance(expert)

        # Weighted combination
        overall = (
            expertise_match * 0.35
            + workload_score * 0.25
            + availability_score * 0.20
            + performance_score * 0.20
        )

        # Zero out if expert is unavailable or overloaded
        if not expert.is_available:
            overall = 0.0
        if expert.current_workload >= expert.max_concurrent:
            overall *= 0.1  # Heavily penalize but don't zero (for fallback)

        return RoutingScore(
            expert_id=expert.expert_id,
            expertise_match=round(expertise_match, 3),
            workload_score=round(workload_score, 3),
            availability_score=round(availability_score, 3),
            performance_score=round(performance_score, 3),
            overall=round(overall, 3),
        )

    def _score_expertise(self, expert: ExpertProfile, case: RoutingCase) -> float:
        """Score expertise match."""
        category = case.category
        desired_areas = self.CATEGORY_TO_EXPERTISE.get(category, ["General Support"])

        best_match = 0.0
        for area in desired_areas:
            if area in expert.expertise_areas:
                proficiency = expert.proficiency_levels.get(area, 3)
                match_score = proficiency / 5.0
                # Primary match gets full score, secondary gets 0.7x
                if area == desired_areas[0]:
                    best_match = max(best_match, match_score)
                else:
                    best_match = max(best_match, match_score * 0.7)

        return best_match

    def _score_workload(self, expert: ExpertProfile) -> float:
        """Score based on available capacity."""
        if expert.max_concurrent <= 0:
            return 0.0
        utilization = expert.current_workload / expert.max_concurrent
        return max(0.0, 1.0 - utilization)

    def _score_availability(self, expert: ExpertProfile) -> float:
        """Binary availability score."""
        return 1.0 if expert.is_available else 0.0

    def _score_performance(self, expert: ExpertProfile) -> float:
        """Score based on historical performance."""
        # Normalize satisfaction (1-5) to (0-1)
        satisfaction_score = (expert.satisfaction_rating - 1) / 4.0

        # Volume bonus (experienced experts)
        volume_score = min(expert.total_resolved / 100.0, 1.0)

        # Speed bonus (faster resolution)
        speed_score = max(0.0, 1.0 - (expert.avg_resolution_time_minutes / 120.0))

        return (satisfaction_score * 0.5 + volume_score * 0.25 + speed_score * 0.25)


class RoutingDecisionEngine:
    """
    High-level routing engine that orchestrates expert matching
    with load balancing and fairness considerations.
    """

    def __init__(self):
        self.matcher = ExpertMatcher()

    def route(
        self,
        case: RoutingCase,
        experts: List[ExpertProfile],
    ) -> RoutingDecision:
        """
        Route a case to the best expert with load balancing.
        
        Priority-based: HIGH/CRITICAL cases get the best expert.
        For MEDIUM/LOW, we also consider fairness (least-loaded).
        """
        # Filter available experts
        available = [e for e in experts if e.is_available]
        
        if not available:
            # Fall back to all experts (some might become available)
            available = experts

        # For high priority, use pure best-match
        if case.priority in ("HIGH", "CRITICAL"):
            return self.matcher.match(case, available)

        # For lower priority, apply fairness boost
        decision = self.matcher.match(case, available)

        # If primary expert is heavily loaded but fallback is free, consider swap
        if (decision.primary_expert_id and decision.fallback_expert_id
                and len(decision.scores) >= 2):
            primary_score = decision.scores[0]
            fallback_score = decision.scores[1]

            # Swap if workload difference is significant and expertise gap is small
            if (fallback_score.workload_score - primary_score.workload_score > 0.3
                    and primary_score.expertise_match - fallback_score.expertise_match < 0.2):
                decision.primary_expert_id = fallback_score.expert_id
                decision.fallback_expert_id = primary_score.expert_id
                decision.reasoning += " (load-balanced swap applied)"

        return decision
