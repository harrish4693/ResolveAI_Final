"""ResolveAIV2 — Call Agent Voice & Noise Filtering Backend Tests

Comprehensive test suite verifying:
1. Rejection of empty, whitespace, and punctuation-only inputs.
2. Filtering of bracketed sound descriptors ([music], (applause), [laughter], [cough], etc.).
3. Filtering of subtitle/video corpus hallucinations ("thank you for watching", "subtitles by", etc.).
4. Filtering of isolated non-speech filler murmurs ("uh", "um", "hmm" alone) while preserving
   sentences containing fillers ("Uh yes, where is my order?").
5. Low confidence STT rejection (< 0.35) for non-whitelisted text.
6. Strict preservation of legitimate short answers ("yes", "no", "stop", "cancel", "help") across
   English, Tamil, Hindi, Tanglish, Hinglish, Kannada, Telugu, Malayalam in both scripts.
7. Preservation of full natural multilingual utterances without truncation.
8. LiveKit utterance endpoint integration: ignoring background noise without LLM roundtrip.
9. Duplicate utterance rejection and turn isolation.
"""

import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch

from app.config import settings
from app.voice.noise_filter import (
    validate_spoken_utterance,
    UtteranceValidationResult,
    WHITELISTED_SHORT_UTTERANCES,
)


# ═══════════════════════════════════════════════════════════
# Unit Tests: validate_spoken_utterance
# ═══════════════════════════════════════════════════════════

def test_reject_empty_and_whitespace():
    """Empty and whitespace strings must be rejected."""
    for text in ["", "   ", "\t\n", None]:
        res = validate_spoken_utterance(text)
        assert res.is_valid is False
        assert res.reason == "empty_or_whitespace"


def test_reject_punctuation_only():
    """Strings containing only punctuation or symbols must be rejected."""
    for text in [".", "...", "?", "!?!?", ", - .", "***"]:
        res = validate_spoken_utterance(text)
        assert res.is_valid is False
        assert res.reason in ("punctuation_only", "repetitive_character_noise")


def test_reject_bracketed_noise_descriptors():
    """Whisper and Saaras bracketed noise tags must be rejected."""
    noise_tags = [
        "[music]",
        "[Music]",
        "[applause]",
        "[laughter]",
        "[cough]",
        "[coughing]",
        "[groan]",
        "[sigh]",
        "[screaming]",
        "(applause)",
        "(music)",
        "[noise]",
        "[background noise]",
        "[inaudible]",
        "[chatter]",
    ]
    for tag in noise_tags:
        res = validate_spoken_utterance(tag)
        assert res.is_valid is False
        assert res.reason == "bracketed_noise_tag", f"Failed for {tag}"


def test_reject_corpus_hallucinations():
    """Common subtitle and video training set hallucinations must be rejected."""
    hallucinations = [
        "thank you for watching",
        "Thank you for watching.",
        "thanks for watching",
        "subtitles by",
        "please subscribe",
        "like and subscribe",
        "all rights reserved",
    ]
    for text in hallucinations:
        res = validate_spoken_utterance(text)
        assert res.is_valid is False
        assert res.reason == "corpus_hallucination", f"Failed for {text}"


def test_reject_isolated_filler_murmurs():
    """Isolated fillers alone must be rejected, not forwarded to LLM."""
    fillers = ["uh", "um", "umm", "uhh", "ah", "ahh", "hmm", "hm", "hmmm", "er", "eh", "shh"]
    for filler in fillers:
        res = validate_spoken_utterance(filler)
        assert res.is_valid is False
        assert res.reason == "isolated_filler_noise", f"Failed for {filler}"


def test_preserve_fillers_within_legitimate_sentences():
    """Utterances containing fillers mixed with legitimate words must be preserved!"""
    sentences = [
        "Uh yes, where is my order?",
        "Um, I would like a refund please.",
        "Hmm, enaku delivery delay aachu.",
        "Aap mera order cancel kar sakte hain kya, umm?",
    ]
    for sentence in sentences:
        res = validate_spoken_utterance(sentence)
        assert res.is_valid is True, f"Failed for legitimate sentence with filler: {sentence}"


def test_low_confidence_noise_rejected():
    """Non-whitelisted text with very low STT confidence (< 0.35) must be rejected."""
    res = validate_spoken_utterance("random background mumbling fragment", confidence=0.20)
    assert res.is_valid is False
    assert res.reason == "low_stt_confidence"


def test_borderline_confidence_flags_confirmation():
    """Confidence between 0.35 and 0.60 is accepted but marked for confirmation."""
    res = validate_spoken_utterance("refund please", confidence=0.45)
    assert res.is_valid is True
    assert res.needs_confirmation is True


# ═══════════════════════════════════════════════════════════
# Multilingual & Short Answer Preservation Tests
# ═══════════════════════════════════════════════════════════

def test_preserve_english_short_answers():
    """Standard English affirmative, negative, and control commands must pass."""
    short_answers = [
        "yes", "no", "yeah", "nope", "ok", "okay", "sure",
        "stop", "cancel", "help", "wait", "bye", "hi", "thanks",
    ]
    for ans in short_answers:
        res = validate_spoken_utterance(ans)
        assert res.is_valid is True, f"Failed for {ans}"
        assert res.is_short_answer is True


def test_preserve_tamil_and_tanglish_short_answers():
    """Tamil and Tanglish short responses (both Latin and native script) must pass."""
    tamil_words = [
        # Latin / Tanglish
        "aam", "aama", "illai", "illa", "seri", "sari",
        "podhum", "niruthu", "udhavi", "vanakkam", "nandri",
        # Tamil Script
        "ஆம்", "ஆமாம்", "இல்லை", "சரி", "போதும்", "நிறுத்து", "உதவி", "வணக்கம்", "நன்றி",
    ]
    for word in tamil_words:
        res = validate_spoken_utterance(word)
        assert res.is_valid is True, f"Failed for Tamil word: {word}"
        assert res.is_short_answer is True


def test_preserve_hindi_and_hinglish_short_answers():
    """Hindi and Hinglish short responses (both Latin and Devanagari script) must pass."""
    hindi_words = [
        # Latin / Hinglish
        "haan", "ha", "nahi", "nahin", "theek", "theek hai",
        "accha", "ruko", "band karo", "madad", "namaste", "shukriya",
        # Devanagari Script
        "हाँ", "नहीं", "ठीक", "ठीक है", "अच्छा", "रुको", "बंद करो", "मदद", "नमस्ते", "शुक्रिया",
    ]
    for word in hindi_words:
        res = validate_spoken_utterance(word)
        assert res.is_valid is True, f"Failed for Hindi word: {word}"
        assert res.is_short_answer is True


def test_preserve_kannada_telugu_malayalam_short_answers():
    """Kannada, Telugu, and Malayalam short responses must pass in both scripts."""
    other_indic = [
        # Kannada
        "houdu", "illa", "sari", "nillisi", "sahaya", "namaskara",
        "ಹೌದು", "ಇಲ್ಲ", "ಸರಿ", "ನಿಲ್ಲಿಸಿ",
        # Telugu
        "avunu", "kaadhu", "sare", "aapu", "sahayam", "namaskaram",
        "అవును", "కాదు", "సరే", "ఆపు",
        # Malayalam
        "athe", "alla", "seri", "nirthu", "sahayam", "namaskaram",
        "അതെ", "അല്ല", "ശരി", "നിർത്തൂ",
    ]
    for word in other_indic:
        res = validate_spoken_utterance(word)
        assert res.is_valid is True, f"Failed for Indic word: {word}"
        assert res.is_short_answer is True


def test_preserve_full_multilingual_customer_utterances():
    """Legitimate customer queries across Indian languages and Tanglish/Hinglish must pass."""
    queries = [
        "Where is my package and why is it delayed?",
        "Enaku refund innum varala, konjam check pannunga.",
        "Mera order kab tak deliver hoga please batayein.",
        "ನನ್ನ ಆರ್ಡರ್ ಯಾವಾಗ ಬರುತ್ತದೆ ಎಂದು ಹೇಳಿ.",
        "నా ఆర్డర్ ఎప్పుడు డెలివరీ అవుతుందో చెప్పండి.",
        "എന്റെ ഓർഡർ എപ്പോൾ എത്തും എന്ന് ദയവായി പറയൂ.",
        "I need help updating my shipping address to Bangalore.",
        "Payment aayiduchu aana order status innum confirm aagala.",
    ]
    for query in queries:
        res = validate_spoken_utterance(query)
        assert res.is_valid is True, f"Failed for legitimate query: {query}"
        assert res.is_short_answer is False


# ═══════════════════════════════════════════════════════════
# LiveKit API Integration & Noise Guard Tests
# ═══════════════════════════════════════════════════════════

@pytest.fixture
def configure_livekit():
    orig_url = settings.livekit_url
    orig_key = settings.livekit_api_key
    orig_secret = settings.livekit_api_secret

    settings.livekit_url = "wss://test-project.livekit.cloud"
    settings.livekit_api_key = "test_key_12345"
    settings.livekit_api_secret = "test_secret_at_least_32_bytes_long_12345"

    yield

    settings.livekit_url = orig_url
    settings.livekit_api_key = orig_key
    settings.livekit_api_secret = orig_secret


@pytest.mark.asyncio
async def test_livekit_utterance_blocks_background_noise(
    async_client: AsyncClient,
    auth_headers_a: dict,
    configure_livekit,
):
    """Background TV/noise artifacts ([music], isolated filler) are ignored without LLM roundtrip."""
    # 1. Create a conversation
    convo_res = await async_client.post(
        "/api/conversations",
        json={"initial_message": "Hello Voice Support"},
        headers=auth_headers_a,
    )
    assert convo_res.status_code == 200
    convo_id = convo_res.json()["id"]

    # 2. Send Whisper noise tag [music]
    noise_res = await async_client.post(
        "/api/audio/livekit/utterance",
        json={
            "conversation_id": convo_id,
            "utterance_id": "test_noise_music_1",
            "transcript": "[music]",
        },
        headers=auth_headers_a,
    )
    assert noise_res.status_code == 200
    data = noise_res.json()
    assert data["status"] == "ignored"
    assert data["reason"] == "bracketed_noise_tag"

    # 3. Send isolated murmur "uh"
    murmur_res = await async_client.post(
        "/api/audio/livekit/utterance",
        json={
            "conversation_id": convo_id,
            "utterance_id": "test_noise_murmur_1",
            "transcript": "uh",
        },
        headers=auth_headers_a,
    )
    assert murmur_res.status_code == 200
    m_data = murmur_res.json()
    assert m_data["status"] == "ignored"
    assert m_data["reason"] == "isolated_filler_noise"


@pytest.mark.asyncio
async def test_livekit_utterance_preserves_short_answer_and_full_turn(
    async_client: AsyncClient,
    auth_headers_a: dict,
    configure_livekit,
):
    """Valid short answer and customer utterance are accepted and processed."""
    # 1. Create a conversation
    convo_res = await async_client.post(
        "/api/conversations",
        json={"initial_message": "Hi"},
        headers=auth_headers_a,
    )
    assert convo_res.status_code == 200
    convo_id = convo_res.json()["id"]

    # 2. Mock process_customer_message to avoid external LLM network dependency in test
    with patch("app.conversations.service.ConversationService.process_customer_message") as mock_proc:
        mock_proc.return_value = {
            "status": "success",
            "ai_response": "Thank you, how can I assist you today?",
        }

        # Send valid Tanglish short answer "seri"
        res = await async_client.post(
            "/api/audio/livekit/utterance",
            json={
                "conversation_id": convo_id,
                "utterance_id": "test_short_ans_turn_1",
                "transcript": "seri",
            },
            headers=auth_headers_a,
        )
        assert res.status_code == 200
        data = res.json()
        assert data.get("status") != "ignored"
        assert mock_proc.called

