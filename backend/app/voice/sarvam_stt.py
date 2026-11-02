import io
import json
import logging
import wave
import httpx
from typing import Dict, Any, Optional, List

from app.config import settings
from app.voice.stt_registry import resolve_stt_language_code, get_stt_capability

logger = logging.getLogger(__name__)

SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"
MAX_REST_AUDIO_DURATION_SEC = 30.0


def build_stt_prompt(language_code: str, custom_prompt: Optional[str] = None) -> Optional[str]:
    """
    Constructs an unbiased, language-specific or neutral multi-lingual prompt
    for Sarvam Saaras v4 STT to guide domain terminology (Order IDs, tickets, UPI, amounts)
    without corrupting non-Tamil languages with Tanglish prompts.
    """
    if custom_prompt is not None:
        return str(custom_prompt).strip()

    req_lang = (language_code or "unknown").strip().lower()
    if req_lang == "unknown" or req_lang == "auto":
        cfg_prompt = getattr(settings, "sarvam_stt_prompt", None)
        return str(cfg_prompt).strip() if cfg_prompt else (
            "Indian customer support conversation. Transcribe speech naturally in the spoken Indian "
            "language, regional code-mixed speech, or Indian English. "
            "Preserve English technical terms, order IDs like ORD-101, tickets like TKT-301, UPI, and amounts accurately."
        )

    cap = get_stt_capability(req_lang)
    if cap:
        code_mixed_phrase = f" and English ({cap.romanized_code_mixed_name})" if cap.romanized_code_mixed_name else ""
        return (
            f"Indian customer support call in {cap.language}{code_mixed_phrase}. "
            f"Transcribe speech accurately in the requested mode, preserving English technical terms, "
            f"order IDs like ORD-101, tickets like TKT-301, UPI, and amounts without phonetic substitution."
        )

    return getattr(settings, "sarvam_stt_prompt", None)


class SarvamSTTError(Exception):
    """Raised when Sarvam Speech-to-Text API call fails."""
    pass


def get_audio_duration_seconds(audio_bytes: bytes) -> Optional[float]:
    """Inspects audio headers to calculate duration in seconds when possible."""
    if not audio_bytes:
        return 0.0
    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            if rate > 0:
                return float(frames) / float(rate)
    except Exception:
        pass
    return None


async def transcribe_sarvam(
    audio_bytes: bytes,
    language_code: str = "unknown",
    mode: str = "translit",
    keyterms: Optional[List[str]] = None,
    prompt: Optional[str] = None,
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Transcribes audio bytes using Sarvam AI Saaras STT API (saaras:v4).
    
    Args:
        audio_bytes: WAV or MP3 audio binary data (16kHz mono recommended).
        language_code: Expected base language (e.g. 'ta-IN', 'hi-IN', 'en-IN', 'unknown' for auto-detect).
        mode: Output mode:
            - 'translit': Romanized output suitable for Tanglish/Hinglish normalization.
            - 'codemix': English in Latin script and Indic-language words in native script.
            - 'transcribe': Standard transcription.
            - 'verbatim': Word-for-word including filler words.
        keyterms: List of domain terms, product names, or support keywords (max 50 terms, <= 64 chars each).
        timeout: Request timeout in seconds (defaults to settings.sarvam_stt_timeout).
        
    Returns:
        Dict with keys:
            transcript: Transcribed text string
            language_code: Detected/returned language code (e.g. 'ta-IN', 'hi-IN', 'en-IN')
            confidence: Float confidence / language probability score (0.0 - 1.0) or None
            request_id: Sarvam API request ID when available
            mode: Mode used for transcription
            provider: 'sarvam'
    """
    if not audio_bytes:
        raise SarvamSTTError("Audio bytes cannot be empty")

    # Enforce 30-second documented REST limit
    duration = get_audio_duration_seconds(audio_bytes)
    max_duration = getattr(settings, "sarvam_stt_max_duration_sec", MAX_REST_AUDIO_DURATION_SEC) or MAX_REST_AUDIO_DURATION_SEC
    if duration is not None and duration > max_duration:
        raise SarvamSTTError(
            f"Audio duration ({duration:.1f}s) exceeds documented {max_duration}s limit for REST STT. "
            "Use realtime streaming API or shorter utterances."
        )

    api_key = settings.sarvam_api_key
    if not api_key:
        raise SarvamSTTError("SARVAM_API_KEY is not configured")

    headers = {
        "api-subscription-key": api_key,
    }

    model = settings.sarvam_stt_model or "saaras:v4"
    stt_mode = mode or settings.sarvam_stt_mode or "translit"
    raw_lang = language_code or settings.sarvam_stt_language_code or "unknown"
    req_lang = resolve_stt_language_code(raw_lang, provider="sarvam")
    req_timeout = timeout or getattr(settings, "sarvam_stt_timeout", 15.0) or 15.0

    files = {
        "file": ("utterance.wav", audio_bytes, "audio/wav"),
    }
    data: Dict[str, Any] = {
        "model": model,
        "mode": stt_mode,
        "language_code": req_lang,
    }

    # Inject domain keyterms (up to 50 terms, max 64 chars per term)
    term_candidates = keyterms if keyterms is not None else getattr(settings, "sarvam_stt_keyterms", None)
    if term_candidates:
        clean_terms = [str(t).strip()[:64] for t in term_candidates if str(t).strip()][:50]
        if clean_terms:
            data["keyterms"] = json.dumps(clean_terms)

    # Inject STT context biasing prompt dynamically based on language
    stt_prompt = build_stt_prompt(req_lang, custom_prompt=prompt)
    if stt_prompt:
        data["prompt"] = str(stt_prompt).strip()

    try:
        async with httpx.AsyncClient(timeout=req_timeout) as client:
            resp = await client.post(
                SARVAM_STT_URL,
                headers=headers,
                files=files,
                data=data,
            )

        if resp.status_code in (401, 403):
            raise SarvamSTTError(f"Sarvam STT authentication failed (HTTP {resp.status_code})")
        elif resp.status_code == 429:
            raise SarvamSTTError("Sarvam STT rate limit exceeded (HTTP 429)")
        elif resp.status_code != 200:
            raise SarvamSTTError(f"Sarvam STT API error (HTTP {resp.status_code}): {resp.text[:200]}")

        res_json = resp.json()
        transcript = res_json.get("transcript", "").strip()
        detected_lang = res_json.get("language_code", req_lang)

        # Saaras v4 returns language_probability which acts as language detection confidence
        confidence = res_json.get("confidence")
        if confidence is None:
            confidence = res_json.get("language_probability")
        if confidence is not None:
            try:
                confidence = float(confidence)
            except (ValueError, TypeError):
                confidence = None

        return {
            "transcript": transcript,
            "language_code": detected_lang,
            "confidence": confidence,
            "request_id": res_json.get("request_id"),
            "mode": stt_mode,
            "provider": "sarvam",
        }

    except httpx.TimeoutException:
        raise SarvamSTTError(f"Sarvam STT request timed out after {req_timeout}s")
    except httpx.RequestError as e:
        raise SarvamSTTError(f"Sarvam STT network request failed: {e}")

