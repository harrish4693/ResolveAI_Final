"""
ResolveAIV2 — Voice Agent Language Consistency & Customer Switching Test Suite
==============================================================================
Validates:
1. Default English at call start.
2. Explicit customer language requests ("Tamil la pesunga", "Now speak in Hindi", "Please switch back to English").
3. Persistence of chosen response language across subsequent responses.
4. Resistance to spurious language flipping on isolated foreign-language loanwords ("dosa pan", "kurta").
5. Resistance to noisy STT provider language labels.
6. Support for natural Tanglish/Hinglish code-mixing without forcing native script.
7. Return to English when customer switches back to English.
8. 10-turn full session continuity without duplicate replies or lost turns.
9. Honest explanation and fallback for unsupported languages (French, German, etc.).
"""

import pytest
import re
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.users.models import User
from app.conversations.models import Conversation, ConversationMessage, ProcessedUtterance
from app.conversations.service import ConversationService
from app.shared.models import ConversationChannel, SenderType
from app.voice.language_controller import (
    VoiceLanguageController,
    VoiceLanguagePolicy,
    SUPPORTED_LANGUAGES,
)
from app.voice.livekit_service import LiveKitService


# ── UNIT TESTS: VoiceLanguageController ──────────────────────────────────────

def test_controller_default_english():
    """Test 1: Default English on new call without prior preference."""
    policy = VoiceLanguagePolicy()
    assert policy.response_language == "english"
    assert policy.bcp47_code == "en-IN"

    # Turn 1
    policy = VoiceLanguageController.evaluate_turn(policy, "Hi, I need help with my order.")
    assert policy.response_language == "english"
    assert policy.bcp47_code == "en-IN"

    # Turn 2
    policy = VoiceLanguageController.evaluate_turn(policy, "Can you check the tracking?")
    assert policy.response_language == "english"
    assert policy.bcp47_code == "en-IN"


def test_controller_isolated_foreign_words_in_english():
    """Test 3: Isolated foreign/culinary/product terms in English must NOT flip language."""
    policy = VoiceLanguagePolicy(response_language="english")

    # Dosa pan
    policy = VoiceLanguageController.evaluate_turn(policy, "Can you check if my dosa pan order is on the way?")
    assert policy.response_language == "english", f"Expected english, got {policy.response_language}"

    # Kurta
    policy = VoiceLanguageController.evaluate_turn(policy, "I ordered a kurta and delivery is delayed.")
    assert policy.response_language == "english", f"Expected english, got {policy.response_language}"

    # Biryani masala
    policy = VoiceLanguageController.evaluate_turn(policy, "Where is my biryani masala package?")
    assert policy.response_language == "english", f"Expected english, got {policy.response_language}"


def test_controller_noisy_stt_language_label():
    """Test 5: Noisy STT detector reporting Hindi/Tamil for short English words must be ignored."""
    policy = VoiceLanguagePolicy(response_language="english")

    # STT falsely labels "Yes please" as Hindi
    policy = VoiceLanguageController.evaluate_turn(
        policy, "Yes please", stt_metadata={"language_code": "hi-IN", "confidence": 0.65}
    )
    assert policy.response_language == "english"

    # STT falsely labels "Check tracking" as Tamil
    policy = VoiceLanguageController.evaluate_turn(
        policy, "Check tracking", stt_metadata={"language_code": "ta-IN", "confidence": 0.55}
    )
    assert policy.response_language == "english"


def test_controller_explicit_switch_and_code_mixed_continuity():
    """Test 2 & Test 6: Explicit switch to Tamil/Tanglish and natural code-mixed style."""
    policy = VoiceLanguagePolicy(response_language="english")

    # Explicit switch to Tamil
    policy = VoiceLanguageController.evaluate_turn(policy, "I want to speak in Tamil.")
    assert policy.response_language in ("tamil", "tanglish")

    # Customer speaks Tanglish
    policy = VoiceLanguageController.evaluate_turn(policy, "En order innum varala.")
    assert policy.response_language in ("tamil", "tanglish")
    assert policy.language_style in ("code-mixed", "conversational")
    assert policy.bcp47_code == "ta-IN"

    # Customer continues in Tanglish
    policy = VoiceLanguageController.evaluate_turn(policy, "Tracking status check panni sollunga.")
    assert policy.response_language in ("tamil", "tanglish")


def test_controller_switch_back_to_english():
    """Test 4: Customer previously speaking Tamil/Hindi explicitly or implicitly switches back to English."""
    policy = VoiceLanguagePolicy(response_language="tanglish")

    # Explicit request to explain in English
    policy = VoiceLanguageController.evaluate_turn(policy, "Please explain in English.")
    assert policy.response_language == "english"
    assert policy.bcp47_code == "en-IN"

    # Subsequent English turn
    policy = VoiceLanguageController.evaluate_turn(policy, "Can you check the tracking?")
    assert policy.response_language == "english"


def test_controller_unsupported_language_explanation():
    """Test 9: Honest explanation and fallback for unsupported languages."""
    policy = VoiceLanguagePolicy(response_language="english")

    # French
    policy = VoiceLanguageController.evaluate_turn(policy, "Can you speak in French please?")
    assert policy.unsupported_requested_language == "French"
    msg = VoiceLanguageController.get_unsupported_language_message(policy.unsupported_requested_language, "english")
    assert "French" in msg
    assert "English" in msg
    assert "Tamil" in msg
    assert "Hindi" in msg


# ── INTEGRATION TESTS: End-to-End Voice Turns in ConversationService ─────────

@pytest.mark.asyncio
async def test_full_acceptance_sequence_10_turns():
    """
    Mandatory Acceptance Test + Full 10-turn session continuity:
    1. Turn 1 (en): Customer starts in English -> Agent speaks English.
    2. Turn 2 (en): Customer asks tracking in English -> Agent speaks English.
    3. Turn 3 (loanword): Customer mentions 'dosa pan' in English -> Agent remains in English.
    4. Turn 4 (switch): Customer says 'Tamil la pesunga' -> Agent switches to Tamil/Tanglish.
    5. Turn 5 (tanglish): Customer continues 'En order innum varala.' -> Agent maintains Tanglish.
    6. Turn 6 (tanglish): Customer says 'Tracking status check panni sollunga.' -> Agent maintains Tanglish.
    7. Turn 7 (switch): Customer says 'Now speak in Hindi' -> Agent switches to Hindi.
    8. Turn 8 (switch): Customer says 'Please switch back to English' -> Agent returns to English.
    9. Turn 9 (en): Customer asks 'Where is my order?' -> Agent continues in English.
    10. Turn 10 (unsupported): Customer says 'Can you speak in German?' -> Agent explains limitation.
    """
    async with async_session_factory() as session:
        # Create test customer and conversation
        user = User(email="voice_lang_test@example.com", password_hash="testpasshash", full_name="Voice Test User")
        session.add(user)
        await session.flush()

        convo = Conversation(customer_id=user.id, channel=ConversationChannel.VOICE)
        session.add(convo)
        await session.flush()

        svc = ConversationService()
        spoken_audio_turns = []

        async def capture_tts(text: str):
            spoken_audio_turns.append(text)

        # Turn 1: Customer starts in English
        await svc.process_customer_message(
            db=session,
            conversation=convo,
            customer_id=user.id,
            message_content="Hi, I need help with my order.",
            tts_callback=capture_tts,
            reply_with_voice=True,
        )
        assert convo.preferred_language == "english"

        # Turn 2: Customer asks tracking in English
        await svc.process_customer_message(
            db=session,
            conversation=convo,
            customer_id=user.id,
            message_content="Can you check the tracking?",
            tts_callback=capture_tts,
            reply_with_voice=True,
        )
        assert convo.preferred_language == "english"

        # Turn 3: Customer mentions 'dosa pan' loanword in English
        await svc.process_customer_message(
            db=session,
            conversation=convo,
            customer_id=user.id,
            message_content="Can you check if my dosa pan order is on the way?",
            tts_callback=capture_tts,
            reply_with_voice=True,
        )
        # MUST remain in English!
        assert convo.preferred_language == "english", f"Expected english, got {convo.preferred_language}"

        # Turn 4: Customer says 'Tamil la pesunga'
        await svc.process_customer_message(
            db=session,
            conversation=convo,
            customer_id=user.id,
            message_content="Tamil la pesunga",
            tts_callback=capture_tts,
            reply_with_voice=True,
        )
        assert convo.preferred_language in ("tanglish", "tamil")

        # Turn 5: Customer continues in Tanglish
        await svc.process_customer_message(
            db=session,
            conversation=convo,
            customer_id=user.id,
            message_content="En order innum varala.",
            tts_callback=capture_tts,
            reply_with_voice=True,
        )
        assert convo.preferred_language in ("tanglish", "tamil")

        # Turn 6: Customer continues in Tanglish
        await svc.process_customer_message(
            db=session,
            conversation=convo,
            customer_id=user.id,
            message_content="Tracking status check panni sollunga.",
            tts_callback=capture_tts,
            reply_with_voice=True,
        )
        assert convo.preferred_language in ("tanglish", "tamil")

        # Turn 7: Customer says 'Now speak in Hindi'
        await svc.process_customer_message(
            db=session,
            conversation=convo,
            customer_id=user.id,
            message_content="Now speak in Hindi",
            tts_callback=capture_tts,
            reply_with_voice=True,
        )
        assert convo.preferred_language in ("hindi", "hinglish")

        # Turn 8: Customer says 'Please switch back to English'
        await svc.process_customer_message(
            db=session,
            conversation=convo,
            customer_id=user.id,
            message_content="Please switch back to English",
            tts_callback=capture_tts,
            reply_with_voice=True,
        )
        assert convo.preferred_language == "english"

        # Turn 9: Customer continues in English
        await svc.process_customer_message(
            db=session,
            conversation=convo,
            customer_id=user.id,
            message_content="Where is my package right now?",
            tts_callback=capture_tts,
            reply_with_voice=True,
        )
        assert convo.preferred_language == "english"

        # Turn 10: Customer asks for unsupported German
        await svc.process_customer_message(
            db=session,
            conversation=convo,
            customer_id=user.id,
            message_content="Can you speak in German please?",
            tts_callback=capture_tts,
            reply_with_voice=True,
        )
        # Check last message content
        msgs = (await session.execute(
            select(ConversationMessage).where(ConversationMessage.conversation_id == convo.id).order_by(ConversationMessage.id.desc())
        )).scalars().all()
        last_ai_msg = msgs[0]
        assert "German" in last_ai_msg.content
        assert "English" in last_ai_msg.content


@pytest.mark.asyncio
async def test_livekit_utterance_metadata_and_idempotency():
    """Verify LiveKit utterance processing preserves language metadata and rejects duplicates."""
    async with async_session_factory() as session:
        user = User(email="livekit_lang_test@example.com", password_hash="testpasshash", full_name="LK Lang User")
        session.add(user)
        await session.flush()

        convo = Conversation(customer_id=user.id, channel=ConversationChannel.VOICE)
        session.add(convo)
        await session.flush()

        utterance_id = f"utt_lang_{user.id}_{convo.id}_1"
        res = await LiveKitService.process_spoken_utterance(
            db=session,
            conversation_id=convo.id,
            customer_id=user.id,
            utterance_id=utterance_id,
            transcript="Hello, can you help me?",
        )
        assert res["status"] == "processed"
        assert res["language"] == "English"
        assert res["bcp47_code"] == "en-IN"

        # Duplicate utterance must be rejected
        res_dup = await LiveKitService.process_spoken_utterance(
            db=session,
            conversation_id=convo.id,
            customer_id=user.id,
            utterance_id=utterance_id,
            transcript="Hello, can you help me?",
        )
        assert res_dup["status"] == "duplicate"
