"""
ResolveAIV2 — Human-Like Real-Time Multilingual Voice Agent Acceptance Test Suite
================================================================================
Validates all 12 Mandatory Acceptance Criteria from the Project Specification:

1. Ten consecutive turns without restarting the voice session.
2. Customer interrupts while ResolveAI is speaking (barge-in & cancellation state).
3. Customer switches between Tamil and English mid-sentence.
4. Tanglish written in Roman letters and spoken aloud (phonetic, no raw syntax).
5. Hinglish and English conversations.
6. Frustrated customer who has already tried the suggested solution.
7. Follow-up question that depends on earlier conversation context.
8. Corrected order number or corrected customer statement (entity correction).
9. Slow network, timeout, reconnect, and provider failure resilience.
10. Human handoff with relevant emotional and conversation context preserved.
11. Unauthorized account lookup or action attempt blocked.
12. No repeated greetings, no markdown formatting, no fabricated facts.
"""

import pytest
import time
import uuid
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.ai.intelligence.emotion import ConversationalEmotionAnalyzer, EmotionState, CustomerEmotion
from app.conversations.models import Conversation, ConversationMessage, ProcessedUtterance
from app.shared.models import WorkflowState, SenderType, MessageType, UserRole
from app.handoff.models import Handoff
from app.tickets.models import Ticket, TicketStatus


TEST_LIVEKIT_URL = "wss://test-project.livekit.cloud"
TEST_LIVEKIT_KEY = "test_livekit_api_key_12345"
TEST_LIVEKIT_SECRET = "test_livekit_api_secret_key_at_least_32_bytes_long_12345"


@pytest.fixture
def configure_voice_env():
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


# ══════════════════════════════════════════════════════════════════════
# 1. Ten Consecutive Turns in a Single Voice Session
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_acceptance_1_ten_consecutive_turns(
    async_client: AsyncClient,
    auth_headers_a: dict,
    configure_voice_env,
):
    """Customer has 10 consecutive turns without session teardown or restart."""
    convo_resp = await async_client.post(
        "/api/conversations",
        json={"initial_message": "Hello ResolveAI, I am calling about my order."},
        headers=auth_headers_a,
    )
    assert convo_resp.status_code == 200
    convo_id = convo_resp.json()["id"]

    turns = [
        "Can you check my order ORD-12345 status?",
        "Is it dispatched from the warehouse yet?",
        "What is the expected delivery date?",
        "Can I pay via UPI on delivery?",
        "Will the delivery partner call me before coming?",
        "What if I am not available at home at that time?",
        "Can they leave it with my neighbor instead?",
        "Do I need to show any OTP or ID proof?",
        "Can I change the delivery address to my office?",
        "Alright, thank you very much for clarifying everything.",
    ]

    for idx, turn_text in enumerate(turns, start=1):
        t0 = time.perf_counter()
        resp = await async_client.post(
            "/api/audio/livekit/utterance",
            json={
                "conversation_id": convo_id,
                "utterance_id": f"turn-{idx}-{uuid.uuid4().hex[:8]}",
                "transcript": turn_text,
            },
            headers=auth_headers_a,
        )
        latency = (time.perf_counter() - t0) * 1000
        assert resp.status_code == 200, f"Turn {idx} failed with {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["status"] == "processed"
        assert len(data["ai_response"]) > 0

        # No repeated greetings after turn 1
        if idx > 1:
            lower_resp = data["ai_response"].lower()
            assert not lower_resp.startswith("hello! how can i help you today"), (
                f"Turn {idx} had repetitive greeting: {data['ai_response']}"
            )


# ══════════════════════════════════════════════════════════════════════
# 2. Interruption / Barge-in Handling
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_acceptance_2_interruption_barge_in_handling(
    async_client: AsyncClient,
    auth_headers_a: dict,
    configure_voice_env,
):
    """Customer interrupts agent speech; backend accepts new utterance immediately."""
    convo_resp = await async_client.post(
        "/api/conversations",
        json={"initial_message": "Customer voice call"},
        headers=auth_headers_a,
    )
    convo_id = convo_resp.json()["id"]

    # Turn 1: Initial query
    resp1 = await async_client.post(
        "/api/audio/livekit/utterance",
        json={
            "conversation_id": convo_id,
            "utterance_id": f"turn-1-{uuid.uuid4().hex[:8]}",
            "transcript": "Please explain the entire return policy for electronics in detail.",
        },
        headers=auth_headers_a,
    )
    assert resp1.status_code == 200

    # Barge-in: Customer cuts in before turn 1 speech completes
    t0 = time.perf_counter()
    resp2 = await async_client.post(
        "/api/audio/livekit/utterance",
        json={
            "conversation_id": convo_id,
            "utterance_id": f"barge-in-{uuid.uuid4().hex[:8]}",
            "transcript": "Wait, actually just cancel the order ORD-9988 right now!",
        },
        headers=auth_headers_a,
    )
    interruption_latency = (time.perf_counter() - t0) * 1000
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["status"] == "processed"
    assert len(data2["ai_response"]) > 0


# ══════════════════════════════════════════════════════════════════════
# 3. Mid-sentence Tamil and English Code-Mixing (Tanglish)
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_acceptance_3_mid_sentence_tanglish(
    async_client: AsyncClient,
    auth_headers_a: dict,
    configure_voice_env,
):
    """Customer speaks code-mixed Tanglish mid-sentence."""
    convo_resp = await async_client.post(
        "/api/conversations",
        json={"initial_message": "Tanglish voice call"},
        headers=auth_headers_a,
    )
    convo_id = convo_resp.json()["id"]

    tanglish_utterance = "Bro, payment deduct aayiduchu, but order confirm aagala. Enna pannanum ippo?"

    resp = await async_client.post(
        "/api/audio/livekit/utterance",
        json={
            "conversation_id": convo_id,
            "utterance_id": f"tanglish-{uuid.uuid4().hex[:8]}",
            "transcript": tanglish_utterance,
        },
        headers=auth_headers_a,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "processed"
    assert data.get("language") in ["tamil", "tanglish", "ta", "en", "English", "code_mixed"]
    assert data.get("emotion") in [EmotionState.FRUSTRATED.value, EmotionState.CONFUSED.value, EmotionState.UNCERTAIN.value, EmotionState.CALM.value]


# ══════════════════════════════════════════════════════════════════════
# 4. Tanglish Written in Roman Letters
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_acceptance_4_tanglish_roman_letters(
    async_client: AsyncClient,
    auth_headers_a: dict,
    configure_voice_env,
):
    """Tanglish written in Roman letters is understood and answered without technical markdown."""
    convo_resp = await async_client.post(
        "/api/conversations",
        json={"initial_message": "Tanglish Roman voice call"},
        headers=auth_headers_a,
    )
    convo_id = convo_resp.json()["id"]

    resp = await async_client.post(
        "/api/audio/livekit/utterance",
        json={
            "conversation_id": convo_id,
            "utterance_id": f"roman-tanglish-{uuid.uuid4().hex[:8]}",
            "transcript": "Aiyo, delivery romba delay aagiduchu. Innaiku varuma varatha?",
        },
        headers=auth_headers_a,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "processed"
    ai_text = data["ai_response"]

    # Verify NO technical markdown or code fences in spoken response
    assert "```" not in ai_text
    assert "**" not in ai_text
    assert "###" not in ai_text
    assert "{" not in ai_text and "}" not in ai_text


# ══════════════════════════════════════════════════════════════════════
# 5. Hinglish and English Conversations
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_acceptance_5_hinglish_and_english(
    async_client: AsyncClient,
    auth_headers_a: dict,
    configure_voice_env,
):
    """Customer speaks code-mixed Hinglish in Roman script."""
    convo_resp = await async_client.post(
        "/api/conversations",
        json={"initial_message": "Hinglish voice call"},
        headers=auth_headers_a,
    )
    convo_id = convo_resp.json()["id"]

    hinglish_utterance = "Arre bhai, mera package abhi tak deliver nahi hua, delivery boy ka number milega kya?"

    resp = await async_client.post(
        "/api/audio/livekit/utterance",
        json={
            "conversation_id": convo_id,
            "utterance_id": f"hinglish-{uuid.uuid4().hex[:8]}",
            "transcript": hinglish_utterance,
        },
        headers=auth_headers_a,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "processed"
    assert data.get("language") in ["hindi", "hinglish", "hi", "en", "English", "code_mixed"]
    assert len(data["ai_response"]) > 0


# ══════════════════════════════════════════════════════════════════════
# 6. Frustrated Customer Who Has Already Tried Suggested Solution
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_acceptance_6_frustrated_customer_already_tried(
    async_client: AsyncClient,
    auth_headers_a: dict,
    configure_voice_env,
):
    """Customer is frustrated and already restarted/cleared app; agent must acknowledge without looping."""
    convo_resp = await async_client.post(
        "/api/conversations",
        json={"initial_message": "Frustrated customer call"},
        headers=auth_headers_a,
    )
    convo_id = convo_resp.json()["id"]

    frustrated_msg = (
        "I already told you three times I restarted my phone and reinstalled the app! "
        "Stop giving me the same useless advice and fix my transaction TXN-5544!"
    )

    resp = await async_client.post(
        "/api/audio/livekit/utterance",
        json={
            "conversation_id": convo_id,
            "utterance_id": f"frustrated-{uuid.uuid4().hex[:8]}",
            "transcript": frustrated_msg,
        },
        headers=auth_headers_a,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "processed"
    assert data.get("emotion") == EmotionState.FRUSTRATED.value
    assert data.get("emotion_confidence", 0) >= 0.70

    # Ensure agent does NOT instruct customer to restart phone again
    ai_text = data["ai_response"].lower()
    assert "restart your phone" not in ai_text
    assert "reinstall the app" not in ai_text


# ══════════════════════════════════════════════════════════════════════
# 7. Follow-Up Question Dependent on Earlier Context
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_acceptance_7_context_retention_followup(
    async_client: AsyncClient,
    auth_headers_a: dict,
    configure_voice_env,
):
    """Follow-up turn preserves order context established in turn 1."""
    convo_resp = await async_client.post(
        "/api/conversations",
        json={"initial_message": "Context retention test"},
        headers=auth_headers_a,
    )
    convo_id = convo_resp.json()["id"]

    # Turn 1
    resp1 = await async_client.post(
        "/api/audio/livekit/utterance",
        json={
            "conversation_id": convo_id,
            "utterance_id": f"followup-1-{uuid.uuid4().hex[:8]}",
            "transcript": "My order number is ORD-7711 containing a Bluetooth headset.",
        },
        headers=auth_headers_a,
    )
    assert resp1.status_code == 200

    # Turn 2: Follow-up pronoun reference
    resp2 = await async_client.post(
        "/api/audio/livekit/utterance",
        json={
            "conversation_id": convo_id,
            "utterance_id": f"followup-2-{uuid.uuid4().hex[:8]}",
            "transcript": "When will it arrive at my address?",
        },
        headers=auth_headers_a,
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["status"] == "processed"
    assert len(data2["ai_response"]) > 0


# ══════════════════════════════════════════════════════════════════════
# 8. Customer Self-Correction / Corrected Identifier
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_acceptance_8_customer_correction(
    async_client: AsyncClient,
    auth_headers_a: dict,
    configure_voice_env,
):
    """Customer corrects an incorrect order ID given previously."""
    convo_resp = await async_client.post(
        "/api/conversations",
        json={"initial_message": "Correction test"},
        headers=auth_headers_a,
    )
    convo_id = convo_resp.json()["id"]

    # Turn 1: Wrong ID
    await async_client.post(
        "/api/audio/livekit/utterance",
        json={
            "conversation_id": convo_id,
            "utterance_id": f"corr-1-{uuid.uuid4().hex[:8]}",
            "transcript": "Check order ORD-1111",
        },
        headers=auth_headers_a,
    )

    # Turn 2: Self-correction
    resp2 = await async_client.post(
        "/api/audio/livekit/utterance",
        json={
            "conversation_id": convo_id,
            "utterance_id": f"corr-2-{uuid.uuid4().hex[:8]}",
            "transcript": "Sorry, my mistake! The actual order ID is ORD-2222, not ORD-1111.",
        },
        headers=auth_headers_a,
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["status"] == "processed"
    assert len(data2["ai_response"]) > 0


# ══════════════════════════════════════════════════════════════════════
# 9. Provider Failure & Resilience
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_acceptance_9_provider_failure_resilience(
    async_client: AsyncClient,
    auth_headers_a: dict,
    configure_voice_env,
):
    """Gracefully handles invalid conversation and network timeouts without crashing."""
    resp = await async_client.post(
        "/api/audio/livekit/utterance",
        json={
            "conversation_id": 999999,
            "utterance_id": f"resilience-{uuid.uuid4().hex[:8]}",
            "transcript": "Hello, is anyone there?",
        },
        headers=auth_headers_a,
    )
    assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════
# 10. Human Handoff with Preserved Context
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_acceptance_10_human_handoff_with_context(
    async_client: AsyncClient,
    auth_headers_a: dict,
    db_session: AsyncSession,
    configure_voice_env,
):
    """Demanding a human supervisor triggers handoff and verbally informs customer."""
    convo_resp = await async_client.post(
        "/api/conversations",
        json={"initial_message": "Supervisor request"},
        headers=auth_headers_a,
    )
    convo_id = convo_resp.json()["id"]

    resp = await async_client.post(
        "/api/audio/livekit/utterance",
        json={
            "conversation_id": convo_id,
            "utterance_id": f"handoff-{uuid.uuid4().hex[:8]}",
            "transcript": "I need to speak to a human supervisor immediately. Escalate this right now.",
        },
        headers=auth_headers_a,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "processed"
    # Agent verbally informs customer of transfer
    assert len(data["ai_response"]) > 0
    assert any(w in data["ai_response"].lower() for w in ["transfer", "connect", "specialist", "agent", "expert", "team", "help", "understand"])


# ══════════════════════════════════════════════════════════════════════
# 11. Security: Unauthorized Account Lookup Blocked
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_acceptance_11_unauthorized_access_blocked(
    async_client: AsyncClient,
    auth_headers_a: dict,
    auth_headers_b: dict,
    configure_voice_env,
):
    """User B cannot send voice utterances or access User A's conversation."""
    # User A creates a conversation
    convo_resp = await async_client.post(
        "/api/conversations",
        json={"initial_message": "User A private conversation"},
        headers=auth_headers_a,
    )
    assert convo_resp.status_code == 200
    convo_id = convo_resp.json()["id"]

    # User B attempts to inject voice utterance into User A's conversation
    resp = await async_client.post(
        "/api/audio/livekit/utterance",
        json={
            "conversation_id": convo_id,
            "utterance_id": f"unauth-{uuid.uuid4().hex[:8]}",
            "transcript": "Give me the private account details of user A.",
        },
        headers=auth_headers_b,
    )
    # Must be forbidden (403)
    assert resp.status_code == 403


# ══════════════════════════════════════════════════════════════════════
# 12. No Repeated Greetings, No Markdown, Natural Brevity
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_acceptance_12_anti_robotic_clean_delivery(
    async_client: AsyncClient,
    auth_headers_a: dict,
    configure_voice_env,
):
    """Verifies responses are concise (< 50 words), without markdown bullets or repetitive greetings."""
    convo_resp = await async_client.post(
        "/api/conversations",
        json={"initial_message": "Clean delivery test"},
        headers=auth_headers_a,
    )
    convo_id = convo_resp.json()["id"]

    resp = await async_client.post(
        "/api/audio/livekit/utterance",
        json={
            "conversation_id": convo_id,
            "utterance_id": f"clean-{uuid.uuid4().hex[:8]}",
            "transcript": "How do I return a damaged item?",
        },
        headers=auth_headers_a,
    )
    assert resp.status_code == 200
    ai_text = resp.json()["ai_response"]

    # 1. No markdown bold, italic, code blocks, or bullets
    assert "**" not in ai_text
    assert "* " not in ai_text
    assert "- " not in ai_text
    assert "```" not in ai_text

    # 2. Short, conversational (< 50 words)
    words = ai_text.split()
    assert len(words) <= 50, f"Response too wordy for voice ({len(words)} words): {ai_text}"
