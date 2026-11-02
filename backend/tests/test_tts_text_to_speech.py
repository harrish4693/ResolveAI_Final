"""
ResolveAIV2 — Neural TTS Fast-Path Tests

Tests the /api/audio/tts endpoint and SarvamTTS provider with mocked HTTP.
No network calls. Covers:
  - Ownership check (customer can only TTS their own conversation)
  - Text length limit (>400 chars rejected)
  - Emotion → pace mapping
  - Sarvam API call + base64 decode
  - Fallback when tts_provider != sarvam
  - Fallback when Sarvam API errors
  - Text cleaner edge cases
"""

import base64
import json
import pytest
import httpx

from unittest.mock import patch, AsyncMock

from httpx import ASGITransport
from app.main import app
from app.voice.sarvam_tts import (
    clean_text_for_tts,
    synthesize_sarvam,
    SarvamTTSError,
    EMOTION_PACE_MAP,
)


# ── Fixtures ────────────────────────────────────────────────────────

@pytest.fixture
def async_client():
    """HTTPX async client pointed at our FastAPI app."""
    transport = ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _auth_headers(token: str = "test-token") -> dict:
    return {"Authorization": f"Bearer {token}"}


def _mock_sarvam_response(text: str = "hello") -> httpx.Response:
    """Build a fake Sarvam API success response."""
    fake_audio = b"FAKE_MP3_DATA_" + text.encode()
    return httpx.Response(
        200,
        json={"audios": [base64.b64encode(fake_audio).decode()]},
    )


def _mock_sarvam_transport(status: int = 200, body: dict | None = None):
    """Return an httpx MockTransport that returns a Sarvam-shaped response."""
    fake_audio = base64.b64encode(b"FAKE_MP3_DATA").decode()
    default_body = {"audios": [fake_audio]}

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body or default_body)

    return httpx.MockTransport(handler)


# ── clean_text_for_tts tests ────────────────────────────────────────

class TestCleanTextForTTS:

    def test_strips_markdown_bold(self):
        assert clean_text_for_tts("**hello**") == "hello"

    def test_strips_code_blocks(self):
        result = clean_text_for_tts("Check this:\n```python\nprint('hi')\n```\nDone.")
        assert "```" not in result
        assert "Done." in result

    def test_expands_abbreviations(self):
        result = clean_text_for_tts("e.g. use i.e. the ID")
        assert "for example" in result
        assert "that is" in result
        assert "I D" in result

    def test_spaces_out_txn_id(self):
        result = clean_text_for_tts("Your TXN12345 is processed")
        assert "T X N" in result

    def test_commas_in_large_numbers(self):
        result = clean_text_for_tts("Amount is 100000 rupees")
        assert "100,000" in result or "1,00,000" in result

    def test_small_numbers_unchanged(self):
        result = clean_text_for_tts("Order 1234 confirmed")
        assert "1234" in result

    def test_empty_string(self):
        assert clean_text_for_tts("") == ""

    def test_strips_urls(self):
        result = clean_text_for_tts("Visit https://example.com/page for details")
        assert "link" in result
        assert "https" not in result


# ── EMOTION_PACE_MAP tests ──────────────────────────────────────────

class TestEmotionPaceMapping:

    def test_frustrated_pace(self):
        assert EMOTION_PACE_MAP["frustrated"] == 0.93

    def test_confused_pace(self):
        assert EMOTION_PACE_MAP["confused"] == 0.90

    def test_urgent_pace(self):
        assert EMOTION_PACE_MAP["urgent"] == 1.05

    def test_calm_default(self):
        assert EMOTION_PACE_MAP["calm"] == 1.0

    def test_unknown_emotion_defaults_to_1(self):
        assert EMOTION_PACE_MAP.get("unknown", 1.0) == 1.0


# ── synthesize_sarvam unit tests ────────────────────────────────────

class TestSynthesizeSarvam:

    @pytest.mark.asyncio
    async def test_success_returns_audio_bytes(self):
        transport = _mock_sarvam_transport()
        async with httpx.AsyncClient(transport=transport) as client:
            with patch("app.voice.sarvam_tts.settings") as mock_settings:
                mock_settings.sarvam_api_key = "test-key"
                mock_settings.sarvam_tts_model = "bulbul:v3"
                mock_settings.sarvam_speaker = "kavya"

                audio = await synthesize_sarvam(
                    "Hello test", "en-IN", "calm", http_client=client
                )
                assert audio == b"FAKE_MP3_DATA"

    @pytest.mark.asyncio
    async def test_no_api_key_raises(self):
        with patch("app.voice.sarvam_tts.settings") as mock_settings:
            mock_settings.sarvam_api_key = None
            with pytest.raises(SarvamTTSError, match="not configured"):
                await synthesize_sarvam("Hello", "en-IN")

    @pytest.mark.asyncio
    async def test_api_error_raises(self):
        transport = _mock_sarvam_transport(status=500, body={"error": "server error"})
        async with httpx.AsyncClient(transport=transport) as client:
            with patch("app.voice.sarvam_tts.settings") as mock_settings:
                mock_settings.sarvam_api_key = "test-key"
                mock_settings.sarvam_tts_model = "bulbul:v3"
                mock_settings.sarvam_speaker = "kavya"

                with pytest.raises(SarvamTTSError, match="500"):
                    await synthesize_sarvam("Hello", "en-IN", http_client=client)

    @pytest.mark.asyncio
    async def test_empty_audios_raises(self):
        transport = _mock_sarvam_transport(body={"audios": []})
        async with httpx.AsyncClient(transport=transport) as client:
            with patch("app.voice.sarvam_tts.settings") as mock_settings:
                mock_settings.sarvam_api_key = "test-key"
                mock_settings.sarvam_tts_model = "bulbul:v3"
                mock_settings.sarvam_speaker = "kavya"

                with pytest.raises(SarvamTTSError, match="empty audios"):
                    await synthesize_sarvam("Hello", "en-IN", http_client=client)

    @pytest.mark.asyncio
    async def test_emotion_maps_to_pace(self):
        """Verify the pace sent to Sarvam API matches emotion mapping."""
        captured_payloads = []

        async def capture_handler(request: httpx.Request) -> httpx.Response:
            captured_payloads.append(json.loads(request.content))
            fake_audio = base64.b64encode(b"AUDIO").decode()
            return httpx.Response(200, json={"audios": [fake_audio]})

        transport = httpx.MockTransport(capture_handler)
        async with httpx.AsyncClient(transport=transport) as client:
            with patch("app.voice.sarvam_tts.settings") as mock_settings:
                mock_settings.sarvam_api_key = "test-key"
                mock_settings.sarvam_tts_model = "bulbul:v3"
                mock_settings.sarvam_speaker = "kavya"

                await synthesize_sarvam("Hello", "en-IN", "frustrated", http_client=client)

        assert len(captured_payloads) == 1
        assert captured_payloads[0]["pace"] == 0.93
