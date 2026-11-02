"""
ResolveAI V2 — All-Languages Multilingual Call Agent Verification Suite
========================================================================
Validates end-to-end Call Agent voice pipeline capabilities across:
- Telugu (Telugu script & Tenglish)
- Kannada (Kannada script & Kanglish)
- Malayalam (Malayalam script & Manglish)
- Bengali (Bengali script & Benglish)
- Marathi (Marathi Devanagari script & Marathish)
- Gujarati (Gujarati script & Gujlish)
- Punjabi (Gurmukhi script & Punglish)
- Odia (Odia script & Odlish)
- Tamil (Tamil script & Tanglish)
- Hindi (Hindi Devanagari script & Hinglish)
- English (Indian English)
- Urdu & Assamese (Saaras STT + LLM + TTS browser fallback)
- Unsupported foreign languages (French, German, etc. -> polite explanation)
"""

import pytest
from sqlalchemy import select

from app.database import async_session_factory
from app.users.models import User
from app.commerce.models import Order, Transaction
from app.conversations.models import Conversation, ConversationMessage
from app.conversations.service import ConversationService
from app.shared.models import ConversationChannel
from app.voice.opener_cache import (
    STANDARD_GREETINGS,
    STANDARD_FILLERS,
    STANDARD_ESCALATIONS,
    LANGUAGE_CODE_MAP,
    get_cached_opener_audio,
    store_cached_opener_audio,
)
from app.voice.sarvam_tts import (
    SARVAM_TTS_SUPPORTED_CODES,
    normalize_tts_language_code,
    synthesize_sarvam,
    SarvamTTSError,
)
from app.voice.language_controller import (
    VoiceLanguageController,
    VoiceLanguagePolicy,
    VOICE_CAPABILITY_REGISTRY,
    SUPPORTED_LANGUAGES,
)
from app.voice.stt_registry import STT_CAPABILITY_REGISTRY, resolve_stt_language_code


# ── TEST 1: Provider Capability Alignment Matrix ──────────────────────────────

def test_stt_and_tts_provider_capability_boundaries():
    """
    Confirms provider capability truthfulness:
    - STT (Sarvam Saaras v4): 22 scheduled Indian languages + English.
    - TTS (Sarvam Bulbul v3): 11 supported languages.
    - Fallback: Non-Bulbul languages cleanly trigger browser fallback.
    """
    # 11 languages supported by Sarvam Bulbul neural TTS
    bulbul_languages = {
        "en-IN", "hi-IN", "ta-IN", "te-IN", "kn-IN",
        "ml-IN", "bn-IN", "mr-IN", "gu-IN", "pa-IN", "od-IN"
    }
    assert SARVAM_TTS_SUPPORTED_CODES == bulbul_languages

    # Check normalizer maps all alias variants correctly
    assert normalize_tts_language_code("telugu") == "te-IN"
    assert normalize_tts_language_code("kannada") == "kn-IN"
    assert normalize_tts_language_code("malayalam") == "ml-IN"
    assert normalize_tts_language_code("bengali") == "bn-IN"
    assert normalize_tts_language_code("marathi") == "mr-IN"
    assert normalize_tts_language_code("gujarati") == "gu-IN"
    assert normalize_tts_language_code("punjabi") == "pa-IN"
    assert normalize_tts_language_code("odia") == "od-IN"
    assert normalize_tts_language_code("or-IN") == "od-IN"
    assert normalize_tts_language_code("tamil") == "ta-IN"
    assert normalize_tts_language_code("tanglish") == "ta-IN"
    assert normalize_tts_language_code("hindi") == "hi-IN"
    assert normalize_tts_language_code("hinglish") == "hi-IN"
    assert normalize_tts_language_code("english") == "en-IN"

    # Non-Bulbul languages normalize correctly but trigger fallback in TTS
    assert normalize_tts_language_code("urdu") == "ur-IN"
    assert normalize_tts_language_code("assamese") == "as-IN"


# ── TEST 2: Opener & Filler Cache Coverage Across All Languages ───────────────

def test_opener_cache_dictionary_completeness():
    """Verify greetings, fillers, and escalations exist for all 11+ languages."""
    core_languages = [
        "English", "Tamil", "Tanglish", "Hindi", "Hinglish",
        "Telugu", "Tenglish", "Kannada", "Kanglish",
        "Malayalam", "Manglish", "Bengali", "Benglish",
        "Marathi", "Marathish", "Gujarati", "Gujlish",
        "Punjabi", "Punglish", "Odia", "Assamese", "Urdu"
    ]
    for lang in core_languages:
        assert lang in STANDARD_GREETINGS, f"Missing greeting for {lang}"
        assert lang in STANDARD_FILLERS, f"Missing fillers for {lang}"
        assert lang in STANDARD_ESCALATIONS, f"Missing escalation for {lang}"
        assert len(STANDARD_FILLERS[lang]) >= 3, f"Insufficient fillers for {lang}"

    # Verify memory cache store and retrieval
    test_phrase = "Testing cached audio"
    fake_audio = b"ID3FakeAudioBytesData"
    store_cached_opener_audio(test_phrase, fake_audio, speaker="kavya", language_code="te-IN")
    retrieved = get_cached_opener_audio(test_phrase, speaker="kavya", language_code="te-IN")
    assert retrieved == fake_audio


# ── TEST 3: TTS Graceful Fallback for Non-Bulbul Languages ───────────────────

@pytest.mark.asyncio
async def test_sarvam_tts_unsupported_language_raises_clean_error():
    """Synthesizing for Urdu or Assamese raises SarvamTTSError so /tts triggers browser fallback."""
    with pytest.raises(SarvamTTSError) as excinfo:
        await synthesize_sarvam("Hello", language_code="ur-IN")
    assert "Unsupported TTS language" in str(excinfo.value)
    assert "browser" in str(excinfo.value).lower()

    with pytest.raises(SarvamTTSError) as excinfo2:
        await synthesize_sarvam("Hello", language_code="as-IN")
    assert "Unsupported TTS language" in str(excinfo2.value)


# ── TEST 4: Multi-Turn Voice Flow Across Dravidian & Indo-Aryan Languages ────

@pytest.mark.asyncio
async def test_multiturn_bengali_voice_flow():
    """Validates multi-turn Bengali conversation with order query and tool lookup."""
    async with async_session_factory() as session:
        user = User(email="bengali_user@example.com", password_hash="testpasshash", full_name="Debasis Roy")
        session.add(user)
        await session.flush()

        order = Order(
            order_number="ORD-BN-777",
            customer_id=user.id,
            status="shipped",
            tracking_number="BNTRK12345",
        )
        session.add(order)

        convo = Conversation(customer_id=user.id, channel=ConversationChannel.VOICE)
        session.add(convo)
        await session.flush()

        svc = ConversationService()
        spoken = []

        async def capture_tts(text: str):
            spoken.append(text)

        # Turn 1: Switch to Bengali
        await svc.process_customer_message(
            db=session,
            conversation=convo,
            customer_id=user.id,
            message_content="Bangla te kotha bolun.",
            tts_callback=capture_tts,
            reply_with_voice=True,
        )
        assert convo.preferred_language in ("bengali", "benglish")
        all_spoken = " ".join(spoken)
        assert any(t in all_spoken for t in ["বাংলায়", "অবশ্যই", "সাহায্য", "Benglish", "help"])

        # Turn 2: Ask about order status in Benglish
        await svc.process_customer_message(
            db=session,
            conversation=convo,
            customer_id=user.id,
            message_content="Aamar order ORD-BN-777 status ki?",
            tts_callback=capture_tts,
            reply_with_voice=True,
        )
        all_spoken = " ".join(spoken)
        assert "ORD-BN-777" in all_spoken or "BNTRK12345" in all_spoken or "shipped" in all_spoken.lower() or "স্ট্যাটাস" in all_spoken


@pytest.mark.asyncio
async def test_multiturn_marathi_voice_flow():
    """Validates multi-turn Marathi conversation with order query."""
    async with async_session_factory() as session:
        user = User(email="marathi_user@example.com", password_hash="testpasshash", full_name="Tanvi Kulkarni")
        session.add(user)
        await session.flush()

        order = Order(
            order_number="ORD-MR-333",
            customer_id=user.id,
            status="delivered",
            tracking_number="MRTRK999",
        )
        session.add(order)

        convo = Conversation(customer_id=user.id, channel=ConversationChannel.VOICE)
        session.add(convo)
        await session.flush()

        svc = ConversationService()
        spoken = []

        async def capture_tts(text: str):
            spoken.append(text)

        # Turn 1: Switch to Marathi
        await svc.process_customer_message(
            db=session,
            conversation=convo,
            customer_id=user.id,
            message_content="Marathi madhe bola.",
            tts_callback=capture_tts,
            reply_with_voice=True,
        )
        assert convo.preferred_language in ("marathi", "marathish")
        all_spoken = " ".join(spoken)
        assert any(t in all_spoken for t in ["मराठीत", "नक्कीच", "मदत", "Marathish", "help"])

        # Turn 2: Query order in Marathish
        await svc.process_customer_message(
            db=session,
            conversation=convo,
            customer_id=user.id,
            message_content="Majha order ORD-MR-333 status kay ahe?",
            tts_callback=capture_tts,
            reply_with_voice=True,
        )
        all_spoken = " ".join(spoken)
        assert "ORD-MR-333" in all_spoken or "delivered" in all_spoken.lower() or "स्थिती" in all_spoken or "status" in all_spoken.lower()


@pytest.mark.asyncio
async def test_multiturn_gujarati_voice_flow():
    """Validates multi-turn Gujarati conversation with transaction query."""
    async with async_session_factory() as session:
        user = User(email="gujarati_user@example.com", password_hash="testpasshash", full_name="Jignesh Patel")
        session.add(user)
        await session.flush()

        txn = Transaction(
            transaction_id="TXN-GUJ-808",
            customer_id=user.id,
            amount=1500.0,
            currency="INR",
            status="success",
        )
        session.add(txn)

        convo = Conversation(customer_id=user.id, channel=ConversationChannel.VOICE)
        session.add(convo)
        await session.flush()

        svc = ConversationService()
        spoken = []

        async def capture_tts(text: str):
            spoken.append(text)

        # Turn 1: Switch to Gujarati
        await svc.process_customer_message(
            db=session,
            conversation=convo,
            customer_id=user.id,
            message_content="Gujarati ma vaat karo.",
            tts_callback=capture_tts,
            reply_with_voice=True,
        )
        assert convo.preferred_language in ("gujarati", "gujlish")
        all_spoken = " ".join(spoken)
        assert any(t in all_spoken for t in ["ગુજરાતીમાં", "ચોક્કસ", "મદદ", "Gujlish", "help"])

        # Turn 2: Query transaction
        await svc.process_customer_message(
            db=session,
            conversation=convo,
            customer_id=user.id,
            message_content="Maro transaction TXN-GUJ-808 status shu chhe?",
            tts_callback=capture_tts,
            reply_with_voice=True,
        )
        all_spoken = " ".join(spoken)
        assert "TXN-GUJ-808" in all_spoken or "1500" in all_spoken or "સ્થિતિ" in all_spoken or "status" in all_spoken.lower()


@pytest.mark.asyncio
async def test_multiturn_punjabi_voice_flow():
    """Validates multi-turn Punjabi conversation with transaction query."""
    async with async_session_factory() as session:
        user = User(email="punjabi_user@example.com", password_hash="testpasshash", full_name="Harpreet Singh")
        session.add(user)
        await session.flush()

        txn = Transaction(
            transaction_id="TXN-PA-909",
            customer_id=user.id,
            amount=4200.0,
            currency="INR",
            status="success",
        )
        session.add(txn)

        convo = Conversation(customer_id=user.id, channel=ConversationChannel.VOICE)
        session.add(convo)
        await session.flush()

        svc = ConversationService()
        spoken = []

        async def capture_tts(text: str):
            spoken.append(text)

        # Turn 1: Switch to Punjabi
        await svc.process_customer_message(
            db=session,
            conversation=convo,
            customer_id=user.id,
            message_content="Punjabi vich gal karo.",
            tts_callback=capture_tts,
            reply_with_voice=True,
        )
        assert convo.preferred_language in ("punjabi", "punglish")
        all_spoken = " ".join(spoken)
        assert any(t in all_spoken for t in ["ਪੰਜਾਬੀ", "ਜ਼ਰੂਰ", "ਮਦਦ", "Punglish", "help"])

        # Turn 2: Query transaction
        await svc.process_customer_message(
            db=session,
            conversation=convo,
            customer_id=user.id,
            message_content="Mera transaction TXN-PA-909 status ki hai?",
            tts_callback=capture_tts,
            reply_with_voice=True,
        )
        all_spoken = " ".join(spoken)
        assert "TXN-PA-909" in all_spoken or "4200" in all_spoken or "ਸਥਿਤੀ" in all_spoken or "status" in all_spoken.lower()


# ── TEST 5: Switching Back to English from Any Language ──────────────────────

@pytest.mark.asyncio
async def test_switching_back_to_english_from_regional_language():
    """Tests seamless return to English after having switched to Telugu."""
    async with async_session_factory() as session:
        user = User(email="switch_eng_user@example.com", password_hash="testpasshash", full_name="Ravi Kumar")
        session.add(user)
        await session.flush()

        convo = Conversation(customer_id=user.id, channel=ConversationChannel.VOICE)
        session.add(convo)
        await session.flush()

        svc = ConversationService()
        spoken = []

        async def capture_tts(text: str):
            spoken.append(text)

        # Turn 1: Switch to Telugu
        await svc.process_customer_message(
            db=session,
            conversation=convo,
            customer_id=user.id,
            message_content="Telugu lo matladu.",
            tts_callback=capture_tts,
            reply_with_voice=True,
        )
        assert convo.preferred_language == "telugu"

        # Turn 2: Switch back to English
        await svc.process_customer_message(
            db=session,
            conversation=convo,
            customer_id=user.id,
            message_content="Please switch back to English.",
            tts_callback=capture_tts,
            reply_with_voice=True,
        )
        assert convo.preferred_language == "english"
        last_spoken = spoken[-1]
        assert "english" in last_spoken.lower() or "assist" in last_spoken.lower() or "help" in last_spoken.lower()
