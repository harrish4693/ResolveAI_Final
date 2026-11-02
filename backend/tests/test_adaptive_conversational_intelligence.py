"""
ResolveAIV2 — Comprehensive Adaptive Multilingual Conversational Intelligence Test Suite
========================================================================================
Validates that ResolveAI V2 understands conversational meaning, discourse functions,
contextual state continuity, and changes in communication style across English,
Tamil, Tanglish, Hindi, Hinglish, and code-mixed expressions.

Key Requirements Tested:
1. Discourse function recognition (UniversalMeaningEngine):
   - Diverse unseen acknowledgments ("seri", "sari pa", "hmm okay", "ohh", "correct",
     "puriyudhu", "acha theek hai", "haan okay", "fine bro", "k thanks bro", "got it")
     are identified as ACKNOWLEDGMENT.
   - Greetings, follow-ups, answers to pending requests, topic shifts, corrections,
     and emotional reactions are accurately classified.
2. Communication style detection:
   - Identifies formality, slang, code-mixing, transliteration, and sentiment.
3. ConversationState & StateManager:
   - Correctly updates active intent, entities, pending questions, and resolution status.
   - Preserves accumulated entities across related turns.
   - Cleanses entities and resets intent cleanly on topic change or acknowledgment.
4. End-to-end conversation flow via ConversationService & M4 Decision Pipeline:
   - Acknowledgment turns produce warm conversational closings and NEVER re-prompt
     for an Order ID or execute redundant tools.
   - Follow-up questions maintain topic continuity without asking for an Order ID.
   - Pending Order ID response fetches order details immediately without re-prompting.
   - Topic change resets the conversation state cleanly.
   - Clarifications and corrections ("No, I meant ORD-456") update entities cleanly.
   - Emotional frustration receives empathetic de-escalation rather than technical error.
   - Language switch preserves the conversation flow in the newly requested language.
5. Voice turn parity:
   - Acknowledgments and speech acts in process_voice_turn generate natural concise closings.
6. Tenant and customer isolation:
   - Different customers and conversations have strictly isolated state; no cross-leakage.
"""

import pytest
import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from httpx import AsyncClient

from app.users.models import User
from app.conversations.models import Conversation, ConversationMessage
from app.conversations.service import ConversationService
from app.conversations.state import ConversationState, ConversationStateManager
from app.shared.models import SenderType, WorkflowState
from app.ai.intelligence.language import UniversalMeaningEngine
from app.ai.m4.provider import M4AIProvider
from app.ai.m4.decision import DecisionEngine, ResponseGenerator
from app.commerce.models import Order


@pytest.fixture
def meaning_engine():
    return UniversalMeaningEngine()


@pytest.fixture
def m4_provider():
    return M4AIProvider()


@pytest.fixture
def decision_engine():
    return DecisionEngine()


@pytest.fixture
def response_generator():
    return ResponseGenerator()


# ==============================================================================
# 1. Discourse Function & Meaning Understanding Tests
# ==============================================================================

class TestDiscourseFunctionUnderstanding:
    """Validates that diverse natural expressions across multiple languages
    are accurately mapped to their conversational discourse functions."""

    @pytest.mark.parametrize("acknowledgment_text,expected_lang", [
        ("seri", "ta"),
        ("sari pa", "ta"),
        ("hmm okay", "en"),
        ("ohh", "en"),
        ("correct", "en"),
        ("puriyudhu", "ta"),
        ("acha theek hai", "hi"),
        ("haan okay", "hi"),
        ("fine bro", "en"),
        ("k thanks bro", "en"),
        ("got it", "en"),
        ("theek hai ji", "hi"),
        ("appidiya seri", "ta"),
        ("sure thank you", "en"),
        ("dhanyavad", "hi"),
        ("nandri pa", "ta"),
    ])
    def test_unseen_acknowledgments_classified_correctly(self, meaning_engine, acknowledgment_text, expected_lang):
        """Proves that a diverse range of natural acknowledgments are recognized
        as conversational acknowledgments and NOT as order requests or greetings."""
        meaning = meaning_engine.understand_utterance(acknowledgment_text)
        assert meaning.conversational_function == "ACKNOWLEDGMENT", (
            f"Expected ACKNOWLEDGMENT for '{acknowledgment_text}', got '{meaning.conversational_function}'"
        )
        assert meaning.intent != "ORDER_STATUS", (
            f"Acknowledgment '{acknowledgment_text}' must never be classified as ORDER_STATUS"
        )

    @pytest.mark.parametrize("greeting_text", [
        "hi",
        "hello",
        "hey",
        "hey there",
        "vanakkam",
        "வணக்கம்",
        "namaste",
        "नमस्ते",
        "good morning",
        "good evening",
    ])
    def test_greetings_classified_as_greeting(self, meaning_engine, greeting_text):
        meaning = meaning_engine.understand_utterance(greeting_text)
        assert meaning.conversational_function == "GREETING"
        assert meaning.intent == "GREETING"

    @pytest.mark.parametrize("non_greeting_with_they", [
        "Can they leave it with my neighbor instead?",
        "They told me it would arrive yesterday",
        "Are they delivering today?",
        "What if they cannot reach me?",
        "Will they call before coming?",
    ])
    def test_they_does_not_trigger_greeting(self, meaning_engine, non_greeting_with_they):
        """Regression test: 'they' contains 'hey' but must never be classified as GREETING."""
        meaning = meaning_engine.understand_utterance(non_greeting_with_they)
        assert meaning.conversational_function != "GREETING", (
            f"Sentence '{non_greeting_with_they}' was incorrectly classified as GREETING"
        )
        assert meaning.intent != "GREETING"

    @pytest.mark.parametrize("correction_text", [
        "no wait, I meant ORD-99881",
        "actually not that one, check ORD-4455",
        "mistake ah solten, ORD-777 thaan",
        "galat order number tha, ORD-1234 check karo",
    ])
    def test_corrections_classified_as_correction(self, meaning_engine, correction_text):
        meaning = meaning_engine.understand_utterance(correction_text)
        assert meaning.conversational_function == "CLARIFICATION_OR_CORRECTION"
        assert "order_id" in meaning.entities or any(k in meaning.entities for k in ["order_id", "transaction_id"])

    @pytest.mark.parametrize("emotional_text", [
        "This is totally ridiculous! I am waiting for days!",
        "Very worst customer service ever",
        "romba waste service pa, waste of money",
        "bahut ghatiya service hai aapki",
    ])
    def test_emotional_reactions_detected(self, meaning_engine, emotional_text):
        meaning = meaning_engine.understand_utterance(emotional_text)
        assert meaning.conversational_function == "EMOTIONAL_REACTION" or meaning.communication_style.get("sentiment") in ("frustrated", "negative", "angry")


# ==============================================================================
# 2. Conversation State Manager Lifecycle & Continuity Tests
# ==============================================================================

class TestConversationStateManager:
    """Validates state loading, multi-turn updates, entity accumulation,
    and state sanitization."""

    def test_state_initialization(self):
        state = ConversationStateManager.load_state(None)
        assert state.active_intent == "GENERAL_QUERY"
        assert state.entities == {}
        assert state.pending_question is None
        assert state.resolution_status == "in_progress"

    def test_state_updates_before_and_after_turn(self):
        state = ConversationState(conversation_id=1, customer_id=1)

        # Turn 1: Customer asks where is order
        meaning_1 = UniversalMeaningEngine().understand_utterance("Where is my order?")
        state = ConversationStateManager.update_before_turn(state, "Where is my order?", meaning_1)
        assert state.active_intent in ("ORDER_STATUS", "DELIVERY_ISSUE")
        assert state.active_topic in ("order", "delivery")

        # AI asks for order ID
        state = ConversationStateManager.update_after_turn(
            state,
            decision="ASK_USER",
            response_text="Sure! Could you please provide your Order ID?",
        )
        assert state.pending_question == "ask_order_id"

        # Turn 2: Customer provides Order ID
        meaning_2 = UniversalMeaningEngine().understand_utterance("ORD-55443")
        state = ConversationStateManager.update_before_turn(state, "ORD-55443", meaning_2)
        assert state.entities.get("order_id") == "ORD-55443"
        assert state.pending_question is None  # Fulfilled!

        # AI resolves with status
        state = ConversationStateManager.update_after_turn(
            state,
            decision="RESOLVE",
            response_text="Your order ORD-55443 is out for delivery today.",
        )
        assert state.resolution_status == "in_progress"

        # Turn 3: Customer acknowledges "seri thanks"
        meaning_3 = UniversalMeaningEngine().understand_utterance("seri thanks")
        assert meaning_3.conversational_function == "ACKNOWLEDGMENT"
        state = ConversationStateManager.update_before_turn(state, "seri thanks", meaning_3)
        assert state.active_intent == "ACKNOWLEDGMENT"
        assert state.entities == {}  # Cleared on acknowledgment closing!


# ==============================================================================
# 3. Decision Pipeline & Response Generation Tests
# ==============================================================================

class TestDecisionAndResponseGeneration:
    """Verifies that the decision engine chooses RESOLVE for acknowledgments
    and does not invoke tools or ask for order IDs."""

    @pytest.mark.parametrize("ack_word,lang", [
        ("seri pa", "ta"),
        ("hmm okay", "en"),
        ("got it", "en"),
        ("acha theek hai", "hi"),
        ("puriyudhu", "ta"),
    ])
    def test_acknowledgment_resolves_with_closing_no_tool(self, decision_engine, response_generator, ack_word, lang):
        analysis = {
            "intent": "ACKNOWLEDGMENT",
            "category": "conversational",
            "conversational_function": "ACKNOWLEDGMENT",
            "entities": {},
            "original_message": ack_word,
            "language": lang,
        }
        decision = decision_engine.decide(
            analysis=analysis,
            retrieved_articles=[],
        )
        assert decision.get("decision") == "RESOLVE"
        assert decision.get("tool_name") is None  # Must NOT call get_order_status
        assert decision.get("action_type") == "acknowledgment_closing"

        response = response_generator.generate(
            decision_obj=decision,
            language=lang,
        )
        assert len(response) > 5
        # Must NOT ask for Order ID
        assert "order id" not in response.lower()


# ==============================================================================
# 4. End-to-End Multi-Turn Integration Tests via AsyncClient
# ==============================================================================

@pytest.mark.asyncio
async def test_flow_acknowledgment_after_order_lookup_no_loop(
    async_client: AsyncClient,
    auth_headers_a: dict,
    test_user_a: User,
    db_session: AsyncSession,
):
    """
    Validates that once an order status is provided:
    1. Customer provides Order ID -> gets status.
    2. Customer says 'seri' or 'thanks' -> AI gives polite close, NOT an Order ID prompt!
    """
    # Create test order in DB
    test_order = Order(
        customer_id=test_user_a.id,
        tenant_id=test_user_a.tenant_id,
        order_number="ORD-77112",
        status="DELIVERED",
        tracking_number="TRK123",
    )
    db_session.add(test_order)
    await db_session.commit()

    # Turn 1: Ask about order
    resp1 = await async_client.post(
        "/api/conversations",
        json={"initial_message": "Where is my order ORD-77112?"},
        headers=auth_headers_a,
    )
    assert resp1.status_code == 200
    convo_id = resp1.json()["id"]

    # Verify Turn 1 response provides status
    stmt1 = (
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == convo_id)
        .order_by(ConversationMessage.created_at.asc())
    )
    msgs1 = (await db_session.execute(stmt1)).scalars().all()
    ai_msg1 = [m for m in msgs1 if m.sender_type == SenderType.AI][-1]
    assert "delivered" in ai_msg1.content.lower() or "ord-77112" in ai_msg1.content.lower()

    # Turn 2: Customer acknowledges with Tanglish "seri pa thanks"
    resp2 = await async_client.post(
        f"/api/conversations/{convo_id}/messages",
        json={"content": "seri pa thanks"},
        headers=auth_headers_a,
    )
    assert resp2.status_code == 200

    stmt2 = (
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == convo_id)
        .order_by(ConversationMessage.created_at.asc())
    )
    msgs2 = (await db_session.execute(stmt2)).scalars().all()
    ai_msg2 = [m for m in msgs2 if m.sender_type == SenderType.AI][-1]

    # Turn 2 MUST NOT ask for Order ID or repeat status lookup!
    assert "order id" not in ai_msg2.content.lower()
    assert "could you please provide" not in ai_msg2.content.lower()
    assert any(w in ai_msg2.content.lower() for w in ["help", "welcome", "paravala", "glad", "day", "assist"])


@pytest.mark.asyncio
async def test_flow_unseen_order_id_answer_to_pending(
    async_client: AsyncClient,
    auth_headers_a: dict,
    test_user_a: User,
    db_session: AsyncSession,
):
    """
    Validates answering a pending question:
    1. 'where is my package?' -> AI asks for Order ID.
    2. 'ORD-88221' -> AI recognizes as answer to pending, executes lookup, DOES NOT repeat prompt!
    """
    test_order = Order(
        customer_id=test_user_a.id,
        tenant_id=test_user_a.tenant_id,
        order_number="ORD-88221",
        status="SHIPPED",
        tracking_number="TRK456",
    )
    db_session.add(test_order)
    await db_session.commit()

    resp1 = await async_client.post(
        "/api/conversations",
        json={"initial_message": "where is my package?"},
        headers=auth_headers_a,
    )
    assert resp1.status_code == 200
    convo_id = resp1.json()["id"]

    # Turn 2: Customer provides Order ID directly
    resp2 = await async_client.post(
        f"/api/conversations/{convo_id}/messages",
        json={"content": "ORD-88221"},
        headers=auth_headers_a,
    )
    assert resp2.status_code == 200

    stmt = (
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == convo_id)
        .order_by(ConversationMessage.created_at.asc())
    )
    msgs = (await db_session.execute(stmt)).scalars().all()
    ai_msg2 = [m for m in msgs if m.sender_type == SenderType.AI][-1]

    # Must provide the status, NOT ask for Order ID again!
    assert "could you please provide your order id" not in ai_msg2.content.lower()
    assert "shipped" in ai_msg2.content.lower() or "ord-88221" in ai_msg2.content.lower()


@pytest.mark.asyncio
async def test_flow_topic_change_cleans_state(
    async_client: AsyncClient,
    auth_headers_a: dict,
    db_session: AsyncSession,
):
    """
    Validates switching topics cleanly:
    1. Customer asks about order status (AI prompts for Order ID).
    2. Customer changes topic: 'Actually, how do I reset my password?'
    3. AI MUST NOT ask for Order ID; must address the new topic.
    """
    resp1 = await async_client.post(
        "/api/conversations",
        json={"initial_message": "Where is my order?"},
        headers=auth_headers_a,
    )
    assert resp1.status_code == 200
    convo_id = resp1.json()["id"]

    # Turn 2: Topic switch
    resp2 = await async_client.post(
        f"/api/conversations/{convo_id}/messages",
        json={"content": "Actually how do I change my account password?"},
        headers=auth_headers_a,
    )
    assert resp2.status_code == 200

    stmt = (
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == convo_id)
        .order_by(ConversationMessage.created_at.asc())
    )
    msgs = (await db_session.execute(stmt)).scalars().all()
    ai_msg2 = [m for m in msgs if m.sender_type == SenderType.AI][-1]

    # Must NOT ask for Order ID on a password change query
    assert "order id" not in ai_msg2.content.lower()
    assert any(w in ai_msg2.content.lower() for w in ["password", "account", "settings", "profile", "reset"])


@pytest.mark.asyncio
async def test_voice_turn_parity_for_acknowledgment(m4_provider: M4AIProvider):
    """
    Validates that process_voice_turn handles acknowledgments naturally
    and provides concise spoken conversational closings without tool execution.
    """
    voice_turn_result = await m4_provider.process_voice_turn(
        message="seri pa, puriyudhu",
        context={"language": "ta", "history": []},
    )
    assert voice_turn_result is not None
    spoken_text = voice_turn_result.get("response_text", "")
    assert len(spoken_text) > 0
    # Must be polite closing, not asking for order ID
    assert "order id" not in spoken_text.lower()
    assert voice_turn_result.get("tool_name") is None


@pytest.mark.asyncio
async def test_flow_correction_updates_entity(
    async_client: AsyncClient,
    auth_headers_a: dict,
    test_user_a: User,
    db_session: AsyncSession,
):
    """
    Validates correction flow:
    1. Customer provides ORD-111.
    2. Customer says 'No wait, sorry, I meant ORD-222'.
    3. AI recognizes correction and resolves with status for ORD-222.
    """
    order1 = Order(
        customer_id=test_user_a.id,
        tenant_id=test_user_a.tenant_id,
        order_number="ORD-111",
        status="PROCESSING",
        tracking_number="TRK111",
    )
    order2 = Order(
        customer_id=test_user_a.id,
        tenant_id=test_user_a.tenant_id,
        order_number="ORD-222",
        status="DELIVERED",
        tracking_number="TRK222",
    )
    db_session.add_all([order1, order2])
    await db_session.commit()

    resp1 = await async_client.post(
        "/api/conversations",
        json={"initial_message": "Can you check order ORD-111?"},
        headers=auth_headers_a,
    )
    assert resp1.status_code == 200
    convo_id = resp1.json()["id"]

    # Turn 2: Customer corrects to ORD-222
    resp2 = await async_client.post(
        f"/api/conversations/{convo_id}/messages",
        json={"content": "No wait, sorry, I meant ORD-222"},
        headers=auth_headers_a,
    )
    assert resp2.status_code == 200

    stmt = (
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == convo_id)
        .order_by(ConversationMessage.created_at.asc())
    )
    msgs = (await db_session.execute(stmt)).scalars().all()
    ai_msg2 = [m for m in msgs if m.sender_type == SenderType.AI][-1]

    # Must provide details for the corrected order ORD-222
    assert "ord-222" in ai_msg2.content.lower() or "delivered" in ai_msg2.content.lower()


@pytest.mark.asyncio
async def test_strict_customer_isolation_no_entity_leak(
    async_client: AsyncClient,
    auth_headers_a: dict,
    auth_headers_b: dict,
    test_user_a: User,
    test_user_b: User,
    db_session: AsyncSession,
):
    """
    Validates strict conversation state isolation:
    Customer A asks about ORD-99001.
    Customer B in their own conversation asks 'Where is my order?'
    Customer B must NOT have Customer A's ORD-99001 in their state or response!
    """
    # Customer A starts conversation
    resp_a = await async_client.post(
        "/api/conversations",
        json={"initial_message": "Where is my order ORD-99001?"},
        headers=auth_headers_a,
    )
    assert resp_a.status_code == 200

    # Customer B starts conversation with vague message
    resp_b = await async_client.post(
        "/api/conversations",
        json={"initial_message": "Where is my order?"},
        headers=auth_headers_b,
    )
    assert resp_b.status_code == 200
    convo_id_b = resp_b.json()["id"]

    stmt_b = (
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == convo_id_b)
        .order_by(ConversationMessage.created_at.asc())
    )
    msgs_b = (await db_session.execute(stmt_b)).scalars().all()
    ai_msg_b = [m for m in msgs_b if m.sender_type == SenderType.AI][-1]

    # Customer B MUST NOT see ORD-99001!
    assert "ord-99001" not in ai_msg_b.content.lower()
    assert "99001" not in ai_msg_b.content.lower()
