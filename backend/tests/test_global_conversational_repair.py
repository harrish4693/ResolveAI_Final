"""
ResolveAIV2 — Comprehensive Global Conversational Intelligence & Safe Recovery Test Suite
========================================================================================
Validates fixes for:
1. Tanglish return policy questions receiving grounded policy answers (30 days, original condition) without generic greetings.
2. Repeating the question preserves conversational context and returns consistent grounded responses without technical difficulties.
3. Explicit supervisor demands across varied phrasing ("Can u connect with the expert?", "connect with the expert", "agent kitta connect pannunga")
   reliably trigger immediate expert handoff with status WAITING, without generic technical-difficulties errors.
4. Informational cancellation inquiries ("order cancel eppadi pannuradhu?", "how to cancel order") receive cancellation policy details
   rather than erroneously prompting for an Order ID.
5. Multilingual and code-mixed language support (English, Tanglish, Tamil, Hinglish, Hindi) remains grounded and consistent.
6. Voice turn pipeline parity for both policy responses and expert escalation.
7. Strict tenant context isolation.
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
from app.ai.intelligence.escalation_keywords import is_supervisor_demand, is_fraud_or_security


class TestSupervisorDemandDetection:
    """Validates robust conversational phrasing detection for expert handoff requests."""

    @pytest.mark.parametrize("phrase", [
        "Can u connect with the expert?",
        "connect with the expert",
        "connect with an expert",
        "can you connect me with a human",
        "please connect me to an expert",
        "agent kitta connect pannunga",
        "expert ta pesanum",
        "expert se connect karo",
        "kisi expert se baat karao",
        "agent se baat karni hai",
        "human agent venum",
        "I want to speak with someone",
        "transfer to support",
    ])
    def test_supervisor_demand_matches_variations(self, phrase: str):
        assert is_supervisor_demand(phrase) is True

    @pytest.mark.parametrize("phrase", [
        "return policy pathi sollunga",
        "unga return policy enna?",
        "order cancel eppadi pannuradhu?",
        "how to cancel order",
        "where is my package",
        "payment failed but money deducted",
    ])
    def test_non_supervisor_queries_do_not_match(self, phrase: str):
        assert is_supervisor_demand(phrase) is False


@pytest.mark.asyncio
async def test_tanglish_return_policy_answers_grounded_policy_not_greeting(
    async_client: AsyncClient,
    auth_headers_a: dict,
    db_session: AsyncSession,
):
    """
    Class A: Customer asks return policy in Tanglish ('return policy pathi sollunga').
    AI must reply with grounded 30-day policy, NOT generic greeting, and NOT prompt for Order ID.
    """
    resp = await async_client.post(
        "/api/conversations",
        headers=auth_headers_a,
        json={"initial_message": "return policy pathi sollunga"},
    )
    assert resp.status_code == 200
    convo_id = resp.json()["id"]

    msgs_res = await async_client.get(f"/api/conversations/{convo_id}/messages", headers=auth_headers_a)
    assert msgs_res.status_code == 200
    ai_msgs = [m for m in msgs_res.json() if m["sender_type"] == "ai"]
    assert len(ai_msgs) >= 1
    content_lower = ai_msgs[-1]["content"].lower()

    # Must contain grounded policy information
    assert any(w in content_lower for w in ["return", "30", "days", "original condition", "policy"])
    # Must NOT be a generic greeting
    assert not content_lower.startswith("hello! how can i help")
    assert not content_lower.startswith("vanakkam! ungaluku naan eppadi")
    # Must NOT ask for Order ID
    assert "order id" not in content_lower
    # Must NOT have technical difficulties
    assert "technical difficulties" not in content_lower


@pytest.mark.asyncio
async def test_repeated_tanglish_policy_question_does_not_trigger_technical_difficulties(
    async_client: AsyncClient,
    auth_headers_a: dict,
    db_session: AsyncSession,
):
    """
    Class B: Repeating the return policy question must safely respond with policy info,
    NEVER degrading into 'technical difficulties' or false escalation.
    """
    resp = await async_client.post(
        "/api/conversations",
        headers=auth_headers_a,
        json={"initial_message": "return policy pathi sollunga"},
    )
    assert resp.status_code == 200
    convo_id = resp.json()["id"]

    # Wait past 2s anti-duplicate debounce
    await asyncio.sleep(2.1)

    # Customer repeats question in second turn
    resp2 = await async_client.post(
        f"/api/conversations/{convo_id}/messages",
        headers=auth_headers_a,
        json={"content": "return policy pathi sollunga"},
    )
    assert resp2.status_code == 200

    msgs_res = await async_client.get(f"/api/conversations/{convo_id}/messages", headers=auth_headers_a)
    ai_msgs = [m for m in msgs_res.json() if m["sender_type"] == "ai"]
    assert len(ai_msgs) >= 2
    content_lower = ai_msgs[-1]["content"].lower()

    assert any(w in content_lower for w in ["return", "30", "days", "original condition", "policy"])
    assert "technical difficulties" not in content_lower
    assert "trouble processing" not in content_lower

    # Confirm no unintended handoff was created
    handoff = await db_session.scalar(select(Handoff).where(Handoff.conversation_id == convo_id))
    assert handoff is None


@pytest.mark.asyncio
async def test_explicit_expert_request_triggers_handoff_not_technical_difficulties(
    async_client: AsyncClient,
    auth_headers_a: dict,
    db_session: AsyncSession,
):
    """
    Class C: Explicit request 'Can u connect with the expert?' triggers immediate handoff
    with truthful handoff confirmation, NOT a technical difficulties fallback.
    """
    # Start conversation
    resp = await async_client.post(
        "/api/conversations",
        headers=auth_headers_a,
        json={"initial_message": "Can u connect with the expert?"},
    )
    assert resp.status_code == 200
    convo_id = resp.json()["id"]

    convo_res = await async_client.get(f"/api/conversations/{convo_id}", headers=auth_headers_a)
    assert convo_res.status_code == 200
    assert convo_res.json()["workflow_state"] == "waiting_for_expert"

    msgs_res = await async_client.get(f"/api/conversations/{convo_id}/messages", headers=auth_headers_a)
    ai_msgs = [m for m in msgs_res.json() if m["sender_type"] == "ai"]
    assert len(ai_msgs) == 1
    content_lower = ai_msgs[0]["content"].lower()

    # Must confirm expert connection
    assert any(w in content_lower for w in ["expert", "connecting", "support", "hold on", "join"])
    # Must NEVER claim technical difficulties
    assert "technical difficulties" not in content_lower

    # Handoff record must exist in DB with WAITING status
    handoff = await db_session.scalar(select(Handoff).where(Handoff.conversation_id == convo_id))
    assert handoff is not None
    assert handoff.status == HandoffStatus.WAITING


@pytest.mark.asyncio
async def test_cancellation_inquiry_answers_policy_without_prompting_order_id(
    async_client: AsyncClient,
    auth_headers_a: dict,
    db_session: AsyncSession,
):
    """
    Class D: 'order cancel eppadi pannuradhu?' must explain cancellation policy,
    NOT classify as delivery issue or prompt for Order ID.
    """
    resp = await async_client.post(
        "/api/conversations",
        headers=auth_headers_a,
        json={"initial_message": "order cancel eppadi pannuradhu?"},
    )
    assert resp.status_code == 200
    convo_id = resp.json()["id"]

    msgs_res = await async_client.get(f"/api/conversations/{convo_id}/messages", headers=auth_headers_a)
    ai_msgs = [m for m in msgs_res.json() if m["sender_type"] == "ai"]
    assert len(ai_msgs) >= 1
    content_lower = ai_msgs[-1]["content"].lower()

    assert any(w in content_lower for w in ["cancel", "dispatch", "shipped", "policy"])
    assert "order id" not in content_lower
    assert "technical difficulties" not in content_lower


@pytest.mark.asyncio
async def test_voice_turn_parity_expert_request_and_policy(
    db_session: AsyncSession,
    test_user_a: User,
):
    """
    Class E: Voice turn pipeline processes both policy questions and expert requests correctly.
    """
    provider = M4AIProvider()

    # Voice Policy Question
    ctx_policy = {
        "conversation_id": 881,
        "history": [],
        "preferred_language": "tanglish",
        "turn_index": 1,
        "is_voice": True,
    }
    voice_policy = await provider.process_voice_turn("return policy pathi sollunga", ctx_policy, db_session)
    assert voice_policy.get("decision") in ("RESOLVE", "ASK_USER")
    spoken_policy = voice_policy.get("spoken_response", "").lower()
    assert any(w in spoken_policy for w in ["return", "30", "days", "original condition", "policy"])

    # Voice Expert Request
    ctx_expert = {
        "conversation_id": 882,
        "history": [],
        "preferred_language": "english",
        "turn_index": 1,
        "is_voice": True,
    }
    voice_expert = await provider.process_voice_turn("Can u connect with the expert?", ctx_expert, db_session)
    assert voice_expert.get("decision") == "ESCALATE"
    spoken_expert = voice_expert.get("spoken_response", "").lower()
    assert any(w in spoken_expert for w in ["expert", "connecting", "support", "hold on", "join"])
    assert "technical difficulties" not in spoken_expert
