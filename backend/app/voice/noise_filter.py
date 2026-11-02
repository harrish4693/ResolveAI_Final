"""ResolveAIV2 — Voice Input & STT Noise / Hallucination Filter (Backend).

Prevents ambient noise, background conversations, TV audio, and STT hallucinations
from reaching the LLM or triggering an agent response while strictly preserving:
1. Legitimate short answers (e.g., "yes", "no", "stop", "cancel", "help", "seri", "haan")
2. All 22 supported Indian languages, native scripts, and code-mixed speech (Tanglish, Hinglish)
3. Natural customer utterances with pauses
"""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class UtteranceValidationResult:
    is_valid: bool
    reason: Optional[str]
    cleaned_text: str
    is_short_answer: bool
    needs_confirmation: bool = False


# Normalized Whitelist of Valid Short Answers and Commands.
WHITELISTED_SHORT_UTTERANCES = {
    # ── English ──
    "yes",
    "yeah",
    "yep",
    "yup",
    "no",
    "nope",
    "nah",
    "ok",
    "okay",
    "sure",
    "fine",
    "stop",
    "cancel",
    "help",
    "wait",
    "hold",
    "bye",
    "hi",
    "hello",
    "hey",
    "correct",
    "right",
    "wrong",
    "proceed",
    "continue",
    "done",
    "thanks",
    "thank you",
    "please",
    # ── Tamil & Tanglish ──
    "aam",
    "aama",
    "aamam",
    "ama",
    "amam",
    "illai",
    "illa",
    "seri",
    "sari",
    "podhum",
    "niruthu",
    "nillu",
    "udhavi",
    "vanakkam",
    "nandri",
    "sollunga",
    "kandippa",
    "kandippaga",
    "thappu",
    "mudinjadhu",
    "aamanga",
    "illanga",
    "seringa",
    "saringa",
    # Tamil Script
    "ஆம்",
    "ஆமாம்",
    "இல்லை",
    "சரி",
    "போதும்",
    "நிறுத்து",
    "நில்லு",
    "உதவி",
    "வணக்கம்",
    "நன்றி",
    "சொல்லுங்க",
    "கண்டிப்பா",
    # ── Hindi & Hinglish ──
    "haan",
    "ha",
    "han",
    "haa",
    "nahi",
    "nahin",
    "na",
    "theek",
    "theek hai",
    "thik",
    "thik hai",
    "accha",
    "achha",
    "sahi",
    "galat",
    "ruk",
    "ruko",
    "roko",
    "band",
    "band karo",
    "madad",
    "sahayata",
    "namaste",
    "namaskar",
    "shukriya",
    "dhanyawad",
    "dhanyavad",
    "bolo",
    "batao",
    "zaroor",
    # Hindi Devanagari Script
    "हाँ",
    "नहीं",
    "ठीक",
    "ठीक है",
    "अच्छा",
    "सही",
    "गलत",
    "रुको",
    "रोको",
    "बंद करो",
    "मदद",
    "नमस्ते",
    "नमस्कार",
    "शुक्रिया",
    "धन्यवाद",
    # ── Kannada & Kanglish ──
    "houdu",
    "haudu",
    "illa",
    "sari",
    "nillisi",
    "nilli",
    "sahaya",
    "namaskara",
    "dhanyavadagalu",
    "hegi",
    "heli",
    # Kannada Script
    "ಹೌದು",
    "ಇಲ್ಲ",
    "ಸರಿ",
    "ನಿಲ್ಲಿಸಿ",
    "ಸಹಾಯ",
    "ನಮಸ್ಕಾರ",
    "ಧನ್ಯವಾದಗಳು",
    # ── Telugu & Tenglish ──
    "avunu",
    "kaadhu",
    "kadu",
    "sare",
    "sari",
    "aapu",
    "aagandi",
    "sahayam",
    "namaskaram",
    "dhanyavadamulu",
    "cheppandi",
    # Telugu Script
    "అవును",
    "కాదు",
    "సరే",
    "ఆపు",
    "ఆగండి",
    "సహాయం",
    "నమస్కారం",
    "ధన్యవాదాలు",
    # ── Malayalam & Manglish ──
    "athe",
    "alla",
    "seri",
    "nirthu",
    "nilkku",
    "sahayam",
    "namaskaram",
    "nanni",
    "parayu",
    # Malayalam Script
    "അതെ",
    "അല്ല",
    "ശരി",
    "നിർത്തൂ",
    "സഹായം",
    "നമസ്കാരം",
    "നന്ദി",
    # ── Bengali ──
    "hyan",
    "na",
    "thik achhe",
    "thamo",
    "sahajjo",
    "namaskar",
    "dhonnobad",
    # Bengali Script
    "হ্যাঁ",
    "না",
    "ঠিক আছে",
    "থামো",
    "সাহায্য",
    "নমস্কার",
    "ধন্যবাদ",
    # ── Marathi ──
    "ho",
    "nahi",
    "thik ahe",
    "thamba",
    "madat",
    "dhanyavad",
    # Marathi Script
    "हो",
    "नाही",
    "ठीक आहे",
    "थांबा",
    "मदत",
    # ── Gujarati ──
    "haa",
    "na",
    "barobar",
    "madad",
    "aabhar",
    # Gujarati Script
    "હા",
    "ના",
    "બરાબર",
    "મદદ",
    "આભાર",
    # ── Punjabi ──
    "haanji",
    "theek ae",
    "roko",
    "sat sri akal",
    # Punjabi Script
    "ਹਾਂ",
    "ਨਹੀਂ",
    "ਠੀਕ ਹੈ",
    "ਰੋਕੋ",
    "ਮਦਦ",
    "ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ",
    # ── Odia ──
    "thik achhi",
    # Odia Script
    "ହଁ",
    "ନା",
    "ଠିକ ଅଛି",
    "ସାହାଯ୍ୟ",
    # ── Urdu ──
    "ہاں",
    "نہیں",
    "شکریہ",
    "مدد",
    "ٹھیک ہے",
    "آداب",
}

# Bracketed non-speech sound descriptors (Whisper, YouTube data, Saaras).
BRACKETED_NOISE_PATTERN = re.compile(
    r"^(\[|\()(music|applause|laughter|laughter and applause|cheering|cough|coughing|throat clearing|groan|sigh|gasp|screaming|snicker|crying|noise|background noise|whisper|chatter|inaudible|unintelligible|bell|silence)(\]|\))$",
    re.IGNORECASE,
)

# Common subtitle / video training corpus hallucinations.
CORPUS_HALLUCINATIONS = (
    "thank you for watching",
    "thanks for watching",
    "subtitles by",
    "please subscribe",
    "like and subscribe",
    "translated by",
    "all rights reserved",
    "watching this video",
    "see you next time",
)

# Isolated non-lexical filler murmurs that do not constitute meaningful speech.
ISOLATED_FILLERS = {
    "uh",
    "um",
    "umm",
    "uhh",
    "ah",
    "ahh",
    "oh",
    "hmm",
    "hm",
    "hmmm",
    "er",
    "eh",
    "shh",
    "mhm",
    "mm",
}

# Regex to strip leading and trailing punctuation
STRIP_PUNCT_REGEX = re.compile(r"^[.,\/#!$%\^&\*;:{}=\-_`~()?\"'–—\s]+|[.,\/#!$%\^&\*;:{}=\-_`~()?\"'–—\s]+$")


def validate_spoken_utterance(
    transcript: Optional[str],
    confidence: Optional[float] = None,
) -> UtteranceValidationResult:
    """Validate a spoken customer utterance before sending to the LLM or triggering an agent response.

    Args:
        transcript: Transcribed text string from STT.
        confidence: Optional confidence score [0.0, 1.0] from STT provider.

    Returns:
        UtteranceValidationResult indicating whether to process or ignore.
    """
    raw = (transcript or "").strip()

    # 1. Reject empty or whitespace-only
    if not raw:
        return UtteranceValidationResult(
            is_valid=False,
            reason="empty_or_whitespace",
            cleaned_text="",
            is_short_answer=False,
        )

    # Normalize punctuation for matching
    stripped = STRIP_PUNCT_REGEX.sub("", raw).lower().strip()

    if not stripped:
        return UtteranceValidationResult(
            is_valid=False,
            reason="punctuation_only",
            cleaned_text=raw,
            is_short_answer=False,
        )

    # 2. Strict Whitelist Check: Valid short answers must always pass!
    if stripped in WHITELISTED_SHORT_UTTERANCES:
        return UtteranceValidationResult(
            is_valid=True,
            reason=None,
            cleaned_text=raw,
            is_short_answer=True,
            needs_confirmation=False,
        )

    # 3. Bracketed audio/sound tag hallucinations (e.g. [music], (applause))
    if BRACKETED_NOISE_PATTERN.match(raw) or BRACKETED_NOISE_PATTERN.match(stripped):
        return UtteranceValidationResult(
            is_valid=False,
            reason="bracketed_noise_tag",
            cleaned_text=raw,
            is_short_answer=False,
        )

    # 4. Corpus / subtitle hallucination phrases
    lower_text = raw.lower()
    for hallucination in CORPUS_HALLUCINATIONS:
        if (
            lower_text == hallucination
            or lower_text.startswith(hallucination + ".")
            or lower_text.endswith(hallucination)
        ):
            return UtteranceValidationResult(
                is_valid=False,
                reason="corpus_hallucination",
                cleaned_text=raw,
                is_short_answer=False,
            )

    # 5. Isolated filler murmurs (e.g. "uh", "hmm", "um" alone)
    if stripped in ISOLATED_FILLERS:
        return UtteranceValidationResult(
            is_valid=False,
            reason="isolated_filler_noise",
            cleaned_text=raw,
            is_short_answer=False,
        )

    # 6. Single character fragment (except for digits 0-9)
    if len(stripped) == 1 and not stripped.isdigit():
        return UtteranceValidationResult(
            is_valid=False,
            reason="single_char_fragment",
            cleaned_text=raw,
            is_short_answer=False,
        )

    # 7. Repetitive noise characters (e.g. ".....", "zzzzz", "?????")
    if len(stripped) >= 4 and len(set(stripped)) == 1:
        return UtteranceValidationResult(
            is_valid=False,
            reason="repetitive_character_noise",
            cleaned_text=raw,
            is_short_answer=False,
        )

    # 8. Low-Confidence Safety Check (when provider exposes confidence)
    if confidence is not None:
        if confidence < 0.35:
            return UtteranceValidationResult(
                is_valid=False,
                reason="low_stt_confidence",
                cleaned_text=raw,
                is_short_answer=False,
            )
        if confidence < 0.60:
            return UtteranceValidationResult(
                is_valid=True,
                reason="borderline_confidence",
                cleaned_text=raw,
                is_short_answer=False,
                needs_confirmation=True,
            )

    # Passed all filters: legitimate customer utterance
    return UtteranceValidationResult(
        is_valid=True,
        reason=None,
        cleaned_text=raw,
        is_short_answer=False,
        needs_confirmation=False,
    )

