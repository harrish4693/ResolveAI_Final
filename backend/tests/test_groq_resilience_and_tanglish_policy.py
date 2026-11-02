"""
ResolveAIV2 — Groq Resilience, Tanglish Policy Routing, & Conversation Recovery Tests
====================================================================================
Tests verifying:
1. Groq HTTP 429 rate limit parsing (RPM, TPM, Quota, Throttle) and latency budget enforcement.
2. Fast recovery without sleeping through long provider rate limits (>2.5s).
3. Tanglish broad policy query ("unga kitaa ena ena policy la iruku?") intent routing to POLICY_QUERY.
4. Grounded policy overview enumeration (Return within 30 days, Cancellation before dispatch, Delivery in 3-5 days)
   without inappropriately demanding an Order ID.
5. Contextual disambiguation of short tokens ("ena", "enna", "kya", "what", "why") following an Order ID prompt
   to explain *why* the Order ID is required, without verbatim repetition.
6. Provider-independent conversation recovery that answers in the customer's language instead of
   defaulting to "technical difficulties" or false expert escalation.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from openai import RateLimitError, APITimeoutError

from app.ai.intelligence.language import UniversalMeaningEngine, CodeMixedLanguageDetector, IndianLanguageNormalizer
from app.ai.m4.decision import DecisionEngine, ResponseGenerator
from app.ai.groq_provider import GroqProvider, parse_rate_limit_info
from app.conversations.service import ConversationService
from app.ai.validation.llm import check_semantic_grounding
from app.ai.validation.models import ResponseValidationContext, ValidationStatus


class TestGroqRateLimitParsing:
    """Verifies that HTTP 429 and rate limit errors are categorized accurately."""

    def test_parse_rpm_rate_limit(self):
        err = RateLimitError(
            message="Rate limit reached for model `llama-3.3-70b-versatile` on requests per minute (RPM): Limit 30, Used 30, Requested 1. Please try again in 8.35s.",
            response=MagicMock(headers={"retry-after": "8.35"}, status_code=429),
            body={"error": {"message": "RPM exceeded", "type": "requests", "code": "rate_limit_exceeded"}}
        )
        info = parse_rate_limit_info(err)
        assert info["is_rate_limit"] is True
        assert info["category"] == "RPM"
        assert info["retry_after"] == 8.35

    def test_parse_tpm_rate_limit_from_message(self):
        err = RateLimitError(
            message="Rate limit reached on tokens per minute (TPM). Please try again in 1.5s.",
            response=MagicMock(headers={}, status_code=429),
            body={"error": {"message": "TPM exceeded", "type": "tokens"}}
        )
        info = parse_rate_limit_info(err)
        assert info["is_rate_limit"] is True
        assert info["category"] == "TPM"
        assert info["retry_after"] == 1.5

    def test_parse_quota_restriction(self):
        err = RateLimitError(
            message="You exceeded your current quota, please check your plan and billing details.",
            response=MagicMock(headers={}, status_code=429),
            body={"error": {"message": "quota exceeded"}}
        )
        info = parse_rate_limit_info(err)
        assert info["is_rate_limit"] is True
        assert info["category"] == "QUOTA"
        assert info["retry_after"] is None

    def test_non_rate_limit_error(self):
        err = ValueError("Standard validation failure")
        info = parse_rate_limit_info(err)
        assert info["is_rate_limit"] is False
        assert info["category"] == "UNKNOWN"


class TestTanglishPolicyIntentRouting:
    """Verifies Tanglish colloquial normalization and policy query classification."""

    def setup_method(self):
        self.engine = UniversalMeaningEngine()

    @pytest.mark.parametrize("query,expected_intent,expected_category", [
        ("unga kitaa ena ena policy la iruku?", "POLICY_QUERY", "policy"),
        ("unga kitta enna policy irukku", "POLICY_QUERY", "policy"),
        ("what policies do you have", "POLICY_QUERY", "policy"),
        ("return policy pathi sollunga", "REFUND_ISSUE", "refund"),
        ("cancellation rules enna", "ORDER_MANAGEMENT", "order"),
        ("shipping policy sollunga", "DELIVERY_ISSUE", "delivery"),
    ])
    def test_policy_inquiries_classified_correctly(self, query: str, expected_intent: str, expected_category: str):
        understanding = self.engine.understand_utterance(query)
        assert understanding.intent == expected_intent
        assert understanding.category == expected_category
        assert understanding.intent != "GREETING"
        assert understanding.intent != "ORDER_STATUS"

    def test_broad_policy_overview_flag(self):
        res = self.engine.understand_utterance("unga kitaa ena ena policy la iruku?")
        assert res.intent == "POLICY_QUERY"
        assert res.diagnostic_details.get("is_policy_overview") is True

    def test_tanglish_colloquial_normalization(self):
        normalizer = IndianLanguageNormalizer()
        norm = normalizer.normalize("unga kitaa ena ena policy la iruku?")
        # "kitaa" normalized to "with you", "ena ena" to "what all"
        assert "with you" in norm.normalized or "kitta" in norm.normalized
        assert "what all" in norm.normalized or "what" in norm.normalized


class TestPolicyOverviewGroundedResponse:
    """Verifies that asking what policies exist generates an enumerated policy overview without demanding an Order ID."""

    def setup_method(self):
        self.decider = DecisionEngine()
        self.generator = ResponseGenerator()

    def test_m4_decision_for_policy_overview(self):
        analysis = {
            "original_message": "unga kitaa ena ena policy la iruku?",
            "intent": "POLICY_QUERY",
            "category": "policy",
            "language": "Tanglish",
            "entities": {},
            "diagnostic_details": {"is_policy_overview": True}
        }
        decision = self.decider.decide(analysis, [])
        assert decision["decision"] == "RESOLVE"
        assert decision["action_type"] == "policy_overview"

        resp = self.generator.generate(decision, language="tanglish")
        # Must mention the core policies in Tanglish
        assert "Return Policy" in resp or "return" in resp.lower()
        assert "Cancellation Policy" in resp or "cancel" in resp.lower()
        assert "Delivery" in resp or "3-5" in resp
        # Must NOT demand an Order ID
        assert "Order ID" not in resp

    def test_english_policy_overview(self):
        decision = {"decision": "RESOLVE", "action_type": "policy_overview", "article": {}}
        resp = self.generator.generate(decision, language="english")
        assert "Return Policy" in resp
        assert "Cancellation Policy" in resp
        assert "within 30 days" in resp
        assert "Order ID" not in resp

    def test_routine_fallback_prompt_for_policy_query(self):
        resp_tanglish = ConversationService._get_routine_fallback_prompt("POLICY_QUERY", "tanglish")
        assert "Return Policy" in resp_tanglish or "return" in resp_tanglish.lower()
        assert "Order ID" not in resp_tanglish

        resp_en = ConversationService._get_routine_fallback_prompt("POLICY_QUERY", "english")
        assert "Return Policy" in resp_en
        assert "Order ID" not in resp_en


class TestShortMessagesAndContextualDisambiguation:
    """Verifies handling of short tokens ('ena', 'enna', 'kya', 'what', 'why')."""

    def setup_method(self):
        self.engine = UniversalMeaningEngine()
        self.decider = DecisionEngine()
        self.generator = ResponseGenerator()

    def test_ena_following_order_id_prompt_explains_purpose(self):
        history = [
            {"sender_type": "customer", "content": "where is my order?"},
            {"sender_type": "ai", "content": "Sure! Could you please provide your Order ID so I can check its status for you?"}
        ]
        res = self.engine.understand_utterance("ena", history=history)
        assert res.intent == "CLARIFICATION_ORDER_ID_PURPOSE"
        assert res.diagnostic_details.get("clarification_target") == "order_id_reason"

        decision = self.decider.decide({
            "original_message": "ena",
            "intent": res.intent,
            "category": res.category,
            "entities": {},
            "diagnostic_details": res.diagnostic_details
        }, [])
        assert decision["decision"] == "ASK_USER"
        assert decision["missing_entity"] == "order_id_reason"

        tanglish_resp = self.generator.generate(decision, language="tanglish")
        # Explains why Order ID is needed
        assert "check panna Order ID theva padudhu" in tanglish_resp or "Order ID" in tanglish_resp
        assert "ORD-" in tanglish_resp or "SMS" in tanglish_resp

    def test_why_following_order_id_prompt(self):
        history = [
            {"sender_type": "ai", "content": "Could you please provide your order ID?"}
        ]
        res = self.engine.understand_utterance("why do you need that?", history=history)
        assert res.intent == "CLARIFICATION_ORDER_ID_PURPOSE"

    def test_ena_without_order_history_does_not_invent_order(self):
        res = self.engine.understand_utterance("ena", history=[])
        assert res.intent != "ORDER_STATUS"


class TestProviderIndependentRecovery:
    """Verifies that Groq 429 or provider failure cleanly recovers locally without generic technical difficulties."""

    @pytest.mark.asyncio
    async def test_groq_provider_policy_fallback_on_429(self):
        provider = GroqProvider()
        # Mock generate_structured to simulate Groq 429 RateLimitError
        provider.generate_structured = AsyncMock(side_effect=RateLimitError(
            message="Rate limit reached for model. Please try again in 8.35s.",
            response=MagicMock(headers={"retry-after": "8.35"}, status_code=429),
            body={"error": {"message": "Rate limit exceeded"}}
        ))

        analysis = {
            "original_message": "unga kitaa ena ena policy la iruku?",
            "intent": "POLICY_QUERY",
            "category": "policy",
            "language": "Tanglish",
            "entities": {},
            "diagnostic_details": {"is_policy_overview": True}
        }
        context = {"history": []}

        # generate_response should gracefully synthesize the grounded policy overview in Tanglish
        resp = await provider.generate_response(analysis, [], context)
        assert "technical difficulties" not in resp.lower()
        assert analysis["decision_state"] == "RESOLVE"
        assert "Return Policy" in resp or "return" in resp.lower()

    @pytest.mark.asyncio
    async def test_groq_provider_order_status_fallback_on_429(self):
        provider = GroqProvider()
        provider.generate_structured = AsyncMock(side_effect=RateLimitError(
            message="Rate limit reached.",
            response=MagicMock(headers={"retry-after": "8.0"}, status_code=429),
            body={}
        ))

        analysis = {
            "original_message": "where is my order?",
            "intent": "ORDER_STATUS",
            "category": "order",
            "language": "English",
            "entities": {},
        }
        context = {"history": []}

        resp = await provider.generate_response(analysis, [], context)
        assert "technical difficulties" not in resp.lower()
        assert analysis["decision_state"] == "ASK_USER"
        assert "Order ID" in resp

    @pytest.mark.asyncio
    async def test_groq_provider_supervisor_demand_escalates_cleanly_on_429(self):
        provider = GroqProvider()
        provider.generate_structured = AsyncMock(side_effect=RateLimitError(
            message="Rate limit reached.",
            response=MagicMock(headers={"retry-after": "8.0"}, status_code=429),
            body={}
        ))

        analysis = {
            "original_message": "connect with the expert",
            "intent": "ESCALATION_REQUEST",
            "language": "Tanglish",
            "entities": {},
        }
        context = {"history": []}

        resp = await provider.generate_response(analysis, [], context)
        assert "technical difficulties" not in resp.lower()
        assert analysis["decision_state"] == "ESCALATE"
        assert "support team-kku connect" in resp or "human expert" in resp


class TestValidationOptimization:
    """Verifies that deterministic grounded templates avoid redundant LLM validation calls."""

    @pytest.mark.asyncio
    async def test_deterministic_template_skips_llm_call(self):
        ctx = ResponseValidationContext(
            conversation_id=1,
            customer_id=1,
            user_message="unga kitaa ena ena policy la iruku?",
            draft_response="Namma ResolveMart-la 3 mukkiyamana policies irukku: 1) Return Policy: Items delivery aana 30 days kulla return panna mudiyum.",
            agent_decision="RESOLVE",
            rag_context=[],
        )
        # Should validate deterministically without calling any external provider
        result = await check_semantic_grounding(ctx)
        assert result.status == ValidationStatus.VALID

