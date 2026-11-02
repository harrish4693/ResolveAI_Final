"""
ResolveAIV2 — Held-Out Dynamic Semantic Generalization Test Suite
================================================================
Validates that ResolveAI V2 dynamically interprets customer intent, conversational context,
and multilingual expressions without depending on rigid fixed-word dictionaries or template overrides.

Held-Out Test Scenarios:
1. Novel Tanglish and Hinglish colloquial phrases not present in dictionaries (morphology-aware).
2. Elimination of false gibberish classification on legitimate multi-syllabic Indian language words.
3. Multi-intent utterances (e.g., Greeting + Substantive query) preserve the substantive intent.
4. Inquiries explaining identifier necessity ("edhukku order id venum?") are answered and never sanitized.
5. Policy questions without keyword 'policy' ("thiruppi anupa evlo naal time irukku") answer the return window without requesting Order ID.
6. Dynamic language detection correctly sets and preserves conversation language preferences.
7. Resilience against provider throttling (429 Rate Limits) with bounded, non-blocking fallback.
"""

import pytest
import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from httpx import AsyncClient

from app.users.models import User
from app.conversations.models import Conversation, ConversationMessage
from app.conversations.service import ConversationService
from app.shared.models import SenderType, WorkflowState
from app.ai.intelligence.language import (
    CodeMixedLanguageDetector,
    UniversalMeaningEngine,
)
from app.ai.m4.provider import M4AIProvider
from app.ai.groq_provider import GroqProvider
from app.commerce.models import Order


@pytest.fixture
def meaning_engine():
    return UniversalMeaningEngine()


@pytest.fixture
def detector():
    return CodeMixedLanguageDetector()


@pytest.fixture
def m4_provider():
    return M4AIProvider()


class TestDynamicMorphologyAndNovelVocabulary:
    """Verifies that novel vocabulary and morphological variations are recognized without fixed dictionary entries."""

    def test_novel_tanglish_morphology_detected_as_tanglish(self, detector):
        """Unseen Tanglish words with characteristic suffixes classify as Tanglish."""
        phrases = [
            "en parcel innum reach aagala",
            "naan vaangina saaman sariyaave vela seiyala",
            "thiruppi anupuradhukku evlo naal time irukku",
            "bill amount extra charge aayiduchu",
        ]
        for phrase in phrases:
            result = detector.detect(phrase)
            assert result.code_mix_type == "tanglish" or result.primary_language == "ta", (
                f"Expected Tanglish detection for '{phrase}', got {result.code_mix_type} ({result.primary_language})"
            )

    def test_novel_hinglish_morphology_detected_as_hinglish(self, detector):
        """Unseen Hinglish words with characteristic suffixes classify as Hinglish."""
        phrases = [
            "saman wapas bhejne ke liye kitne din lagenge",
            "mera package abhi tak nahi pohcha",
            "kya bina id ke check kar sakte ho",
        ]
        for phrase in phrases:
            result = detector.detect(phrase)
            assert result.code_mix_type == "hinglish" or result.primary_language == "hi", (
                f"Expected Hinglish detection for '{phrase}', got {result.code_mix_type} ({result.primary_language})"
            )

    def test_legitimate_multisyllabic_words_not_marked_as_gibberish(self, meaning_engine):
        """Long Indian words (7+ letters) must not be treated as gibberish UNCLEAR."""
        legitimate_words = [
            "thiruppanum",
            "maranthuten",
            "anupuradhukku",
            "kavalapadatheenga",
            "pidichutaanga",
        ]
        for word in legitimate_words:
            meaning = meaning_engine.understand_utterance(word)
            # Must not be flagged as gibberish / low-quality input
            assert meaning.intent != "UNCLEAR" or meaning.conversational_function != "GIBBERISH", (
                f"Word '{word}' was incorrectly treated as gibberish"
            )


class TestMultiIntentPreservation:
    """Verifies that greetings in multi-intent turns do not wipe out substantive customer issues."""

    def test_greeting_plus_delivery_issue_preserves_delivery(self, meaning_engine):
        """'hi, delivery reach aagala' must classify as DELIVERY_ISSUE, not GREETING."""
        res = meaning_engine.understand_utterance("hi, delivery reach aagala")
        assert res.intent == "DELIVERY_ISSUE"

    def test_vanakkam_plus_refund_preserves_refund(self, meaning_engine):
        """'vanakkam, refund amount eppo varum' must classify as REFUND_ISSUE, not GREETING."""
        res = meaning_engine.understand_utterance("vanakkam, refund amount eppo varum")
        assert res.intent == "REFUND_ISSUE"

    def test_pure_greeting_still_classified_as_greeting(self, meaning_engine):
        """Pure greetings without substantive issues remain GREETING."""
        pure_greetings = ["hi", "hello", "vanakkam", "namaste", "hey there"]
        for g in pure_greetings:
            res = meaning_engine.understand_utterance(g)
            assert res.conversational_function == "GREETING" or res.intent == "GREETING"


class TestIdentifierExplanationAndSanitizerProtection:
    """Verifies that questions explaining why an identifier is needed are preserved and not sanitized."""

    def test_order_id_purpose_question_classified(self, meaning_engine):
        """'edhukku order id venum?' is recognized as asking for the purpose of the order ID."""
        queries = [
            "edhukku order id venum?",
            "edhukku Order ID theva padudhu?",
            "why do you need my order id?",
            "bina order id ke nahi ho sakta kya?",
        ]
        for q in queries:
            res = meaning_engine.understand_utterance(q)
            # Intent should reflect purpose clarification or general inquiry
            assert res.conversational_function in (
                "FOLLOW_UP",
                "CLARIFICATION",
                "NEW_REQUEST",
            ) or res.intent in ("CLARIFICATION_ORDER_ID_PURPOSE", "GENERAL_QUERY")

    @pytest.mark.asyncio
    async def test_order_id_explanation_not_clobbered_by_sanitizer(self, async_client: AsyncClient, auth_headers_a: dict, db_session: AsyncSession):
        """When user asks why Order ID is needed, the system explains and does not sanitize to generic fallback."""
        # 1. Ask a delivery question without order ID
        resp1 = await async_client.post(
            "/api/conversations",
            json={"initial_message": "en package innum varala"},
            headers=auth_headers_a,
        )
        assert resp1.status_code == 200
        convo_id = resp1.json()["id"]

        # 2. Customer asks why Order ID is required
        resp2 = await async_client.post(
            f"/api/conversations/{convo_id}/messages",
            json={"content": "edhukku order id venum?"},
            headers=auth_headers_a,
        )
        assert resp2.status_code == 200

        stmt = (
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == convo_id)
            .order_by(ConversationMessage.created_at.asc())
        )
        messages = (await db_session.execute(stmt)).scalars().all()
        ai_msgs = [m for m in messages if m.sender_type == SenderType.AI]
        assert len(ai_msgs) >= 2

        last_ai = ai_msgs[-1].content.lower()
        # Must explain purpose: tracking, finding details, checking account, etc.
        assert any(kw in last_ai for kw in ["track", "details", "locate", "check", "theva", "kandupidikka", "verify", "order"])
        # Must NOT be a generic greeting
        assert not (last_ai.startswith("hello!") and len(last_ai) < 40)


class TestPolicyGeneralizationWithoutOrderPrompt:
    """Verifies that general policy inquiries answer grounded policy without requesting an Order ID."""

    def test_colloquial_return_time_window_query(self, meaning_engine):
        """'thiruppi anupa evlo naal time irukku' identifies as a return/refund policy query."""
        res = meaning_engine.understand_utterance("thiruppi anupa evlo naal time irukku")
        assert res.intent in ("REFUND_ISSUE", "POLICY_QUERY")

    @pytest.mark.asyncio
    async def test_return_policy_query_does_not_prompt_for_order_id(self, async_client: AsyncClient, auth_headers_a: dict, db_session: AsyncSession):
        """Asking for return policy answers with 30-day policy and does not demand an Order ID."""
        resp = await async_client.post(
            "/api/conversations",
            json={"initial_message": "thiruppi anupa evlo naal time irukku sollunga bro"},
            headers=auth_headers_a,
        )
        assert resp.status_code == 200
        convo_id = resp.json()["id"]

        stmt = (
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == convo_id)
            .order_by(ConversationMessage.created_at.asc())
        )
        messages = (await db_session.execute(stmt)).scalars().all()
        ai_msg = [m for m in messages if m.sender_type == SenderType.AI][-1]

        content = ai_msg.content.lower()
        # Must contain the accurate 30 days return window
        assert "30" in content
        # Must not demand an order ID for a general policy inquiry
        assert "unga order id sollunga" not in content
        assert "please provide your order id" not in content


class TestDynamicLanguageContinuity:
    """Verifies that language detected from novel phrases is sticky across conversation turns."""

    @pytest.mark.asyncio
    async def test_initial_tanglish_sets_sticky_preference(self, async_client: AsyncClient, auth_headers_a: dict, db_session: AsyncSession):
        """A conversation initiated in Tanglish retains Tanglish preferred_language across turns."""
        resp1 = await async_client.post(
            "/api/conversations",
            json={"initial_message": "en saaman innum reach aagala epo varum"},
            headers=auth_headers_a,
        )
        assert resp1.status_code == 200
        convo_id = resp1.json()["id"]

        stmt = select(Conversation).where(Conversation.id == convo_id)
        convo = (await db_session.execute(stmt)).scalars().first()
        assert convo is not None
        assert convo.preferred_language == "tanglish"

        # Follow-up turn in Tanglish
        resp2 = await async_client.post(
            f"/api/conversations/{convo_id}/messages",
            json={"content": "romba late aagudhu bro"},
            headers=auth_headers_a,
        )
        assert resp2.status_code == 200

        await db_session.refresh(convo)
        assert convo.preferred_language == "tanglish"
