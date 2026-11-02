"""
ResolveAIV2 — Comprehensive Expert Handoff Suite

Covers:
1. End-to-end handoff lifecycle: M4 escalation, expert queue retrieval, atomic assignment, double-claim protection, messaging, resolution, and feedback.
2. Expert transfer validation: self-transfer prevention, inactive expert protection, successful transfer, and previous expert authorization revocation.
3. Internal notes security: isolation of internal expert notes from customer views.
4. Adaptive autonomy regression: explicit human requests (English, Tanglish, Tamil, Hinglish, Hindi), high confidence non-blocking, failure prediction escalation, clarification questioning, non-duplication, truthful queue states, context completeness, and tenant isolation.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Conversation, ConversationMessage
from app.feedback.models import Feedback
from app.handoff.models import Handoff
from app.shared.models import HandoffStatus, SenderType, UserRole, WorkflowState
from app.tickets.models import Ticket
from app.users.models import User


# ============================================================================
# Section 1: End-to-End Handoff Lifecycle
# ============================================================================

@pytest.mark.asyncio
async def test_m5_handoff_lifecycle(
    async_client: AsyncClient,
    auth_headers_a: dict,
    auth_headers_b: dict,
    auth_headers_expert: dict,
    db_session: AsyncSession,
):
    """M4 ESCALATE creates handoff, queue management, atomic claim, messaging, resolution, and feedback."""
    # 1. M4 ESCALATE creates handoff
    response = await async_client.post(
        "/api/conversations",
        headers=auth_headers_a,
        json={"initial_message": "Someone accessed my account and stole money!", "subject": "Hacked"},
    )
    convo_id = response.json()["id"]

    convo_res = await async_client.get(f"/api/conversations/{convo_id}", headers=auth_headers_a)
    assert convo_res.json()["workflow_state"] == "waiting_for_expert"

    # Check Handoff
    result = await db_session.execute(select(Handoff).where(Handoff.conversation_id == convo_id))
    handoff = result.scalar_one_or_none()
    assert handoff is not None
    assert handoff.status == HandoffStatus.WAITING
    assert handoff.category == "Security"
    assert handoff.priority == "critical"

    # 2. Expert Queue Retrieval
    queue_res = await async_client.get("/api/handoffs/queue", headers=auth_headers_expert)
    assert queue_res.status_code == 200
    queue = queue_res.json()
    assert any(h["id"] == handoff.id for h in queue)

    # 3. Customer Unauthorized Access to Queue
    bad_queue = await async_client.get("/api/handoffs/queue", headers=auth_headers_a)
    assert bad_queue.status_code == 403

    # 4. Expert Assignment (Atomic Claim)
    assign_res = await async_client.post(f"/api/handoffs/{handoff.id}/assign", headers=auth_headers_expert)
    assert assign_res.status_code == 200
    assert assign_res.json()["status"] == HandoffStatus.ASSIGNED

    # 5. Double-Claim Protection
    assign_res2 = await async_client.post(f"/api/handoffs/{handoff.id}/assign", headers=auth_headers_expert)
    assert assign_res2.status_code == 409

    # 6. Customer checks workflow state
    convo_res2 = await async_client.get(f"/api/conversations/{convo_id}", headers=auth_headers_a)
    assert convo_res2.json()["workflow_state"] == "with_expert"

    # 7. Customer sends message while with expert (should not trigger AI)
    await async_client.post(
        f"/api/conversations/{convo_id}/messages",
        headers=auth_headers_a,
        json={"content": "Are you there?"},
    )

    # 8. Expert sends message
    msg_res = await async_client.post(
        f"/api/conversations/{convo_id}/messages",
        headers=auth_headers_expert,
        json={"content": "Yes, I am looking into your account now."},
    )
    assert msg_res.status_code == 200

    # Verify message isolation (Customer B cannot view Customer A conversation)
    bad_view = await async_client.get(f"/api/conversations/{convo_id}", headers=auth_headers_b)
    assert bad_view.status_code == 404

    # 9. Expert Resolves
    resolve_res = await async_client.post(
        f"/api/handoffs/{handoff.id}/resolve",
        headers=auth_headers_expert,
        json={"resolution_message": "Account secured."},
    )
    assert resolve_res.status_code == 200

    # 10. Check Conversation is RESOLVED
    convo_res3 = await async_client.get(f"/api/conversations/{convo_id}", headers=auth_headers_a)
    assert convo_res3.json()["workflow_state"] == "resolved"

    # 11. Feedback Submission
    feed_res = await async_client.post(
        f"/api/conversations/{convo_id}/feedback",
        headers=auth_headers_a,
        json={"rating": 5, "comment": "Great service!"},
    )
    assert feed_res.status_code == 200

    # 12. Duplicate feedback rejection
    feed_res2 = await async_client.post(
        f"/api/conversations/{convo_id}/feedback",
        headers=auth_headers_a,
        json={"rating": 1, "comment": "Changed mind."},
    )
    assert feed_res2.status_code == 409


# ============================================================================
# Section 2: Expert Transfer & Authorization
# ============================================================================

@pytest.mark.asyncio
async def test_transfer_validation(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_user_a: User,
    test_expert: User,
    auth_headers_expert: dict,
):
    """Validation rules for transferring handoff cases between experts."""
    # Create another expert
    other_expert = User(
        email="expert2@example.com",
        password_hash="hash",
        full_name="Expert Two",
        role=UserRole.EXPERT,
        is_active=True,
    )
    db_session.add(other_expert)

    # Create inactive expert
    inactive_expert = User(
        email="inactive@example.com",
        password_hash="hash",
        full_name="Inactive Expert",
        role=UserRole.EXPERT,
        is_active=False,
    )
    db_session.add(inactive_expert)
    await db_session.flush()

    # Create conversation and handoff assigned to test_expert
    convo = Conversation(customer_id=test_user_a.id)
    db_session.add(convo)
    await db_session.flush()

    ticket = Ticket(customer_id=test_user_a.id, conversation_id=convo.id, subject="Transfer test")
    db_session.add(ticket)
    await db_session.flush()

    handoff = Handoff(
        conversation_id=convo.id,
        ticket_id=ticket.id,
        customer_id=test_user_a.id,
        status=HandoffStatus.ASSIGNED,
        assigned_expert_id=test_expert.id,
        category="general",
        escalation_reason="test",
    )
    db_session.add(handoff)
    await db_session.commit()

    # 1. Expert cannot transfer to themselves
    res = await async_client.post(
        f"/api/handoffs/{handoff.id}/transfer",
        json={"expert_id": test_expert.id},
        headers=auth_headers_expert,
    )
    assert res.status_code == 400
    assert "Cannot transfer to yourself" in res.json()["detail"]

    # 2. Cannot transfer to inactive expert
    res = await async_client.post(
        f"/api/handoffs/{handoff.id}/transfer",
        json={"expert_id": inactive_expert.id},
        headers=auth_headers_expert,
    )
    assert res.status_code == 400
    assert "Target expert not found or inactive" in res.json()["detail"]

    # 3. Successful transfer to another active expert
    res = await async_client.post(
        f"/api/handoffs/{handoff.id}/transfer",
        json={"expert_id": other_expert.id},
        headers=auth_headers_expert,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == HandoffStatus.ASSIGNED.value
    assert data["assigned_expert_id"] == other_expert.id

    # 4. test_expert no longer has access to context
    res_context = await async_client.get(
        f"/api/handoffs/{handoff.id}/context",
        headers=auth_headers_expert,
    )
    assert res_context.status_code == 403


# ============================================================================
# Section 3: Internal Notes Isolation
# ============================================================================

@pytest.mark.asyncio
async def test_customer_cannot_access_internal_notes(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_user_a: User,
    test_expert: User,
    auth_headers_expert: dict,
    auth_headers_a: dict,
):
    """Ensure internal expert notes are strictly inaccessible to customer views."""
    # Create conversation
    convo = Conversation(customer_id=test_user_a.id)
    db_session.add(convo)
    await db_session.flush()

    # Create ticket
    ticket = Ticket(customer_id=test_user_a.id, conversation_id=convo.id, subject="Test internal notes")
    db_session.add(ticket)
    await db_session.flush()

    # Create active handoff for expert
    handoff = Handoff(
        conversation_id=convo.id,
        ticket_id=ticket.id,
        customer_id=test_user_a.id,
        status=HandoffStatus.ASSIGNED,
        assigned_expert_id=test_expert.id,
        category="general",
        escalation_reason="test",
    )
    db_session.add(handoff)
    await db_session.flush()

    # Create public message from expert
    msg_public = ConversationMessage(
        conversation_id=convo.id,
        sender_type=SenderType.EXPERT,
        sender_id=test_expert.id,
        content="This is public",
    )
    db_session.add(msg_public)

    # Create internal message from expert
    msg_internal = ConversationMessage(
        conversation_id=convo.id,
        sender_type=SenderType.EXPERT,
        sender_id=test_expert.id,
        content="This is internal",
        metadata_={"is_internal": True},
    )
    db_session.add(msg_internal)
    await db_session.commit()

    # Customer fetches messages
    res_customer = await async_client.get(f"/api/conversations/{convo.id}/messages", headers=auth_headers_a)
    assert res_customer.status_code == 200
    customer_msgs = res_customer.json()
    assert len(customer_msgs) == 1
    assert customer_msgs[0]["content"] == "This is public"

    # Try to manipulate request parameters (e.g., query strings)
    res_customer_manip = await async_client.get(
        f"/api/conversations/{convo.id}/messages?exclude_internal=false",
        headers=auth_headers_a,
    )
    customer_msgs_manip = res_customer_manip.json()
    assert len(customer_msgs_manip) == 1
    assert customer_msgs_manip[0]["content"] == "This is public"

    # Expert fetches messages
    res_expert = await async_client.get(f"/api/conversations/{convo.id}/messages", headers=auth_headers_expert)
    assert res_expert.status_code == 200
    expert_msgs = res_expert.json()
    assert len(expert_msgs) == 2
    contents = [m["content"] for m in expert_msgs]
    assert "This is public" in contents
    assert "This is internal" in contents


# ============================================================================
# Section 4: Adaptive Autonomy & Handoff Regressions
# ============================================================================

@pytest.mark.asyncio
async def test_scenario_1_english_direct_requests_trigger_immediate_handoff(
    async_client: AsyncClient, auth_headers_a: dict, db_session: AsyncSession
):
    """Scenario 1: Direct English human/expert escalation requests trigger immediate handoff."""
    phrases = [
        "I want to talk to a human.",
        "Connect me to an expert.",
        "Can I speak to a real person?",
        "Please transfer me to customer support.",
    ]

    for phrase in phrases:
        resp = await async_client.post(
            "/api/conversations",
            headers=auth_headers_a,
            json={"initial_message": phrase},
        )
        assert resp.status_code == 200, f"Failed on phrase: {phrase}"
        convo_id = resp.json()["id"]

        convo_res = await async_client.get(f"/api/conversations/{convo_id}", headers=auth_headers_a)
        assert convo_res.status_code == 200
        convo_data = convo_res.json()

        assert convo_data["workflow_state"] == "waiting_for_expert", (
            f"Expected waiting_for_expert for '{phrase}', got '{convo_data['workflow_state']}'"
        )

        handoff = await db_session.scalar(
            select(Handoff).where(Handoff.conversation_id == convo_id)
        )
        assert handoff is not None, f"Handoff record missing for phrase: {phrase}"
        assert handoff.status == HandoffStatus.WAITING

        msgs_res = await async_client.get(f"/api/conversations/{convo_id}/messages", headers=auth_headers_a)
        assert msgs_res.status_code == 200
        msgs = msgs_res.json()
        ai_msgs = [m for m in msgs if m["sender_type"] == "ai"]
        assert len(ai_msgs) == 1
        assert "expert" in ai_msgs[0]["content"].lower() or "support" in ai_msgs[0]["content"].lower() or "hold on" in ai_msgs[0]["content"].lower()


@pytest.mark.asyncio
async def test_scenario_2_multilingual_direct_requests_trigger_immediate_handoff(
    async_client: AsyncClient, auth_headers_a: dict, db_session: AsyncSession
):
    """Scenario 2: Multilingual direct requests (Tanglish, Tamil, Hinglish, Hindi) trigger immediate handoff."""
    multilingual_phrases = [
        ("Agent kitta connect pannunga.", "tanglish"),
        ("Enakku human support venum.", "tanglish"),
        ("மனித ஆதரவு வேண்டும்", "tamil"),
        ("Mujhe human agent se baat karni hai.", "hinglish"),
        ("मानव सहायता चाहिए", "hindi"),
    ]

    for phrase, lang_type in multilingual_phrases:
        resp = await async_client.post(
            "/api/conversations",
            headers=auth_headers_a,
            json={"initial_message": phrase},
        )
        assert resp.status_code == 200, f"Failed on multilingual phrase: {phrase}"
        convo_id = resp.json()["id"]

        convo_res = await async_client.get(f"/api/conversations/{convo_id}", headers=auth_headers_a)
        assert convo_res.status_code == 200
        convo_data = convo_res.json()

        assert convo_data["workflow_state"] == "waiting_for_expert", (
            f"Expected waiting_for_expert for '{phrase}' ({lang_type}), got '{convo_data['workflow_state']}'"
        )

        handoff = await db_session.scalar(
            select(Handoff).where(Handoff.conversation_id == convo_id)
        )
        assert handoff is not None, f"Handoff record missing for '{phrase}'"
        assert handoff.status == HandoffStatus.WAITING


@pytest.mark.asyncio
async def test_scenario_3_high_ai_confidence_does_not_block_explicit_human_request(
    async_client: AsyncClient, auth_headers_a: dict, db_session: AsyncSession
):
    """Scenario 3: Explicit customer request for human support cannot be overridden by AI confidence."""
    resp = await async_client.post(
        "/api/conversations",
        headers=auth_headers_a,
        json={"initial_message": "I know you have answers, but I want to talk to a human supervisor right now."},
    )
    assert resp.status_code == 200
    convo_id = resp.json()["id"]

    convo_res = await async_client.get(f"/api/conversations/{convo_id}", headers=auth_headers_a)
    assert convo_res.json()["workflow_state"] == "waiting_for_expert"

    handoff = await db_session.scalar(
        select(Handoff).where(Handoff.conversation_id == convo_id)
    )
    assert handoff is not None
    assert handoff.status == HandoffStatus.WAITING


@pytest.mark.asyncio
async def test_scenario_4_low_confidence_or_failure_risk_escalates(
    async_client: AsyncClient, auth_headers_a: dict, db_session: AsyncSession
):
    """Scenario 4: High resolution failure risk or security risk escalates autonomously."""
    resp = await async_client.post(
        "/api/conversations",
        headers=auth_headers_a,
        json={"initial_message": "Someone accessed my account and stole money!"},
    )
    assert resp.status_code == 200
    convo_id = resp.json()["id"]

    convo_res = await async_client.get(f"/api/conversations/{convo_id}", headers=auth_headers_a)
    assert convo_res.json()["workflow_state"] == "waiting_for_expert"

    handoff = await db_session.scalar(
        select(Handoff).where(Handoff.conversation_id == convo_id)
    )
    assert handoff is not None
    assert handoff.status == HandoffStatus.WAITING
    assert handoff.priority == "critical"


@pytest.mark.asyncio
async def test_scenario_5_missing_info_asks_clarification_no_premature_escalation(
    async_client: AsyncClient, auth_headers_a: dict
):
    """Scenario 5: When information is missing, ask one concise clarification question instead of premature escalation."""
    resp = await async_client.post(
        "/api/conversations",
        headers=auth_headers_a,
        json={"initial_message": "Where is my package? When will it be delivered?"},
    )
    assert resp.status_code == 200
    convo_id = resp.json()["id"]

    convo_res = await async_client.get(f"/api/conversations/{convo_id}", headers=auth_headers_a)
    convo_data = convo_res.json()

    assert convo_data["workflow_state"] == "asking_user"

    msgs_res = await async_client.get(f"/api/conversations/{convo_id}/messages", headers=auth_headers_a)
    assert msgs_res.status_code == 200
    msgs = msgs_res.json()
    ai_msgs = [m for m in msgs if m["sender_type"] == "ai"]
    assert len(ai_msgs) == 1
    assert "order id" in ai_msgs[0]["content"].lower()


@pytest.mark.asyncio
async def test_scenario_6_repeated_failed_attempts_escalate(
    async_client: AsyncClient, auth_headers_a: dict, db_session: AsyncSession
):
    """Scenario 6: Multiple consecutive attempts without resolution escalate to an expert."""
    resp = await async_client.post(
        "/api/conversations",
        headers=auth_headers_a,
        json={"initial_message": "My device does not turn on at all."},
    )
    convo_id = resp.json()["id"]

    await async_client.post(
        f"/api/conversations/{convo_id}/messages",
        headers=auth_headers_a,
        json={"content": "I already tried that and it's still broken."},
    )

    await async_client.post(
        f"/api/conversations/{convo_id}/messages",
        headers=auth_headers_a,
        json={"content": "Nothing works, this is terrible and completely unresponsive."},
    )

    convo_res = await async_client.get(f"/api/conversations/{convo_id}", headers=auth_headers_a)
    convo_data = convo_res.json()

    assert convo_data["workflow_state"] == "waiting_for_expert"

    handoff = await db_session.scalar(
        select(Handoff).where(Handoff.conversation_id == convo_id)
    )
    assert handoff is not None
    assert handoff.status == HandoffStatus.WAITING


@pytest.mark.asyncio
async def test_scenario_7_repeated_customer_requests_do_not_create_duplicate_handoffs(
    async_client: AsyncClient, auth_headers_a: dict, db_session: AsyncSession
):
    """Scenario 7: Repeated escalation messages in the same conversation do not create duplicate handoff rows."""
    resp = await async_client.post(
        "/api/conversations",
        headers=auth_headers_a,
        json={"initial_message": "Connect me to an expert."},
    )
    convo_id = resp.json()["id"]

    await async_client.post(
        f"/api/conversations/{convo_id}/messages",
        headers=auth_headers_a,
        json={"content": "Please hurry, connect me to an expert now!"},
    )

    result = await db_session.execute(
        select(Handoff).where(Handoff.conversation_id == convo_id)
    )
    handoffs = result.scalars().all()
    assert len(handoffs) == 1
    assert handoffs[0].status == HandoffStatus.WAITING


@pytest.mark.asyncio
async def test_scenario_8_no_available_expert_preserves_truthful_waiting_state(
    async_client: AsyncClient, auth_headers_a: dict, db_session: AsyncSession
):
    """Scenario 8: If no expert has claimed the ticket, state remains WAITING; never claims expert joined."""
    resp = await async_client.post(
        "/api/conversations",
        headers=auth_headers_a,
        json={"initial_message": "I want to speak to an expert."},
    )
    convo_id = resp.json()["id"]

    convo_res = await async_client.get(f"/api/conversations/{convo_id}", headers=auth_headers_a)
    convo_data = convo_res.json()

    assert convo_data["workflow_state"] == "waiting_for_expert"

    handoff = await db_session.scalar(
        select(Handoff).where(Handoff.conversation_id == convo_id)
    )
    assert handoff.status == HandoffStatus.WAITING
    assert handoff.assigned_expert_id is None

    msgs_res = await async_client.get(f"/api/conversations/{convo_id}/messages", headers=auth_headers_a)
    assert msgs_res.status_code == 200
    msgs = msgs_res.json()
    ai_msgs = [m for m in msgs if m["sender_type"] == "ai"]
    for msg in ai_msgs:
        assert "has joined" not in msg["content"].lower()


@pytest.mark.asyncio
async def test_scenario_9_expert_assignment_updates_customer_state_to_with_expert(
    async_client: AsyncClient,
    auth_headers_a: dict,
    auth_headers_expert: dict,
    db_session: AsyncSession,
):
    """Scenario 9: Expert claiming the handoff transitions conversation to with_expert."""
    resp = await async_client.post(
        "/api/conversations",
        headers=auth_headers_a,
        json={"initial_message": "Connect me to an expert."},
    )
    convo_id = resp.json()["id"]

    handoff = await db_session.scalar(
        select(Handoff).where(Handoff.conversation_id == convo_id)
    )

    assign_res = await async_client.post(
        f"/api/handoffs/{handoff.id}/assign",
        headers=auth_headers_expert,
    )
    assert assign_res.status_code == 200
    assert assign_res.json()["status"] == HandoffStatus.ASSIGNED

    convo_res = await async_client.get(f"/api/conversations/{convo_id}", headers=auth_headers_a)
    assert convo_res.json()["workflow_state"] == "with_expert"


@pytest.mark.asyncio
async def test_scenario_10_expert_context_completeness(
    async_client: AsyncClient,
    auth_headers_a: dict,
    auth_headers_expert: dict,
    db_session: AsyncSession,
):
    """Scenario 10: Expert context contains conversation history, language details, and extracted entities."""
    resp = await async_client.post(
        "/api/conversations",
        headers=auth_headers_a,
        json={"initial_message": "En order ORD-77665 varala, please agent kitta connect pannunga."},
    )
    convo_id = resp.json()["id"]

    handoff = await db_session.scalar(
        select(Handoff).where(Handoff.conversation_id == convo_id)
    )

    await async_client.post(f"/api/handoffs/{handoff.id}/assign", headers=auth_headers_expert)

    ctx_res = await async_client.get(
        f"/api/handoffs/{handoff.id}/context",
        headers=auth_headers_expert,
    )
    assert ctx_res.status_code == 200
    ctx_data = ctx_res.json()

    assert "ai_context" in ctx_data
    assert "summary" in ctx_data["ai_context"]
    assert "intent" in ctx_data["ai_context"]
    assert "language_context" in ctx_data


@pytest.mark.asyncio
async def test_scenario_11_tenant_isolation_and_authorization(
    async_client: AsyncClient,
    auth_headers_a: dict,
    auth_headers_b: dict,
    db_session: AsyncSession,
):
    """Scenario 11: Customers cannot access the expert queue or another customer's handoff context."""
    resp = await async_client.post(
        "/api/conversations",
        headers=auth_headers_a,
        json={"initial_message": "Connect me to an expert."},
    )
    convo_id = resp.json()["id"]

    handoff = await db_session.scalar(
        select(Handoff).where(Handoff.conversation_id == convo_id)
    )

    queue_res = await async_client.get("/api/handoffs/queue", headers=auth_headers_a)
    assert queue_res.status_code == 403

    queue_res_b = await async_client.get("/api/handoffs/queue", headers=auth_headers_b)
    assert queue_res_b.status_code == 403

    ctx_res = await async_client.get(f"/api/handoffs/{handoff.id}/context", headers=auth_headers_b)
    assert ctx_res.status_code == 403


@pytest.mark.asyncio
async def test_scenario_12_existing_resolve_ask_user_escalate_parity(
    async_client: AsyncClient, auth_headers_a: dict
):
    """Scenario 12: Baseline RESOLVE, ASK_USER, and ESCALATE continue operating with precision."""
    # 1. Greeting -> ASK_USER (Hello!)
    resp1 = await async_client.post(
        "/api/conversations",
        headers=auth_headers_a,
        json={"initial_message": "Hello!"},
    )
    assert resp1.status_code == 200
    assert resp1.json()["workflow_state"] == "asking_user"

    # 2. Known policy inquiry -> RESOLVE
    resp2 = await async_client.post(
        "/api/conversations",
        headers=auth_headers_a,
        json={"initial_message": "What are your customer service hours?"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["workflow_state"] == "resolving"


# ============================================================================
# Section 5: Voice Call Channel Indicator Regression
# ============================================================================

@pytest.mark.asyncio
async def test_voice_call_handoff_channel_indicator_regression(
    async_client: AsyncClient,
    auth_headers_a: dict,
    auth_headers_expert: dict,
    db_session: AsyncSession,
):
    """
    Regression test:
    1. Voice-call originated escalations (channel='voice') must preserve channel='voice'
       in DB persistence, queue listing, conversation handoff, and context API responses.
    2. Text-chat originated escalations (channel='text') must preserve channel='text'.
    3. Channel remains correct after expert assignment and across lifecycle steps.
    """
    # --- 1. Voice Call Escalation ---
    voice_resp = await async_client.post(
        "/api/conversations",
        headers=auth_headers_a,
        json={
            "channel": "voice",
            "subject": "Voice Call with ResolveAI",
            "initial_message": "Someone accessed my account and stole money!",
        },
    )
    assert voice_resp.status_code == 200
    voice_convo = voice_resp.json()
    voice_convo_id = voice_convo["id"]
    assert voice_convo["channel"] == "voice"
    assert voice_convo["workflow_state"] == "waiting_for_expert"

    # Verify Queue lists the handoff with channel == 'voice'
    queue_res = await async_client.get("/api/handoffs/queue", headers=auth_headers_expert)
    assert queue_res.status_code == 200
    voice_queue_items = [h for h in queue_res.json() if h["conversation_id"] == voice_convo_id]
    assert len(voice_queue_items) == 1
    voice_item = voice_queue_items[0]
    assert voice_item["channel"] == "voice"
    voice_handoff_id = voice_item["id"]

    # Verify GET /api/handoffs/conversation/{conversation_id} returns channel == 'voice'
    conv_handoff_res = await async_client.get(
        f"/api/handoffs/conversation/{voice_convo_id}",
        headers=auth_headers_expert,
    )
    assert conv_handoff_res.status_code == 200
    assert conv_handoff_res.json()["channel"] == "voice"

    # Verify GET /api/handoffs/{id}/context and /conversation/{id}/context include channel in active_ticket
    ctx_res = await async_client.get(
        f"/api/handoffs/{voice_handoff_id}/context",
        headers=auth_headers_expert,
    )
    assert ctx_res.status_code == 200
    ctx_data = ctx_res.json()
    assert ctx_data["active_ticket"]["channel"] == "voice"

    conv_ctx_res = await async_client.get(
        f"/api/handoffs/conversation/{voice_convo_id}/context",
        headers=auth_headers_expert,
    )
    assert conv_ctx_res.status_code == 200
    assert conv_ctx_res.json()["active_ticket"]["channel"] == "voice"

    # Verify after assignment, channel is still voice
    assign_res = await async_client.post(
        f"/api/handoffs/{voice_handoff_id}/assign",
        headers=auth_headers_expert,
    )
    assert assign_res.status_code == 200
    assert assign_res.json()["channel"] == "voice"

    # --- 2. Text Chat Escalation ---
    text_resp = await async_client.post(
        "/api/conversations",
        headers=auth_headers_a,
        json={
            "channel": "text",
            "subject": "Text Hacked Support",
            "initial_message": "Fraudulent charge detected on my card, urgent help needed!",
        },
    )
    assert text_resp.status_code == 200
    text_convo = text_resp.json()
    text_convo_id = text_convo["id"]
    assert text_convo["channel"] == "text"

    # Verify queue returns channel == 'text'
    queue_res2 = await async_client.get("/api/handoffs/queue", headers=auth_headers_expert)
    text_queue_items = [h for h in queue_res2.json() if h["conversation_id"] == text_convo_id]
    assert len(text_queue_items) == 1
    text_item = text_queue_items[0]
    assert text_item["channel"] == "text"

    # Verify GET /api/handoffs/conversation/{conversation_id} returns channel == 'text'
    text_conv_handoff = await async_client.get(
        f"/api/handoffs/conversation/{text_convo_id}",
        headers=auth_headers_expert,
    )
    assert text_conv_handoff.status_code == 200
    assert text_conv_handoff.json()["channel"] == "text"

    # Verify context returns channel == 'text'
    text_ctx_res = await async_client.get(
        f"/api/handoffs/{text_item['id']}/context",
        headers=auth_headers_expert,
    )
    assert text_ctx_res.status_code == 200
    assert text_ctx_res.json()["active_ticket"]["channel"] == "text"

