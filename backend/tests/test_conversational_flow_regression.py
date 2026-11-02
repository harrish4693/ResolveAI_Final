"""
ResolveAIV2 — Conversational Flow Regression Test Suite
======================================================
Proves the resolution for repeated AI responses and natural conversation:
1. "hi" receives a greeting rather than an unrelated order-ID request.
2. A subsequent "hello" is processed as a distinct new message.
3. Two distinct customer messages are not accidentally mapped to the same stale response.
4. Genuine order questions still request the necessary Order ID.
5. Follow-up questions retain the relevant conversation context.
6. Duplicate submissions do not create duplicate messages.
7. Existing multilingual intelligence, voice behavior and expert handoff remain intact.
"""

import pytest
import asyncio
import datetime
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.users.models import User
from app.conversations.models import Conversation, ConversationMessage
from app.conversations.service import ConversationService
from app.shared.models import SenderType, WorkflowState
from app.ai.intelligence.language import UniversalMeaningEngine
from app.ai.m4.provider import M4AIProvider
from app.ai.groq_provider import GroqProvider
from app.commerce.models import Order


@pytest.fixture
def meaning_engine():
    return UniversalMeaningEngine()


@pytest.mark.asyncio
async def test_regression_1_hi_receives_greeting_not_order_id(
    async_client: AsyncClient,
    auth_headers_a: dict,
    db_session: AsyncSession,
):
    """Proves 'hi' receives a natural greeting and NOT an Order ID prompt."""
    resp = await async_client.post(
        "/api/conversations",
        json={"initial_message": "hi"},
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
    assert len(messages) >= 2
    ai_msg = [m for m in messages if m.sender_type == SenderType.AI][-1]
    
    # Must NOT ask for Order ID on "hi"
    assert "order id" not in ai_msg.content.lower()
    assert "order" not in ai_msg.content.lower()
    # Must be a friendly greeting or opening offer
    assert any(w in ai_msg.content.lower() for w in ["hello", "hi", "help", "assist"])


@pytest.mark.asyncio
async def test_regression_2_subsequent_hello_is_processed_as_new_message(
    async_client: AsyncClient,
    auth_headers_a: dict,
    db_session: AsyncSession,
):
    """Proves sending 'hi' and then 'hello' processes 'hello' as a distinct turn."""
    # 1. First message: "hi"
    resp1 = await async_client.post(
        "/api/conversations",
        json={"initial_message": "hi"},
        headers=auth_headers_a,
    )
    assert resp1.status_code == 200
    convo_id = resp1.json()["id"]

    # 2. Second message: "hello"
    resp2 = await async_client.post(
        f"/api/conversations/{convo_id}/messages",
        json={"content": "hello"},
        headers=auth_headers_a,
    )
    assert resp2.status_code == 200

    stmt = (
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == convo_id)
        .order_by(ConversationMessage.created_at.asc())
    )
    messages = (await db_session.execute(stmt)).scalars().all()
    
    # We should have 4 messages: Customer(hi), AI, Customer(hello), AI
    customer_msgs = [m for m in messages if m.sender_type == SenderType.CUSTOMER]
    ai_msgs = [m for m in messages if m.sender_type == SenderType.AI]

    assert len(customer_msgs) == 2
    assert customer_msgs[0].content == "hi"
    assert customer_msgs[1].content == "hello"
    assert len(ai_msgs) == 2

    # Second response must also NOT be an Order ID prompt
    assert "order id" not in ai_msgs[1].content.lower()


@pytest.mark.asyncio
async def test_regression_3_distinct_messages_not_mapped_to_same_stale_response(
    async_client: AsyncClient,
    auth_headers_a: dict,
    db_session: AsyncSession,
):
    """Proves two distinct messages (e.g. general question vs greeting) do not receive the same stale response."""
    # Message 1: greeting
    resp1 = await async_client.post(
        "/api/conversations",
        json={"initial_message": "hi"},
        headers=auth_headers_a,
    )
    convo_id = resp1.json()["id"]

    # Message 2: payment question
    resp2 = await async_client.post(
        f"/api/conversations/{convo_id}/messages",
        json={"content": "I have an issue with my payment"},
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

    assert len(ai_msgs) == 2
    # The two AI messages must be distinct and reflect the respective customer turns
    assert ai_msgs[0].content != ai_msgs[1].content
    assert "payment" in ai_msgs[1].content.lower() or "transaction" in ai_msgs[1].content.lower()


@pytest.mark.asyncio
async def test_regression_4_genuine_order_questions_request_order_id(
    async_client: AsyncClient,
    auth_headers_a: dict,
    db_session: AsyncSession,
):
    """Proves genuine order questions ('where is my order?') still ask for the Order ID cleanly."""
    resp = await async_client.post(
        "/api/conversations",
        json={"initial_message": "can i get status of my order?"},
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

    # Must ask for Order ID
    assert "order id" in ai_msg.content.lower() or "order" in ai_msg.content.lower()


@pytest.mark.asyncio
async def test_regression_5_follow_up_questions_retain_conversation_context(
    async_client: AsyncClient,
    auth_headers_a: dict,
    test_user_a: User,
    db_session: AsyncSession,
):
    """Proves follow-up providing an Order ID retains context and retrieves the order status."""
    # Seed an order for test_user_a
    order = Order(
        customer_id=test_user_a.id,
        tenant_id=test_user_a.tenant_id or "default",
        order_number="ORD-99881",
        status="Shipped",
        tracking_number="TRK-99881",
    )
    db_session.add(order)
    await db_session.commit()

    # 1. Ask about order
    resp1 = await async_client.post(
        "/api/conversations",
        json={"initial_message": "where is my order?"},
        headers=auth_headers_a,
    )
    convo_id = resp1.json()["id"]

    # 2. Provide the Order ID as follow-up
    resp2 = await async_client.post(
        f"/api/conversations/{convo_id}/messages",
        json={"content": "ORD-99881"},
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
    assert len(ai_msgs) == 2

    # Second response should report order status or acknowledge the provided order
    assert "ord-99881" in ai_msgs[1].content.lower() or "shipped" in ai_msgs[1].content.lower()


@pytest.mark.asyncio
async def test_regression_6_duplicate_submissions_do_not_create_duplicate_messages(
    async_client: AsyncClient,
    auth_headers_a: dict,
    db_session: AsyncSession,
):
    """Proves rapid identical submissions (e.g. double-click) within 2s are safely de-duplicated."""
    # 1. Initial message
    resp1 = await async_client.post(
        "/api/conversations",
        json={"initial_message": "Hello support"},
        headers=auth_headers_a,
    )
    convo_id = resp1.json()["id"]

    # 2. First follow-up
    await async_client.post(
        f"/api/conversations/{convo_id}/messages",
        json={"content": "duplicate click"},
        headers=auth_headers_a,
    )

    # 3. Rapid duplicate submission with identical content
    await async_client.post(
        f"/api/conversations/{convo_id}/messages",
        json={"content": "duplicate click"},
        headers=auth_headers_a,
    )

    stmt = (
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == convo_id)
        .order_by(ConversationMessage.created_at.asc())
    )
    messages = (await db_session.execute(stmt)).scalars().all()
    dup_messages = [m for m in messages if m.content == "duplicate click"]
    # Only 1 customer message should be created
    assert len(dup_messages) == 1


@pytest.mark.asyncio
async def test_regression_7_multilingual_intelligence_and_handoff_intact(
    async_client: AsyncClient,
    auth_headers_a: dict,
    db_session: AsyncSession,
    meaning_engine: UniversalMeaningEngine,
):
    """Proves multilingual greetings, Tanglish/Hinglish recognition, and human expert handoff remain intact."""
    # 1. Meaning Engine checks
    u_tanglish = meaning_engine.understand_utterance("Vanakkam, eppadi irukkeenga?")
    assert u_tanglish.intent == "GREETING"
    assert u_tanglish.primary_language in ["tamil", "tanglish"] or u_tanglish.code_mix_type in ["tanglish", "tamil"]

    u_hinglish = meaning_engine.understand_utterance("Namaste, mujhe ek dikkat hai")
    assert u_hinglish.intent in ["GREETING", "OPENING_PROBLEM_STATEMENT"]

    # 2. Tanglish routine fallback
    tanglish_fb = ConversationService._get_routine_fallback_prompt("GREETING", "tanglish")
    assert "vanakkam" in tanglish_fb.lower()

    # 3. Explicit escalation demand triggers handoff
    resp = await async_client.post(
        "/api/conversations",
        json={"initial_message": "I demand to talk to a human agent right now"},
        headers=auth_headers_a,
    )
    assert resp.status_code == 200
    convo_id = resp.json()["id"]

    stmt = select(Conversation).where(Conversation.id == convo_id)
    convo = (await db_session.execute(stmt)).scalar_one()
    assert convo.workflow_state == WorkflowState.WAITING_FOR_EXPERT


@pytest.mark.asyncio
async def test_regression_8_direct_order_id_lookup_status(
    async_client: AsyncClient,
    auth_headers_a: dict,
    test_user_a: User,
    db_session: AsyncSession,
):
    """Proves supplying an Order ID directly (e.g. ORD-99881) triggers lookup and returns Shipped status."""
    order = Order(
        customer_id=test_user_a.id,
        tenant_id=test_user_a.tenant_id or "default",
        order_number="ORD-99881",
        status="Shipped",
        tracking_number="TRK-99881",
    )
    db_session.add(order)
    await db_session.commit()

    resp = await async_client.post(
        "/api/conversations",
        json={"initial_message": "ORD-99881"},
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

    # Must contain the authoritative order status and NOT ask for Order ID
    assert "shipped" in ai_msg.content.lower() or "ord-99881" in ai_msg.content.lower()
    assert "could you please provide your order id" not in ai_msg.content.lower()


@pytest.mark.asyncio
async def test_regression_9_nonexistent_order_id_reports_not_found_no_reask(
    async_client: AsyncClient,
    auth_headers_a: dict,
    db_session: AsyncSession,
):
    """Proves supplying a nonexistent Order ID (ORD-123) reports not found and does not ask for ID again."""
    resp = await async_client.post(
        "/api/conversations",
        json={"initial_message": "ORD-123"},
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

    # Must report not found and NOT use the generic "Sure! Could you please provide your Order ID"
    content_lower = ai_msg.content.lower()
    assert "couldn't find an order" in content_lower or "not found" in content_lower
    assert "sure! could you please provide your order id" not in content_lower


@pytest.mark.asyncio
async def test_regression_10_unrecognized_daaksakd_requests_clarification_no_order_id(
    async_client: AsyncClient,
    auth_headers_a: dict,
    db_session: AsyncSession,
):
    """Proves unrecognized gibberish ('daaksakd') asks for clarification and does NOT ask for an Order ID."""
    resp = await async_client.post(
        "/api/conversations",
        json={"initial_message": "daaksakd"},
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

    content_lower = ai_msg.content.lower()
    # Must ask for clarification
    assert any(w in content_lower for w in ["understand", "clarify", "details", "assist", "help"])
    # Must NOT mention or ask for an Order ID
    assert "order id" not in content_lower
    assert "order" not in content_lower


@pytest.mark.asyncio
async def test_regression_11_simulated_provider_failure_escalates_without_order_id_prompt(
    async_client: AsyncClient,
    auth_headers_a: dict,
    db_session: AsyncSession,
    monkeypatch,
):
    """Proves provider failures/rate limits escalate gracefully and do NOT masquerade as an Order ID prompt."""
    from unittest.mock import AsyncMock

    # Create a conversation with an inquiry
    resp = await async_client.post(
        "/api/conversations",
        json={"initial_message": "can you help me with an account inquiry?"},
        headers=auth_headers_a,
    )
    assert resp.status_code == 200
    convo_id = resp.json()["id"]

    # Mock the active provider's generate_response to raise a simulated RateLimitError
    from app.conversations.service import ConversationService
    original_service_init = ConversationService.__init__

    async def mock_generate_failure(*args, **kwargs):
        raise RuntimeError("Simulated upstream provider 429 quota exhaustion")

    monkeypatch.setattr(
        "app.ai.groq_provider.GroqProvider.generate_response",
        mock_generate_failure,
    )
    monkeypatch.setattr(
        "app.ai.m4.provider.M4AIProvider.generate_response",
        mock_generate_failure,
    )

    resp2 = await async_client.post(
        f"/api/conversations/{convo_id}/messages",
        json={"content": "how do I update my settings?"},
        headers=auth_headers_a,
    )
    assert resp2.status_code == 200

    stmt = (
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == convo_id)
        .order_by(ConversationMessage.created_at.asc())
    )
    messages = (await db_session.execute(stmt)).scalars().all()
    last_ai_msg = [m for m in messages if m.sender_type == SenderType.AI][-1]

    # Must escalate or report technical difficulty, NEVER ask for Order ID
    content_lower = last_ai_msg.content.lower()
    assert "technical difficulties" in content_lower or "expert" in content_lower or "escalat" in content_lower
    assert "order id" not in content_lower


@pytest.mark.asyncio
async def test_regression_12_genuine_repeated_questions_respond_consistently(
    async_client: AsyncClient,
    auth_headers_a: dict,
    db_session: AsyncSession,
):
    """Proves genuine repeated questions receive legitimate answers rather than breaking."""
    resp1 = await async_client.post(
        "/api/conversations",
        json={"initial_message": "hi"},
        headers=auth_headers_a,
    )
    convo_id = resp1.json()["id"]

    # Repeat question 1
    resp2 = await async_client.post(
        f"/api/conversations/{convo_id}/messages",
        json={"content": "what is your return policy?"},
        headers=auth_headers_a,
    )
    assert resp2.status_code == 200

    # Repeat question 2 (after small pause to bypass exact 2s debounce window)
    await asyncio.sleep(2.1)
    resp3 = await async_client.post(
        f"/api/conversations/{convo_id}/messages",
        json={"content": "what is your return policy?"},
        headers=auth_headers_a,
    )
    assert resp3.status_code == 200

    stmt = (
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == convo_id)
        .order_by(ConversationMessage.created_at.asc())
    )
    messages = (await db_session.execute(stmt)).scalars().all()
    ai_msgs = [m for m in messages if m.sender_type == SenderType.AI]
    # We should have 3 AI responses total (for hi, question 1, and question 2)
    assert len(ai_msgs) == 3
    # Neither return policy response should erroneously ask for Order ID
    assert "order id" not in ai_msgs[1].content.lower()
    assert "order id" not in ai_msgs[2].content.lower()

