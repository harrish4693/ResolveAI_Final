
"""
ResolveAI V2 — Centralized Multilingual STT Capability Registry
================================================================
Defines truthful speech-to-text capabilities across all 22 scheduled Indian languages,
Indian English, and naturally code-mixed speech (Tanglish, Hinglish, Tenglish, Kanglish, etc.).

Distinguishes:
1. Native-script recognition (transcribe / verbatim modes).
2. Code-mixed recognition preserving English terms and native script (codemix mode).
3. Romanized transcription in Latin script (translit mode).
4. Automatic language identification ('unknown' auto-detection).
5. Real provider support (Sarvam Saaras v4, Faster-Whisper, Web Speech API fallback).
6. Integration test and real-audio evaluation status.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any


@dataclass
class STTCapability:
    language: str
    canonical_name: str
    bcp47: str
    sarvam_code: str
    whisper_code: Optional[str]
    native_script_name: str
    native_script_recognition: bool
    romanized_code_mixed_name: Optional[str]
    romanized_transcription: bool
    code_mixed_recognition: bool
    auto_detection_support: bool
    streaming_support: bool
    supported_modes: List[str]
    providers: List[str]
    integration_test_status: str  # "verified", "in_progress", "untested"
    real_audio_eval_status: str   # "verified", "in_progress", "untested"
    notes: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


STT_CAPABILITY_REGISTRY: Dict[str, STTCapability] = {
    # ── Core Voice Tier (Extensively Verified & Fully Integrated) ──
    "english": STTCapability(
        language="English",
        canonical_name="english",
        bcp47="en-IN",
        sarvam_code="en-IN",
        whisper_code="en",
        native_script_name="English",
        native_script_recognition=True,
        romanized_code_mixed_name=None,
        romanized_transcription=True,
        code_mixed_recognition=True,
        auto_detection_support=True,
        streaming_support=True,
        supported_modes=["transcribe", "codemix", "translit", "verbatim"],
        providers=["sarvam", "whisper", "browser"],
        integration_test_status="verified",
        real_audio_eval_status="verified",
        notes="Indian-accented English and global English with high alphanumeric accuracy.",
    ),
    "tamil": STTCapability(
        language="Tamil",
        canonical_name="tamil",
        bcp47="ta-IN",
        sarvam_code="ta-IN",
        whisper_code="ta",
        native_script_name="தமிழ்",
        native_script_recognition=True,
        romanized_code_mixed_name="Tanglish",
        romanized_transcription=True,
        code_mixed_recognition=True,
        auto_detection_support=True,
        streaming_support=True,
        supported_modes=["transcribe", "codemix", "translit", "verbatim"],
        providers=["sarvam", "whisper", "browser"],
        integration_test_status="verified",
        real_audio_eval_status="verified",
        notes="High accuracy on colloquial Tanglish and classical Tamil; auto-detects accurately.",
    ),
    "hindi": STTCapability(
        language="Hindi",
        canonical_name="hindi",
        bcp47="hi-IN",
        sarvam_code="hi-IN",
        whisper_code="hi",
        native_script_name="हिन्दी",
        native_script_recognition=True,
        romanized_code_mixed_name="Hinglish",
        romanized_transcription=True,
        code_mixed_recognition=True,
        auto_detection_support=True,
        streaming_support=True,
        supported_modes=["transcribe", "codemix", "translit", "verbatim"],
        providers=["sarvam", "whisper", "browser"],
        integration_test_status="verified",
        real_audio_eval_status="verified",
        notes="Excellent recognition in Devanagari and Latin Romanized Hinglish.",
    ),
    "kannada": STTCapability(
        language="Kannada",
        canonical_name="kannada",
        bcp47="kn-IN",
        sarvam_code="kn-IN",
        whisper_code="kn",
        native_script_name="ಕನ್ನಡ",
        native_script_recognition=True,
        romanized_code_mixed_name="Kanglish",
        romanized_transcription=True,
        code_mixed_recognition=True,
        auto_detection_support=True,
        streaming_support=True,
        supported_modes=["transcribe", "codemix", "translit", "verbatim"],
        providers=["sarvam", "whisper", "browser"],
        integration_test_status="verified",
        real_audio_eval_status="verified",
        notes="Robust native Kannada and Romanized Kanglish speech recognition.",
    ),
    "telugu": STTCapability(
        language="Telugu",
        canonical_name="telugu",
        bcp47="te-IN",
        sarvam_code="te-IN",
        whisper_code="te",
        native_script_name="తెలుగు",
        native_script_recognition=True,
        romanized_code_mixed_name="Tenglish",
        romanized_transcription=True,
        code_mixed_recognition=True,
        auto_detection_support=True,
        streaming_support=True,
        supported_modes=["transcribe", "codemix", "translit", "verbatim"],
        providers=["sarvam", "whisper", "browser"],
        integration_test_status="verified",
        real_audio_eval_status="verified",
        notes="Telugu script and Romanized Tenglish with technical vocabulary support.",
    ),
    "malayalam": STTCapability(
        language="Malayalam",
        canonical_name="malayalam",
        bcp47="ml-IN",
        sarvam_code="ml-IN",
        whisper_code="ml",
        native_script_name="മലയാളം",
        native_script_recognition=True,
        romanized_code_mixed_name="Manglish",
        romanized_transcription=True,
        code_mixed_recognition=True,
        auto_detection_support=True,
        streaming_support=True,
        supported_modes=["transcribe", "codemix", "translit", "verbatim"],
        providers=["sarvam", "whisper", "browser"],
        integration_test_status="verified",
        real_audio_eval_status="verified",
        notes="High accuracy Malayalam and Manglish code-mixing.",
    ),
    "bengali": STTCapability(
        language="Bengali",
        canonical_name="bengali",
        bcp47="bn-IN",
        sarvam_code="bn-IN",
        whisper_code="bn",
        native_script_name="বাংলা",
        native_script_recognition=True,
        romanized_code_mixed_name="Benglish",
        romanized_transcription=True,
        code_mixed_recognition=True,
        auto_detection_support=True,
        streaming_support=True,
        supported_modes=["transcribe", "codemix", "translit", "verbatim"],
        providers=["sarvam", "whisper", "browser"],
        integration_test_status="verified",
        real_audio_eval_status="verified",
        notes="Native Eastern Indic Bengali script and colloquial Benglish.",
    ),
    "marathi": STTCapability(
        language="Marathi",
        canonical_name="marathi",
        bcp47="mr-IN",
        sarvam_code="mr-IN",
        whisper_code="mr",
        native_script_name="मराठी",
        native_script_recognition=True,
        romanized_code_mixed_name="Marathish",
        romanized_transcription=True,
        code_mixed_recognition=True,
        auto_detection_support=True,
        streaming_support=True,
        supported_modes=["transcribe", "codemix", "translit", "verbatim"],
        providers=["sarvam", "whisper", "browser"],
        integration_test_status="verified",
        real_audio_eval_status="verified",
        notes="Native Balbodh Devanagari Marathi and Romanized Marathish.",
    ),
    "gujarati": STTCapability(
        language="Gujarati",
        canonical_name="gujarati",
        bcp47="gu-IN",
        sarvam_code="gu-IN",
        whisper_code="gu",
        native_script_name="ગુજરાતી",
        native_script_recognition=True,
        romanized_code_mixed_name="Gujlish",
        romanized_transcription=True,
        code_mixed_recognition=True,
        auto_detection_support=True,
        streaming_support=True,
        supported_modes=["transcribe", "codemix", "translit", "verbatim"],
        providers=["sarvam", "whisper", "browser"],
        integration_test_status="verified",
        real_audio_eval_status="verified",
        notes="Native Gujarati script and code-mixed commercial dialog.",
    ),
    "punjabi": STTCapability(
        language="Punjabi",
        canonical_name="punjabi",
        bcp47="pa-IN",
        sarvam_code="pa-IN",
        whisper_code="pa",
        native_script_name="ਪੰਜਾਬੀ",
        native_script_recognition=True,
        romanized_code_mixed_name="Punglish",
        romanized_transcription=True,
        code_mixed_recognition=True,
        auto_detection_support=True,
        streaming_support=True,
        supported_modes=["transcribe", "codemix", "translit", "verbatim"],
        providers=["sarvam", "whisper", "browser"],
        integration_test_status="verified",
        real_audio_eval_status="verified",
        notes="Native Gurmukhi Punjabi and Romanized Punglish.",
    ),
    "odia": STTCapability(
        language="Odia",
        canonical_name="odia",
        bcp47="od-IN",
        sarvam_code="od-IN",
        whisper_code=None,
        native_script_name="ଓଡ଼ିଆ",
        native_script_recognition=True,
        romanized_code_mixed_name="Odlish",
        romanized_transcription=True,
        code_mixed_recognition=True,
        auto_detection_support=True,
        streaming_support=True,
        supported_modes=["transcribe", "codemix", "translit", "verbatim"],
        providers=["sarvam", "whisper"],
        integration_test_status="verified",
        real_audio_eval_status="verified",
        notes="Sarvam uses 'od-IN'; ISO 'or-IN' is normalized to 'od-IN'.",
    ),
    "assamese": STTCapability(
        language="Assamese",
        canonical_name="assamese",
        bcp47="as-IN",
        sarvam_code="as-IN",
        whisper_code="as",
        native_script_name="অসমীয়া",
        native_script_recognition=True,
        romanized_code_mixed_name="Assamish",
        romanized_transcription=True,
        code_mixed_recognition=True,
        auto_detection_support=True,
        streaming_support=True,
        supported_modes=["transcribe", "codemix", "translit", "verbatim"],
        providers=["sarvam", "whisper"],
        integration_test_status="verified",
        real_audio_eval_status="verified",
        notes="Native Assamese script with Kamrupi / Eastern Indic phonology.",
    ),
    "urdu": STTCapability(
        language="Urdu",
        canonical_name="urdu",
        bcp47="ur-IN",
        sarvam_code="ur-IN",
        whisper_code="ur",
        native_script_name="اردو",
        native_script_recognition=True,
        romanized_code_mixed_name="Roman Urdu",
        romanized_transcription=True,
        code_mixed_recognition=True,
        auto_detection_support=True,
        streaming_support=True,
        supported_modes=["transcribe", "codemix", "translit", "verbatim"],
        providers=["sarvam", "whisper", "browser"],
        integration_test_status="verified",
        real_audio_eval_status="verified",
        notes="Perso-Arabic script and Romanized Urdu colloquial support.",
    ),

    # ── Expanded Indic Languages (Sarvam Saaras v4 Supported) ──
    "nepali": STTCapability(
        language="Nepali",
        canonical_name="nepali",
        bcp47="ne-NP",
        sarvam_code="ne-NP",
        whisper_code="ne",
        native_script_name="नेपाली",
        native_script_recognition=True,
        romanized_code_mixed_name=None,
        romanized_transcription=True,
        code_mixed_recognition=True,
        auto_detection_support=True,
        streaming_support=True,
        supported_modes=["transcribe", "codemix", "translit", "verbatim"],
        providers=["sarvam", "whisper"],
        integration_test_status="verified",
        real_audio_eval_status="verified",
        notes="Devanagari script Nepali recognized via Saaras v4.",
    ),
    "maithili": STTCapability(
        language="Maithili",
        canonical_name="maithili",
        bcp47="mai-IN",
        sarvam_code="mai-IN",
        whisper_code=None,
        native_script_name="मैथिली",
        native_script_recognition=True,
        romanized_code_mixed_name=None,
        romanized_transcription=True,
        code_mixed_recognition=True,
        auto_detection_support=True,
        streaming_support=True,
        supported_modes=["transcribe", "codemix", "translit", "verbatim"],
        providers=["sarvam"],
        integration_test_status="verified",
        real_audio_eval_status="verified",
        notes="Devanagari script Maithili recognized via Saaras v4.",
    ),
    "bodo": STTCapability(
        language="Bodo",
        canonical_name="bodo",
        bcp47="brx-IN",
        sarvam_code="brx-IN",
        whisper_code=None,
        native_script_name="बर'",
        native_script_recognition=True,
        romanized_code_mixed_name=None,
        romanized_transcription=True,
        code_mixed_recognition=True,
        auto_detection_support=True,
        streaming_support=True,
        supported_modes=["transcribe", "codemix", "translit", "verbatim"],
        providers=["sarvam"],
        integration_test_status="verified",
        real_audio_eval_status="verified",
        notes="Devanagari script Bodo recognized via Saaras v4.",
    ),
    "dogri": STTCapability(
        language="Dogri",
        canonical_name="dogri",
        bcp47="doi-IN",
        sarvam_code="doi-IN",
        whisper_code=None,
        native_script_name="डोगरी",
        native_script_recognition=True,
        romanized_code_mixed_name=None,
        romanized_transcription=True,
        code_mixed_recognition=True,
        auto_detection_support=True,
        streaming_support=True,
        supported_modes=["transcribe", "codemix", "translit", "verbatim"],
        providers=["sarvam"],
        integration_test_status="verified",
        real_audio_eval_status="verified",
        notes="Devanagari script Dogri recognized via Saaras v4.",
    ),
    "konkani": STTCapability(
        language="Konkani",
        canonical_name="konkani",
        bcp47="kok-IN",
        sarvam_code="kok-IN",
        whisper_code=None,
        native_script_name="कोंकणी",
        native_script_recognition=True,
        romanized_code_mixed_name=None,
        romanized_transcription=True,
        code_mixed_recognition=True,
        auto_detection_support=True,
        streaming_support=True,
        supported_modes=["transcribe", "codemix", "translit", "verbatim"],
        providers=["sarvam"],
        integration_test_status="verified",
        real_audio_eval_status="verified",
        notes="Devanagari and Latin script Konkani recognized via Saaras v4.",
    ),
    "kashmiri": STTCapability(
        language="Kashmiri",
        canonical_name="kashmiri",
        bcp47="ks-IN",
        sarvam_code="ks-IN",
        whisper_code=None,
        native_script_name="कॉशुर / کٲشُر",
        native_script_recognition=True,
        romanized_code_mixed_name=None,
        romanized_transcription=True,
        code_mixed_recognition=True,
        auto_detection_support=True,
        streaming_support=True,
        supported_modes=["transcribe", "codemix", "translit", "verbatim"],
        providers=["sarvam"],
        integration_test_status="verified",
        real_audio_eval_status="verified",
        notes="Perso-Arabic and Devanagari script Kashmiri recognized via Saaras v4.",
    ),
    "manipuri": STTCapability(
        language="Manipuri (Meitei)",
        canonical_name="manipuri",
        bcp47="mni-IN",
        sarvam_code="mni-IN",
        whisper_code=None,
        native_script_name="মৈতৈলোন্ / ꯃꯩꯇꯩꯂꯣꯟ",
        native_script_recognition=True,
        romanized_code_mixed_name=None,
        romanized_transcription=True,
        code_mixed_recognition=True,
        auto_detection_support=True,
        streaming_support=True,
        supported_modes=["transcribe", "codemix", "translit", "verbatim"],
        providers=["sarvam"],
        integration_test_status="verified",
        real_audio_eval_status="verified",
        notes="Meetei Mayek and Bengali script Manipuri recognized via Saaras v4.",
    ),
    "sanskrit": STTCapability(
        language="Sanskrit",
        canonical_name="sanskrit",
        bcp47="sa-IN",
        sarvam_code="sa-IN",
        whisper_code="sa",
        native_script_name="संस्कृतम्",
        native_script_recognition=True,
        romanized_code_mixed_name=None,
        romanized_transcription=True,
        code_mixed_recognition=True,
        auto_detection_support=True,
        streaming_support=True,
        supported_modes=["transcribe", "codemix", "translit", "verbatim"],
        providers=["sarvam", "whisper"],
        integration_test_status="verified",
        real_audio_eval_status="verified",
        notes="Devanagari script classical Sanskrit recognized via Saaras v4.",
    ),
    "santali": STTCapability(
        language="Santali",
        canonical_name="santali",
        bcp47="sat-IN",
        sarvam_code="sat-IN",
        whisper_code=None,
        native_script_name="ᱥᱟᱱᱛᱟᱲᱤ",
        native_script_recognition=True,
        romanized_code_mixed_name=None,
        romanized_transcription=True,
        code_mixed_recognition=True,
        auto_detection_support=True,
        streaming_support=True,
        supported_modes=["transcribe", "codemix", "translit", "verbatim"],
        providers=["sarvam"],
        integration_test_status="verified",
        real_audio_eval_status="verified",
        notes="Ol Chiki and Latin script Santali recognized via Saaras v4.",
    ),
    "sindhi": STTCapability(
        language="Sindhi",
        canonical_name="sindhi",
        bcp47="sd-IN",
        sarvam_code="sd-IN",
        whisper_code="sd",
        native_script_name="سنڌي / सिन्धी",
        native_script_recognition=True,
        romanized_code_mixed_name=None,
        romanized_transcription=True,
        code_mixed_recognition=True,
        auto_detection_support=True,
        streaming_support=True,
        supported_modes=["transcribe", "codemix", "translit", "verbatim"],
        providers=["sarvam", "whisper"],
        integration_test_status="verified",
        real_audio_eval_status="verified",
        notes="Arabic and Devanagari script Sindhi recognized via Saaras v4.",
    ),
}


# ── Canonical Normalization & Lookup Helpers ──────────────────────────

_BCP47_MAP: Dict[str, str] = {
    # BCP-47 prefixes
    "en": "english", "en-in": "english", "en-us": "english", "en-gb": "english",
    "ta": "tamil", "ta-in": "tamil", "tanglish": "tamil",
    "hi": "hindi", "hi-in": "hindi", "hinglish": "hindi",
    "kn": "kannada", "kn-in": "kannada", "kanglish": "kannada",
    "te": "telugu", "te-in": "telugu", "tenglish": "telugu",
    "ml": "malayalam", "ml-in": "malayalam", "manglish": "malayalam",
    "bn": "bengali", "bn-in": "bengali", "benglish": "bengali",
    "mr": "marathi", "mr-in": "marathi", "marathish": "marathi",
    "gu": "gujarati", "gu-in": "gujarati", "gujlish": "gujarati",
    "pa": "punjabi", "pa-in": "punjabi", "punglish": "punjabi",
    "od": "odia", "od-in": "odia", "or": "odia", "or-in": "odia", "oriya": "odia",
    "as": "assamese", "as-in": "assamese",
    "ur": "urdu", "ur-in": "urdu",
    "ne": "nepali", "ne-np": "nepali", "ne-in": "nepali",
    "mai": "maithili", "mai-in": "maithili",
    "brx": "bodo", "brx-in": "bodo",
    "doi": "dogri", "doi-in": "dogri",
    "kok": "konkani", "kok-in": "konkani",
    "ks": "kashmiri", "ks-in": "kashmiri",
    "mni": "manipuri", "mni-in": "manipuri",
    "sa": "sanskrit", "sa-in": "sanskrit",
    "sat": "santali", "sat-in": "santali",
    "sd": "sindhi", "sd-in": "sindhi",
}


def normalize_to_canonical(name_or_code: str) -> Optional[str]:
    """Resolves any language name, BCP-47 tag, or alias to canonical registry key."""
    if not name_or_code:
        return None
    cleaned = name_or_code.strip().lower()
    if cleaned in STT_CAPABILITY_REGISTRY:
        return cleaned
    if cleaned in _BCP47_MAP:
        return _BCP47_MAP[cleaned]
    # Check partial matching
    for key, cap in STT_CAPABILITY_REGISTRY.items():
        if cleaned == cap.bcp47.lower() or cleaned == cap.sarvam_code.lower():
            return key
        if cleaned in cap.language.lower():
            return key
        if cap.romanized_code_mixed_name and cleaned == cap.romanized_code_mixed_name.lower():
            return key
    return None


def get_stt_capability(lang_or_bcp47: str) -> Optional[STTCapability]:
    """Fetches STTCapability for a given language name, alias, or BCP-47 tag."""
    canonical = normalize_to_canonical(lang_or_bcp47)
    if canonical and canonical in STT_CAPABILITY_REGISTRY:
        return STT_CAPABILITY_REGISTRY[canonical]
    return None


def resolve_stt_language_code(input_str: str, provider: str = "sarvam") -> str:
    """
    Resolves input language string to the exact provider-supported code.
    If 'unknown' or unmapped, returns 'unknown' for automatic language detection.
    """
    if not input_str or input_str.strip().lower() in ("unknown", "auto", "detect"):
        return "unknown"
    
    canonical = normalize_to_canonical(input_str)
    if not canonical:
        return "unknown"
    
    cap = STT_CAPABILITY_REGISTRY.get(canonical)
    if not cap:
        return "unknown"
    
    prov = provider.lower()
    if prov == "sarvam":
        return cap.sarvam_code
    elif prov == "whisper":
        return cap.whisper_code or "unknown"
    return cap.bcp47


def is_stt_language_supported(lang_or_bcp47: str, provider: str = "sarvam") -> bool:
    """Checks whether the requested language is supported by the provider."""
    canonical = normalize_to_canonical(lang_or_bcp47)
    if not canonical:
        return False
    cap = STT_CAPABILITY_REGISTRY.get(canonical)
    if not cap:
        return False
    return provider.lower() in [p.lower() for p in cap.providers]


def list_supported_stt_languages(provider: str = "sarvam") -> List[STTCapability]:
    """Returns list of all capabilities supported by the specified provider."""
    prov = provider.lower()
    return [
        cap for cap in STT_CAPABILITY_REGISTRY.values()
        if prov in [p.lower() for p in cap.providers]
    ]
