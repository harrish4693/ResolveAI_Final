"""
ResolveAIV2 — Tanglish Continuity, Policy Resolution, and Safe Escalation Regression Suite
========================================================================================
Validates fixes for:
1. Tanglish policy inquiries receiving substantive policy knowledge rather than generic greetings.
2. Explicit language switch ("tanglish la continue pannu") cleanly persisting customer's preferred language.
3. Language switch retaining previous conversational context and answering pending questions in the new language.
4. Language switches alone NEVER causing false expert handoff or escalation.
5. Language switches alone NEVER triggering "technical difficulties" error responses.
6. Sticky preferred language remaining active across subsequent turns.
7. Policy questions never erroneously requesting an Order ID.
8. Voice turn parity for Tanglish language switching and conversational continuity.
9. Explicit human supervisor requests in Tanglish escalating immediately.
10. Account compromise or fraud in Tanglish escalating immediately to critical priority.
"""

import pytest
import asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.users.models import User
from app.conversations.models import Conversation, ConversationMessage
from app.conversations.service import ConversationService
from app.handoff.models import Handoff, HandoffStatus
from app.shared.models import SenderType, WorkflowState
from app.ai.m4.provider import M4AIProvider


@pytest.mark.asyncio
async def test_scenario_1_tanglish_policy_inquiry_answers_policy_not_greeting(
    async_client: AsyncClient,
    auth_headers_a: dict,
    db_session: AsyncSession,
):
    """Scenario 1: Tanglish policy inquiry ('unga return policy enna?') answers return policy, not greeting."""
    resp = await async_client.post(
        "/api/conversations",
        headers=auth_headers_a,
        json={"initial_message": "unga return policy enna?"},
    )
    assert resp.status_code == 200
    convo_id = resp.json()["id"]

    convo_res = await async_client.get(f"/api/conversations/{convo_id}", headers=auth_headers_a)
    assert convo_res.status_code == 200
    assert convo_res.json()["workflow_state"] != "waiting_for_expert"

    msgs_res = await async_client.get(f"/api/conversations/{convo_id}/messages", headers=auth_headers_a)
    assert msgs_res.status_code == 200
    msgs = msgs_res.json()
    ai_msgs = [m for m in msgs if m["sender_type"] == "ai"]
    assert len(ai_msgs) >= 1
    content_lower = ai_msgs[-1]["content"].lower()

    # Must provide return policy details (e.g. 30 days, return, refund)
    assert any(term in content_lower for term in ["return", "refund", "30", "days", "naatkal", "kulla"])
    # Must NOT be a pure generic greeting
    assert not content_lower.startswith("hello! how can i assist")
    # Must NOT ask for Order ID on a general policy inquiry
    assert "order id" not in content_lower


@pytest.mark.asyncio
async def test_scenario_2_explicit_language_switch_updates_preferred_language(
    async_client: AsyncClient,
    auth_headers_a: dict,
    db_session: AsyncSession,
):
    """Scenario 2: 'tanglish la continue pannu' updates conversation.preferred_language to 'tanglish'."""
    resp = await async_client.post(
        "/api/conversations",
        headers=auth_headers_a,
        json={"initial_message": "hi"},
    )
    assert resp.status_code == 200
    convo_id = resp.json()["id"]

    resp2 = await async_client.post(
        f"/api/conversations/{convo_id}/messages",
        headers=auth_headers_a,
        json={"content": "tanglish la continue pannu"},
    )
    assert resp2.status_code == 200

    # Refresh DB conversation and verify preferred_language
    convo = await db_session.scalar(select(Conversation).where(Conversation.id == convo_id))
    assert convo is not None
    assert convo.preferred_language == "tanglish"


@pytest.mark.asyncio
async def test_scenario_3_language_switch_retains_context_and_answers_pending_inquiry(
    async_client: AsyncClient,
    auth_headers_a: dict,
    db_session: AsyncSession,
):
    """Scenario 3: Language switch retains previous question context and answers the pending question in Tanglish."""
    # Step 1: Customer asks about return policy
    resp = await async_client.post(
        "/api/conversations",
        headers=auth_headers_a,
        json={"initial_message": "What is your return policy?"},
    )
    assert resp.status_code == 200
    convo_id = resp.json()["id"]

    # Step 2: Customer asks to switch to Tanglish
    resp2 = await async_client.post(
        f"/api/conversations/{convo_id}/messages",
        headers=auth_headers_a,
        json={"content": "tanglish la continue pannu"},
    )
    assert resp2.status_code == 200

    msgs_res = await async_client.get(f"/api/conversations/{convo_id}/messages", headers=auth_headers_a)
    msgs = msgs_res.json()
    ai_msgs = [m for m in msgs if m["sender_type"] == "ai"]
    assert len(ai_msgs) >= 2
    last_reply = ai_msgs[-1]["content"].lower()

    # The reply should acknowledge Tanglish and provide the return policy info
    assert "tanglish" in last_reply or "pesalam" in last_reply or "kandippa" in last_reply or "sollunga" in last_reply
    assert any(term in last_reply for term in ["return", "refund", "30", "days", "kulla", "naatkal"])
    assert "technical difficulties" not in last_reply


@pytest.mark.asyncio
async def test_scenario_4_language_switch_alone_does_not_create_handoff(
    async_client: AsyncClient,
    auth_headers_a: dict,
    db_session: AsyncSession,
):
    """Scenario 4: Language switch alone does NOT create a handoff or escalate to expert."""
    resp = await async_client.post(
        "/api/conversations",
        headers=auth_headers_a,
        json={"initial_message": "hello"},
    )
    convo_id = resp.json()["id"]

    resp2 = await async_client.post(
        f"/api/conversations/{convo_id}/messages",
        headers=auth_headers_a,
        json={"content": "can we continue in tanglish?"},
    )
    assert resp2.status_code == 200

    # Ensure no handoff record was created
    handoff = await db_session.scalar(
        select(Handoff).where(Handoff.conversation_id == convo_id)
    )
    assert handoff is None

    convo_res = await async_client.get(f"/api/conversations/{convo_id}", headers=auth_headers_a)
    assert convo_res.json()["workflow_state"] != "waiting_for_expert"


@pytest.mark.asyncio
async def test_scenario_5_language_switch_does_not_return_technical_difficulties(
    async_client: AsyncClient,
    auth_headers_a: dict,
    db_session: AsyncSession,
):
    """Scenario 5: Language switch phrases never return 'technical difficulties'."""
    switch_phrases = [
        "tanglish la continue pannu",
        "continue pannunga tanglish la",
        "switch to tanglish",
        "tanglish la pesu",
    ]

    for phrase in switch_phrases:
        resp = await async_client.post(
            "/api/conversations",
            headers=auth_headers_a,
            json={"initial_message": phrase},
        )
        assert resp.status_code == 200
        convo_id = resp.json()["id"]

        msgs_res = await async_client.get(f"/api/conversations/{convo_id}/messages", headers=auth_headers_a)
        ai_msgs = [m for m in msgs_res.json() if m["sender_type"] == "ai"]
        assert len(ai_msgs) == 1
        content_lower = ai_msgs[0]["content"].lower()

        assert "technical difficulties" not in content_lower
        assert "trouble processing" not in content_lower
        assert "tanglish" in content_lower or "pesalam" in content_lower or "sure" in content_lower


@pytest.mark.asyncio
async def test_scenario_6_sticky_language_preference_in_subsequent_turns(
    async_client: AsyncClient,
    auth_headers_a: dict,
    db_session: AsyncSession,
):
    """Scenario 6: Subsequent turns stay in Tanglish once preference is established."""
    resp = await async_client.post(
        "/api/conversations",
        headers=auth_headers_a,
        json={"initial_message": "tanglish la continue pannu"},
    )
    convo_id = resp.json()["id"]

    # Next turn: customer asks about cancellation
    resp2 = await async_client.post(
        f"/api/conversations/{convo_id}/messages",
        headers=auth_headers_a,
        json={"content": "order cancel eppadi pannuradhu?"},
    )
    assert resp2.status_code == 200

    msgs_res = await async_client.get(f"/api/conversations/{convo_id}/messages", headers=auth_headers_a)
    ai_msgs = [m for m in msgs_res.json() if m["sender_type"] == "ai"]
    assert len(ai_msgs) >= 2
    cancellation_reply = ai_msgs[-1]["content"].lower()

    # Must retain Tanglish phrasing and cancellation policy details
    assert any(w in cancellation_reply for w in ["cancel", "pannalam", "mudiyum", "hours", "dispatch", "kulla", "aagum"])
    assert "technical difficulties" not in cancellation_reply


@pytest.mark.asyncio
async def test_scenario_7_policy_question_does_not_prompt_for_order_id(
    async_client: AsyncClient,
    auth_headers_a: dict,
    db_session: AsyncSession,
):
    """Scenario 7: Policy questions ('unga refund policy pathi sollu') do NOT prompt for Order ID."""
    resp = await async_client.post(
        "/api/conversations",
        headers=auth_headers_a,
        json={"initial_message": "unga refund policy pathi sollu"},
    )
    assert resp.status_code == 200
    convo_id = resp.json()["id"]

    msgs_res = await async_client.get(f"/api/conversations/{convo_id}/messages", headers=auth_headers_a)
    ai_msgs = [m for m in msgs_res.json() if m["sender_type"] == "ai"]
    assert len(ai_msgs) >= 1
    content_lower = ai_msgs[0]["content"].lower()

    # Must explain refund policy
    assert any(w in content_lower for w in ["refund", "return", "days", "naatkal", "kulla", "aagum"])
    # Must NOT ask for Order ID
    assert "order id" not in content_lower


@pytest.mark.asyncio
async def test_scenario_8_voice_turn_parity_tanglish_continuity(
    db_session: AsyncSession,
    test_user_a: User,
):
    """Scenario 8: Voice turn pipeline preserves Tanglish language switch and answers properly."""
    provider = M4AIProvider()
    context = {
        "conversation_id": 999,
        "history": [],
        "preferred_language": "tanglish",
        "turn_index": 1,
        "is_voice": True,
    }

    voice_result = await provider.process_voice_turn(
        message="return policy enna?",
        context=context,
        db=db_session,
    )

    assert voice_result is not None
    spoken = voice_result.get("spoken_response", "").lower()
    assert voice_result.get("decision") in ("RESOLVE", "ASK_USER")
    assert any(w in spoken for w in ["return", "refund", "30", "days", "kulla", "naatkal", "solren"])
    assert "technical difficulties" not in spoken


@pytest.mark.asyncio
async def test_scenario_9_explicit_supervisor_request_in_tanglish_escalates_immediately(
    async_client: AsyncClient,
    auth_headers_a: dict,
    db_session: AsyncSession,
):
    """Scenario 9: Explicit supervisor request in Tanglish ('agent kitta connect pannunga') escalates immediately."""
    resp = await async_client.post(
        "/api/conversations",
        headers=auth_headers_a,
        json={"initial_message": "agent kitta connect pannunga"},
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
async def test_scenario_10_tanglish_fraud_or_security_escalates_immediately(
    async_client: AsyncClient,
    auth_headers_a: dict,
    db_session: AsyncSession,
):
    """Scenario 10: Security/fraud issue in Tanglish ('account hack aayiduchu panam thiruditaanga') escalates to CRITICAL."""
    resp = await async_client.post(
        "/api/conversations",
        headers=auth_headers_a,
        json={"initial_message": "account hack aayiduchu panam thiruditaanga"},
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

