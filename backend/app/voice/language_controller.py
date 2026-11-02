"""
ResolveAIV2 — Voice Language Controller
=======================================
Session-level language policy and customer-controlled language switching for voice calls.

Required behaviors:
1. Start every new call in English by default unless explicit saved customer preference exists.
2. Continue in English until customer clearly indicates a preference for another supported language.
3. Explicit switch requests ("Tamil la pesunga", "Hindi mein baat karo", "English la sollunga",
   "Please switch back to English", "Kannada please") switch immediately.
4. Once selected, response language persists across subsequent responses.
5. Support Tamil, Tanglish, Hindi, Hinglish, Telugu, Kannada, Malayalam, Bengali, Marathi,
   Gujarati, Punjabi, Odia, and Indian English.
6. Preserve conversational Tanglish / Hinglish code-mixed style (Romanized Latin characters)
   without forcing rigid native script when customer speaks code-mixed language.
7. Isolated foreign words, loanwords, or culinary/product terms ("dosa pan", "kurta") MUST NOT
   flip the conversation language.
8. Noisy STT provider language labels MUST NOT flip the conversation language.
9. Return to English when customer switches back to English.
10. Honest explanation and fallback when customer requests an unsupported language (e.g. French, German).
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ── Truthful Voice Capability Registry ─────────────────────────────────
@dataclass
class VoiceCapability:
    language: str
    code: str
    bcp47: str
    tier: str
    text_understanding: bool
    native_script_recognition: bool
    code_mixed_understanding: bool
    stt_support: List[str]
    tts_support: List[str]
    full_voice_conversation: bool
    notes: str

    @property
    def speech_to_text(self) -> bool:
        return len(self.stt_support) > 0

    @property
    def text_to_speech(self) -> bool:
        return len(self.tts_support) > 0


VOICE_CAPABILITY_REGISTRY: Dict[str, VoiceCapability] = {
    # Tier 1 (Core Dravidian & Indo-Aryan Voice Suite)
    "english": VoiceCapability("English", "en", "en-IN", "core", True, True, True, ["sarvam", "whisper", "browser"], ["sarvam", "browser"], True, "Full end-to-end voice with neural TTS and browser fallback"),
    "tanglish": VoiceCapability("Tanglish", "ta", "ta-IN", "core", True, True, True, ["sarvam", "whisper", "browser"], ["sarvam", "browser"], True, "Tamil-English code-mixed speech in Latin script"),
    "tamil": VoiceCapability("Tamil", "ta", "ta-IN", "core", True, True, True, ["sarvam", "whisper", "browser"], ["sarvam", "browser"], True, "Native Tamil script speech and TTS"),
    "hinglish": VoiceCapability("Hinglish", "hi", "hi-IN", "core", True, True, True, ["sarvam", "whisper", "browser"], ["sarvam", "browser"], True, "Hindi-English code-mixed speech in Latin script"),
    "hindi": VoiceCapability("Hindi", "hi", "hi-IN", "core", True, True, True, ["sarvam", "whisper", "browser"], ["sarvam", "browser"], True, "Native Devanagari script speech and TTS"),
    "kannada": VoiceCapability("Kannada", "kn", "kn-IN", "core", True, True, True, ["sarvam", "whisper", "browser"], ["sarvam", "browser"], True, "Native Kannada script speech and neural TTS"),
    "kanglish": VoiceCapability("Kanglish", "kn", "kn-IN", "core", True, True, True, ["sarvam", "whisper", "browser"], ["sarvam", "browser"], True, "Kannada-English code-mixed speech in Latin script"),
    "telugu": VoiceCapability("Telugu", "te", "te-IN", "core", True, True, True, ["sarvam", "whisper", "browser"], ["sarvam", "browser"], True, "Native Telugu script speech and neural TTS"),
    "tenglish": VoiceCapability("Tenglish", "te", "te-IN", "core", True, True, True, ["sarvam", "whisper", "browser"], ["sarvam", "browser"], True, "Telugu-English code-mixed speech in Latin script"),
    "malayalam": VoiceCapability("Malayalam", "ml", "ml-IN", "core", True, True, True, ["sarvam", "whisper", "browser"], ["sarvam", "browser"], True, "Native Malayalam script speech and neural TTS"),
    "manglish": VoiceCapability("Manglish", "ml", "ml-IN", "core", True, True, True, ["sarvam", "whisper", "browser"], ["sarvam", "browser"], True, "Malayalam-English code-mixed speech in Latin script"),

    # Tier 2 (Major Regional Indian Languages)
    "bengali": VoiceCapability("Bengali", "bn", "bn-IN", "core", True, True, True, ["sarvam", "whisper", "browser"], ["sarvam", "browser"], True, "Native Bengali script speech and neural TTS"),
    "benglish": VoiceCapability("Benglish", "bn", "bn-IN", "core", True, True, True, ["sarvam", "whisper", "browser"], ["sarvam", "browser"], True, "Bengali-English code-mixed speech in Latin script"),
    "marathi": VoiceCapability("Marathi", "mr", "mr-IN", "core", True, True, True, ["sarvam", "whisper", "browser"], ["sarvam", "browser"], True, "Native Marathi Devanagari speech and neural TTS"),
    "marathish": VoiceCapability("Marathish", "mr", "mr-IN", "core", True, True, True, ["sarvam", "whisper", "browser"], ["sarvam", "browser"], True, "Marathi-English code-mixed speech in Latin script"),
    "gujarati": VoiceCapability("Gujarati", "gu", "gu-IN", "core", True, True, True, ["sarvam", "whisper", "browser"], ["sarvam", "browser"], True, "Native Gujarati script speech and neural TTS"),
    "gujlish": VoiceCapability("Gujlish", "gu", "gu-IN", "core", True, True, True, ["sarvam", "whisper", "browser"], ["sarvam", "browser"], True, "Gujarati-English code-mixed speech in Latin script"),
    "punjabi": VoiceCapability("Punjabi", "pa", "pa-IN", "core", True, True, True, ["sarvam", "whisper", "browser"], ["sarvam", "browser"], True, "Native Gurmukhi script speech and neural TTS"),
    "punglish": VoiceCapability("Punglish", "pa", "pa-IN", "core", True, True, True, ["sarvam", "whisper", "browser"], ["sarvam", "browser"], True, "Punjabi-English code-mixed speech in Latin script"),

    # Tier 3 (Expanded Indic Languages)
    "odia": VoiceCapability("Odia", "or", "od-IN", "expanded", True, True, True, ["sarvam", "whisper"], ["sarvam"], True, "Native Odia script speech and Sarvam neural TTS"),
    "assamese": VoiceCapability("Assamese", "as", "as-IN", "expanded", True, True, True, ["sarvam", "whisper"], ["sarvam", "browser"], True, "Native Assamese script speech and Sarvam neural TTS"),
    "urdu": VoiceCapability("Urdu", "ur", "ur-IN", "expanded", True, True, True, ["whisper", "browser"], ["browser"], True, "Urdu voice via Whisper STT and browser speech synthesis"),
    "nepali": VoiceCapability("Nepali", "ne", "ne-NP", "expanded", True, True, True, ["whisper", "browser"], ["browser"], True, "Nepali voice via Whisper STT and browser speech synthesis"),

    # Text-Only Indic Languages (Text chat intelligence; no voice models)
    "bodo": VoiceCapability("Bodo", "brx", "brx-IN", "text_only", True, True, True, [], [], False, "Text-only chat understanding; no voice STT/TTS models deployed"),
    "dogri": VoiceCapability("Dogri", "doi", "doi-IN", "text_only", True, True, True, [], [], False, "Text-only chat understanding; no voice STT/TTS models deployed"),
    "santali": VoiceCapability("Santali", "sat", "sat-IN", "text_only", True, True, True, [], [], False, "Text-only chat understanding; no voice STT/TTS models deployed"),
    "maithili": VoiceCapability("Maithili", "mai", "mai-IN", "text_only", True, True, True, [], [], False, "Text-only chat understanding; no voice STT/TTS models deployed"),
    "manipuri": VoiceCapability("Manipuri", "mni", "mni-IN", "text_only", True, True, True, [], [], False, "Text-only chat understanding; no voice STT/TTS models deployed"),
    "kashmiri": VoiceCapability("Kashmiri", "ks", "ks-IN", "text_only", True, True, True, [], [], False, "Text-only chat understanding; no voice STT/TTS models deployed"),
    "konkani": VoiceCapability("Konkani", "kok", "kok-IN", "text_only", True, True, True, [], [], False, "Text-only chat understanding; no voice STT/TTS models deployed"),
    "sanskrit": VoiceCapability("Sanskrit", "sa", "sa-IN", "text_only", True, True, True, [], [], False, "Text-only chat understanding; no voice STT/TTS models deployed"),
    "sindhi": VoiceCapability("Sindhi", "sd", "sd-IN", "text_only", True, True, True, [], [], False, "Text-only chat understanding; no voice STT/TTS models deployed"),
}


# ── Canonical Language Registry & BCP-47 Mappings ──────────────────────
SUPPORTED_LANGUAGES: Dict[str, Dict[str, Any]] = {
    "english": {
        "canonical": "english",
        "bcp47": "en-IN",
        "display_name": "English",
        "script": "latin",
        "is_code_mixed": False,
        "greeting": "Hello! I am ResolveAI. How can I help you today?",
        "ack": "Sure, let's continue in English.",
    },
    "tanglish": {
        "canonical": "tanglish",
        "bcp47": "ta-IN",
        "display_name": "Tanglish",
        "script": "latin",
        "is_code_mixed": True,
        "greeting": "Vanakkam! Naan ResolveAI. Ungalukku enna help venum?",
        "ack": "Kandippa, Tanglish-la pesalam! Enna help venum?",
    },
    "tamil": {
        "canonical": "tamil",
        "bcp47": "ta-IN",
        "display_name": "Tamil",
        "script": "tamil",
        "is_code_mixed": False,
        "greeting": "வணக்கம்! நான் ResolveAI. உங்களுக்கு என்ன உதவி வேண்டும்?",
        "ack": "நிச்சயமாக, தமிழில் பேசலாம்! உங்களுக்கு என்ன உதவி வேண்டும்?",
    },
    "hinglish": {
        "canonical": "hinglish",
        "bcp47": "hi-IN",
        "display_name": "Hinglish",
        "script": "latin",
        "is_code_mixed": True,
        "greeting": "Namaste! Main ResolveAI hoon. Main aapki kya help kar sakta hoon?",
        "ack": "Bilkul, Hinglish mein baat karte hain! Main aapki kya help kar sakta hoon?",
    },
    "hindi": {
        "canonical": "hindi",
        "bcp47": "hi-IN",
        "display_name": "Hindi",
        "script": "devanagari",
        "is_code_mixed": False,
        "greeting": "नमस्ते! मैं ResolveAI हूँ। मैं आपकी क्या मदद कर सकता हूँ?",
        "ack": "नमस्ते! बिल्कुल, हिन्दी में बात करते हैं। मैं आपकी क्या सहायता कर सकता हूँ?",
    },
    "kannada": {
        "canonical": "kannada",
        "bcp47": "kn-IN",
        "display_name": "Kannada",
        "script": "kannada",
        "is_code_mixed": False,
        "greeting": "ನಮಸ್ಕಾರ! ನಾನು ResolveAI. ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಬಹುದು?",
        "ack": "ಖಂಡಿತ, ಕನ್ನಡದಲ್ಲಿ ಮಾತನಾಡೋಣ! ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಬಹುದು?",
    },
    "kanglish": {
        "canonical": "kanglish",
        "bcp47": "kn-IN",
        "display_name": "Kanglish",
        "script": "latin",
        "is_code_mixed": True,
        "greeting": "Namaskara! Naanu ResolveAI. Nimage hege sahayavannu madabahudu?",
        "ack": "Khanditha, Kannada-dalli mathadona! Nimage hege sahayavannu madabahudu?",
    },
    "telugu": {
        "canonical": "telugu",
        "bcp47": "te-IN",
        "display_name": "Telugu",
        "script": "telugu",
        "is_code_mixed": False,
        "greeting": "నమస్కారం! నేను ResolveAI. మీకు ఎలా సహాయపడగలను?",
        "ack": "తప్పకుండా, తెలుగులో మాట్లాడదాం! మీకు ఎలా సహాయపడగలను?",
    },
    "tenglish": {
        "canonical": "tenglish",
        "bcp47": "te-IN",
        "display_name": "Tenglish",
        "script": "latin",
        "is_code_mixed": True,
        "greeting": "Namaskaram! Nenu ResolveAI. Meeku ela sahaya padagalanu?",
        "ack": "Thappakunda, Telugu-lo matladadam! Meeku ela sahaya padagalanu?",
    },
    "malayalam": {
        "canonical": "malayalam",
        "bcp47": "ml-IN",
        "display_name": "Malayalam",
        "script": "malayalam",
        "is_code_mixed": False,
        "greeting": "നമസ്കാരം! ഞാൻ ResolveAI ആണ്. എങ്ങനെ സഹായിക്കണം?",
        "ack": "തീർച്ചയായും, മലയാളത്തിൽ സംസാരിക്കാം! ഞാൻ എങ്ങനെ സഹായിക്കണം?",
    },
    "manglish": {
        "canonical": "manglish",
        "bcp47": "ml-IN",
        "display_name": "Manglish",
        "script": "latin",
        "is_code_mixed": True,
        "greeting": "Namaskaram! Njan ResolveAI aanu. Njan engane sahayeekkanam?",
        "ack": "Theerchayayum, Malayalam-il samsarikkam! Njan engane sahayeekkanam?",
    },
    "bengali": {
        "canonical": "bengali",
        "bcp47": "bn-IN",
        "display_name": "Bengali",
        "script": "bengali",
        "is_code_mixed": False,
        "greeting": "নমস্কার! আমি ResolveAI. আমি আপনাকে কীভাবে সাহায্য করতে পারি?",
        "ack": "অবশ্যই, বাংলায় কথা বলা যাক! আমি আপনাকে কীভাবে সাহায্য করতে পারি?",
    },
    "benglish": {
        "canonical": "benglish",
        "bcp47": "bn-IN",
        "display_name": "Benglish",
        "script": "latin",
        "is_code_mixed": True,
        "greeting": "Nomoshkar! Ami ResolveAI. Ami apnake kibhabe sahajjo korte pari?",
        "ack": "Obosshoi, Bangla-te kotha bola jak! Ami apnake kibhabe sahajjo korte pari?",
    },
    "marathi": {
        "canonical": "marathi",
        "bcp47": "mr-IN",
        "display_name": "Marathi",
        "script": "devanagari",
        "is_code_mixed": False,
        "greeting": "नमस्कार! मी ResolveAI आहे. मी तुम्हाला कशी मदत करू शकतो?",
        "ack": "नक्कीच, मराठीत बोलूया! मी तुम्हाला कशी मदत करू शकतो?",
    },
    "marathish": {
        "canonical": "marathish",
        "bcp47": "mr-IN",
        "display_name": "Marathish",
        "script": "latin",
        "is_code_mixed": True,
        "greeting": "Namaskar! Mee ResolveAI ahe. Mee tumhala kashi madat karu shakto?",
        "ack": "Nakkich, Marathi-t boluya! Mee tumhala kashi madat karu shakto?",
    },
    "gujarati": {
        "canonical": "gujarati",
        "bcp47": "gu-IN",
        "display_name": "Gujarati",
        "script": "gujarati",
        "is_code_mixed": False,
        "greeting": "નમસ્તે! હું ResolveAI છું. હું તમારી કેવી રીતે મદદ કરી શકું?",
        "ack": "ચોક્કસ, ગુજરાતીમાં વાત કરીએ! હું તમારી કેવી રીતે મદદ કરી શકું?",
    },
    "gujlish": {
        "canonical": "gujlish",
        "bcp47": "gu-IN",
        "display_name": "Gujlish",
        "script": "latin",
        "is_code_mixed": True,
        "greeting": "Namaste! Hu ResolveAI chhu. Hu tamari kevi rite madad kari shaku?",
        "ack": "Chokkas, Gujarati-ma vaat kariye! Hu tamari kevi rite madad kari shaku?",
    },
    "punjabi": {
        "canonical": "punjabi",
        "bcp47": "pa-IN",
        "display_name": "Punjabi",
        "script": "gurmukhi",
        "is_code_mixed": False,
        "greeting": "ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ! ਮੈਂ ResolveAI ਹਾਂ। ਮੈਂ ਤੁਹਾਡੀ ਕੀ ਮਦਦ ਕਰ ਸਕਦਾ ਹਾਂ?",
        "ack": "ਜ਼ਰੂਰ, ਪੰਜਾਬੀ ਵਿੱਚ ਗੱਲ ਕਰਦੇ ਹਾਂ! ਮੈਂ ਤੁਹਾਡੀ ਕੀ ਮਦਦ ਕਰ ਸਕਦਾ ਹਾਂ?",
    },
    "punglish": {
        "canonical": "punglish",
        "bcp47": "pa-IN",
        "display_name": "Punglish",
        "script": "latin",
        "is_code_mixed": True,
        "greeting": "Sat Sri Akal! Main ResolveAI haan. Main tuhadi ki madad kar sakda haan?",
        "ack": "Zaroor, Punjabi-vich gal karde haan! Main tuhadi ki madad kar sakda haan?",
    },
    "odia": {
        "canonical": "odia",
        "bcp47": "od-IN",
        "display_name": "Odia",
        "script": "odia",
        "is_code_mixed": False,
        "greeting": "ନମସ୍କାର! ମୁଁ ResolveAI. ମୁଁ ଆପଣଙ୍କୁ କିପରି ସାହାଯ୍ୟ କରିପାରିବି?",
        "ack": "ନିଶ୍ଚିତ ଭାବରେ, ଓଡ଼ିଆରେ କଥାବାର୍ତ୍ତା କରିବା! ମୁଁ ଆପଣଙ୍କୁ କିପରି ସାହାଯ୍ୟ କରିପାରିବି?",
    },
    "assamese": {
        "canonical": "assamese",
        "bcp47": "as-IN",
        "display_name": "Assamese",
        "script": "bengali",
        "is_code_mixed": False,
        "greeting": "নমস্কাৰ! মই ResolveAI. মই আপোনাক কেনেকৈ সহায় কৰিব পাৰোঁ?",
        "ack": "নিশ্চয়, অসমীয়াত কথা পাতোঁ আহক! মই আপোনাক কেনেকৈ সহায় কৰিব পাৰোঁ?",
    },
    "urdu": {
        "canonical": "urdu",
        "bcp47": "ur-IN",
        "display_name": "Urdu",
        "script": "arabic",
        "is_code_mixed": False,
        "greeting": "السلام علیکم! میں ResolveAI ہوں۔ میں آپ کی کیا مدد کر سکتا ہوں؟",
        "ack": "ضرور، اردو میں بات کرتے ہیں۔ میں آپ کی کیا مدد کر سکتا ہوں؟",
    },
    "nepali": {
        "canonical": "nepali",
        "bcp47": "ne-NP",
        "display_name": "Nepali",
        "script": "devanagari",
        "is_code_mixed": False,
        "greeting": "नमस्ते! म ResolveAI हुँ। म तपाईंलाई कसरी सहयोग गर्न सक्छु?",
        "ack": "अवश्य, नेपालीमा कुरा गरौं! म तपाईंलाई कसरी सहयोग गर्न सक्छु?",
    },
}

# Known unsupported foreign languages
UNSUPPORTED_FOREIGN_LANGUAGES: Dict[str, str] = {
    "french": "French",
    "francais": "French",
    "spanish": "Spanish",
    "espanol": "Spanish",
    "german": "German",
    "deutsch": "German",
    "italian": "Italian",
    "portuguese": "Portuguese",
    "russian": "Russian",
    "japanese": "Japanese",
    "chinese": "Chinese",
    "mandarin": "Mandarin",
    "arabic": "Arabic",
    "korean": "Korean",
    "dutch": "Dutch",
    "turkish": "Turkish",
}

# Indian languages with text chat capability but no voice STT/TTS models deployed
TEXT_ONLY_INDIAN_LANGUAGES: Dict[str, str] = {
    "bodo": "Bodo",
    "dogri": "Dogri",
    "santali": "Santali",
    "maithili": "Maithili",
    "kashmiri": "Kashmiri",
    "konkani": "Konkani",
    "manipuri": "Manipuri",
    "sanskrit": "Sanskrit",
    "sindhi": "Sindhi",
}

UNSUPPORTED_LANGUAGES: Dict[str, str] = {
    **UNSUPPORTED_FOREIGN_LANGUAGES,
    **TEXT_ONLY_INDIAN_LANGUAGES,
}

# Common English grammatical structure words
ENGLISH_GRAMMAR_WORDS = {
    "i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us", "them",
    "my", "your", "his", "her", "its", "our", "their", "mine", "yours", "ours",
    "is", "am", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "having",
    "do", "does", "did", "done", "doing",
    "can", "could", "will", "would", "shall", "should", "may", "might", "must",
    "the", "a", "an", "this", "that", "these", "those",
    "in", "on", "at", "to", "for", "with", "from", "by", "about", "of", "into", "through",
    "and", "or", "but", "if", "not", "so", "as", "than", "then", "because",
    "what", "where", "when", "why", "how", "who", "which",
    "there", "here", "just", "now", "please", "help", "need", "want", "check",
    "order", "status", "delivery", "shipping", "track", "tracking", "package",
    "item", "items", "cancel", "refund", "return", "product", "account", "login",
}

# Tanglish vocabulary markers
TANGLISH_MARKERS = {
    "enna", "eppadi", "eppo", "enga", "edhukku", "ethuku", "yen", "yaar",
    "pannunga", "pannala", "panna", "panniten", "panten", "panren",
    "varala", "varave", "vandhuduchu", "vandhuruchu", "varum", "vandha",
    "innum", "aagala", "aagiduchu", "aagudhu", "irukku", "illa", "illai",
    "kedaikala", "kidaikala", "solla", "sollunga", "solren", "solli",
    "kudunga", "paaru", "paarunga", "konjam", "romba", "seri", "kandippa",
    "enakku", "unakku", "ungalukku", "namma", "naan", "neenga", "adhu", "idhu",
    "duddu", "panam", "kaasu", "pesalam", "pesunga", "theriyanum", "puriyala",
}

# Hinglish vocabulary markers
HINGLISH_MARKERS = {
    "kya", "kaise", "kab", "kahan", "kyun", "kaun",
    "karo", "kijiye", "karunga", "kar", "kiya", "karein",
    "aaya", "aayega", "aayi", "mila", "milega", "mili",
    "nahi", "nahin", "mat", "hua", "hoga", "hai", "hain", "hoon", "tha", "the",
    "mera", "meri", "mere", "aapka", "aapki", "aapke", "tumhara",
    "batao", "bataiye", "boliye", "baat", "chahiye", "thoda", "bohot", "bahut",
    "paise", "rupaye", "samajh", "theek", "bilkul", "abhi", "tak", "jaldi",
}


@dataclass
class VoiceLanguagePolicy:
    """
    Session-level voice language policy.
    Maintained consistently across turns within a single voice call.
    """
    default_language: str = "english"
    response_language: str = "english"
    customer_language_preference: Optional[str] = None  # e.g., "explicit:tamil", "explicit:english", "implicit:tanglish", None
    language_style: str = "conversational"              # "formal", "conversational", "code-mixed"
    language_switch_pending: bool = False
    language_confidence: float = 1.0
    consecutive_turns_in_language: int = 1
    unsupported_requested_language: Optional[str] = None
    bcp47_code: str = "en-IN"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VoiceLanguagePolicy":
        valid = {
            "default_language", "response_language", "customer_language_preference",
            "language_style", "language_switch_pending", "language_confidence",
            "consecutive_turns_in_language", "unsupported_requested_language",
            "bcp47_code"
        }
        filtered = {k: v for k, v in data.items() if k in valid}
        return cls(**filtered)


class VoiceLanguageController:
    """
    Stateful controller managing voice language decisions, sticky preferences,
    and customer-controlled language switching.
    """

    @classmethod
    def normalize_language_name(cls, raw: Optional[str]) -> str:
        """Normalizes any language string to its canonical supported key."""
        if not raw:
            return "english"
        r = raw.strip().lower()
        if r in ("en", "en-in", "en-us", "english"):
            return "english"
        if r in ("ta", "ta-in", "tamil"):
            return "tamil"
        if r in ("tanglish", "ta-en", "tamil_english"):
            return "tanglish"
        if r in ("hi", "hi-in", "hindi"):
            return "hindi"
        if r in ("hinglish", "hi-en", "hindi_english"):
            return "hinglish"
        if r in ("kn", "kn-in", "kannada"):
            return "kannada"
        if r in ("kanglish", "kn-en", "kannada_english", "kannadish"):
            return "kanglish"
        if r in ("te", "te-in", "telugu"):
            return "telugu"
        if r in ("tenglish", "te-en", "telugu_english"):
            return "tenglish"
        if r in ("ml", "ml-in", "malayalam"):
            return "malayalam"
        if r in ("manglish", "ml-en", "malayalam_english"):
            return "manglish"
        if r in ("bn", "bn-in", "bengali", "bangla"):
            return "bengali"
        if r in ("benglish", "bn-en", "bengali_english"):
            return "benglish"
        if r in ("mr", "mr-in", "marathi"):
            return "marathi"
        if r in ("marathish", "mr-en", "marathi_english"):
            return "marathish"
        if r in ("gu", "gu-in", "gujarati"):
            return "gujarati"
        if r in ("gujlish", "gu-en", "gujarati_english"):
            return "gujlish"
        if r in ("pa", "pa-in", "punjabi"):
            return "punjabi"
        if r in ("punglish", "pa-en", "punjabi_english"):
            return "punglish"
        if r in ("od", "or", "od-in", "or-in", "odia", "oriya"):
            return "odia"
        if r in ("as", "as-in", "assamese", "axomiya"):
            return "assamese"
        if r in ("ur", "ur-in", "urdu"):
            return "urdu"
        if r in ("ne", "ne-np", "ne-in", "nepali"):
            return "nepali"
        return "english"

    @classmethod
    def get_bcp47(cls, language: str) -> str:
        """Maps canonical or raw language name to BCP-47 for TTS / STT."""
        norm = cls.normalize_language_name(language)
        return SUPPORTED_LANGUAGES.get(norm, SUPPORTED_LANGUAGES["english"])["bcp47"]

    @classmethod
    def from_conversation(
        cls,
        conversation: Any,
        session_context: Optional[dict] = None
    ) -> VoiceLanguagePolicy:
        """
        Initializes or restores the session-level voice language policy.
        Rule 1: Always starts in English by default unless explicit saved customer
        preference or call-level selection exists.
        """
        ctx = session_context or {}
        explicit_saved = getattr(conversation, "preferred_language", None) or ctx.get("preferred_language")

        if explicit_saved and explicit_saved.lower() not in ("none", "", "null"):
            norm = cls.normalize_language_name(explicit_saved)
            style = "code-mixed" if norm in ("tanglish", "hinglish") else "conversational"
            return VoiceLanguagePolicy(
                default_language="english",
                response_language=norm,
                customer_language_preference=f"saved:{norm}",
                language_style=style,
                language_confidence=1.0,
                consecutive_turns_in_language=1,
                bcp47_code=cls.get_bcp47(norm),
            )

        # Default: English
        return VoiceLanguagePolicy(
            default_language="english",
            response_language="english",
            customer_language_preference=None,
            language_style="conversational",
            language_confidence=1.0,
            consecutive_turns_in_language=1,
            bcp47_code="en-IN",
        )

    @classmethod
    def detect_explicit_request(cls, text: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Detects explicit language requests in customer speech.
        Returns:
            (supported_language_or_none, unsupported_language_name_or_none)
        """
        if not text:
            return None, None

        t = text.lower().strip()
        t_clean = re.sub(r"[^\w\s\u0B80-\u0BFF\u0900-\u097F\u0C00-\u0C7F\u0C80-\u0CFF\u0D00-\u0D7F\u0980-\u09FF\u0A80-\u0AFF\u0A00-\u0A7F\u0B00-\u0B7F\u0600-\u06FF]", " ", t)
        t_clean = " ".join(t_clean.split())

        # 0. Check for Unsupported Languages (Foreign or text-only)
        for unsupp_key, unsupp_name in UNSUPPORTED_LANGUAGES.items():
            patterns = [
                rf"\b(?:speak|talk|continue|switch|convert|translate)\s+(?:in|to)\s+{unsupp_key}\b",
                rf"\b(?:can\s+(?:you|we)\s+speak|do\s+you\s+speak|please\s+speak|can\s+(?:you|we)\s+talk)\s+(?:in\s+)?{unsupp_key}\b",
                rf"\b{unsupp_key}\s+(?:please|language|mein|me|la|te\s+ror)\b",
                rf"\b{unsupp_key}\s+(?:mein\s+baat\s+karo|te\s+ror\s+me)\b",
                rf"^{unsupp_key}\b",
                rf"\bparlez[- ]vous\s+{unsupp_key}\b",
                rf"\bsprechen\s+sie\s+{unsupp_key}\b",
            ]
            if unsupp_key in ("french", "francais"):
                patterns.append(r"\bparlez[- ]vous\b")
            if unsupp_key in ("german", "deutsch"):
                patterns.append(r"\bsprechen\s+sie\b")

            if any(re.search(pat, t_clean) for pat in patterns):
                logger.info(f"Explicit request for unsupported language detected: {unsupp_name}")
                return None, unsupp_name

        # 1. Cross-Language switch pattern: e.g. "Hindi se English mein switch karo"
        cross_switch = re.search(r"\b([a-zA-Z]+)\s+se\s+([a-zA-Z]+)\s+(?:mein\s+)?(?:switch|badlo|karo|change)\b", t_clean)
        if cross_switch:
            target_raw = cross_switch.group(2)
            target_norm = cls.normalize_language_name(target_raw)
            if target_norm in SUPPORTED_LANGUAGES:
                logger.info(f"Cross-language switch detected: from '{cross_switch.group(1)}' to '{target_norm}'")
                return target_norm, None

        # Helper to test comprehensive multilingual switch triggers
        def matches_lang(keys: List[str], extra_patterns: Optional[List[str]] = None, native_keywords: Optional[List[str]] = None) -> bool:
            if native_keywords and any(nk in text for nk in native_keywords):
                return True
            for k in keys:
                pats = [
                    # Direct English requests (with or without 'in/to')
                    rf"\b(?:switch|change|convert|translate)\s+(?:language\s+)?(?:in|to)\s+{k}\b",
                    rf"\b(?:speak|talk|continue|converse)\s+(?:in\s+)?{k}\b",
                    rf"\b(?:can\s+you\s+speak|do\s+you\s+speak|please\s+speak)\s+(?:in\s+)?{k}\b",
                    rf"\bi\s+want\s+to\s+speak\s+(?:in\s+)?{k}\b",
                    rf"\b{k}\s+please\b",
                    rf"\b{k}\s+language\b",
                    rf"\bnow\s+speak\s+(?:in\s+)?{k}\b",
                    rf"^{k}\b",
                    # Cross-lingual Tanglish / Tamil phrases
                    rf"\b{k}\s+(?:la\s+pesu|la\s+pesunga|la\s+pesalam|le\s+pesu|pesu|la\s+sollunga|la|le)\b",
                    # Cross-lingual Hindi / Hinglish phrases
                    rf"\b{k}\s+(?:mein\s+bolo|mein\s+baat\s+karo|mein\s+boliye|me\s+bolo|mein|me)\b",
                    # Cross-lingual Telugu phrases
                    rf"\b{k}\s+(?:lo\s+matladu|lo\s+matladandi|lo\s+cheppandi|matladu|lo)\b",
                    # Cross-lingual Kannada phrases
                    rf"\b{k}\s+(?:dalli\s+mathadi|dalli\s+maatadi|dalli\s+heli|mathadi|maatadi|dalli)\b",
                    rf"\b{k}dalli\s+(?:mathadi|maatadi|heli)\b",
                    # Cross-lingual Malayalam phrases
                    rf"\b{k}\s+(?:il\s+samsarikku|il\s+samsarikkamo|il\s+samsarikkumo|samsarikku|samsarikkamo|il)\b",
                    rf"\b{k}-?il\s+(?:samsarikku|samsarikkamo)\b",
                    # Cross-lingual Marathi phrases
                    rf"\b{k}\s+(?:madhe\s+bola|t\s+bola|madhe|bola)\b",
                    # Cross-lingual Gujarati phrases
                    rf"\b{k}\s+(?:ma\s+bolo|ma\s+vaat\s+karo|ma)\b",
                    # Cross-lingual Punjabi phrases
                    rf"\b{k}\s+(?:vich\s+gal\s+karo|ch\s+gal\s+karo|vich)\b",
                    # Cross-lingual Odia phrases
                    rf"\b{k}\s+(?:re\s+katha\s+kuha|re)\b",
                ]
                if any(re.search(p, t_clean) for p in pats):
                    return True
            if extra_patterns:
                if any(re.search(ep, t_clean) for ep in extra_patterns):
                    return True
            return False

        # 2. English Explicit Switch (Rule 8: Return to English)
        if matches_lang(
            ["english"],
            extra_patterns=[
                r"\bback\s+to\s+english\b",
                r"\bswitch\s+(?:back\s+)?to\s+english\b",
                r"\benglish\s+la\s+pesalam\b",
            ],
            native_keywords=["ஆங்கிலம்", "angilam"]
        ):
            return "english", None

        # Code-mixed specific checks first (if customer specifically says "kanglish", "tenglish", etc.)
        if matches_lang(["kanglish"]):
            return "kanglish", None
        if matches_lang(["tenglish"]):
            return "tenglish", None
        if matches_lang(["manglish"]):
            return "manglish", None
        if matches_lang(["tanglish"]):
            return "tanglish", None
        if matches_lang(["hinglish"]):
            return "hinglish", None
        if matches_lang(["benglish"]):
            return "benglish", None
        if matches_lang(["marathish"]):
            return "marathish", None
        if matches_lang(["gujlish"]):
            return "gujlish", None
        if matches_lang(["punglish"]):
            return "punglish", None

        # 3. Kannada Explicit Switch (Tier 1 Priority)
        if matches_lang(
            ["kannada"],
            extra_patterns=[
                r"\bkannadadalli\s+(?:mathadi|maatadi|heli)\b",
                r"\bkannadalli\s+(?:mathadi|maatadi|heli)\b",
                r"\bkannada\s+mathadona\b",
            ],
            native_keywords=["ಕನ್ನಡ", "ಕನ್ನಡದಲ್ಲಿ"]
        ):
            return "kannada", None

        # 4. Telugu Explicit Switch (Tier 1 Priority)
        if matches_lang(
            ["telugu"],
            extra_patterns=[
                r"\btelugulo\s+(?:matladandi|matladu|cheppandi)\b",
                r"\btelugu\s+matladadam\b",
            ],
            native_keywords=["తెలుగు", "తెలుగులో"]
        ):
            return "telugu", None

        # 5. Malayalam Explicit Switch (Tier 1 Priority)
        if matches_lang(
            ["malayalam"],
            extra_patterns=[
                r"\bmalayalamil\s+(?:samsarikku|samsarikkamo|samsarikkumo)\b",
                r"\bmalayalam\s+samsarikkam\b",
            ],
            native_keywords=["മലയാളം", "മലയാളത്തിൽ"]
        ):
            return "malayalam", None

        # 6. Tamil Explicit Switch
        if matches_lang(
            ["tamil"],
            extra_patterns=[r"\btamilil\s+pesavum\b", r"\btamil\s+laye\b"],
            native_keywords=["தமிழ்", "தமிழ்ல", "தமிழில்"]
        ):
            return "tamil", None

        # 7. Hindi Explicit Switch
        if matches_lang(
            ["hindi"],
            extra_patterns=[r"\bnow\s+speak\s+in\s+hindi\b"],
            native_keywords=["हिन्दी", "हिंदी", "हिन्दी में", "हिंदी में"]
        ):
            return "hindi", None

        # 8. Bengali Explicit Switch (Tier 2 Priority)
        if matches_lang(
            ["bengali", "bangla"],
            extra_patterns=[r"\bbangla\s+te\s+kotha\s+bolun\b", r"\bbanglate\s+kotha\b"],
            native_keywords=["বাংলা", "বাংলায়"]
        ):
            return "bengali", None

        # 9. Marathi Explicit Switch (Tier 2 Priority)
        if matches_lang(
            ["marathi"],
            extra_patterns=[r"\bmarathi\s+madhe\s+bola\b", r"\bmarathit\s+bola\b"],
            native_keywords=["मराठी", "मराठीत"]
        ):
            return "marathi", None

        # 10. Gujarati Explicit Switch (Tier 2 Priority)
        if matches_lang(
            ["gujarati"],
            extra_patterns=[r"\bgujarati\s+ma\s+bolo\b", r"\bgujaratima\s+bolo\b"],
            native_keywords=["ગુજરાતી", "ગુજરાતીમાં"]
        ):
            return "gujarati", None

        # 11. Punjabi Explicit Switch (Tier 2 Priority)
        if matches_lang(
            ["punjabi"],
            extra_patterns=[r"\bpunjabi\s+vich\s+gal\s+karo\b", r"\bpunjabi\s+ch\s+gal\b"],
            native_keywords=["ਪੰਜਾਬੀ", "ਪੰਜਾਬੀ ਵਿੱਚ"]
        ):
            return "punjabi", None

        # 12. Odia Explicit Switch (Tier 3 Priority)
        if matches_lang(
            ["odia", "oriya"],
            extra_patterns=[r"\bodia\s+re\s+katha\s+kuha\b", r"\bodiare\s+katha\b"],
            native_keywords=["ଓଡ଼ିଆ", "ଓଡ଼ିଆରେ"]
        ):
            return "odia", None

        # 13. Assamese Explicit Switch (Tier 3 Priority)
        if matches_lang(
            ["assamese", "asomiya"],
            extra_patterns=[r"\bassamese\s+t\s+kotha\s+kowk\b"],
            native_keywords=["অসমীয়া", "অসমীয়াত"]
        ):
            return "assamese", None

        # 14. Urdu Explicit Switch (Tier 3 Priority)
        if matches_lang(
            ["urdu"],
            extra_patterns=[r"\burdu\s+mein\s+baat\s+kijiye\b", r"\burdu\s+mein\s+bolo\b"],
            native_keywords=["اردو", "اردو میں"]
        ):
            return "urdu", None

        # 15. Nepali Explicit Switch (Tier 3 Priority)
        if matches_lang(
            ["nepali"],
            extra_patterns=[r"\bnepali\s+ma\s+kura\s+gara\b"],
            native_keywords=["नेपाली"]
        ):
            return "nepali", None

        return None, None

    @classmethod
    def is_isolated_foreign_word_in_english(cls, words: List[str]) -> bool:
        """
        Rule 9: Checks if an utterance is predominantly English with isolated
        foreign words (e.g. 'dosa', 'kurta', 'masala', 'biryani').
        """
        if not words:
            return False

        word_count = len(words)
        english_gram_count = sum(1 for w in words if w in ENGLISH_GRAMMAR_WORDS)

        # If 3 or more English grammatical function words, or >= 60% English tokens
        if word_count >= 4 and english_gram_count >= 2:
            english_ratio = english_gram_count / word_count
            if english_ratio >= 0.40:
                return True

        return False

    @classmethod
    def evaluate_turn(
        cls,
        policy: VoiceLanguagePolicy,
        message: str,
        stt_metadata: Optional[dict] = None
    ) -> VoiceLanguagePolicy:
        """
        Evaluates a single customer turn and returns the updated VoiceLanguagePolicy.

        Enforces:
        - Rule 1: Starts in English by default.
        - Rule 2: Explicit switch requests switch immediately.
        - Rule 3 & 4: Sustained language preference persists across turns.
        - Rule 7: Isolated foreign words / product names DO NOT switch language.
        - Rule 8: Returns to English when customer switches back to English.
        - Rule 9: Noisy STT labels DO NOT switch language.
        - Rule 10: LLM response language is strictly locked.
        """
        new_policy = VoiceLanguagePolicy(
            default_language=policy.default_language,
            response_language=policy.response_language,
            customer_language_preference=policy.customer_language_preference,
            language_style=policy.language_style,
            language_switch_pending=False,
            language_confidence=policy.language_confidence,
            consecutive_turns_in_language=policy.consecutive_turns_in_language,
            unsupported_requested_language=None,
            bcp47_code=policy.bcp47_code,
        )

        clean_text = (message or "").strip()
        if not clean_text:
            return new_policy

        # Step 1: Check for Explicit Language Request (Top Priority)
        explicit_lang, unsupported_lang = cls.detect_explicit_request(clean_text)

        if unsupported_lang:
            logger.info(f"Customer requested unsupported language '{unsupported_lang}'")
            new_policy.unsupported_requested_language = unsupported_lang
            new_policy.language_confidence = 1.0
            return new_policy

        if explicit_lang:
            logger.info(f"Customer explicitly requested language switch to '{explicit_lang}'")
            # If explicit request is Tamil, decide style based on script/phrasing
            if explicit_lang == "tamil":
                # If typed in English letters ("Tamil la pesunga"), support conversational Tanglish/Tamil
                is_native_script = any("\u0B80" <= c <= "\u0BFF" for c in clean_text)
                target_lang = "tamil" if is_native_script else "tanglish"
            else:
                target_lang = explicit_lang

            new_policy.response_language = target_lang
            new_policy.customer_language_preference = f"explicit:{target_lang}"
            new_policy.language_style = "code-mixed" if target_lang in ("tanglish", "hinglish") else "conversational"
            new_policy.bcp47_code = cls.get_bcp47(target_lang)
            new_policy.consecutive_turns_in_language = 1
            new_policy.language_confidence = 1.0
            return new_policy

        # Step 2: Extract linguistic features
        msg_lower = clean_text.lower()
        words = re.findall(r"\b\w+\b", msg_lower)
        if not words:
            return new_policy

        # Check Native Indic Unicode Scripts
        has_tamil_script = any("\u0B80" <= c <= "\u0BFF" for c in clean_text)
        has_devanagari = any("\u0900" <= c <= "\u097F" for c in clean_text)
        has_telugu = any("\u0C00" <= c <= "\u0C7F" for c in clean_text)
        has_kannada = any("\u0C80" <= c <= "\u0CFF" for c in clean_text)
        has_malayalam = any("\u0D00" <= c <= "\u0D7F" for c in clean_text)
        has_bengali = any("\u0980" <= c <= "\u09FF" for c in clean_text)
        has_gujarati = any("\u0A80" <= c <= "\u0AFF" for c in clean_text)
        has_gurmukhi = any("\u0A00" <= c <= "\u0A7F" for c in clean_text)
        has_odia = any("\u0B00" <= c <= "\u0B7F" for c in clean_text)
        has_arabic = any("\u0600" <= c <= "\u06FF" for c in clean_text)

        # Word marker sets
        word_set = set(words)
        tanglish_hits = word_set & TANGLISH_MARKERS
        hinglish_hits = word_set & HINGLISH_MARKERS
        english_hits = word_set & ENGLISH_GRAMMAR_WORDS

        # Pan-Indian code-mixed markers from CodeMixedLanguageDetector
        from app.ai.intelligence.language import CodeMixedLanguageDetector
        kannada_hits = word_set & set(getattr(CodeMixedLanguageDetector, "KANNADA_MARKERS", {}).keys())
        telugu_hits = word_set & set(getattr(CodeMixedLanguageDetector, "TELUGU_MARKERS", {}).keys())
        malayalam_hits = word_set & set(getattr(CodeMixedLanguageDetector, "MALAYALAM_MARKERS", {}).keys())
        bengali_hits = word_set & set(getattr(CodeMixedLanguageDetector, "BENGALI_MARKERS", {}).keys())
        marathi_hits = word_set & set(getattr(CodeMixedLanguageDetector, "MARATHI_MARKERS", {}).keys())
        gujarati_hits = word_set & set(getattr(CodeMixedLanguageDetector, "GUJARATI_MARKERS", {}).keys())
        punjabi_hits = word_set & set(getattr(CodeMixedLanguageDetector, "PUNJABI_MARKERS", {}).keys())

        any_indic_marker = (
            tanglish_hits or hinglish_hits or kannada_hits or telugu_hits
            or malayalam_hits or bengali_hits or marathi_hits or gujarati_hits
            or punjabi_hits
        )
        any_indic_script = (
            has_tamil_script or has_devanagari or has_telugu or has_kannada
            or has_malayalam or has_bengali or has_gujarati or has_gurmukhi
            or has_odia or has_arabic
        )

        # Step 3: Guard against Isolated Foreign Words in English (Test 3)
        # e.g., "Can you check my dosa pan order?", "I ordered a kurta and delivery is delayed"
        if policy.response_language == "english":
            if cls.is_isolated_foreign_word_in_english(words):
                logger.info(f"Isolated foreign terms in English sentence; retaining English. ({words})")
                new_policy.consecutive_turns_in_language += 1
                return new_policy

            # Guard against Noisy STT label reporting Indic language for short English words (Test 5)
            # e.g. "Yes please", "Check tracking", "Hello"
            if len(words) <= 3 and len(english_hits) >= 1 and not (any_indic_script or any_indic_marker):
                logger.info(f"Short English utterance with potential noisy STT; retaining English. ('{clean_text}')")
                new_policy.consecutive_turns_in_language += 1
                return new_policy

        # Step 4: Check for Return to English (Test 4)
        # If the customer was previously speaking an Indic language, and now clearly speaks English:
        if policy.response_language != "english":
            is_clear_english = (
                len(words) >= 3
                and len(english_hits) >= 2
                and not (any_indic_script or any_indic_marker)
            )
            if is_clear_english:
                logger.info(f"Customer returned to English speech ('{clean_text}'); switching response language to English.")
                new_policy.response_language = "english"
                new_policy.customer_language_preference = "implicit:english"
                new_policy.language_style = "conversational"
                new_policy.bcp47_code = "en-IN"
                new_policy.consecutive_turns_in_language = 1
                new_policy.language_confidence = 0.95
                return new_policy

        # Step 5: Implicit Language Preference Adoption (Test 2, Test 6)
        # Native script triggers immediate adaptation
        if has_kannada and len(clean_text) >= 2:
            new_policy.response_language = "kannada"
            new_policy.customer_language_preference = "implicit:kannada"
            new_policy.bcp47_code = "kn-IN"
            new_policy.consecutive_turns_in_language = 1
            new_policy.language_confidence = 0.98
            return new_policy

        if has_telugu and len(clean_text) >= 2:
            new_policy.response_language = "telugu"
            new_policy.customer_language_preference = "implicit:telugu"
            new_policy.bcp47_code = "te-IN"
            new_policy.consecutive_turns_in_language = 1
            new_policy.language_confidence = 0.98
            return new_policy

        if has_malayalam and len(clean_text) >= 2:
            new_policy.response_language = "malayalam"
            new_policy.customer_language_preference = "implicit:malayalam"
            new_policy.bcp47_code = "ml-IN"
            new_policy.consecutive_turns_in_language = 1
            new_policy.language_confidence = 0.98
            return new_policy

        if has_tamil_script and len(clean_text) >= 2:
            new_policy.response_language = "tamil"
            new_policy.customer_language_preference = "implicit:tamil"
            new_policy.language_style = "formal"
            new_policy.bcp47_code = "ta-IN"
            new_policy.consecutive_turns_in_language = 1
            new_policy.language_confidence = 0.98
            return new_policy

        if has_bengali and len(clean_text) >= 2:
            new_policy.response_language = "bengali"
            new_policy.customer_language_preference = "implicit:bengali"
            new_policy.bcp47_code = "bn-IN"
            new_policy.consecutive_turns_in_language = 1
            new_policy.language_confidence = 0.98
            return new_policy

        if has_devanagari and len(clean_text) >= 2:
            target = "marathi" if marathi_hits else "hindi"
            new_policy.response_language = target
            new_policy.customer_language_preference = f"implicit:{target}"
            new_policy.language_style = "formal"
            new_policy.bcp47_code = "mr-IN" if target == "marathi" else "hi-IN"
            new_policy.consecutive_turns_in_language = 1
            new_policy.language_confidence = 0.98
            return new_policy

        if has_gujarati and len(clean_text) >= 2:
            new_policy.response_language = "gujarati"
            new_policy.customer_language_preference = "implicit:gujarati"
            new_policy.bcp47_code = "gu-IN"
            new_policy.consecutive_turns_in_language = 1
            new_policy.language_confidence = 0.98
            return new_policy

        if has_gurmukhi and len(clean_text) >= 2:
            new_policy.response_language = "punjabi"
            new_policy.customer_language_preference = "implicit:punjabi"
            new_policy.bcp47_code = "pa-IN"
            new_policy.consecutive_turns_in_language = 1
            new_policy.language_confidence = 0.98
            return new_policy

        if has_odia and len(clean_text) >= 2:
            new_policy.response_language = "odia"
            new_policy.customer_language_preference = "implicit:odia"
            new_policy.bcp47_code = "od-IN"
            new_policy.consecutive_turns_in_language = 1
            new_policy.language_confidence = 0.98
            return new_policy

        # Code-mixed candidate scoring with hit count and session continuity ranking
        cm_candidates = [
            ("marathish", marathi_hits, "mr-IN", ["ajun", "aala nahi", "kela nahi", "pahije", "saanga", "majha", "majhi", "majhe", "aala"]),
            ("benglish", bengali_hits, "bn-IN", ["asheni", "aseni", "ekhono", "korini", "lagbe", "bolun", "aamar"]),
            ("gujlish", gujarati_hits, "gu-IN", ["nathi aavyo", "haji sudhi", "nathi karyu", "joie", "kaho"]),
            ("punglish", punjabi_hits, "pa-IN", ["nahi aaya", "aje tak", "nahi kita", "chahida", "dasso"]),
            ("kanglish", kannada_hits, "kn-IN", ["bandilla", "innu", "nanage", "maadiddini", "madilla", "baralla", "aagilla", "hege", "beku", "heli", "nimma", "yenu"]),
            ("tenglish", telugu_hits, "te-IN", ["raledu", "inka", "naaku", "chesanu", "cheyaledu", "kavali", "cheppandi", "mee"]),
            ("manglish", malayalam_hits, "ml-IN", ["vannilla", "ithuvare", "enikku", "cheythu", "cheythilla", "venam", "parayamo", "kittiyilla", "njangalude"]),
            ("tanglish", tanglish_hits, "ta-IN", ["varala", "innum", "pannunga", "sollunga", "kedaikala", "theriyanum", "pesalam"]),
            ("hinglish", hinglish_hits, "hi-IN", ["nahi", "aaya", "milega", "chahiye", "karo", "batao", "mera", "meri", "mere"]),
        ]

        scored_candidates = []
        for lang_name, hits, bcp, strong_markers in cm_candidates:
            if not hits:
                continue
            ratio = len(hits) / len(words)
            has_strong = any(k in word_set for k in strong_markers)
            if len(hits) >= 2 or ratio >= 0.20 or has_strong:
                score = float(len(hits)) * 2.0
                if has_strong:
                    score += 2.0
                if policy.response_language.startswith(lang_name[:4]):
                    score += 5.0
                if lang_name != "hinglish":
                    score += 0.5
                scored_candidates.append((score, lang_name, hits, bcp))

        if scored_candidates:
            scored_candidates.sort(key=lambda x: x[0], reverse=True)
            best_score, best_lang, best_hits, best_bcp = scored_candidates[0]
            logger.info(f"Sustained {best_lang.capitalize()} detected (score={best_score}, hits={best_hits}); setting response language to {best_lang.capitalize()}.")
            new_policy.response_language = best_lang
            new_policy.customer_language_preference = f"implicit:{best_lang}"
            new_policy.language_style = "code-mixed"
            new_policy.bcp47_code = best_bcp
            new_policy.consecutive_turns_in_language = 1
            new_policy.language_confidence = 0.95
            return new_policy

        # Step 6: Multi-Turn Stability — Retain Active Response Language (Test 7)
        # For ambiguous, neutral, or unclassified turns, preserve existing policy
        new_policy.consecutive_turns_in_language += 1
        return new_policy

    @classmethod
    def get_unsupported_language_message(cls, requested_lang: str, current_lang: str = "english") -> str:
        """
        Rule 9: Explains that the requested language is unsupported and lists supported alternatives.
        Truthfully distinguishes between unsupported foreign languages and text-only Indian languages.
        """
        curr = cls.normalize_language_name(current_lang)
        req_lower = requested_lang.lower().strip()
        supported_list = "English, Kannada, Telugu, Malayalam, Tamil, Tanglish, Hindi, Hinglish, Bengali, Marathi, Gujarati, Punjabi, Odia, or Assamese"

        is_text_only = req_lower in TEXT_ONLY_INDIAN_LANGUAGES

        if is_text_only:
            if curr == "tanglish":
                return (
                    f"{requested_lang} mozhi chat-la support aagum, aana voice call-la innum varala bro. "
                    "Voice-la naan English, Kannada, Telugu, Malayalam, Tamil, matrum Hindi support panren. "
                    "Indha mozhigalil continue pannalama?"
                )
            elif curr == "kannada" or curr == "kanglish":
                return (
                    f"{requested_lang} bhasha text chat-alli ide, aadre voice call-alli innu labhyavilla. "
                    "Voice call-alli naan Kannada, Telugu, Malayalam, Tamil, Hindi athava English-alli mathadabahudu. "
                    "Kannada-dalli munde varisabahuda?"
                )
            elif curr == "telugu" or curr == "tenglish":
                return (
                    f"{requested_lang} bhasha text chat lo undi, kani voice call lo inka ledu andi. "
                    "Voice call lo nenu Telugu, Kannada, Malayalam, Tamil, Hindi leda English lo matladagalanu. "
                    "Telugu lo continue cheddama?"
                )
            elif curr in ("hindi", "hinglish"):
                return (
                    f"{requested_lang} bhasha text chat mein uplabdh hai, lekin voice call mein abhi uplabdh nahi hai. "
                    "Voice call mein main Hindi, Kannada, Telugu, Malayalam, Tamil ya English mein baat kar sakta hoon. "
                    "Kya hum inme se kisi bhasha mein baat karein?"
                )
            return (
                f"I can understand {requested_lang} with text support in chat, but full voice conversation is not yet available for it. "
                f"I can assist you by voice in {supported_list}. "
                "Would you like to continue in one of our supported voice languages?"
            )

        # Unsupported foreign language
        if curr == "tanglish":
            return (
                f"Mannikavum, ennala {requested_lang}-la pesa mudiyadhu. "
                "Naan English, Kannada, Telugu, Malayalam, Tamil, Tanglish, Hindi, matrum Hinglish-la support panren. "
                "Neenga English-layo illa ungalukku viruppamana mozhiyilo continue panna virumbureengala?"
            )
        elif curr == "kannada" or curr == "kanglish":
            return (
                f"Kshamisi, nanninda {requested_lang}-alli mathadalu sadhyavilla. "
                "Naanu Kannada, Telugu, Malayalam, Tamil, Hindi athava English-alli sahayavannu madabahudu. "
                "Naavu Kannada athava English-alli munde varisabahuda?"
            )
        elif curr == "telugu" or curr == "tenglish":
            return (
                f"Kshaminchandi, nenu {requested_lang} lo matladalenu. "
                "Nenu Telugu, Kannada, Malayalam, Tamil, Hindi mariyu English lo sahayam cheyagalanu. "
                "Manam Telugu leda English lo continue cheddama?"
            )
        elif curr in ("tamil",):
            return (
                f"மன்னிக்கவும், என்னால் {requested_lang} மொழியில் பேச முடியாது. "
                "நான் ஆங்கிலம், கன்னடம், தெலுங்கு, மலையாளம், தமிழ் மற்றும் இந்தி மொழிகளில் குரல் ஆதரவு தருகிறேன். "
                "நாம் ஆங்கிலத்திலோ அல்லது தமிழிலோ தொடரலாமா?"
            )
        elif curr in ("hindi", "hinglish"):
            return (
                f"Maaf kijiye, main {requested_lang} mein baat nahi kar sakta. "
                "Main English, Hindi, Kannada, Telugu, Malayalam, Tamil, Bengali, Marathi, Gujarati, aur Punjabi support karta hoon. "
                "Kya hum English ya Hindi mein continue kar sakte hain?"
            )
        return (
            f"I apologize, but I currently do not support {requested_lang}. "
            f"I can speak {supported_list}. "
            "Would you like to continue in English or one of our supported languages?"
        )

    @classmethod
    def format_llm_system_instructions(cls, policy: VoiceLanguagePolicy) -> str:
        """
        Constructs rigid, authoritative LLM system instructions to enforce the active language.
        Prevents LLMs from arbitrarily switching language on turn N.
        """
        lang = policy.response_language

        if lang == "kannada":
            return (
                "CRITICAL MANDATORY VOICE LANGUAGE DIRECTIVE:\n"
                "- The customer's chosen language is KANNADA (ಕನ್ನಡ).\n"
                "- You MUST respond EXCLUSIVELY in clear, respectful, natural Kannada script (ಕನ್ನಡ).\n"
                "- Example: 'ಖಂಡಿತ! ನಿಮ್ಮ ಆರ್ಡರ್ ಸ್ಥಿತಿಯನ್ನು ಪರಿಶೀಲಿಸಲು ನಿಮ್ಮ ಆರ್ಡರ್ ಐಡಿಯನ್ನು ತಿಳಿಸಿ.'\n"
                "- Do NOT switch languages unless the customer explicitly requests it."
            )
        elif lang == "kanglish":
            return (
                "CRITICAL MANDATORY VOICE LANGUAGE DIRECTIVE:\n"
                "- The customer's chosen language is KANGLISH (Kannada words written phonetically in English/Latin letters).\n"
                "- You MUST respond EXCLUSIVELY in natural, conversational KANGLISH using the English alphabet.\n"
                "- Example: 'Khanditha check maadthene! Nimma Order ID heli, status thilisthene.'\n"
                "- NEVER respond in native Kannada script (ಕನ್ನಡ).\n"
                "- Do NOT switch languages unless the customer explicitly requests it."
            )
        elif lang == "telugu":
            return (
                "CRITICAL MANDATORY VOICE LANGUAGE DIRECTIVE:\n"
                "- The customer's chosen language is TELUGU (తెలుగు).\n"
                "- You MUST respond EXCLUSIVELY in clear, respectful, natural Telugu script (తెలుగు).\n"
                "- Example: 'తప్పకుండా! మీ ఆర్డర్ స్థితిని తనిఖీ చేయడానికి దయచేసి మీ ఆర్డర్ ఐడీని చెప్పండి.'\n"
                "- Do NOT switch languages unless the customer explicitly requests it."
            )
        elif lang == "tenglish":
            return (
                "CRITICAL MANDATORY VOICE LANGUAGE DIRECTIVE:\n"
                "- The customer's chosen language is TENGLISH (Telugu words written phonetically in English/Latin letters).\n"
                "- You MUST respond EXCLUSIVELY in natural, conversational TENGLISH using the English alphabet.\n"
                "- Example: 'Thappakunda check chesthanu! Mee Order ID cheppandi, status chepthanu.'\n"
                "- NEVER respond in native Telugu script (తెలుగు).\n"
                "- Do NOT switch languages unless the customer explicitly requests it."
            )
        elif lang == "malayalam":
            return (
                "CRITICAL MANDATORY VOICE LANGUAGE DIRECTIVE:\n"
                "- The customer's chosen language is MALAYALAM (മലയാളം).\n"
                "- You MUST respond EXCLUSIVELY in clear, respectful, natural Malayalam script (മലയാളം).\n"
                "- Example: 'തീർച്ചയായും! നിങ്ങളുടെ ഓർഡർ നില പരിശോധിക്കാൻ ദയവായി ഓർഡർ ഐഡി നൽകുക.'\n"
                "- Do NOT switch languages unless the customer explicitly requests it."
            )
        elif lang == "manglish":
            return (
                "CRITICAL MANDATORY VOICE LANGUAGE DIRECTIVE:\n"
                "- The customer's chosen language is MANGLISH (Malayalam words written phonetically in English/Latin letters).\n"
                "- You MUST respond EXCLUSIVELY in natural, conversational MANGLISH using the English alphabet.\n"
                "- Example: 'Theerchayayum check cheyyam! Ningalude Order ID parayamo, status parayam.'\n"
                "- NEVER respond in native Malayalam script (മലയാളം).\n"
                "- Do NOT switch languages unless the customer explicitly requests it."
            )
        elif lang == "bengali":
            return (
                "CRITICAL MANDATORY VOICE LANGUAGE DIRECTIVE:\n"
                "- The customer's chosen language is BENGALI (বাংলা).\n"
                "- You MUST respond EXCLUSIVELY in clear, respectful Bengali script (বাংলা).\n"
                "- Example: 'অবশ্যই! আপনার অর্ডারের স্থিতি দেখতে দয়া করে অর্ডার আইডি জানান।'\n"
                "- Do NOT switch languages unless the customer explicitly requests it."
            )
        elif lang == "benglish":
            return (
                "CRITICAL MANDATORY VOICE LANGUAGE DIRECTIVE:\n"
                "- The customer's chosen language is BENGLISH (Bengali words written phonetically in English/Latin letters).\n"
                "- You MUST respond EXCLUSIVELY in conversational BENGLISH using the English alphabet.\n"
                "- Example: 'Obosshoi check korchi! Apnar Order ID bolun, status janachi.'\n"
                "- Do NOT switch languages unless the customer explicitly requests it."
            )
        elif lang == "marathi":
            return (
                "CRITICAL MANDATORY VOICE LANGUAGE DIRECTIVE:\n"
                "- The customer's chosen language is MARATHI (मराठी).\n"
                "- You MUST respond EXCLUSIVELY in clear, respectful Marathi script (मराठी).\n"
                "- Example: 'नक्कीच! तुमच्या ऑर्डरची स्थिती तपासण्यासाठी कृपया ऑर्डर आयडी सांगा.'\n"
                "- Do NOT switch languages unless the customer explicitly requests it."
            )
        elif lang == "marathish":
            return (
                "CRITICAL MANDATORY VOICE LANGUAGE DIRECTIVE:\n"
                "- The customer's chosen language is MARATHISH (Marathi words written phonetically in English/Latin letters).\n"
                "- You MUST respond EXCLUSIVELY in conversational MARATHISH using the English alphabet.\n"
                "- Example: 'Nakkich check karto! Tumcha Order ID saanga, status sangto.'\n"
                "- Do NOT switch languages unless the customer explicitly requests it."
            )
        elif lang == "gujarati":
            return (
                "CRITICAL MANDATORY VOICE LANGUAGE DIRECTIVE:\n"
                "- The customer's chosen language is GUJARATI (ગુજરાતી).\n"
                "- You MUST respond EXCLUSIVELY in clear, respectful Gujarati script (ગુજરાતી).\n"
                "- Example: 'ચોક્કસ! તમારા ઓર્ડરની સ્થિતિ તપાસવા માટે કૃપા કરીને ઓર્ડર આઈડી જણાવો.'\n"
                "- Do NOT switch languages unless the customer explicitly requests it."
            )
        elif lang == "gujlish":
            return (
                "CRITICAL MANDATORY VOICE LANGUAGE DIRECTIVE:\n"
                "- The customer's chosen language is GUJLISH (Gujarati words written phonetically in English/Latin letters).\n"
                "- You MUST respond EXCLUSIVELY in conversational GUJLISH using the English alphabet.\n"
                "- Example: 'Chokkas check kariye! Tamaro Order ID kaho, status janavu.'\n"
                "- Do NOT switch languages unless the customer explicitly requests it."
            )
        elif lang == "punjabi":
            return (
                "CRITICAL MANDATORY VOICE LANGUAGE DIRECTIVE:\n"
                "- The customer's chosen language is PUNJABI (ਪੰਜਾਬੀ).\n"
                "- You MUST respond EXCLUSIVELY in clear, respectful Punjabi Gurmukhi script (ਪੰਜਾਬੀ).\n"
                "- Example: 'ਜ਼ਰੂਰ! ਤੁਹਾਡੇ ਆਰਡਰ ਦੀ ਸਥਿਤੀ ਦੇਖਣ ਲਈ ਕਿਰਪਾ ਕਰਕੇ ਆਰਡਰ ਆਈਡੀ ਦੱਸੋ।'\n"
                "- Do NOT switch languages unless the customer explicitly requests it."
            )
        elif lang == "punglish":
            return (
                "CRITICAL MANDATORY VOICE LANGUAGE DIRECTIVE:\n"
                "- The customer's chosen language is PUNGLISH (Punjabi words written phonetically in English/Latin letters).\n"
                "- You MUST respond EXCLUSIVELY in conversational PUNGLISH using the English alphabet.\n"
                "- Example: 'Zaroor check karde haan! Apna Order ID dasso, status dassange.'\n"
                "- Do NOT switch languages unless the customer explicitly requests it."
            )
        elif lang == "odia":
            return (
                "CRITICAL MANDATORY VOICE LANGUAGE DIRECTIVE:\n"
                "- The customer's chosen language is ODIA (ଓଡ଼ିଆ).\n"
                "- You MUST respond EXCLUSIVELY in clear, respectful Odia script (ଓଡ଼ିଆ).\n"
                "- Example: 'ନିଶ୍ଚିତ! ଆପଣଙ୍କ ଅର୍ଡର ସ୍ଥିତି ଯାଞ୍ଚ କରିବାକୁ ଦୟାକରି ଅର୍ଡର ଆଇଡି କୁହନ୍ତୁ।'\n"
                "- Do NOT switch languages unless the customer explicitly requests it."
            )
        elif lang == "assamese":
            return (
                "CRITICAL MANDATORY VOICE LANGUAGE DIRECTIVE:\n"
                "- The customer's chosen language is ASSAMESE (অসমীয়া).\n"
                "- You MUST respond in clear, respectful Assamese script (অসমীয়া).\n"
                "- Do NOT switch languages unless the customer explicitly requests it."
            )
        elif lang == "urdu":
            return (
                "CRITICAL MANDATORY VOICE LANGUAGE DIRECTIVE:\n"
                "- The customer's chosen language is URDU (اردو).\n"
                "- You MUST respond in clear, respectful Urdu script (اردو).\n"
                "- Do NOT switch languages unless the customer explicitly requests it."
            )
        elif lang == "nepali":
            return (
                "CRITICAL MANDATORY VOICE LANGUAGE DIRECTIVE:\n"
                "- The customer's chosen language is NEPALI (नेपाली).\n"
                "- You MUST respond in clear, respectful Nepali Devanagari script (नेपाली).\n"
                "- Do NOT switch languages unless the customer explicitly requests it."
            )
        elif lang == "tanglish":
            return (
                "CRITICAL MANDATORY VOICE LANGUAGE DIRECTIVE:\n"
                "- The customer's chosen language is TANGLISH (Tamil words written in English letters).\n"
                "- You MUST respond EXCLUSIVELY in natural, conversational TANGLISH using the English alphabet (Latin script).\n"
                "- Example: 'Kandippa check panren! Unga Order ID kudunga, status solren.'\n"
                "- NEVER respond in native Tamil script (தமிழ்).\n"
                "- NEVER respond purely in English.\n"
                "- Do NOT switch languages unless the customer explicitly requests it."
            )
        elif lang == "tamil":
            return (
                "CRITICAL MANDATORY VOICE LANGUAGE DIRECTIVE:\n"
                "- The customer's chosen language is TAMIL (தமிழ்).\n"
                "- You MUST respond EXCLUSIVELY in proper, respectful Tamil script.\n"
                "- Example: 'நிச்சயமாக! உங்கள் ஆர்டர் நிலவரத்தை சரிபார்க்க ஆர்டர் எண்ணை தெரிவிக்கவும்.'\n"
                "- Do NOT switch languages unless the customer explicitly requests it."
            )
        elif lang == "hinglish":
            return (
                "CRITICAL MANDATORY VOICE LANGUAGE DIRECTIVE:\n"
                "- The customer's chosen language is HINGLISH (Hindi words written in English letters).\n"
                "- You MUST respond EXCLUSIVELY in natural, conversational HINGLISH using the English alphabet (Latin script).\n"
                "- Example: 'Bilkul! Main aapka order status check kar deta hoon. Kripya apna Order ID share karein.'\n"
                "- NEVER respond in Devanagari script (हिन्दी).\n"
                "- Do NOT switch languages unless the customer explicitly requests it."
            )
        elif lang == "hindi":
            return (
                "CRITICAL MANDATORY VOICE LANGUAGE DIRECTIVE:\n"
                "- The customer's chosen language is HINDI (हिन्दी).\n"
                "- You MUST respond EXCLUSIVELY in proper, respectful Hindi in Devanagari script.\n"
                "- Example: 'नमस्ते! मैं आपका ऑर्डर स्टेटस तुरंत देख लेता हूँ। कृपया अपना ऑर्डर आईडी बताएं।'\n"
                "- Do NOT switch languages unless the customer explicitly requests it."
            )
        else:
            return (
                "CRITICAL MANDATORY VOICE LANGUAGE DIRECTIVE:\n"
                "- The customer's chosen voice language is ENGLISH.\n"
                "- You MUST respond EXCLUSIVELY in clear, natural ENGLISH.\n"
                "- Even if the customer mentions Indian dishes, products, or brand names (e.g. 'dosa', 'kurta', 'masala'), "
                "do NOT switch away from English.\n"
                "- Speak in a helpful, conversational, professional voice tone."
            )

