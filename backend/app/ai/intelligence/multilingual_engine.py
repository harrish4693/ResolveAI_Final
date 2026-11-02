"""
Multilingual Understanding Service for ResolveAI V2.
Provides deep semantic understanding, language/code-mix detection,
negation preservation, and search query canonicalization across
Tamil script, Tanglish, Hindi, Hinglish, and English.
"""

from __future__ import annotations

import re
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.ai.intelligence.language import (
    UniversalMeaningEngine,
    UniversalMeaningUnderstanding,
    CodeMixedLanguageDetector,
    IndianLanguageNormalizer,
)

logger = logging.getLogger(__name__)


class MultilingualUnderstanding(BaseModel):
    """
    Validated Pydantic representation of customer understanding across
    native scripts, code-mixed Latin, and English.
    """
    original_text: str
    primary_language: str = "en"
    detected_script: str = "latin"
    code_mix_type: str = "english"
    is_code_mixed: bool = False
    normalized_meaning: str = ""
    normalized_search_query: str = ""
    intent: str = "GENERAL_QUERY"
    category: str = "general"
    conversational_function: str = "NEW_REQUEST"
    confidence: float = 0.85
    negation_detected: bool = False
    sentiment: str = "NEUTRAL"
    urgency: str = "normal"
    is_ambiguous: bool = False
    clarification_needed: bool = False
    entities: Dict[str, Any] = Field(default_factory=dict)
    diagnostic_details: Dict[str, Any] = Field(default_factory=dict)
    communication_style: Dict[str, Any] = Field(default_factory=dict)


class MultilingualEngineService:
    """
    Shared singleton service for multilingual understanding with turn-level
    caching and tenant isolation.
    """
    _instance: Optional[MultilingualEngineService] = None
    _cache: Dict[str, MultilingualUnderstanding] = {}
    _CACHE_MAX_SIZE = 500

    def __new__(cls) -> MultilingualEngineService:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.engine = UniversalMeaningEngine()
            cls._cache = {}
        return cls._instance

    @classmethod
    def clear_cache(cls, tenant_id: Optional[str] = None) -> None:
        """Clear cache for a specific tenant or entirely."""
        if tenant_id:
            keys_to_del = [k for k in cls._cache if k.startswith(f"{tenant_id}:")]
            for k in keys_to_del:
                cls._cache.pop(k, None)
        else:
            cls._cache.clear()

    @staticmethod
    def generate_normalized_search_query(
        intent: str,
        category: str,
        entities: Dict[str, Any],
        negation_detected: bool,
        diagnostic_details: Dict[str, Any],
    ) -> str:
        """
        Builds a high-precision, canonical English query for RAG retrieval
        and cross-ticket incident clustering.
        """
        terms: List[str] = []

        if intent in ("DELIVERY_ISSUE", "ORDER_STATUS"):
            terms.extend(["order", "delivery", "shipping", "tracking", "status", "shipment"])
            if negation_detected:
                terms.extend(["delayed", "delay", "not arrived", "pending"])
        elif intent == "PAYMENT_ISSUE":
            terms.extend(["payment", "transaction", "billing", "debit", "deducted"])
            if negation_detected:
                terms.extend(["failed", "unsuccessful", "error"])
        elif intent == "PAYMENT_CONFIRMATION":
            terms.extend(["payment", "completed", "successful", "received", "status"])
        elif intent == "REFUND_ISSUE":
            terms.extend(["refund", "return", "policy", "money back", "reversal"])
            if negation_detected:
                terms.extend(["not received", "delayed", "pending"])
        elif intent == "REFUND_RECEIVED":
            terms.extend(["refund", "received", "completed", "credited"])
        elif intent == "ORDER_MANAGEMENT":
            terms.extend(["order", "cancellation", "cancel", "modify", "change address"])
        elif intent == "LOGIN_ISSUE":
            terms.extend(["login", "password", "account", "locked", "reset", "otp", "authentication"])
        elif intent == "TECHNICAL_ISSUE":
            terms.extend(["app", "crash", "loading", "frozen", "screen", "technical", "error"])
        elif intent in ("POLICY_QUERY", "WARRANTY_SERVICE"):
            terms.extend(["return policy", "refund policy", "warranty", "terms", "replacement"])
        else:
            if category and category.lower() not in ("general", "unknown", "other", ""):
                terms.append(category.lower())

        for k, v in entities.items():
            if isinstance(v, (str, int, float)):
                terms.append(str(v))

        return " ".join(terms)

    def understand(
        self,
        text: str,
        tenant_id: str = "default",
        conversation_id: Optional[int] = None,
        history: Optional[List[Dict[str, Any]]] = None,
        conversation_state: Optional[Any] = None,
    ) -> MultilingualUnderstanding:
        """
        Contextually interprets a customer message in Tamil, Tanglish, Hindi,
        Hinglish, or English with caching.
        """
        if not text or not text.strip():
            return MultilingualUnderstanding(original_text=text)

        clean_text = text.strip()
        state_key = getattr(conversation_state, "active_intent", "") if conversation_state else ""
        cache_key = f"{tenant_id}:{conversation_id or 0}:{state_key}:{clean_text}"

        if not history and cache_key in self._cache:
            return self._cache[cache_key]

        # Call the underlying UniversalMeaningEngine
        raw_u: UniversalMeaningUnderstanding = self.engine.understand_utterance(
            clean_text,
            history=history,
            conversation_state=conversation_state,
        )

        # Compute search query
        search_query = self.generate_normalized_search_query(
            intent=raw_u.intent,
            category=raw_u.category,
            entities=raw_u.entities,
            negation_detected=raw_u.negation_detected,
            diagnostic_details=raw_u.diagnostic_details,
        )
        raw_u.diagnostic_details["normalized_search_query"] = search_query

        # Map sentiment style
        style = raw_u.communication_style or {}
        sentiment_val = style.get("sentiment", "neutral").upper()
        if sentiment_val not in ("POSITIVE", "NEGATIVE", "NEUTRAL"):
            sentiment_val = "NEGATIVE" if sentiment_val == "FRUSTRATED" else "NEUTRAL"

        result = MultilingualUnderstanding(
            original_text=clean_text,
            primary_language=raw_u.primary_language,
            detected_script=raw_u.detected_script,
            code_mix_type=raw_u.code_mix_type,
            is_code_mixed=raw_u.is_code_mixed,
            normalized_meaning=raw_u.normalized_meaning or clean_text,
            normalized_search_query=search_query,
            intent=raw_u.intent,
            category=raw_u.category,
            conversational_function=raw_u.conversational_function,
            confidence=raw_u.intent_confidence,
            negation_detected=raw_u.negation_detected,
            sentiment=sentiment_val,
            urgency=style.get("urgency", "normal"),
            is_ambiguous=raw_u.is_ambiguous,
            clarification_needed=raw_u.clarification_needed,
            entities=raw_u.entities,
            diagnostic_details=raw_u.diagnostic_details,
            communication_style=style,
        )

        if len(self._cache) >= self._CACHE_MAX_SIZE:
            self._cache.clear()
        self._cache[cache_key] = result
        return result


# Global singleton access
multilingual_service = MultilingualEngineService()

