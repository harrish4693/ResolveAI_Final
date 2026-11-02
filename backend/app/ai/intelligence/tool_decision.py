"""
Capability 4: Tool Decision Analysis

Analyzes which tools should be used for a given customer issue,
validates tool parameters, checks authorization, and scores
tool suitability.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class ToolRecommendation:
    """A recommended tool for the current issue."""
    tool_name: str = ""
    suitability_score: float = 0.0    # 0-1
    parameters_available: bool = False
    missing_parameters: List[str] = field(default_factory=list)
    requires_confirmation: bool = False
    risk_level: str = "low"           # low, medium, high
    reasoning: str = ""


@dataclass
class ToolDecisionResult:
    """Result of tool decision analysis."""
    should_use_tool: bool = False
    recommendations: List[ToolRecommendation] = field(default_factory=list)
    best_tool: Optional[str] = None
    fallback_tool: Optional[str] = None
    reasoning: str = ""


# Tool metadata registry (mirrors the actual tool registry but for analysis)
TOOL_CATALOG = {
    "get_order_status": {
        "intents": {"DELIVERY_ISSUE", "PAYMENT_ISSUE"},
        "required_params": ["order_id"],
        "risk": "low",
        "requires_confirmation": False,
        "entity_mapping": {"order_id": "order_id", "transaction_id": "order_id"},
    },
    "check_transaction": {
        "intents": {"PAYMENT_ISSUE"},
        "required_params": ["transaction_id"],
        "risk": "low",
        "requires_confirmation": False,
        "entity_mapping": {"transaction_id": "transaction_id"},
    },
    "get_ticket_status": {
        "intents": {"GENERAL_QUERY"},
        "required_params": ["ticket_id"],
        "risk": "low",
        "requires_confirmation": False,
        "entity_mapping": {"ticket_id": "ticket_id"},
    },
    "get_customer_account_info": {
        "intents": {"LOGIN_ISSUE", "UPDATE_ISSUE", "GENERAL_QUERY"},
        "required_params": [],
        "risk": "low",
        "requires_confirmation": False,
        "entity_mapping": {},
    },
    "create_support_ticket": {
        "intents": {"GENERAL_QUERY"},
        "required_params": ["subject"],
        "risk": "medium",
        "requires_confirmation": True,
        "entity_mapping": {"subject": "original_message"},
    },
    "update_ticket_info": {
        "intents": {"UPDATE_ISSUE"},
        "required_params": ["ticket_id"],
        "risk": "medium",
        "requires_confirmation": True,
        "entity_mapping": {"ticket_id": "ticket_id"},
    },
    "request_human_support": {
        "intents": {"SECURITY_ISSUE", "ESCALATE_REQUEST"},
        "required_params": [],
        "risk": "medium",
        "requires_confirmation": False,
        "entity_mapping": {},
    },
}


class ToolAnalyzer:
    """
    Analyzes which tools are suitable for the current customer issue.
    Maps intents to tools, checks parameter availability, and scores suitability.
    """

    def analyze(
        self,
        intent: str,
        entities: Dict[str, str],
        decision_state: str = "",
        message: str = "",
    ) -> ToolDecisionResult:
        """
        Analyze tool requirements for the current issue.
        
        Args:
            intent: Detected customer intent
            entities: Extracted entities
            decision_state: Current decision state from AI
            message: Original customer message
        
        Returns:
            ToolDecisionResult with recommendations and best tool selection.
        """
        recommendations: List[ToolRecommendation] = []

        for tool_name, metadata in TOOL_CATALOG.items():
            # Check if tool is relevant for this intent
            if intent not in metadata["intents"]:
                continue

            # Score suitability
            rec = self._score_tool(tool_name, metadata, intent, entities, message)
            recommendations.append(rec)

        # Sort by suitability
        recommendations.sort(key=lambda r: r.suitability_score, reverse=True)

        # Determine best and fallback
        best = recommendations[0].tool_name if recommendations and recommendations[0].suitability_score > 0.3 else None
        fallback = recommendations[1].tool_name if len(recommendations) > 1 and recommendations[1].suitability_score > 0.2 else None

        should_use = best is not None and (
            decision_state == "USE_TOOL" or
            (recommendations[0].parameters_available if recommendations else False)
        )

        return ToolDecisionResult(
            should_use_tool=should_use,
            recommendations=recommendations,
            best_tool=best,
            fallback_tool=fallback,
            reasoning=self._build_reasoning(recommendations, best),
        )

    def _score_tool(
        self,
        tool_name: str,
        metadata: Dict[str, Any],
        intent: str,
        entities: Dict[str, str],
        message: str,
    ) -> ToolRecommendation:
        """Score a single tool's suitability."""
        score = 0.0
        missing_params: List[str] = []

        # Intent match (0.4 weight)
        if intent in metadata["intents"]:
            score += 0.4

        # Parameter availability (0.4 weight)
        required = metadata["required_params"]
        if not required:
            score += 0.4
            params_available = True
        else:
            available_count = 0
            for param in required:
                # Check direct match or entity mapping
                entity_map = metadata["entity_mapping"]
                mapped_key = None
                for entity_key, mapped in entity_map.items():
                    if mapped == param and entity_key in entities:
                        mapped_key = entity_key
                        break
                
                if param in entities or mapped_key:
                    available_count += 1
                else:
                    missing_params.append(param)
            
            param_ratio = available_count / len(required)
            score += param_ratio * 0.4
            params_available = len(missing_params) == 0

        # Risk penalty (0.2 weight)
        risk = metadata["risk"]
        if risk == "low":
            score += 0.2
        elif risk == "medium":
            score += 0.1
        else:
            score += 0.0

        return ToolRecommendation(
            tool_name=tool_name,
            suitability_score=round(score, 3),
            parameters_available=params_available,
            missing_parameters=missing_params,
            requires_confirmation=metadata["requires_confirmation"],
            risk_level=risk,
            reasoning=f"Intent match: {intent in metadata['intents']}, "
                      f"Params: {len(required) - len(missing_params)}/{len(required)}",
        )

    def _build_reasoning(self, recommendations: List[ToolRecommendation], best: Optional[str]) -> str:
        if not recommendations:
            return "No suitable tools found for this intent"
        if best:
            rec = recommendations[0]
            return f"Best tool: {best} (score: {rec.suitability_score:.2f}, params available: {rec.parameters_available})"
        return f"Tools found but none fully suitable. Top: {recommendations[0].tool_name}"


class ToolAuthorizationChecker:
    """
    Verifies that the user has authorization to execute a tool.
    """

    # Role -> allowed tool sets
    ROLE_PERMISSIONS = {
        "customer": {
            "get_order_status", "check_transaction", "get_ticket_status",
            "get_customer_account_info", "create_support_ticket",
            "request_human_support",
        },
        "expert": {
            "get_order_status", "check_transaction", "get_ticket_status",
            "get_customer_account_info", "create_support_ticket",
            "update_ticket_info", "request_human_support",
        },
        "admin": set(TOOL_CATALOG.keys()),  # All tools
    }

    def check_authorization(self, user_role: str, tool_name: str) -> Dict[str, Any]:
        """
        Check if a user role is authorized to execute a tool.
        
        Returns dict with authorized flag and details.
        """
        allowed = self.ROLE_PERMISSIONS.get(user_role, set())
        is_authorized = tool_name in allowed

        return {
            "authorized": is_authorized,
            "tool_name": tool_name,
            "user_role": user_role,
            "reason": (
                f"Role '{user_role}' is authorized for '{tool_name}'"
                if is_authorized
                else f"Role '{user_role}' is not authorized for '{tool_name}'"
            ),
        }

    def get_available_tools(self, user_role: str) -> List[str]:
        """Get list of tools available for a user role."""
        return sorted(self.ROLE_PERMISSIONS.get(user_role, set()))
