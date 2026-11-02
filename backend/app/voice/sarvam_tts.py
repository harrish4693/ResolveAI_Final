"""
ResolveAIV2 — Sarvam Neural TTS Provider (Fast-Path)

Calls POST https://api.sarvam.ai/text-to-speech with bulbul:v3.
Returns raw MP3 audio bytes (decoded from base64 response).

Emotion mapping → pace:
  frustrated → 0.93  (slower, calming)
  confused   → 0.90  (clearer, deliberate)
  urgent     → 1.05  (brisk, efficient)
  default    → 1.0
"""

import base64
import logging
import re

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# ── Emotion → Pace mapping ──────────────────────────────────────────
EMOTION_PACE_MAP: dict[str, float] = {
    "frustrated": 0.93,
    "confused": 0.90,
    "urgent": 1.05,
    "satisfied": 1.0,
    "calm": 1.0,
}


# ── Supported Sarvam Bulbul Languages & Normalizer ──────────────────
SARVAM_TTS_SUPPORTED_CODES: set[str] = {
    "en-IN",  # Indian English
    "hi-IN",  # Hindi
    "ta-IN",  # Tamil
    "te-IN",  # Telugu
    "kn-IN",  # Kannada
    "ml-IN",  # Malayalam
    "bn-IN",  # Bengali
    "mr-IN",  # Marathi
    "gu-IN",  # Gujarati
    "pa-IN",  # Punjabi
    "od-IN",  # Odia
}

TTS_LANGUAGE_ALIAS_MAP: dict[str, str] = {
    "english": "en-IN", "en": "en-IN", "en-in": "en-IN", "en-us": "en-IN",
    "tamil": "ta-IN", "tanglish": "ta-IN", "ta": "ta-IN", "ta-in": "ta-IN",
    "hindi": "hi-IN", "hinglish": "hi-IN", "hi": "hi-IN", "hi-in": "hi-IN",
    "telugu": "te-IN", "tenglish": "te-IN", "te": "te-IN", "te-in": "te-IN",
    "kannada": "kn-IN", "kanglish": "kn-IN", "kn": "kn-IN", "kn-in": "kn-IN",
    "malayalam": "ml-IN", "manglish": "ml-IN", "ml": "ml-IN", "ml-in": "ml-IN",
    "bengali": "bn-IN", "benglish": "bn-IN", "bangla": "bn-IN", "bn": "bn-IN", "bn-in": "bn-IN",
    "marathi": "mr-IN", "marathish": "mr-IN", "mr": "mr-IN", "mr-in": "mr-IN",
    "gujarati": "gu-IN", "gujlish": "gu-IN", "gu": "gu-IN", "gu-in": "gu-IN",
    "punjabi": "pa-IN", "punglish": "pa-IN", "pa": "pa-IN", "pa-in": "pa-IN",
    "odia": "od-IN", "odlish": "od-IN", "oriya": "od-IN", "or": "od-IN", "or-in": "od-IN", "od": "od-IN", "od-in": "od-IN",
    "assamese": "as-IN", "as": "as-IN", "as-in": "as-IN",
    "urdu": "ur-IN", "ur": "ur-IN", "ur-in": "ur-IN",
}


def normalize_tts_language_code(language_code: str) -> str:
    """Normalizes any incoming language identifier to valid BCP-47."""
    if not language_code:
        return "en-IN"
    cleaned = language_code.strip().lower()
    if cleaned in TTS_LANGUAGE_ALIAS_MAP:
        return TTS_LANGUAGE_ALIAS_MAP[cleaned]
    # Check if format is already xx-YY
    parts = language_code.split("-")
    if len(parts) == 2:
        return f"{parts[0].lower()}-{parts[1].upper()}"
    return language_code


# ── Text cleaner (backend mirror of frontend cleanTextForSpeech) ────
def clean_text_for_tts(text: str) -> str:
    """Strip markdown, formatting, and normalise text for spoken delivery."""
    if not text:
        return ""
    cleaned = text
    # Code blocks and inline code
    cleaned = re.sub(r"```[\s\S]*?```", "", cleaned)
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    # Markdown bold / italics
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"\*([^*]+)\*", r"\1", cleaned)
    # Headers and bullet markers
    cleaned = re.sub(r"^#+\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^\s*[-*•]\s+", "", cleaned, flags=re.MULTILINE)
    # URLs → "link"
    cleaned = re.sub(r"https?://\S+", "link", cleaned)
    # Policy tags [CORE], [EXT]
    cleaned = re.sub(r"\[(?:CORE|EXT|INFO)[^\]]*\]", "", cleaned, flags=re.IGNORECASE)
    # JSON-like curly brackets
    cleaned = re.sub(r"\{[^}]*\}", "", cleaned)
    # Space out identifiers for spoken pronunciation
    cleaned = re.sub(
        r"\b(TXN)(\d+)\b",
        lambda m: "T X N " + " ".join(m.group(2)),
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\b(ORD)(\d+)\b",
        lambda m: "O R D " + " ".join(m.group(2)),
        cleaned,
        flags=re.IGNORECASE,
    )
    # Common abbreviations
    cleaned = re.sub(r"\be\.g\.", "for example", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bi\.e\.", "that is", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bID\b", "I D", cleaned)
    # Numbers over 4 digits: insert commas for Sarvam pronunciation
    def _comma_numbers(m: re.Match) -> str:
        num = m.group(0)
        if len(num) > 4:
            # Format with commas (Indian style: 1,00,000)
            return f"{int(num):,}"
        return num
    cleaned = re.sub(r"\b\d{5,}\b", _comma_numbers, cleaned)
    # Whitespace normalisation
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


class SarvamTTSError(Exception):
    """Raised when Sarvam API call fails."""
    pass


async def synthesize_sarvam(
    text: str,
    language_code: str = "en-IN",
    emotion: str | None = None,
    pitch: float | None = None,
    *,
    http_client: httpx.AsyncClient | None = None,
) -> bytes:
    """
    Call the Sarvam text-to-speech API and return raw MP3 audio bytes.

    Parameters
    ----------
    text : str
        Already-cleaned text (max 400 chars enforced by caller).
    language_code : str
        BCP-47 Indic language code: en-IN, ta-IN, hi-IN, etc.
    emotion : str | None
        Detected caller emotion; maps to pace.
    pitch : float | None
        Optional pitch adjustment between -0.5 and 0.5 (negative lowers pitch).
    http_client : httpx.AsyncClient | None
        Injectable client for testing with MockTransport.

    Returns
    -------
    bytes
        Raw MP3 audio data.

    Raises
    ------
    SarvamTTSError
        On any network or API error.
    """
    speaker = settings.sarvam_speaker or "kavya"
    effective_lang = normalize_tts_language_code(language_code)

    if effective_lang not in SARVAM_TTS_SUPPORTED_CODES:
        raise SarvamTTSError(
            f"Unsupported TTS language '{language_code}' ({effective_lang}) for Sarvam Bulbul. "
            f"Supported languages: {', '.join(sorted(SARVAM_TTS_SUPPORTED_CODES))}. "
            "Please fallback to browser speech synthesis."
        )

    # Fast path: check pre-synthesized opener / filler cache
    from app.voice.opener_cache import get_cached_opener_audio, store_cached_opener_audio
    cached = get_cached_opener_audio(text, speaker=speaker, language_code=effective_lang)
    if cached is not None and http_client is None:
        return cached

    api_key = settings.sarvam_api_key
    if not api_key:
        raise SarvamTTSError("SARVAM_API_KEY is not configured")

    pace = EMOTION_PACE_MAP.get((emotion or "calm").lower(), 1.0)
    effective_pitch = pitch if pitch is not None else getattr(settings, "sarvam_pitch", 0.0)
    try:
        clamped_pitch = max(-0.5, min(0.5, float(effective_pitch or 0.0)))
    except (TypeError, ValueError):
        clamped_pitch = 0.0

    raw_sr = getattr(settings, "sarvam_sample_rate", 22050)
    try:
        sample_rate = int(raw_sr)
    except (TypeError, ValueError):
        sample_rate = 22050

    payload = {
        "text": text,
        "language_code": effective_lang,
        "model": settings.sarvam_tts_model or "bulbul:v3",
        "speaker": speaker,
        "pace": pace,
        "speech_sample_rate": sample_rate,
        "output_audio_codec": "mp3",
        "enable_preprocessing": True,
    }
    if clamped_pitch != 0.0:
        payload["pitch"] = round(clamped_pitch, 2)

    headers = {
        "Content-Type": "application/json",
        "api-subscription-key": api_key,
    }

    client = http_client or httpx.AsyncClient(timeout=10.0)
    owns_client = http_client is None
    try:
        resp = await client.post(
            "https://api.sarvam.ai/text-to-speech",
            json=payload,
            headers=headers,
        )
        if resp.status_code != 200:
            raise SarvamTTSError(
                f"Sarvam API returned {resp.status_code}: {resp.text[:200]}"
            )

        data = resp.json()
        audios = data.get("audios")
        if not audios or not audios[0]:
            raise SarvamTTSError("Sarvam API returned empty audios array")

        audio_bytes = base64.b64decode(audios[0])
        store_cached_opener_audio(text, audio_bytes, speaker=speaker, language_code=effective_lang)
        return audio_bytes

    except SarvamTTSError:
        raise
    except Exception as e:
        raise SarvamTTSError(f"Sarvam TTS request failed: {e}") from e
    finally:
        if owns_client:
            await client.aclose()


async def synthesize_sarvam_stream(
    text: str,
    language_code: str = "en-IN",
    emotion: str | None = None,
    pitch: float | None = None,
    *,
    http_client: httpx.AsyncClient | None = None,
):
    """
    Call Sarvam streaming TTS API: POST https://api.sarvam.ai/text-to-speech/stream.
    Yields raw MP3 audio chunks as they arrive for minimum Time-To-First-Audio-Byte (TTFB).
    """
    api_key = settings.sarvam_api_key
    if not api_key:
        raise SarvamTTSError("SARVAM_API_KEY is not configured")

    pace = EMOTION_PACE_MAP.get((emotion or "calm").lower(), 1.0)
    effective_pitch = pitch if pitch is not None else getattr(settings, "sarvam_pitch", 0.0)
    try:
        clamped_pitch = max(-0.5, min(0.5, float(effective_pitch or 0.0)))
    except (TypeError, ValueError):
        clamped_pitch = 0.0

    raw_sr = getattr(settings, "sarvam_sample_rate", 22050)
    try:
        sample_rate = int(raw_sr)
    except (TypeError, ValueError):
        sample_rate = 22050

    effective_lang = normalize_tts_language_code(language_code)
    if effective_lang not in SARVAM_TTS_SUPPORTED_CODES:
        raise SarvamTTSError(
            f"Unsupported TTS language '{language_code}' ({effective_lang}) for Sarvam Bulbul. "
            f"Supported languages: {', '.join(sorted(SARVAM_TTS_SUPPORTED_CODES))}."
        )

    payload = {
        "text": text,
        "language_code": effective_lang,
        "model": settings.sarvam_tts_model or "bulbul:v3",
        "speaker": settings.sarvam_speaker or "kavya",
        "pace": pace,
        "speech_sample_rate": sample_rate,
        "output_audio_codec": "mp3",
        "enable_preprocessing": True,
    }
    if clamped_pitch != 0.0:
        payload["pitch"] = round(clamped_pitch, 2)

    headers = {
        "Content-Type": "application/json",
        "api-subscription-key": api_key,
    }

    client = http_client or httpx.AsyncClient(timeout=15.0)
    owns_client = http_client is None
    try:
        async with client.stream("POST", "https://api.sarvam.ai/text-to-speech/stream", json=payload, headers=headers) as resp:
            if resp.status_code != 200:
                raise SarvamTTSError(f"Sarvam stream returned {resp.status_code}")
            async for chunk in resp.aiter_bytes():
                if chunk:
                    yield chunk
    except SarvamTTSError:
        raise
    except Exception as e:
        raise SarvamTTSError(f"Sarvam stream error: {e}") from e
    finally:
        if owns_client:
            await client.aclose()
