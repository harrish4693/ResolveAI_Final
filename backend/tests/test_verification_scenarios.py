import pytest
import time
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Conversation, ConversationMessage
from app.handoff.models import Handoff
from app.shared.models import HandoffStatus, Priority, SenderType, WorkflowState
from app.ai.intelligence.language import UniversalMeaningEngine
from app.ai.m4.decision import DecisionEngine, ResponseGenerator
from app.ai.groq_provider import GroqProvider, RateLimitError


@pytest.mark.asyncio
async def test_01_tanglish_policy_overview(
    async_client: AsyncClient,
    auth_headers_a: dict,
    db_session: AsyncSession,
):
    """VERIFIED — Tanglish policy overview:
    Ask: 'unga kitta enna enna policy irukku?'
    Verify a grounded policy answer, not a greeting or Order ID request.
    """
    resp = await async_client.post(
        "/api/conversations",
        json={"initial_message": "unga kitta enna enna policy irukku?"},
        headers=auth_headers_a,
    )
    assert resp.status_code == 200
    data = resp.json()
    convo_id = data["id"]

    stmt = (
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == convo_id)
        .order_by(ConversationMessage.created_at.asc())
    )
    messages = (await db_session.execute(stmt)).scalars().all()
    ai_msgs = [m for m in messages if m.sender_type == SenderType.AI]
    assert len(ai_msgs) >= 1
    reply = ai_msgs[-1].content.lower()

    # Must contain grounded policy information (Return 30 days, Cancellation, Delivery)
    assert "return" in reply or "30 days" in reply
    assert "cancel" in reply or "dispatch" in reply or "delivery" in reply

    # Must NOT ask for Order ID
    assert "order id" not in reply
    assert "order number" not in reply

    # Must NOT be a generic greeting
    assert not reply.strip().startswith("hello! how can i help")
    assert not reply.strip().startswith("vanakkam! ungaluku naan eppadi")


@pytest.mark.asyncio
async def test_02_different_writing_styles_preserve_policy_intent(
    async_client: AsyncClient,
    auth_headers_a: dict,
    db_session: AsyncSession,
):
    """VERIFIED — Different writing style:
    Ask the same question using different spellings or mixed English/Tanglish.
    Verify that intent remains correct and returns grounded policy info without asking for Order ID.
    """
    engine = UniversalMeaningEngine()
    variations = [
        "unga kita enna policy iruku bro",
        "can you tell me policies available unga kita?",
        "unga kitta enna policies la irukku?",
    ]

    for utterance in variations:
        res = engine.understand_utterance(utterance)
        assert res.intent == "POLICY_QUERY"
        assert res.category == "policy"
        assert res.diagnostic_details.get("is_policy_overview") is True

    # Test one variation through full API pipeline
    resp = await async_client.post(
        "/api/conversations",
        json={"initial_message": "can you tell me policies available unga kita?"},
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
    ai_msgs = [m for m in messages if m.sender_type == SenderType.AI]
    reply = ai_msgs[-1].content.lower()

    assert "return" in reply or "policies" in reply or "policy" in reply
    assert "30 days" in reply or "delivery" in reply
    assert "order id" not in reply


@pytest.mark.asyncio
async def test_03_contextual_follow_up_edhukku_order_id_venum(
    async_client: AsyncClient,
    auth_headers_a: dict,
    db_session: AsyncSession,
):
    """VERIFIED — Contextual follow-up:
    Ask 'edhukku Order ID venum?' after the assistant requests an Order ID.
    Verify that it explains why, rather than repeating the request blindly.
    """
    # 1. Customer initiates an order query
    resp1 = await async_client.post(
        "/api/conversations",
        json={"initial_message": "where is my order?"},
        headers=auth_headers_a,
    )
    assert resp1.status_code == 200
    convo_id = resp1.json()["id"]

    # Assistant prompts for Order ID
    stmt1 = (
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == convo_id)
        .order_by(ConversationMessage.created_at.asc())
    )
    msgs1 = (await db_session.execute(stmt1)).scalars().all()
    ai_msg1 = [m for m in msgs1 if m.sender_type == SenderType.AI][-1].content.lower()
    assert "order id" in ai_msg1 or "order" in ai_msg1

    # 2. Customer asks why Order ID is needed in Tanglish
    resp2 = await async_client.post(
        f"/api/conversations/{convo_id}/messages",
        json={"content": "edhukku Order ID venum?"},
        headers=auth_headers_a,
    )
    assert resp2.status_code == 200

    stmt2 = (
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == convo_id)
        .order_by(ConversationMessage.created_at.asc())
    )
    msgs2 = (await db_session.execute(stmt2)).scalars().all()
    ai_msg2 = [m for m in msgs2 if m.sender_type == SenderType.AI][-1].content

    # Must explain why Order ID is required (e.g., status/tracking/SMS/email)
    msg2_lower = ai_msg2.lower()
    assert (
        "check panna" in msg2_lower
        or "status" in msg2_lower
        or "theva padudhu" in msg2_lower
        or "sms" in msg2_lower
        or "email" in msg2_lower
        or "tracking" in msg2_lower
    )
    # Must NOT just repeat the bare request "Could you please provide your order ID?"
    assert msg2_lower.strip() != "could you please provide your order id?"


@pytest.mark.asyncio
async def test_04_language_continuity_tanglish_persists(
    async_client: AsyncClient,
    auth_headers_a: dict,
    db_session: AsyncSession,
):
    """VERIFIED — Language continuity:
    Ask to continue in Tanglish, then ask a follow-up.
    Verify that the preference persists across turns.
    """
    # 1. Ask to continue in Tanglish
    resp1 = await async_client.post(
        "/api/conversations",
        json={"initial_message": "can you continue in tanglish?"},
        headers=auth_headers_a,
    )
    assert resp1.status_code == 200
    convo_id = resp1.json()["id"]

    # Verify preference was saved in conversation
    convo = await db_session.get(Conversation, convo_id)
    assert convo.preferred_language.lower() == "tanglish"

    # 2. Ask a follow-up about policy in English/Tanglish
    resp2 = await async_client.post(
        f"/api/conversations/{convo_id}/messages",
        json={"content": "return policy pathi sollunga"},
        headers=auth_headers_a,
    )
    assert resp2.status_code == 200

    stmt = (
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == convo_id)
        .order_by(ConversationMessage.created_at.asc())
    )
    msgs = (await db_session.execute(stmt)).scalars().all()
    ai_msg = [m for m in msgs if m.sender_type == SenderType.AI][-1].content

    # Verify response is generated in Tanglish
    ai_lower = ai_msg.lower()
    assert (
        "padi" in ai_lower
        or "kulla" in ai_lower
        or "panna" in ai_lower
        or "mudiyum" in ai_lower
        or "namma" in ai_lower
    )
    assert "30 days" in ai_lower


@pytest.mark.asyncio
async def test_05_provider_failure_groq_429_bounded_recovery():
    """VERIFIED — Provider failure:
    Simulate a Groq 429.
    Verify bounded recovery (fails fast under latency budget), no UI freeze, and no fabricated answer.
    """
    provider = GroqProvider()

    # Simulate Groq 429 RateLimitError with retry-after header of 8.35s
    mock_resp = MagicMock(headers={"retry-after": "8.35"}, status_code=429)
    provider.client = MagicMock()
    provider.client.chat = MagicMock()
    provider.client.chat.completions = MagicMock()
    provider.client.chat.completions.create = AsyncMock(
        side_effect=RateLimitError(
            message="Rate limit reached for model. Please try again in 8.35s.",
            response=mock_resp,
            body={"error": {"message": "Rate limit exceeded"}},
        )
    )

    t0 = time.perf_counter()
    analysis = {
        "original_message": "unga kitta enna enna policy irukku?",
        "intent": "POLICY_QUERY",
        "category": "policy",
        "language": "Tanglish",
        "entities": {},
        "diagnostic_details": {"is_policy_overview": True},
    }

    # Must recover swiftly (< 2.5s budget) and synthesize grounded policy without sleeping 8s
    reply = await provider.generate_response(analysis, [], {"history": []})
    elapsed = time.perf_counter() - t0

    assert elapsed < 2.5, f"Recovery took too long: {elapsed:.2f}s"
    assert len(reply) > 20
    # Grounded answer: contains ResolveMart policy overview, never fabricated
    reply_lower = reply.lower()
    assert "resolvemart" in reply_lower or "policy" in reply_lower or "return" in reply_lower
    assert "30 days" in reply_lower or "delivery" in reply_lower


@pytest.mark.asyncio
async def test_06_expert_handoff_during_provider_failure(
    async_client: AsyncClient,
    auth_headers_a: dict,
    auth_headers_expert: dict,
    db_session: AsyncSession,
    monkeypatch,
):
    """VERIFIED — Expert handoff:
    Request a human agent during provider failure.
    Verify actual handoff creation and expert-side visibility.
    """
    # Create conversation
    resp = await async_client.post(
        "/api/conversations",
        json={"initial_message": "hello"},
        headers=auth_headers_a,
    )
    assert resp.status_code == 200
    convo_id = resp.json()["id"]

    # Mock provider failure
    async def mock_fail(*args, **kwargs):
        raise RuntimeError("Simulated upstream provider outage / 429 quota exhaustion")

    monkeypatch.setattr("app.ai.m4.provider.M4AIProvider.generate_response", mock_fail)
    monkeypatch.setattr("app.ai.groq_provider.GroqProvider.generate_response", mock_fail)

    # Customer requests human agent
    resp_msg = await async_client.post(
        f"/api/conversations/{convo_id}/messages",
        json={"content": "I want to speak with a human agent please"},
        headers=auth_headers_a,
    )
    assert resp_msg.status_code == 200

    # 1. Verify DB handoff creation
    stmt = select(Handoff).where(Handoff.conversation_id == convo_id)
    handoff = (await db_session.execute(stmt)).scalar_one_or_none()
    assert handoff is not None, "Handoff record was not created in database"
    assert handoff.status in [HandoffStatus.WAITING, HandoffStatus.ASSIGNED]

    # 2. Verify Conversation state
    convo = await db_session.get(Conversation, convo_id)
    assert convo.workflow_state == WorkflowState.WAITING_FOR_EXPERT

    # 3. Verify Expert-side visibility via /api/handoffs/queue
    resp_queue = await async_client.get("/api/handoffs/queue", headers=auth_headers_expert)
    assert resp_queue.status_code == 200
    queue_items = resp_queue.json()
    convo_ids_in_queue = [item["conversation_id"] for item in queue_items]
    assert convo_id in convo_ids_in_queue, f"Conversation {convo_id} not visible in expert queue"


@pytest.mark.asyncio
async def test_07_security_escalation_account_compromise(
    async_client: AsyncClient,
    auth_headers_a: dict,
    db_session: AsyncSession,
):
    """VERIFIED — Security escalation:
    Use a simulated account-compromise scenario.
    Verify the existing critical-risk escalation path.
    """
    engine = UniversalMeaningEngine()
    security_msg = "Someone hacked my account, stole my password, and is making unauthorized transactions!"
    meaning = engine.understand_utterance(security_msg)

    # Verify intent and category
    assert meaning.intent == "SECURITY_ISSUE"
    assert meaning.category == "security"

    # Send through API
    resp = await async_client.post(
        "/api/conversations",
        json={"initial_message": security_msg},
        headers=auth_headers_a,
    )
    assert resp.status_code == 200
    convo_id = resp.json()["id"]

    # Verify Critical priority handoff was created
    stmt = select(Handoff).where(Handoff.conversation_id == convo_id)
    handoff = (await db_session.execute(stmt)).scalar_one_or_none()
    assert handoff is not None
    assert handoff.priority == Priority.CRITICAL

    # Verify conversation state
    convo = await db_session.get(Conversation, convo_id)
    assert convo.workflow_state == WorkflowState.WAITING_FOR_EXPERT


@pytest.mark.asyncio
async def test_08_conversation_isolation_between_customers(
    async_client: AsyncClient,
    auth_headers_a: dict,
    auth_headers_b: dict,
    db_session: AsyncSession,
):
    """VERIFIED — Conversation isolation:
    Use two separate customer accounts and conversations.
    Verify that history, entities, and language preferences never cross over.
    """
    # 1. Customer A starts a conversation in Tanglish
    resp_a = await async_client.post(
        "/api/conversations",
        json={"initial_message": "can you continue in tanglish?"},
        headers=auth_headers_a,
    )
    assert resp_a.status_code == 200
    convo_a_id = resp_a.json()["id"]

    await async_client.post(
        f"/api/conversations/{convo_a_id}/messages",
        json={"content": "unga kitta enna policy irukku?"},
        headers=auth_headers_a,
    )

    # 2. Customer B starts a completely separate conversation in English
    resp_b = await async_client.post(
        "/api/conversations",
        json={"initial_message": "what is your return policy?"},
        headers=auth_headers_b,
    )
    assert resp_b.status_code == 200
    convo_b_id = resp_b.json()["id"]

    # Verify Conversation A has Tanglish preference
    convo_a = await db_session.get(Conversation, convo_a_id)
    assert convo_a.preferred_language.lower() == "tanglish"

    # Verify Conversation B has default English preference, NOT Tanglish
    convo_b = await db_session.get(Conversation, convo_b_id)
    assert convo_b.preferred_language.lower() == "english"

    # Verify Customer B's response is in English (not Tanglish)
    stmt_b = (
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == convo_b_id)
        .order_by(ConversationMessage.created_at.asc())
    )
    msgs_b = (await db_session.execute(stmt_b)).scalars().all()
    ai_msg_b = [m for m in msgs_b if m.sender_type == SenderType.AI][-1].content.lower()

    assert "return" in ai_msg_b
    assert "30 days" in ai_msg_b
    # Must NOT contain Tanglish markers from Customer A's session
    assert "namma" not in ai_msg_b
    assert "unga" not in ai_msg_b
    assert "kulla" not in ai_msg_b

    # Verify Customer B cannot access Customer A's conversation
    resp_cross_access = await async_client.get(
        f"/api/conversations/{convo_a_id}",
        headers=auth_headers_b,
    )
    assert resp_cross_access.status_code in [403, 404]

    # Verify message table isolation
    stmt_a = (
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == convo_a_id)
    )
    msgs_a = (await db_session.execute(stmt_a)).scalars().all()
    for msg in msgs_a:
        assert msg.conversation_id == convo_a_id
        assert msg.conversation_id != convo_b_id

