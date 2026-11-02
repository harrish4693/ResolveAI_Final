"""
ResolveAI V2 — Unified Speech-to-Text (STT) Test Suite
======================================================
Comprehensive automated verification for:
1. Centralized STT capability registry completeness across all 22 scheduled Indian languages + English.
2. Provider language code resolution (e.g. Odia normalization to 'od-IN', Kanglish/Tenglish normalization).
3. STT prompt bias elimination (neutral multi-lingual prompt, language-specific domain guidance without Tanglish poisoning).
4. Audio duration parsing and 30-second duration enforcement.
5. Saaras v4 STT core transcribe tests (empty audio, auto-detect, modes: translit vs codemix, keyterms injection).
6. HTTP error handling (401, 403, 429, 500, timeout mapping to SarvamSTTError).
7. POST /api/audio/stt endpoint (success, empty file rejected, safe browser fallback).
8. POST /api/audio/livekit/audio-turn endpoint (intelligence pipeline, metadata, idempotency, 30s enforcement, silence ignore, customer isolation).
9. SarvamSTTProvider adapter & factory.
10. Multilingual STT evaluation metrics (WER, CER, entity preservation, Indic script normalization).
"""

import io
import json
import wave
import struct
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient, TimeoutException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.users.models import User
from app.conversations.models import Conversation, ProcessedUtterance
from app.voice.stt_registry import (
    STT_CAPABILITY_REGISTRY,
    get_stt_capability,
    resolve_stt_language_code,
    is_stt_language_supported,
    list_supported_stt_languages,
)
from app.voice.sarvam_stt import (
    transcribe_sarvam,
    build_stt_prompt,
    get_audio_duration_seconds,
    SarvamSTTError,
    MAX_REST_AUDIO_DURATION_SEC,
)
from app.voice.providers import SarvamSTTProvider, get_stt_provider
from scripts.evaluate_multilingual_stt import (
    compute_wer,
    compute_cer,
    check_entity_preservation,
    normalize_text_for_eval,
)


def generate_test_wav(duration_sec: float = 1.0, sample_rate: int = 16000) -> bytes:
    """Generates a valid 16-bit mono PCM WAV in memory."""
    num_samples = int(sample_rate * duration_sec)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        frames = bytearray()
        for i in range(num_samples):
            # 440 Hz square/tone sample
            val = int(32767.0 * 0.1 * (1.0 if (i % 36) < 18 else -1.0))
            frames.extend(struct.pack("<h", val))
        wf.writeframes(frames)
    return buf.getvalue()


# ══════════════════════════════════════════════════════════════════════════════
# Section 1: STT Capability Registry & BCP-47 Resolution
# ══════════════════════════════════════════════════════════════════════════════

def test_stt_capability_registry_all_scheduled_languages():
    """Verify that all 22 scheduled Indian languages + English exist in the STT registry."""
    scheduled_languages = [
        "english",
        "tamil",
        "hindi",
        "kannada",
        "telugu",
        "malayalam",
        "bengali",
        "marathi",
        "gujarati",
        "punjabi",
        "odia",
        "assamese",
        "urdu",
        "sanskrit",
        "kashmiri",
        "sindhi",
        "konkani",
        "manipuri",
        "bodo",
        "dogri",
        "santali",
        "maithili",
        "nepali",
    ]
    for lang in scheduled_languages:
        assert lang in STT_CAPABILITY_REGISTRY, f"Missing scheduled language: {lang}"
        cap = STT_CAPABILITY_REGISTRY[lang]
        assert cap.sarvam_code, f"Missing Sarvam code for {lang}"
        assert cap.bcp47, f"Missing BCP-47 locale for {lang}"
        assert cap.native_script_recognition is True, f"{lang} must support native script recognition"
        assert cap.auto_detection_support is True, f"{lang} must support auto-detection"
        assert "transcribe" in cap.supported_modes, f"{lang} must support transcribe mode"
        assert "translit" in cap.supported_modes, f"{lang} must support translit mode"
        assert "codemix" in cap.supported_modes, f"{lang} must support codemix mode"
        assert "sarvam" in cap.providers, f"{lang} must list sarvam as provider"


def test_stt_capability_lookup_by_aliases_and_bcp47():
    """Verify that registry looks up canonical capabilities by alias, dialect, or locale."""
    # Tanglish / Tamil
    cap_tanglish = get_stt_capability("tanglish")
    assert cap_tanglish is not None
    assert cap_tanglish.canonical_name == "tamil"
    assert cap_tanglish.bcp47 == "ta-IN"

    # Hinglish / Hindi
    cap_hinglish = get_stt_capability("hinglish")
    assert cap_hinglish is not None
    assert cap_hinglish.canonical_name == "hindi"
    assert cap_hinglish.bcp47 == "hi-IN"

    # Kanglish / Kannada
    cap_kanglish = get_stt_capability("kanglish")
    assert cap_kanglish is not None
    assert cap_kanglish.canonical_name == "kannada"
    assert cap_kanglish.bcp47 == "kn-IN"

    # Tenglish / Telugu
    cap_tenglish = get_stt_capability("tenglish")
    assert cap_tenglish is not None
    assert cap_tenglish.canonical_name == "telugu"
    assert cap_tenglish.bcp47 == "te-IN"

    # Odia / Oriya
    cap_odia = get_stt_capability("oriya")
    assert cap_odia is not None
    assert cap_odia.canonical_name == "odia"
    assert cap_odia.sarvam_code == "od-IN"


@pytest.mark.parametrize(
    "raw_input,expected_sarvam_code",
    [
        ("kannada", "kn-IN"),
        ("kn-IN", "kn-IN"),
        ("kn", "kn-IN"),
        ("telugu", "te-IN"),
        ("te-IN", "te-IN"),
        ("malayalam", "ml-IN"),
        ("ml-IN", "ml-IN"),
        ("hindi", "hi-IN"),
        ("hi-IN", "hi-IN"),
        ("hinglish", "hi-IN"),
        ("tamil", "ta-IN"),
        ("ta-IN", "ta-IN"),
        ("tanglish", "ta-IN"),
        ("bengali", "bn-IN"),
        ("bn-IN", "bn-IN"),
        ("marathi", "mr-IN"),
        ("mr-IN", "mr-IN"),
        ("gujarati", "gu-IN"),
        ("gu-IN", "gu-IN"),
        ("punjabi", "pa-IN"),
        ("pa-IN", "pa-IN"),
        ("odia", "od-IN"),
        ("or-IN", "od-IN"),
        ("oriya", "od-IN"),
        ("od-IN", "od-IN"),
        ("assamese", "as-IN"),
        ("as-IN", "as-IN"),
        ("urdu", "ur-IN"),
        ("ur-IN", "ur-IN"),
        ("english", "en-IN"),
        ("en-IN", "en-IN"),
        ("unknown", "unknown"),
        ("auto", "unknown"),
        ("detect", "unknown"),
        ("", "unknown"),
        (None, "unknown"),
    ],
)
def test_resolve_stt_language_code(raw_input, expected_sarvam_code):
    assert resolve_stt_language_code(raw_input, provider="sarvam") == expected_sarvam_code


# ══════════════════════════════════════════════════════════════════════════════
# Section 2: Prompt Bias Elimination & Domain Guidance
# ══════════════════════════════════════════════════════════════════════════════

def test_neutral_prompt_when_language_unknown():
    """Verify that auto-detect ('unknown') prompt is neutral and does not bias toward Tanglish."""
    prompt = build_stt_prompt("unknown")
    assert prompt is not None
    assert "Speaker mixes Tamil" not in prompt
    assert "Tanglish" not in prompt
    assert "Indian customer support" in prompt
    assert "ORD-101" in prompt


def test_language_specific_prompt_generation():
    """Verify that Kannada, Telugu, Hindi, etc. generate language-specific prompts."""
    # Kannada
    kn_prompt = build_stt_prompt("kn-IN")
    assert "Kannada" in kn_prompt
    assert "Tamil" not in kn_prompt
    assert "Tanglish" not in kn_prompt
    assert "ORD-101" in kn_prompt

    # Telugu
    te_prompt = build_stt_prompt("te-IN")
    assert "Telugu" in te_prompt
    assert "Tamil" not in te_prompt
    assert "ORD-101" in te_prompt

    # Hindi
    hi_prompt = build_stt_prompt("hi-IN")
    assert "Hindi" in hi_prompt
    assert "Tamil" not in hi_prompt
    assert "ORD-101" in hi_prompt

    # Bengali
    bn_prompt = build_stt_prompt("bn-IN")
    assert "Bengali" in bn_prompt
    assert "Tamil" not in bn_prompt

    # Tamil
    ta_prompt = build_stt_prompt("ta-IN")
    assert "Tamil" in ta_prompt


# ══════════════════════════════════════════════════════════════════════════════
# Section 3: Audio Duration Parsing & Limit Enforcement
# ══════════════════════════════════════════════════════════════════════════════

def test_audio_duration_calculation():
    """Verify WAV duration parsing accurately measures length."""
    wav_1s = generate_test_wav(1.0)
    assert abs(get_audio_duration_seconds(wav_1s) - 1.0) < 0.05

    wav_5s = generate_test_wav(5.0)
    assert abs(get_audio_duration_seconds(wav_5s) - 5.0) < 0.05

    assert get_audio_duration_seconds(b"") == 0.0
    assert get_audio_duration_seconds(b"random-non-wav-bytes") is None


def test_get_audio_duration_seconds():
    wav_2s = generate_test_wav(2.5, 16000)
    dur = get_audio_duration_seconds(wav_2s)
    assert dur is not None
    assert round(dur, 1) == 2.5


@pytest.mark.asyncio
async def test_transcribe_sarvam_empty_audio_raises():
    """Empty audio payload must raise SarvamSTTError."""
    with pytest.raises(SarvamSTTError, match="cannot be empty"):
        await transcribe_sarvam(b"")


@pytest.mark.asyncio
async def test_empty_audio_raises_error():
    with pytest.raises(SarvamSTTError) as exc_info:
        await transcribe_sarvam(b"")
    assert "cannot be empty" in str(exc_info.value)


@pytest.mark.asyncio
async def test_transcribe_sarvam_duration_exceeds_limit_raises():
    """Audio exceeding 30-second documented REST limit must raise SarvamSTTError."""
    wav_31s = generate_test_wav(31.5)
    with pytest.raises(SarvamSTTError, match="exceeds documented 30"):
        await transcribe_sarvam(wav_31s)


@pytest.mark.asyncio
async def test_rest_duration_limit_enforcement():
    """Verify that audio exceeding 30 seconds raises SarvamSTTError."""
    long_wav = generate_test_wav(32.0, 16000)
    with pytest.raises(SarvamSTTError) as exc_info:
        await transcribe_sarvam(long_wav, language_code="kn-IN")
    assert "exceeds documented 30.0s limit" in str(exc_info.value)


# ══════════════════════════════════════════════════════════════════════════════
# Section 4: Saaras v4 STT Core Transcription & Modes
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_transcribe_sarvam_missing_api_key_raises():
    """Missing SARVAM_API_KEY must raise SarvamSTTError."""
    wav_bytes = generate_test_wav(1.0)
    orig_key = settings.sarvam_api_key
    try:
        settings.sarvam_api_key = None
        with pytest.raises(SarvamSTTError, match="not configured"):
            await transcribe_sarvam(wav_bytes)
    finally:
        settings.sarvam_api_key = orig_key


@pytest.mark.asyncio
async def test_transcribe_sarvam_success_with_auto_lang_and_keyterms():
    """Verify Saaras v4 handles language_code='unknown', keyterms injection, and response parsing."""
    wav_bytes = generate_test_wav(2.0)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "transcript": "enaku refund status theriyanum",
        "language_code": "ta-IN",
        "language_probability": 0.94,
        "request_id": "req_mock_12345",
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        result = await transcribe_sarvam(
            audio_bytes=wav_bytes,
            language_code="unknown",
            mode="translit",
            keyterms=["ResolveAI", "refund", "ORD-1234"],
        )

        assert result["transcript"] == "enaku refund status theriyanum"
        assert result["language_code"] == "ta-IN"
        assert result["confidence"] == 0.94
        assert result["mode"] == "translit"
        assert result["request_id"] == "req_mock_12345"
        assert result["provider"] == "sarvam"

        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        data_sent = kwargs["data"]
        assert data_sent["model"] == "saaras:v4"
        assert data_sent["mode"] == "translit"
        assert data_sent["language_code"] == "unknown"
        assert "keyterms" in data_sent
        assert json.loads(data_sent["keyterms"]) == ["ResolveAI", "refund", "ORD-1234"]


@pytest.mark.asyncio
async def test_transcribe_sarvam_codemix_mode():
    """Verify codemix mode produces native script Indic words + English."""
    wav_bytes = generate_test_wav(1.5)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "transcript": "எனக்கு refund வேணும்",
        "language_code": "ta-IN",
        "language_probability": 0.96,
        "request_id": "req_codemix_99",
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        result = await transcribe_sarvam(
            audio_bytes=wav_bytes,
            language_code="unknown",
            mode="codemix",
        )

        assert result["transcript"] == "எனக்கு refund வேணும்"
        assert result["language_code"] == "ta-IN"
        assert result["mode"] == "codemix"


@pytest.mark.asyncio
async def test_sarvam_transcribe_mock_success():
    """Verify successful transcription request construction and metadata extraction."""
    wav_bytes = generate_test_wav(1.0, 16000)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "transcript": "ನನ್ನ ಆರ್ಡರ್ ORD-101 ಎಲ್ಲಿ?",
        "language_code": "kn-IN",
        "language_probability": 0.96,
        "request_id": "req_mock_12345",
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        result = await transcribe_sarvam(
            audio_bytes=wav_bytes,
            language_code="kannada",
            mode="codemix",
        )

        assert result["transcript"] == "ನನ್ನ ಆರ್ಡರ್ ORD-101 ಎಲ್ಲಿ?"
        assert result["language_code"] == "kn-IN"
        assert result["confidence"] == 0.96
        assert result["mode"] == "codemix"
        assert result["provider"] == "sarvam"

        call_kwargs = mock_post.call_args[1]
        data = call_kwargs["data"]
        assert data["language_code"] == "kn-IN"
        assert data["mode"] == "codemix"
        assert "Kannada" in data["prompt"]


# ══════════════════════════════════════════════════════════════════════════════
# Section 5: HTTP Error Handling & Resilience
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_transcribe_sarvam_http_errors():
    """Verify HTTP 401, 429, 500 and timeout map to clean SarvamSTTError."""
    wav_bytes = generate_test_wav(1.0)

    for status_code, expected_err in [
        (401, "authentication failed"),
        (429, "rate limit exceeded"),
        (500, "Sarvam STT API error"),
    ]:
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_resp.text = "Error detail"
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            with pytest.raises(SarvamSTTError, match=expected_err):
                await transcribe_sarvam(wav_bytes)

    # Test timeout
    with patch("httpx.AsyncClient.post", side_effect=TimeoutException("Timed out")):
        with pytest.raises(SarvamSTTError, match="timed out"):
            await transcribe_sarvam(wav_bytes)


# ══════════════════════════════════════════════════════════════════════════════
# Section 6: POST /api/audio/stt Endpoint Tests
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_post_stt_endpoint_success(async_client: AsyncClient, auth_headers_a: dict):
    """Test standard STT upload with automatic language detection."""
    wav_bytes = generate_test_wav(1.0)
    with patch("app.voice.sarvam_stt.transcribe_sarvam", new_callable=AsyncMock) as mock_ts:
        mock_ts.return_value = {
            "transcript": "mera parcel deliver nahi hua",
            "language_code": "hi-IN",
            "confidence": 0.93,
            "mode": "translit",
            "provider": "sarvam",
        }

        files = {"file": ("turn.wav", wav_bytes, "audio/wav")}
        data = {
            "language_code": "unknown",
            "mode": "translit",
            "keyterms": json.dumps(["parcel", "delivery"]),
        }

        resp = await async_client.post(
            "/api/audio/stt",
            files=files,
            data=data,
            headers=auth_headers_a,
        )

        assert resp.status_code == 200
        res_data = resp.json()
        assert res_data["transcript"] == "mera parcel deliver nahi hua"
        assert res_data["language_code"] == "hi-IN"
        assert res_data["confidence"] == 0.93


@pytest.mark.asyncio
async def test_post_stt_empty_file_rejected(async_client: AsyncClient, auth_headers_a: dict):
    """Uploading empty file returns HTTP 400."""
    files = {"file": ("empty.wav", b"", "audio/wav")}
    resp = await async_client.post(
        "/api/audio/stt",
        files=files,
        headers=auth_headers_a,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_post_stt_error_returns_browser_fallback(async_client: AsyncClient, auth_headers_a: dict):
    """Provider failure gracefully returns fallback='browser' flag."""
    wav_bytes = generate_test_wav(1.0)
    with patch("app.voice.sarvam_stt.transcribe_sarvam", side_effect=SarvamSTTError("Simulated upstream error")):
        files = {"file": ("audio.wav", wav_bytes, "audio/wav")}
        resp = await async_client.post(
            "/api/audio/stt",
            files=files,
            headers=auth_headers_a,
        )
        assert resp.status_code == 200
        res = resp.json()
        assert res["fallback"] == "browser"
        assert "Simulated upstream error" in res["reason"]


# ══════════════════════════════════════════════════════════════════════════════
# Section 7: POST /api/audio/livekit/audio-turn Endpoint Tests
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_audio_turn_success_and_intelligence_pipeline(
    async_client: AsyncClient,
    auth_headers_a: dict,
    test_user_a: User,
    db_session: AsyncSession,
):
    """Verify live microphone audio turn is transcribed and processed through the intelligence pipeline."""
    convo = Conversation(
        customer_id=test_user_a.id,
        channel="voice",
    )
    db_session.add(convo)
    await db_session.commit()
    await db_session.refresh(convo)

    wav_bytes = generate_test_wav(2.0)
    utterance_id = "test_audio_turn_001"

    with patch("app.voice.sarvam_stt.transcribe_sarvam", new_callable=AsyncMock) as mock_ts:
        mock_ts.return_value = {
            "transcript": "Where is my order ORD12345",
            "language_code": "en-IN",
            "confidence": 0.95,
            "mode": "translit",
            "request_id": "req_audio_turn_1",
            "provider": "sarvam",
        }

        files = {"file": ("mic.wav", wav_bytes, "audio/wav")}
        data = {
            "conversation_id": str(convo.id),
            "utterance_id": utterance_id,
            "language_code": "unknown",
            "mode": "translit",
        }

        resp = await async_client.post(
            "/api/audio/livekit/audio-turn",
            files=files,
            data=data,
            headers=auth_headers_a,
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "processed"
        assert body["transcript"] == "Where is my order ORD12345"
        assert body["stt_language_code"] == "en-IN"
        assert body["stt_confidence"] == 0.95
        assert body["stt_mode"] == "translit"
        assert body["ai_response"] is not None


@pytest.mark.asyncio
async def test_audio_turn_duplicate_rejection_idempotency(
    async_client: AsyncClient,
    auth_headers_a: dict,
    test_user_a: User,
    db_session: AsyncSession,
):
    """Submitting the identical utterance_id must be rejected with HTTP 409 Conflict."""
    convo = Conversation(
        customer_id=test_user_a.id,
        channel="voice",
    )
    db_session.add(convo)
    await db_session.commit()
    await db_session.refresh(convo)

    wav_bytes = generate_test_wav(1.0)
    utterance_id = "duplicate_audio_turn_test_999"

    with patch("app.voice.sarvam_stt.transcribe_sarvam", new_callable=AsyncMock) as mock_ts:
        mock_ts.return_value = {
            "transcript": "refund eppo varum",
            "language_code": "ta-IN",
            "confidence": 0.92,
            "mode": "translit",
        }

        files = {"file": ("mic.wav", wav_bytes, "audio/wav")}
        data = {
            "conversation_id": str(convo.id),
            "utterance_id": utterance_id,
        }

        # 1. First submission succeeds
        first_resp = await async_client.post(
            "/api/audio/livekit/audio-turn",
            files=files,
            data=data,
            headers=auth_headers_a,
        )
        assert first_resp.status_code == 200

        # 2. Second submission with same utterance_id is rejected with 409
        files2 = {"file": ("mic.wav", wav_bytes, "audio/wav")}
        second_resp = await async_client.post(
            "/api/audio/livekit/audio-turn",
            files=files2,
            data=data,
            headers=auth_headers_a,
        )
        assert second_resp.status_code == 409
        assert "already been processed" in second_resp.json()["detail"]


@pytest.mark.asyncio
async def test_audio_turn_exceeding_30s_rejected(
    async_client: AsyncClient,
    auth_headers_a: dict,
    test_user_a: User,
    db_session: AsyncSession,
):
    """Audio longer than 30 seconds is rejected with HTTP 400 Bad Request."""
    convo = Conversation(customer_id=test_user_a.id, channel="voice")
    db_session.add(convo)
    await db_session.commit()
    await db_session.refresh(convo)

    wav_32s = generate_test_wav(32.0)
    files = {"file": ("long.wav", wav_32s, "audio/wav")}
    data = {
        "conversation_id": str(convo.id),
        "utterance_id": "long_turn_1",
    }

    resp = await async_client.post(
        "/api/audio/livekit/audio-turn",
        files=files,
        data=data,
        headers=auth_headers_a,
    )
    assert resp.status_code == 400
    assert "exceeds documented 30-second limit" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_audio_turn_empty_speech_ignored(
    async_client: AsyncClient,
    auth_headers_a: dict,
    test_user_a: User,
    db_session: AsyncSession,
):
    """When STT recognizes only silence / empty string, return status='ignored'."""
    convo = Conversation(customer_id=test_user_a.id, channel="voice")
    db_session.add(convo)
    await db_session.commit()
    await db_session.refresh(convo)

    wav_bytes = generate_test_wav(1.0)
    with patch("app.voice.sarvam_stt.transcribe_sarvam", new_callable=AsyncMock) as mock_ts:
        mock_ts.return_value = {
            "transcript": "",
            "language_code": "unknown",
            "confidence": 0.0,
            "mode": "translit",
        }

        files = {"file": ("silence.wav", wav_bytes, "audio/wav")}
        data = {
            "conversation_id": str(convo.id),
            "utterance_id": "silence_turn_1",
        }

        resp = await async_client.post(
            "/api/audio/livekit/audio-turn",
            files=files,
            data=data,
            headers=auth_headers_a,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"


@pytest.mark.asyncio
async def test_audio_turn_unauthorized_customer_forbidden(
    async_client: AsyncClient,
    auth_headers_b: dict,
    test_user_a: User,
    db_session: AsyncSession,
):
    """Customer B cannot submit audio turns to Customer A's conversation (403)."""
    convo = Conversation(customer_id=test_user_a.id, channel="voice")
    db_session.add(convo)
    await db_session.commit()
    await db_session.refresh(convo)

    wav_bytes = generate_test_wav(1.0)
    with patch("app.voice.sarvam_stt.transcribe_sarvam", new_callable=AsyncMock) as mock_ts:
        mock_ts.return_value = {"transcript": "hello", "language_code": "en-IN"}
        files = {"file": ("mic.wav", wav_bytes, "audio/wav")}
        data = {
            "conversation_id": str(convo.id),
            "utterance_id": "unauth_turn_1",
        }

        resp = await async_client.post(
            "/api/audio/livekit/audio-turn",
            files=files,
            data=data,
            headers=auth_headers_b,
        )
        assert resp.status_code == 403


# ══════════════════════════════════════════════════════════════════════════════
# Section 8: SarvamSTTProvider Adapter & Factory
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_sarvam_stt_provider_transcribe_bytes():
    """Verify SarvamSTTProvider transcribe_bytes delegates properly."""
    provider = SarvamSTTProvider(language_code="unknown", mode="translit")
    wav_bytes = generate_test_wav(1.0)

    with patch("app.voice.sarvam_stt.transcribe_sarvam", new_callable=AsyncMock) as mock_ts:
        mock_ts.return_value = {
            "transcript": "enakku refund pannanum",
            "language_code": "ta-IN",
            "confidence": 0.91,
        }

        res = await provider.transcribe_bytes(wav_bytes)
        assert res["transcript"] == "enakku refund pannanum"
        assert res["language_code"] == "ta-IN"


def test_get_stt_provider_factory():
    """Verify factory initializes Sarvam provider with configured settings."""
    provider = get_stt_provider("sarvam")
    assert isinstance(provider, SarvamSTTProvider)
    assert provider.mode in ("translit", "codemix")


@pytest.mark.asyncio
async def test_sarvam_provider_wrapper():
    """Verify SarvamSTTProvider wrapper delegates correctly to transcribe_sarvam."""
    provider = SarvamSTTProvider(language_code="te-IN", mode="translit")
    assert provider.language_code == "te-IN"
    assert provider.mode == "translit"

    wav_bytes = generate_test_wav(1.0, 16000)
    mock_resp = {
        "transcript": "Naa order ORD-202 tracking status",
        "language_code": "te-IN",
        "confidence": 0.94,
        "mode": "translit",
        "provider": "sarvam",
    }
    with patch("app.voice.sarvam_stt.transcribe_sarvam", new_callable=AsyncMock) as mock_trans:
        mock_trans.return_value = mock_resp
        res = await provider.transcribe_bytes(wav_bytes)
        assert res["transcript"] == "Naa order ORD-202 tracking status"
        assert res["language_code"] == "te-IN"


# ══════════════════════════════════════════════════════════════════════════════
# Section 9: Evaluation Metrics (WER, CER, Entity Preservation, Normalization)
# ══════════════════════════════════════════════════════════════════════════════

def test_metrics_calculation():
    # Exact match: WER 0.0, CER 0.0
    ref = "I need refund for order ORD-101"
    hyp = "I need refund for order ORD-101"
    assert compute_wer(ref, hyp) == 0.0
    assert compute_cer(ref, hyp) == 0.0

    # 1 word changed: 1 / 7 words = 0.142857
    hyp_err = "I need exchange for order ORD-101"
    assert round(compute_wer(ref, hyp_err), 2) == 0.14

    # Entity preservation
    matched, total = check_entity_preservation(ref, hyp_err)
    assert matched == 1
    assert total == 1

    # Entity corrupted
    hyp_corrupted = "I need refund for order unknown"
    matched_corrupt, total_corrupt = check_entity_preservation(ref, hyp_corrupted)
    assert matched_corrupt == 0
    assert total_corrupt == 1


def test_indic_script_normalization():
    tamil_ref = "என் ஆர்டர் ORD-101 இன்னும் வரவில்லை"
    norm = normalize_text_for_eval(tamil_ref)
    assert "ஆர்டர்" in norm
    assert "ord" in norm
    assert "101" in norm

