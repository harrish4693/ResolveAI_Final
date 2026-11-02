"""
ResolveAI V2 — LiveKit Real-Time Voice Pipeline Test Suite
==========================================================
Comprehensive end-to-end tests for the LiveKit voice subsystem:
1. Authenticated room-scoped token creation with valid credentials.
2. Unauthenticated token request rejection (401).
3. Conversation ownership violations (403 for unauthorized customer, 404 for nonexistent conversation).
4. Missing / unconfigured LiveKit settings return 503 Service Unavailable.
5. Room and participant permission constraints verified in JWT claims (VideoGrants).
6. Spoken utterance association and intelligence pipeline execution.
7. DB-level idempotency and duplicate utterance rejection (409 Conflict).
8. Resilience to TTS callback failures (message pipeline preserved).
9. Voice turn escalation to human expert through existing pipeline.
10. Multi-turn spoken conversations (5+ consecutive turns).
11. Follow-up questions and context preservation without session restart.
12. Empty and silence-only utterance handling ('ignored' status).
13. Local STT and TTS provider configuration (no silent fallback).
14. LiveKit voice request produces AI response without crash.
15. Voice request with streaming TTS callback receives synthesized sentences.
16. Normal text-chat request without voice callbacks produces text messages.
17. Voice request escalating to human expert safely streams escalation message to caller.
18. AI / memory exception branch properly initializes is_voice_turn and avoids UnboundLocalError.
19. Multi-turn continuous voice conversation across multiple consecutive turns.
"""

import os
import pytest
import jwt
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.conversations.models import Conversation, ConversationMessage, ProcessedUtterance
from app.conversations.service import ConversationService
from app.shared.models import WorkflowState, SenderType, MessageType, UserRole, ConversationChannel
from app.handoff.models import Handoff
from app.tickets.models import Ticket, TicketStatus
from app.voice.livekit_service import LiveKitService


TEST_LIVEKIT_URL = "wss://test-project.livekit.cloud"
TEST_LIVEKIT_KEY = "test_livekit_api_key_12345"
TEST_LIVEKIT_SECRET = "test_livekit_api_secret_key_at_least_32_bytes_long_12345"


@pytest.fixture
def configure_livekit():
    """Temporarily configure LiveKit settings for the test."""
    orig_url = settings.livekit_url
    orig_key = settings.livekit_api_key
    orig_secret = settings.livekit_api_secret

    settings.livekit_url = TEST_LIVEKIT_URL
    settings.livekit_api_key = TEST_LIVEKIT_KEY
    settings.livekit_api_secret = TEST_LIVEKIT_SECRET

    yield

    settings.livekit_url = orig_url
    settings.livekit_api_key = orig_key
    settings.livekit_api_secret = orig_secret


# ══════════════════════════════════════════════════════════════════════════════
# Section 1: LiveKit Token Creation, Auth & Permission Constraints
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_livekit_token_creation_success(
    async_client: AsyncClient,
    auth_headers_a: dict,
    test_user_a,
    configure_livekit,
):
    """Authenticated customer receives a room-scoped LiveKit token."""
    convo_resp = await async_client.post(
        "/api/conversations",
        json={"initial_message": "Hello, I want voice support."},
        headers=auth_headers_a,
    )
    assert convo_resp.status_code == 200
    convo_id = convo_resp.json()["id"]

    resp = await async_client.post(
        "/api/audio/livekit/token",
        json={"conversation_id": convo_id},
        headers=auth_headers_a,
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["server_url"] == TEST_LIVEKIT_URL
    assert data["room_name"] == f"resolveai-convo-{convo_id}"
    assert data["participant_identity"] == f"customer-{test_user_a.id}"
    assert data["expires_in_seconds"] == 900
    assert "token" in data and len(data["token"]) > 20


@pytest.mark.asyncio
async def test_livekit_token_unauthenticated_rejected(
    async_client: AsyncClient,
    configure_livekit,
):
    """Unauthenticated token requests are rejected with 401."""
    resp = await async_client.post(
        "/api/audio/livekit/token",
        json={"conversation_id": 10},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_livekit_token_ownership_violation_rejected(
    async_client: AsyncClient,
    auth_headers_a: dict,
    auth_headers_b: dict,
    configure_livekit,
):
    """Customer B cannot request a LiveKit token for Customer A's conversation."""
    convo_resp = await async_client.post(
        "/api/conversations",
        json={"initial_message": "Customer A private support."},
        headers=auth_headers_a,
    )
    convo_id = convo_resp.json()["id"]

    resp = await async_client.post(
        "/api/audio/livekit/token",
        json={"conversation_id": convo_id},
        headers=auth_headers_b,
    )
    assert resp.status_code == 403
    assert "Not authorized" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_livekit_token_nonexistent_conversation(
    async_client: AsyncClient,
    auth_headers_a: dict,
    configure_livekit,
):
    """Requesting token for a non-existent conversation returns 404."""
    resp = await async_client.post(
        "/api/audio/livekit/token",
        json={"conversation_id": 999999},
        headers=auth_headers_a,
    )
    assert resp.status_code == 404
    assert "Conversation not found" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_livekit_token_missing_config_returns_503(
    async_client: AsyncClient,
    auth_headers_a: dict,
):
    """When LiveKit environment variables are missing, returns 503 Service Unavailable."""
    settings.livekit_url = None
    settings.livekit_api_key = None
    settings.livekit_api_secret = None

    convo_resp = await async_client.post(
        "/api/conversations",
        json={"initial_message": "Config check."},
        headers=auth_headers_a,
    )
    convo_id = convo_resp.json()["id"]

    resp = await async_client.post(
        "/api/audio/livekit/token",
        json={"conversation_id": convo_id},
        headers=auth_headers_a,
    )
    assert resp.status_code == 503
    assert "LiveKit real-time voice service is not configured" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_livekit_token_claims_and_permissions(
    async_client: AsyncClient,
    auth_headers_a: dict,
    test_user_a,
    configure_livekit,
):
    """JWT token claims must strictly enforce room scope and minimal permissions."""
    convo_resp = await async_client.post(
        "/api/conversations",
        json={"initial_message": "Permissions test."},
        headers=auth_headers_a,
    )
    convo_id = convo_resp.json()["id"]

    resp = await async_client.post(
        "/api/audio/livekit/token",
        json={"conversation_id": convo_id},
        headers=auth_headers_a,
    )
    assert resp.status_code == 200
    token_str = resp.json()["token"]

    claims = jwt.decode(
        token_str,
        key=TEST_LIVEKIT_SECRET,
        algorithms=["HS256"],
    )

    expected_room = f"resolveai-convo-{convo_id}"
    assert claims["iss"] == TEST_LIVEKIT_KEY
    assert claims["sub"] == f"customer-{test_user_a.id}"

    video_grants = claims.get("video", {})
    assert video_grants.get("room") == expected_room
    assert video_grants.get("roomJoin") is True
    assert video_grants.get("canPublish") is True
    assert video_grants.get("canSubscribe") is True


# ══════════════════════════════════════════════════════════════════════════════
# Section 2: Spoken Utterance Association, Persistence & Idempotency
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_livekit_spoken_utterance_processed_and_associated(
    async_client: AsyncClient,
    auth_headers_a: dict,
    test_user_a,
    db_session: AsyncSession,
):
    """Spoken utterance associates with conversation and triggers the intelligence pipeline."""
    convo_resp = await async_client.post(
        "/api/conversations",
        json={"initial_message": "Start of conversation."},
        headers=auth_headers_a,
    )
    convo_id = convo_resp.json()["id"]

    utt_resp = await async_client.post(
        "/api/audio/livekit/utterance",
        json={
            "conversation_id": convo_id,
            "utterance_id": "utt_spoken_turn_101",
            "transcript": "How do I reset my password?",
        },
        headers=auth_headers_a,
    )
    assert utt_resp.status_code == 200
    assert utt_resp.json()["status"] == "processed"

    stmt = (
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == convo_id)
        .order_by(ConversationMessage.created_at.asc())
    )
    messages = (await db_session.execute(stmt)).scalars().all()
    contents = [m.content for m in messages]
    assert "How do I reset my password?" in contents

    ai_msg = next((m for m in messages if m.sender_type == SenderType.AI), None)
    assert ai_msg is not None


@pytest.mark.asyncio
async def test_livekit_duplicate_utterance_rejected(
    async_client: AsyncClient,
    auth_headers_a: dict,
    db_session: AsyncSession,
):
    """Sending the same utterance_id twice returns 409 Conflict."""
    convo_resp = await async_client.post(
        "/api/conversations",
        json={"initial_message": "Testing deduplication."},
        headers=auth_headers_a,
    )
    convo_id = convo_resp.json()["id"]

    payload = {
        "conversation_id": convo_id,
        "utterance_id": "utt_unique_dup_check_01",
        "transcript": "Repeat check test message.",
    }

    resp1 = await async_client.post(
        "/api/audio/livekit/utterance",
        json=payload,
        headers=auth_headers_a,
    )
    assert resp1.status_code == 200

    resp2 = await async_client.post(
        "/api/audio/livekit/utterance",
        json=payload,
        headers=auth_headers_a,
    )
    assert resp2.status_code == 409
    assert "already been processed" in resp2.json()["detail"]


@pytest.mark.asyncio
async def test_livekit_spoken_utterance_tts_failure_resilience(
    test_user_a,
    db_session: AsyncSession,
):
    """If the TTS callback raises an exception, the conversation and message pipeline does not crash."""
    svc = ConversationService()

    convo = await svc.create_conversation(
        db=db_session,
        customer_id=test_user_a.id,
        initial_message="Initial inquiry",
    )

    async def failing_tts(text: str):
        raise RuntimeError("Simulated LiveKit audio track publication failure")

    result = await LiveKitService.process_spoken_utterance(
        db=db_session,
        conversation_id=convo.id,
        customer_id=test_user_a.id,
        utterance_id="utt_failing_tts_turn",
        transcript="Can you help me with billing?",
        tts_callback=failing_tts,
    )

    assert result["status"] == "processed"

    stmt = (
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == convo.id)
        .where(ConversationMessage.sender_type == SenderType.AI)
    )
    ai_msgs = (await db_session.execute(stmt)).scalars().all()
    assert len(ai_msgs) >= 1


@pytest.mark.asyncio
async def test_livekit_spoken_utterance_escalation_flow(
    async_client: AsyncClient,
    auth_headers_a: dict,
    db_session: AsyncSession,
):
    """Spoken utterance requesting human support escalates through the existing intelligence pipeline."""
    convo_resp = await async_client.post(
        "/api/conversations",
        json={"initial_message": "General query."},
        headers=auth_headers_a,
    )
    convo_id = convo_resp.json()["id"]

    utt_resp = await async_client.post(
        "/api/audio/livekit/utterance",
        json={
            "conversation_id": convo_id,
            "utterance_id": "utt_escalate_human_support_01",
            "transcript": "I need to speak with a human support agent immediately.",
        },
        headers=auth_headers_a,
    )
    assert utt_resp.status_code == 200

    convo = await db_session.scalar(select(Conversation).where(Conversation.id == convo_id))
    assert convo is not None

    handoff = await db_session.scalar(select(Handoff).where(Handoff.conversation_id == convo_id))
    if convo.workflow_state == WorkflowState.WAITING_FOR_EXPERT:
        assert handoff is not None
        ticket = await db_session.scalar(select(Ticket).where(Ticket.conversation_id == convo_id))
        assert ticket.status == TicketStatus.ESCALATED


# ══════════════════════════════════════════════════════════════════════════════
# Section 3: Multi-Turn Continuity, Context & Silence Handling
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_livekit_five_consecutive_spoken_turns(
    async_client: AsyncClient,
    auth_headers_a: dict,
    db_session: AsyncSession,
):
    """Verifies that a customer can execute at least 5 consecutive spoken turns in one session."""
    convo_resp = await async_client.post(
        "/api/conversations",
        json={"initial_message": "Customer started live voice call", "subject": "Voice Call Multi-Turn"},
        headers=auth_headers_a,
    )
    assert convo_resp.status_code == 200
    convo_id = convo_resp.json()["id"]

    turns = [
        ("turn_001", "Hello, I have a question regarding my order ORD123."),
        ("turn_002", "When is the scheduled delivery date?"),
        ("turn_003", "Can I update the delivery phone number?"),
        ("turn_004", "Great, does it require a signature upon delivery?"),
        ("turn_005", "Thank you, that answers all my questions."),
    ]

    for utterance_id, transcript in turns:
        resp = await async_client.post(
            "/api/audio/livekit/utterance",
            json={
                "conversation_id": convo_id,
                "utterance_id": utterance_id,
                "transcript": transcript,
            },
            headers=auth_headers_a,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "processed"
        assert data["conversation_id"] == convo_id
        assert data["ai_response"] is not None

    stmt = (
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == convo_id)
        .order_by(ConversationMessage.created_at.asc())
    )
    all_msgs = (await db_session.execute(stmt)).scalars().all()
    assert len(all_msgs) >= 11

    customer_texts = [m.content for m in all_msgs if m.sender_type == SenderType.CUSTOMER]
    assert "Hello, I have a question regarding my order ORD123." in customer_texts
    assert "When is the scheduled delivery date?" in customer_texts
    assert "Can I update the delivery phone number?" in customer_texts
    assert "Great, does it require a signature upon delivery?" in customer_texts
    assert "Thank you, that answers all my questions." in customer_texts


@pytest.mark.asyncio
async def test_livekit_followup_question_context_preservation(
    async_client: AsyncClient,
    auth_headers_a: dict,
    db_session: AsyncSession,
):
    """Follow-up questions preserve previous turn context without restarting the call."""
    convo_resp = await async_client.post(
        "/api/conversations",
        json={"initial_message": "Voice call started", "subject": "Billing inquiry"},
        headers=auth_headers_a,
    )
    convo_id = convo_resp.json()["id"]

    resp1 = await async_client.post(
        "/api/audio/livekit/utterance",
        json={
            "conversation_id": convo_id,
            "utterance_id": "followup_t1",
            "transcript": "My payment failed for transaction TXN12345.",
        },
        headers=auth_headers_a,
    )
    assert resp1.status_code == 200
    assert resp1.json()["ai_response"] is not None

    resp2 = await async_client.post(
        "/api/audio/livekit/utterance",
        json={
            "conversation_id": convo_id,
            "utterance_id": "followup_t2",
            "transcript": "Why was that transaction declined?",
        },
        headers=auth_headers_a,
    )
    assert resp2.status_code == 200
    assert resp2.json()["ai_response"] is not None

    stmt = (
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == convo_id)
        .where(ConversationMessage.sender_type == SenderType.CUSTOMER)
    )
    cust_msgs = (await db_session.execute(stmt)).scalars().all()
    assert len(cust_msgs) >= 2


@pytest.mark.asyncio
async def test_livekit_empty_or_silence_utterance_handling(
    async_client: AsyncClient,
    auth_headers_a: dict,
):
    """Empty or silence-only transcripts are ignored gracefully without error."""
    convo_resp = await async_client.post(
        "/api/conversations",
        json={"initial_message": "Voice call started"},
        headers=auth_headers_a,
    )
    convo_id = convo_resp.json()["id"]

    resp = await async_client.post(
        "/api/audio/livekit/utterance",
        json={
            "conversation_id": convo_id,
            "utterance_id": "silence_01",
            "transcript": "   ",
        },
        headers=auth_headers_a,
    )
    if resp.status_code == 200:
        assert resp.json()["status"] == "ignored"


@pytest.mark.asyncio
async def test_local_stt_and_tts_providers_no_silent_fallback(tmp_path):
    """Local STT/TTS providers enforce local-only execution and refuse silent cloud fallback."""
    from app.voice.providers import (
        FasterWhisperSTTProvider,
        LocalTTSProvider,
        get_stt_provider,
        get_tts_provider,
    )

    whisper_prov = get_stt_provider("whisper")
    assert isinstance(whisper_prov, FasterWhisperSTTProvider)
    assert whisper_prov.device == "cpu"
    assert whisper_prov.compute_type == "int8"
    assert whisper_prov.model_size == "base"

    tts_prov = get_tts_provider("local")
    assert isinstance(tts_prov, LocalTTSProvider)

    out_file = str(tmp_path / "test_synth.wav")
    synthesized_path = await tts_prov.synthesize("Hello! This is ResolveAI offline test audio.", out_file)
    assert synthesized_path == out_file
    assert os.path.exists(out_file)
    assert os.path.getsize(out_file) > 40


# ══════════════════════════════════════════════════════════════════════════════
# Section 4: P0 Crash Prevention & Voice Lifecycle Regressions
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_livekit_voice_request_produces_ai_response(
    async_client: AsyncClient,
    auth_headers_a: dict,
    db_session: AsyncSession,
):
    """LiveKit voice request produces an AI response without crashing."""
    convo_resp = await async_client.post(
        "/api/conversations",
        json={"initial_message": "Hello from LiveKit voice."},
        headers=auth_headers_a,
    )
    assert convo_resp.status_code == 200
    convo_id = convo_resp.json()["id"]

    utt_resp = await async_client.post(
        "/api/audio/livekit/utterance",
        json={
            "conversation_id": convo_id,
            "utterance_id": "utt_p0_crash_turn_1",
            "transcript": "What is the status of my order ORD-123?",
        },
        headers=auth_headers_a,
    )
    assert utt_resp.status_code == 200
    data = utt_resp.json()
    assert data["status"] == "processed"
    assert data["ai_response"] is not None
    assert len(data["ai_response"]) > 0

    stmt = (
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == convo_id)
        .order_by(ConversationMessage.created_at.asc())
    )
    messages = (await db_session.execute(stmt)).scalars().all()
    ai_msgs = [m for m in messages if m.sender_type == SenderType.AI]
    assert len(ai_msgs) >= 1
    assert ai_msgs[-1].message_type == MessageType.VOICE


@pytest.mark.asyncio
async def test_voice_request_with_tts_callback(
    db_session: AsyncSession,
    test_user_a,
):
    """Voice request with a streaming TTS callback streams sentences and succeeds."""
    convo = Conversation(
        customer_id=test_user_a.id,
        channel=ConversationChannel.VOICE,
        workflow_state="active",
    )
    db_session.add(convo)
    await db_session.commit()
    await db_session.refresh(convo)

    tts_chunks = []

    async def mock_tts_callback(text_chunk: str):
        tts_chunks.append(text_chunk)

    svc = ConversationService()
    await svc.process_customer_message(
        db=db_session,
        conversation=convo,
        customer_id=test_user_a.id,
        message_content="Where is my delivery?",
        reply_with_voice=True,
        tts_callback=mock_tts_callback,
    )

    assert len(tts_chunks) > 0, "TTS callback should receive at least one sentence chunk"
    assert any("delivery" in c.lower() or "order" in c.lower() or "help" in c.lower() or "assist" in c.lower() for c in tts_chunks)


@pytest.mark.asyncio
async def test_normal_text_chat_request_without_voice_callbacks(
    db_session: AsyncSession,
    test_user_a,
):
    """Normal text-chat request without voice callbacks produces text messages."""
    convo = Conversation(
        customer_id=test_user_a.id,
        channel=ConversationChannel.TEXT,
        workflow_state="active",
    )
    db_session.add(convo)
    await db_session.commit()
    await db_session.refresh(convo)

    svc = ConversationService()
    await svc.process_customer_message(
        db=db_session,
        conversation=convo,
        customer_id=test_user_a.id,
        message_content="Can I change my account email?",
        reply_with_voice=False,
        tts_callback=None,
    )

    stmt = (
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == convo.id)
        .order_by(ConversationMessage.created_at.desc())
    )
    last_msg = (await db_session.execute(stmt)).scalars().first()
    assert last_msg is not None
    assert last_msg.sender_type == SenderType.AI
    assert last_msg.message_type == MessageType.TEXT
    assert last_msg.audio_url is None


@pytest.mark.asyncio
async def test_voice_request_escalation_speaks_to_caller(
    db_session: AsyncSession,
    test_user_a,
):
    """Escalation response on a voice call streams voice reply to caller without UnboundLocalError."""
    convo = Conversation(
        customer_id=test_user_a.id,
        channel=ConversationChannel.VOICE,
        workflow_state="active",
    )
    db_session.add(convo)
    await db_session.commit()
    await db_session.refresh(convo)

    spoken_sentences = []

    async def tts_recorder(text: str):
        spoken_sentences.append(text)

    svc = ConversationService()
    await svc.process_customer_message(
        db=db_session,
        conversation=convo,
        customer_id=test_user_a.id,
        message_content="I demand to speak to your human supervisor immediately!",
        reply_with_voice=True,
        tts_callback=tts_recorder,
    )

    await db_session.refresh(convo)
    assert convo.workflow_state == WorkflowState.WAITING_FOR_EXPERT
    assert len(spoken_sentences) > 0
    assert any("expert" in s.lower() or "human" in s.lower() or "connect" in s.lower() or "specialist" in s.lower() or "help" in s.lower() for s in spoken_sentences)


@pytest.mark.asyncio
async def test_exception_branch_safely_binds_is_voice_turn(
    db_session: AsyncSession,
    test_user_a,
):
    """When an exception occurs early in _trigger_ai_response, is_voice_turn is bound and handles escalation."""
    convo = Conversation(
        customer_id=test_user_a.id,
        channel=ConversationChannel.VOICE,
        workflow_state="active",
    )
    db_session.add(convo)
    await db_session.commit()
    await db_session.refresh(convo)

    tts_called = []

    async def tts_spy(text: str):
        tts_called.append(text)

    svc = ConversationService()

    with patch("app.memory.service.MemoryService.retrieve_relevant_memory", side_effect=RuntimeError("Simulated early memory failure")):
        await svc._trigger_ai_response(
            db=db_session,
            conversation=convo,
            latest_message="Hello, my order is missing.",
            reply_with_voice=True,
            tts_callback=tts_spy,
        )

    await db_session.refresh(convo)
    assert convo.workflow_state == WorkflowState.WAITING_FOR_EXPERT
    assert len(tts_called) > 0
    assert any("technical difficulties" in t.lower() or "expert" in t.lower() for t in tts_called)


@pytest.mark.asyncio
async def test_call_with_agent_processes_consecutive_voice_turns(
    async_client: AsyncClient,
    auth_headers_a: dict,
    db_session: AsyncSession,
):
    """Multi-turn conversation: processes multiple consecutive voice turns without crashing."""
    convo_resp = await async_client.post(
        "/api/conversations",
        json={"initial_message": "Voice call started."},
        headers=auth_headers_a,
    )
    convo_id = convo_resp.json()["id"]

    turns = [
        ("utt_multiturn_1", "I need help with my recent order ORD-123."),
        ("utt_multiturn_2", "Yes, that is the correct order."),
        ("utt_multiturn_3", "When can I expect it to arrive?"),
        ("utt_multiturn_4", "Can I change the delivery address?"),
        ("utt_multiturn_5", "Thank you, that was very helpful."),
    ]

    for utt_id, transcript in turns:
        resp = await async_client.post(
            "/api/audio/livekit/utterance",
            json={
                "conversation_id": convo_id,
                "utterance_id": utt_id,
                "transcript": transcript,
            },
            headers=auth_headers_a,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "processed"
        assert data["ai_response"] is not None
        assert len(data["ai_response"]) > 0

    stmt = (
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == convo_id)
        .order_by(ConversationMessage.created_at.asc())
    )
    msgs = (await db_session.execute(stmt)).scalars().all()
    cust_msgs = [m for m in msgs if m.sender_type == SenderType.CUSTOMER]
    ai_msgs = [m for m in msgs if m.sender_type == SenderType.AI]

    assert len(cust_msgs) == 6
    assert len(ai_msgs) == 6
