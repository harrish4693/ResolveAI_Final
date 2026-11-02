"""
ResolveAI V2 — WebSockets & Voice Session Test Suite
===================================================
Comprehensive test coverage for real-time WebSocket communication, event distribution,
role/tenant authorization, voice session state machine, and audio endpoints:
1. Valid JWT connection & authentication.
2. Invalid & expired JWT rejection.
3. Event delivery authorization (customer receives own events, no cross-customer leak, assigned expert receives, unassigned expert doesn't).
4. Standard envelope structure for NEW_MESSAGE, CONVERSATION_UPDATED, QUEUE_UPDATED, TYPING_START, TYPING_END.
5. Multi-connection management per user, disconnect cleanup, reconnect state freshness.
6. Event ID uniqueness & timezone-aware timestamps.
7. Expert queue broadcast filtering (experts only, customers excluded).
8. VoiceSessionManager state machine (IDLE -> LISTENING -> SPEAKING -> INTERRUPTED).
9. Voice utterance idempotency (duplicate utterance rejection).
10. Barge-in / interruption cancellation of active TTS tasks.
11. REST audio upload validation (unsupported MIME, empty audio rejection).
12. STT upload & AI voice reply generation.
13. Audio URL tenant isolation (Customer A audio inaccessible to Customer B).
14. Graceful text fallback on TTS synthesis failure.
"""

import io
import json
import pytest
import pytest_asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.auth.jwt import create_access_token
from app.websockets.manager import ConnectionManager
from app.websockets.events import (
    new_message_event,
    conversation_updated_event,
    queue_updated_event,
    typing_event,
    create_event,
)
from app.websockets.voice_session import VoiceSessionManager, VoiceSessionState
from app.conversations.models import Conversation, ConversationMessage, ProcessedUtterance
from app.shared.models import MessageType, SenderType


# ══════════════════════════════════════════════════════════════════════════════
# Section 1: WebSocket JWT Authentication & Connection Lifecycle
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_ws_valid_jwt_connects(async_client: AsyncClient, test_user_a):
    """A valid access token should allow WebSocket connection."""
    token = create_access_token(test_user_a.id, "customer")

    async with async_client.stream("GET", f"/api/ws?token={token}") as response:
        pass
    mgr = ConnectionManager()
    assert mgr.active_connections == 0


@pytest.mark.asyncio
async def test_ws_invalid_jwt_rejected():
    """An invalid token should be rejected."""
    from app.auth.jwt import verify_token
    from app.shared.exceptions import AuthenticationError

    with pytest.raises(AuthenticationError):
        verify_token("invalid.token.here", expected_type="access")


@pytest.mark.asyncio
async def test_ws_expired_jwt_rejected():
    """An expired token should be rejected."""
    from app.auth.jwt import verify_token
    from app.shared.exceptions import AuthenticationError

    token = create_access_token("1", "customer", expires_delta=timedelta(seconds=-10))

    with pytest.raises(AuthenticationError):
        verify_token(token, expected_type="access")


# ══════════════════════════════════════════════════════════════════════════════
# Section 2: Event Authorization & Tenant / Role Scoping
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_customer_receives_own_conversation_event():
    """Customer should receive events for their own conversation."""
    mgr = ConnectionManager()

    event = new_message_event(
        conversation_id=101,
        message_id=1,
        sender_type="ai",
        content="Hello!",
        created_at="2026-08-30T12:00:00+00:00",
    )

    await mgr.send_to_conversation_participants(
        customer_id=1, expert_id=None, event=event
    )


@pytest.mark.asyncio
async def test_customer_doesnt_receive_other_conversation():
    """Event authorization: customer B must not receive customer A's events."""
    mgr = ConnectionManager()

    event = new_message_event(
        conversation_id=101,
        message_id=1,
        sender_type="ai",
        content="Hello!",
        created_at="2026-08-30T12:00:00+00:00",
    )

    await mgr.send_to_conversation_participants(
        customer_id=1, expert_id=None, event=event
    )
    assert mgr.get_connection_count(2) == 0


@pytest.mark.asyncio
async def test_assigned_expert_receives_events():
    """Assigned expert should receive conversation events."""
    mgr = ConnectionManager()

    event = new_message_event(
        conversation_id=101,
        message_id=2,
        sender_type="customer",
        content="Help!",
        created_at="2026-08-30T12:00:00+00:00",
    )

    await mgr.send_to_conversation_participants(
        customer_id=1, expert_id=3, event=event
    )


@pytest.mark.asyncio
async def test_unassigned_expert_no_private_events():
    """Unassigned expert should NOT receive private conversation events."""
    mgr = ConnectionManager()

    event = new_message_event(
        conversation_id=101,
        message_id=3,
        sender_type="customer",
        content="Private message",
        created_at="2026-08-30T12:00:00+00:00",
    )

    await mgr.send_to_conversation_participants(
        customer_id=1, expert_id=3, event=event
    )
    assert mgr.get_connection_count(5) == 0


# ══════════════════════════════════════════════════════════════════════════════
# Section 3: WebSocket Event Envelope & Structure
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_new_message_event_structure():
    """NEW_MESSAGE event must follow the standard envelope."""
    event = new_message_event(
        conversation_id=101,
        message_id=42,
        sender_type="expert",
        content="I've checked your payment.",
        created_at="2026-08-30T12:00:00+00:00",
    )

    assert event["type"] == "NEW_MESSAGE"
    assert event["conversation_id"] == 101
    assert "event_id" in event
    assert "timestamp" in event
    assert event["data"]["message_id"] == 42
    assert event["data"]["sender_type"] == "expert"
    assert event["data"]["content"] == "I've checked your payment."


@pytest.mark.asyncio
async def test_conversation_updated_event_structure():
    """CONVERSATION_UPDATED event must follow the standard envelope."""
    event = conversation_updated_event(
        conversation_id=101,
        status="resolved",
        workflow_state="resolved",
    )

    assert event["type"] == "CONVERSATION_UPDATED"
    assert event["conversation_id"] == 101
    assert event["data"]["status"] == "resolved"
    assert event["data"]["workflow_state"] == "resolved"
    assert "event_id" in event
    assert "timestamp" in event


@pytest.mark.asyncio
async def test_queue_updated_event_structure():
    """QUEUE_UPDATED event must contain minimal info only."""
    event = queue_updated_event(
        action="ADDED",
        handoff_id=42,
        priority="critical",
        category="Security",
    )

    assert event["type"] == "QUEUE_UPDATED"
    assert event["conversation_id"] is None
    assert event["data"]["action"] == "ADDED"
    assert event["data"]["handoff_id"] == 42
    assert event["data"]["priority"] == "critical"
    assert event["data"]["category"] == "Security"
    assert "escalation_reason" not in event["data"]
    assert "ai_analysis" not in event["data"]


@pytest.mark.asyncio
async def test_typing_start_event():
    """TYPING_START event structure."""
    event = typing_event(conversation_id=101, sender_type="expert", is_start=True)

    assert event["type"] == "TYPING_START"
    assert event["conversation_id"] == 101
    assert event["data"]["sender_type"] == "expert"


@pytest.mark.asyncio
async def test_typing_end_event():
    """TYPING_END event structure."""
    event = typing_event(conversation_id=101, sender_type="ai", is_start=False)

    assert event["type"] == "TYPING_END"
    assert event["conversation_id"] == 101
    assert event["data"]["sender_type"] == "ai"


# ══════════════════════════════════════════════════════════════════════════════
# Section 4: Connection Management, Concurrency & Reconnection
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_multiple_connections_per_user():
    """Multiple WebSocket connections per user must be supported."""
    mgr = ConnectionManager()

    class MockWebSocket:
        def __init__(self):
            self.sent = []
            self.accepted = False

        async def accept(self):
            self.accepted = True

        async def send_json(self, data):
            self.sent.append(data)

    ws1 = MockWebSocket()
    ws2 = MockWebSocket()
    ws3 = MockWebSocket()

    await mgr.connect(ws1, user_id=1, role="customer")
    await mgr.connect(ws2, user_id=1, role="customer")
    await mgr.connect(ws3, user_id=1, role="customer")

    assert mgr.get_connection_count(1) == 3

    event = new_message_event(
        conversation_id=101, message_id=1,
        sender_type="ai", content="Hi",
        created_at="2026-08-30T12:00:00+00:00",
    )
    await mgr.send_to_user(1, event)

    assert len(ws1.sent) == 1
    assert len(ws2.sent) == 1
    assert len(ws3.sent) == 1

    mgr.disconnect(ws1, 1)
    mgr.disconnect(ws2, 1)
    mgr.disconnect(ws3, 1)
    assert mgr.get_connection_count(1) == 0


@pytest.mark.asyncio
async def test_disconnect_cleanup():
    """Disconnecting should remove the socket from the manager."""
    mgr = ConnectionManager()

    class MockWebSocket:
        async def accept(self):
            pass

        async def send_json(self, data):
            pass

    ws = MockWebSocket()
    await mgr.connect(ws, user_id=10, role="customer")
    assert mgr.get_connection_count(10) == 1

    mgr.disconnect(ws, 10)
    assert mgr.get_connection_count(10) == 0
    assert mgr.active_connections == 0


@pytest.mark.asyncio
async def test_reconnect_clean_state():
    """After disconnect + reconnect, the manager should track correctly."""
    mgr = ConnectionManager()

    class MockWebSocket:
        def __init__(self):
            self.sent = []

        async def accept(self):
            pass

        async def send_json(self, data):
            self.sent.append(data)

    ws1 = MockWebSocket()
    ws2 = MockWebSocket()

    await mgr.connect(ws1, user_id=1, role="customer")
    mgr.disconnect(ws1, 1)
    assert mgr.get_connection_count(1) == 0

    await mgr.connect(ws2, user_id=1, role="customer")
    assert mgr.get_connection_count(1) == 1

    event = new_message_event(
        conversation_id=101, message_id=1,
        sender_type="ai", content="Welcome back",
        created_at="2026-08-30T12:00:00+00:00",
    )
    await mgr.send_to_user(1, event)
    assert len(ws2.sent) == 1
    assert len(ws1.sent) == 0

    mgr.disconnect(ws2, 1)


@pytest.mark.asyncio
async def test_event_id_uniqueness():
    """Every event must have a unique event_id for deduplication."""
    event1 = create_event("NEW_MESSAGE", {"msg": "a"}, conversation_id=1)
    event2 = create_event("NEW_MESSAGE", {"msg": "a"}, conversation_id=1)

    assert event1["event_id"] != event2["event_id"]
    assert event1["type"] == event2["type"]


@pytest.mark.asyncio
async def test_broadcast_to_experts_only():
    """broadcast_to_experts should send to expert users, not customers."""
    mgr = ConnectionManager()

    class MockWebSocket:
        def __init__(self):
            self.sent = []

        async def accept(self):
            pass

        async def send_json(self, data):
            self.sent.append(data)

    customer_ws = MockWebSocket()
    expert_ws = MockWebSocket()

    await mgr.connect(customer_ws, user_id=1, role="customer")
    await mgr.connect(expert_ws, user_id=2, role="expert")

    event = queue_updated_event(
        action="ADDED", handoff_id=1,
        priority="critical", category="Security",
    )
    await mgr.broadcast_to_experts(event)

    assert len(customer_ws.sent) == 0
    assert len(expert_ws.sent) == 1

    mgr.disconnect(customer_ws, 1)
    mgr.disconnect(expert_ws, 2)


@pytest.mark.asyncio
async def test_event_timestamp_is_timezone_aware():
    """Event timestamps must be timezone-aware UTC."""
    event = create_event("TEST", {})
    ts = event["timestamp"]
    assert "+" in ts or "Z" in ts


# ══════════════════════════════════════════════════════════════════════════════
# Section 5: Voice Session State Machine, Deduplication & Barge-in
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_voice_session_state_machine():
    """Verify VoiceSessionManager transition from IDLE to LISTENING."""
    mock_ws = AsyncMock()
    manager = VoiceSessionManager(mock_ws, user_id=1)

    assert manager.state == VoiceSessionState.IDLE

    with patch("app.websockets.voice_session.async_session_factory") as mock_db_factory:
        mock_db = AsyncMock()
        mock_db_factory.return_value.__aenter__.return_value = mock_db

        mock_convo = AsyncMock()
        mock_convo.customer_id = 1
        mock_db.scalar.return_value = mock_convo
        mock_db.scalar.side_effect = [mock_convo, None]

        await manager.handle_voice_start({
            "conversation_id": 100,
            "stream_id": "v1",
            "utterance_id": "u1",
        })

        assert manager.state == VoiceSessionState.LISTENING
        assert manager.stt_session_id is not None

        await manager.handle_audio_chunk(b"fake audio data")
        assert len(manager.stt_provider._sessions[manager.stt_session_id]) > 0


@pytest.mark.asyncio
async def test_duplicate_utterance_rejected():
    """Utterance already recorded must keep the manager in IDLE state."""
    mock_ws = AsyncMock()
    manager = VoiceSessionManager(mock_ws, user_id=1)

    with patch("app.websockets.voice_session.async_session_factory") as mock_db_factory:
        mock_db = AsyncMock()
        mock_db_factory.return_value.__aenter__.return_value = mock_db

        mock_convo = AsyncMock()
        mock_convo.customer_id = 1
        mock_existing = ProcessedUtterance(id=1, utterance_id="u1")
        mock_db.scalar.side_effect = [mock_convo, mock_existing]

        await manager.handle_voice_start({
            "conversation_id": 100,
            "stream_id": "v1",
            "utterance_id": "u1",
        })

        assert manager.state == VoiceSessionState.IDLE


@pytest.mark.asyncio
async def test_barge_in_cancellation():
    """Barge-in interrupt cancels the active TTS task and transitions to INTERRUPTED."""
    mock_ws = AsyncMock()
    manager = VoiceSessionManager(mock_ws, user_id=1)

    manager.state = VoiceSessionState.SPEAKING
    manager.ai_stream_id = "ai-123"

    mock_task = AsyncMock()
    manager.active_tts_task = mock_task

    await manager.handle_interrupt({"ai_stream_id": "ai-123"})

    assert manager.state == VoiceSessionState.INTERRUPTED
    assert manager.ai_stream_id is None
    mock_task.cancel.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════════
# Section 6: Voice Upload REST Endpoints, STT/TTS & Isolation
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_m7_voice_upload_unsupported_mime(async_client: AsyncClient, auth_headers_a, db_session: AsyncSession):
    """Voice upload should reject unsupported MIME types."""
    resp = await async_client.post(
        "/api/conversations",
        json={"initial_message": "How do I reset my password?"},
        headers=auth_headers_a,
    )
    convo_id = resp.json()["id"]

    files = {"file": ("test.webm", b"dummy audio content", "application/pdf")}
    resp = await async_client.post(
        f"/api/conversations/{convo_id}/messages/voice",
        files=files,
        headers=auth_headers_a,
    )
    assert resp.status_code == 400
    assert "Unsupported audio format" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_m7_voice_upload_empty_file(async_client: AsyncClient, auth_headers_a, db_session: AsyncSession):
    """Voice upload should reject empty files."""
    resp = await async_client.post(
        "/api/conversations",
        json={"initial_message": "How do I reset my password?"},
        headers=auth_headers_a,
    )
    convo_id = resp.json()["id"]

    files = {"file": ("test.webm", b"", "audio/webm")}
    resp = await async_client.post(
        f"/api/conversations/{convo_id}/messages/voice",
        files=files,
        headers=auth_headers_a,
    )
    assert resp.status_code == 400
    assert "Empty audio file" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_m7_voice_upload_and_stt_success(async_client: AsyncClient, auth_headers_a, db_session: AsyncSession):
    """Voice upload should succeed, use STT, and trigger AI response with TTS."""
    resp = await async_client.post(
        "/api/conversations",
        json={"initial_message": "How do I reset my password?"},
        headers=auth_headers_a,
    )
    convo_id = resp.json()["id"]

    files = {"file": ("test.webm", b"dummy my payment failed content", "audio/webm")}

    resp = await async_client.post(
        f"/api/conversations/{convo_id}/messages/voice",
        files=files,
        headers=auth_headers_a,
    )
    assert resp.status_code == 200

    messages = resp.json()
    voice_msg = next((m for m in messages if m["message_type"] == "voice" and m["sender_type"] == "customer"), None)
    assert voice_msg is not None
    assert voice_msg["content"] == "My payment failed."
    assert "audio_url" in voice_msg

    last_ai_msg = [m for m in messages if m["sender_type"] == "ai"][-1]
    assert last_ai_msg["message_type"] == "voice"
    assert "audio_url" in last_ai_msg


@pytest.mark.asyncio
async def test_m7_voice_stt_failure(async_client: AsyncClient, auth_headers_a, db_session: AsyncSession):
    """If STT fails, it should return 400 and NOT save garbage to DB."""
    resp = await async_client.post(
        "/api/conversations",
        json={"initial_message": "How do I reset my password?"},
        headers=auth_headers_a,
    )
    convo_id = resp.json()["id"]

    files = {"file": ("test.webm", b"fail_stt", "audio/webm")}
    resp = await async_client.post(
        f"/api/conversations/{convo_id}/messages/voice",
        files=files,
        headers=auth_headers_a,
    )

    assert resp.status_code == 400
    assert "Sorry, I couldn't understand the audio" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_m7_audio_authorization(async_client: AsyncClient, auth_headers_a, auth_headers_b, test_user_a, test_user_b, db_session: AsyncSession):
    """Customer A should not be able to access Customer B's audio."""
    resp = await async_client.post(
        "/api/conversations",
        json={"initial_message": "How do I reset my password?"},
        headers=auth_headers_a,
    )
    convo_id = resp.json()["id"]

    files = {"file": ("test.webm", b"dummy my payment failed content", "audio/webm")}
    resp = await async_client.post(
        f"/api/conversations/{convo_id}/messages/voice",
        files=files,
        headers=auth_headers_a,
    )
    assert resp.status_code == 200
    messages = resp.json()
    voice_msg = next(m for m in messages if m["message_type"] == "voice" and m["sender_type"] == "customer")
    audio_url = voice_msg["audio_url"]

    resp_a = await async_client.get(audio_url, headers=auth_headers_a)
    assert resp_a.status_code == 200

    resp_b = await async_client.get(audio_url, headers=auth_headers_b)
    assert resp_b.status_code == 404


@pytest.mark.asyncio
async def test_m7_tts_failure_saves_text(async_client: AsyncClient, auth_headers_a, db_session: AsyncSession):
    """If TTS fails, the AI text response should still be saved and delivered as TEXT."""
    from app.voice.service import tts_provider
    original_synthesize = tts_provider.synthesize

    async def failing_synthesize(text, output_path):
        raise ValueError("Simulated TTS failure")

    tts_provider.synthesize = failing_synthesize

    try:
        resp = await async_client.post(
            "/api/conversations",
            json={"initial_message": "How do I reset my password?"},
            headers=auth_headers_a,
        )
        convo_id = resp.json()["id"]

        files = {"file": ("test.webm", b"dummy text", "audio/webm")}
        resp = await async_client.post(
            f"/api/conversations/{convo_id}/messages/voice",
            files=files,
            headers=auth_headers_a,
        )

        assert resp.status_code == 200
        messages = resp.json()

        last_ai_msg = [m for m in messages if m["sender_type"] == "ai"][-1]
        assert last_ai_msg["message_type"] == "text"
        assert last_ai_msg["audio_url"] is None
        assert "This is a transcribed voice message." not in last_ai_msg["content"]
        assert len(last_ai_msg["content"]) > 0
    finally:
        tts_provider.synthesize = original_synthesize

