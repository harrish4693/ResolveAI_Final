"""
Capability 6: Universal Multilingual Voice Understanding & Indian Code-Mixed Engine

Handles detection, normalization, negation preservation, and context-aware meaning
understanding from colloquial speech across Tamil, Tanglish, Hindi, Hinglish, English,
and supported mixed-language combinations.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


@dataclass
class LanguageInfo:
    """Metadata describing a supported language, script, locale and capabilities."""
    code: str                     # ISO 639-1 code (e.g. 'ta', 'te', 'hi', 'en')
    name: str                     # English name ('Tamil', 'Telugu', 'Hindi')
    native_name: str              # Endonym ('தமிழ்', 'తెలుగు', 'हिन्दी')
    script: str                   # Primary script ('tamil', 'telugu', 'devanagari', 'latin')
    code_mixed_name: str          # Name for code-mixed variety ('tanglish', 'telugu_english', 'hinglish')
    bcp47: str                    # BCP-47 locale tag ('ta-IN', 'te-IN', 'hi-IN', 'en-IN')
    family: str                   # Language family ('Dravidian', 'Indo-Aryan', 'Germanic', etc.)
    tier: str                     # 'core' (9 languages + English) or 'expanded' (13 languages)
    supported_text: bool = True
    supported_code_mixing: bool = True
    supported_stt: bool = True
    supported_tts: bool = True
    stt_provider_support: str = "sarvam,whisper,browser"
    tts_provider_support: str = "sarvam,browser"


class LanguageRegistry:
    """
    Central, extensible registry of supported Indian languages, scripts,
    BCP-47 locales, and model capabilities for ResolveAI V2.
    """
    _REGISTRY: Dict[str, LanguageInfo] = {
        # Core Rollout (9 Languages + English)
        "ta": LanguageInfo("ta", "Tamil", "தமிழ்", "tamil", "tanglish", "ta-IN", "Dravidian", "core", stt_provider_support="sarvam,whisper,browser", tts_provider_support="sarvam,browser"),
        "te": LanguageInfo("te", "Telugu", "తెలుగు", "telugu", "telugu_english", "te-IN", "Dravidian", "core", stt_provider_support="sarvam,whisper,browser", tts_provider_support="sarvam,browser"),
        "kn": LanguageInfo("kn", "Kannada", "ಕನ್ನಡ", "kannada", "kannada_english", "kn-IN", "Dravidian", "core", stt_provider_support="sarvam,whisper,browser", tts_provider_support="sarvam,browser"),
        "ml": LanguageInfo("ml", "Malayalam", "മലയാളം", "malayalam", "malayalam_english", "ml-IN", "Dravidian", "core", stt_provider_support="sarvam,whisper,browser", tts_provider_support="sarvam,browser"),
        "hi": LanguageInfo("hi", "Hindi", "हिन्दी", "devanagari", "hinglish", "hi-IN", "Indo-Aryan", "core", stt_provider_support="sarvam,whisper,browser", tts_provider_support="sarvam,browser"),
        "bn": LanguageInfo("bn", "Bengali", "বাংলা", "bengali", "bengali_english", "bn-IN", "Indo-Aryan", "core", stt_provider_support="sarvam,whisper,browser", tts_provider_support="sarvam,browser"),
        "mr": LanguageInfo("mr", "Marathi", "मराठी", "devanagari", "marathi_english", "mr-IN", "Indo-Aryan", "core", stt_provider_support="sarvam,whisper,browser", tts_provider_support="sarvam,browser"),
        "gu": LanguageInfo("gu", "Gujarati", "ગુજરાતી", "gujarati", "gujarati_english", "gu-IN", "Indo-Aryan", "core", stt_provider_support="sarvam,whisper,browser", tts_provider_support="sarvam,browser"),
        "pa": LanguageInfo("pa", "Punjabi", "ਪੰਜਾਬੀ", "gurmukhi", "punjabi_english", "pa-IN", "Indo-Aryan", "core", stt_provider_support="sarvam,whisper,browser", tts_provider_support="sarvam,browser"),
        "en": LanguageInfo("en", "English", "English", "latin", "english", "en-IN", "Germanic", "core", stt_provider_support="sarvam,whisper,browser", tts_provider_support="sarvam,browser"),

        # Expanded Rollout (13 Languages)
        "or": LanguageInfo("or", "Odia", "ଓଡ଼ିଆ", "odia", "odia_english", "or-IN", "Indo-Aryan", "expanded", supported_code_mixing=False, stt_provider_support="sarvam,whisper", tts_provider_support="sarvam"),
        "as": LanguageInfo("as", "Assamese", "অসমীয়া", "bengali", "assamese_english", "as-IN", "Indo-Aryan", "expanded", supported_code_mixing=False, stt_provider_support="whisper", tts_provider_support="browser"),
        "ur": LanguageInfo("ur", "Urdu", "اردو", "arabic", "urdu_english", "ur-IN", "Indo-Aryan", "expanded", supported_code_mixing=False, stt_provider_support="whisper,browser", tts_provider_support="browser"),
        "ks": LanguageInfo("ks", "Kashmiri", "کٲشُر", "arabic", "kashmiri_english", "ks-IN", "Indo-Aryan", "expanded", supported_code_mixing=False, stt_provider_support="whisper", tts_provider_support="none"),
        "kok": LanguageInfo("kok", "Konkani", "कोंकणी", "devanagari", "konkani_english", "kok-IN", "Indo-Aryan", "expanded", supported_code_mixing=False, stt_provider_support="whisper", tts_provider_support="none"),
        "mni": LanguageInfo("mni", "Manipuri", "মৈতৈলোন্", "bengali", "manipuri_english", "mni-IN", "Tibeto-Burman", "expanded", supported_code_mixing=False, stt_provider_support="whisper", tts_provider_support="none"),
        "ne": LanguageInfo("ne", "Nepali", "नेपाली", "devanagari", "nepali_english", "ne-IN", "Indo-Aryan", "expanded", supported_code_mixing=False, stt_provider_support="whisper,browser", tts_provider_support="browser"),
        "brx": LanguageInfo("brx", "Bodo", "बड़ो", "devanagari", "bodo_english", "brx-IN", "Tibeto-Burman", "expanded", supported_code_mixing=False, stt_provider_support="none", tts_provider_support="none"),
        "doi": LanguageInfo("doi", "Dogri", "डोगरी", "devanagari", "dogri_english", "doi-IN", "Indo-Aryan", "expanded", supported_code_mixing=False, stt_provider_support="none", tts_provider_support="none"),
        "sa": LanguageInfo("sa", "Sanskrit", "संस्कृतम्", "devanagari", "sanskrit_english", "sa-IN", "Indo-Aryan", "expanded", supported_code_mixing=False, stt_provider_support="whisper", tts_provider_support="browser"),
        "sat": LanguageInfo("sat", "Santali", "ᱥᱟᱱᱛᱟᱲᱤ", "ol_chiki", "santali_english", "sat-IN", "Austroasiatic", "expanded", supported_code_mixing=False, stt_provider_support="none", tts_provider_support="none"),
        "mai": LanguageInfo("mai", "Maithili", "मैथिली", "devanagari", "maithili_english", "mai-IN", "Indo-Aryan", "expanded", supported_code_mixing=False, stt_provider_support="whisper", tts_provider_support="none"),
        "sd": LanguageInfo("sd", "Sindhi", "سنڌي", "arabic", "sindhi_english", "sd-IN", "Indo-Aryan", "expanded", supported_code_mixing=False, stt_provider_support="whisper", tts_provider_support="none"),
    }

    @classmethod
    def get(cls, code: str) -> Optional[LanguageInfo]:
        """Fetch language metadata by ISO code."""
        return cls._REGISTRY.get(code.lower())

    @classmethod
    def get_by_name_or_code(cls, query: str) -> Optional[LanguageInfo]:
        """Lookup language by code, English name, or code-mixed variant name."""
        q = query.lower().strip()
        if q in cls._REGISTRY:
            return cls._REGISTRY[q]
        for info in cls._REGISTRY.values():
            if q in (info.name.lower(), info.code_mixed_name.lower(), info.bcp47.lower()):
                return info
        return None

    @classmethod
    def list_core(cls) -> List[LanguageInfo]:
        """Return all 9 core rollout languages plus English."""
        return [info for info in cls._REGISTRY.values() if info.tier == "core"]

    @classmethod
    def list_expanded(cls) -> List[LanguageInfo]:
        """Return all 13 expanded rollout languages."""
        return [info for info in cls._REGISTRY.values() if info.tier == "expanded"]

    @classmethod
    def register(cls, info: LanguageInfo) -> None:
        """Register or extend language support at runtime without modifying code."""
        cls._REGISTRY[info.code.lower()] = info


@dataclass
class LanguageDetectionResult:
    """Result of code-mixed language detection."""
    primary_language: str = "en"          # ISO code: en, ta, te, kn, ml, hi, bn, mr, gu, pa, etc.
    mixed_with: List[str] = field(default_factory=list)  # Additional languages detected
    is_code_mixed: bool = False
    code_mix_type: str = ""               # tanglish, telugu_english, hinglish, tamil, etc.
    confidence: float = 0.0
    script_types: List[str] = field(default_factory=list)  # latin, tamil, devanagari, telugu, kannada, etc.


@dataclass
class NormalizationResult:
    """Result of text normalization."""
    original: str = ""
    normalized: str = ""
    detected_slang: List[str] = field(default_factory=list)
    language_result: LanguageDetectionResult = field(default_factory=LanguageDetectionResult)


@dataclass
class UniversalMeaningUnderstanding:
    """
    Distinct, auditable representation of customer voice understanding.
    Separates:
    1. What the STT heard (raw_transcript)
    2. What the system believes the customer intended (understood_meaning & intent)
    3. How confident the system is in that interpretation (intent_confidence)
    4. Verified facts & diagnostic context (diagnostic_details)
    5. Negation, ambiguity, and clarification flags
    """
    raw_transcript: str = ""
    understood_meaning: str = ""
    normalized_meaning: str = ""
    normalized_search_query: str = ""
    primary_language: str = "en"
    detected_script: str = "latin"
    code_mix_type: str = "english"
    is_code_mixed: bool = False
    intent: str = "GENERAL_QUERY"
    category: str = "general"
    conversational_function: str = "NEW_REQUEST"
    intent_confidence: float = 0.85
    negation_detected: bool = False
    is_ambiguous: bool = False
    clarification_needed: bool = False
    entities: Dict[str, Any] = field(default_factory=dict)
    diagnostic_details: Dict[str, Any] = field(default_factory=dict)
    communication_style: Dict[str, Any] = field(default_factory=dict)


class CodeMixedLanguageDetector:
    """
    Detects code-mixed Indian languages in customer support messages.
    Supports: Tanglish (Tamil+English), Hinglish (Hindi+English),
    Pure Tamil, Pure Hindi, Kannada+English, Telugu+English, Bengali, Malayalam.
    """

    # Unicode ranges
    TAMIL_RANGE = (0x0B80, 0x0BFF)
    DEVANAGARI_RANGE = (0x0900, 0x097F)
    KANNADA_RANGE = (0x0C80, 0x0CFF)
    TELUGU_RANGE = (0x0C00, 0x0C7F)
    BENGALI_RANGE = (0x0980, 0x09FF)
    MALAYALAM_RANGE = (0x0D00, 0x0D7F)
    GUJARATI_RANGE = (0x0A80, 0x0AFF)
    GURMUKHI_RANGE = (0x0A00, 0x0A7F)
    ODIA_RANGE = (0x0B00, 0x0B7F)
    ARABIC_RANGE = (0x0600, 0x06FF)

    # Common Tanglish words & conversational markers
    TANGLISH_MARKERS: Dict[str, str] = {
        "bro": "brother/friend",
        "da": "emphasis (informal)",
        "la": "in/at (locative)",
        "na": "right? (question)",
        "pa": "sir/father",
        "ma": "madam/mother",
        "enna": "what",
        "ena": "what",
        "kitaa": "with/near",
        "kitta": "with/near",
        "eppo": "when",
        "enga": "where",
        "eppadi": "how",
        "edhukku": "why",
        "yaarum": "nobody/anyone",
        "yaaru": "who",
        "irukku": "is/am/are",
        "iruku": "is/am/are",
        "illa": "no/not",
        "illai": "no/not (formal)",
        "aagala": "did not happen / is not",
        "aayiduchu": "it happened",
        "aagiduchu": "it happened (alt)",
        "aaguthu": "it is happening",
        "venum": "want/need",
        "pannunga": "please do",
        "pannanum": "have to do",
        "panniten": "I did/paid",
        "pannala": "did not do/pay",
        "pantaen": "I did/paid",
        "vandhuruchu": "it came",
        "vandhuduchu": "it came/arrived",
        "varum": "will come",
        "varala": "has not come",
        "varave": "at all (with neg)",
        "mudiyala": "unable to do",
        "kedaikala": "did not get",
        "kedaichuduchu": "got it",
        "aagave": "at all (with neg)",
        "nikkudhu": "is standing/stuck",
        "nikkudha": "is it stuck?",
        "vanakkam": "hello/greetings",
        "nandri": "thank you",
        "panam": "money",
        "kaasu": "money (colloquial)",
        "maranthuten": "I forgot",
        "konjam": "a little/some",
        "sollunga": "tell me",
        "theriyala": "don't know",
        "puriyala": "don't understand",
        "puriyudhu": "understood",
        "paarunga": "please see/check",
        "kudunga": "please give",
        "tholla": "trouble/problem",
        "adhukku": "for that/after that",
        "apram": "afterwards/later",
        "innum": "still/yet",
        "apdiye": "like that/same",
        "kavalapadatheenga": "don't worry",
        "seri": "okay/alright",
        "kandippa": "definitely/sure",
        "oru": "one/a",
        "thambi": "younger brother",
        "akka": "elder sister",
        "anna": "elder brother",
    }

    # Common Hinglish words & conversational markers
    HINGLISH_MARKERS: Dict[str, str] = {
        "nahi": "no/not",
        "kya": "what",
        "kaise": "how",
        "kyun": "why",
        "kab": "when",
        "kaha": "where",
        "paisa": "money",
        "paise": "money",
        "mera": "my/mine",
        "meri": "my/mine",
        "hai": "is",
        "hain": "are",
        "karo": "do",
        "karna": "to do",
        "bhool": "forgot",
        "gaya": "went/gone",
        "aaya": "came",
        "mil": "found/received",
        "yaar": "friend",
        "bhai": "brother",
        "didi": "sister",
        "accha": "okay/good",
        "theek": "okay/fine",
        "kuch": "something",
        "wapas": "back/return",
        "batao": "tell me",
        "dekho": "see/look",
        "mujhe": "to me",
        "chahiye": "want/need",
        "hogaya": "done/happened",
        "hua": "happened",
        "lekin": "but",
        "kat": "deducted",
        "atka": "stuck",
        "khul": "open",
    }

    # Common Telugu code-mixed markers
    TELUGU_MARKERS: Dict[str, str] = {
        "naa": "my/mine",
        "naaku": "to me",
        "inka": "still/yet",
        "raledu": "has not come",
        "raaledu": "has not come",
        "raaledhu": "has not come",
        "kaledu": "did not happen",
        "kaaledu": "did not happen",
        "ledu": "not/no",
        "ledhu": "not/no",
        "kadhu": "not/no",
        "chesanu": "I did/paid",
        "cheyaledu": "did not do/pay",
        "vachindi": "came/arrived",
        "vachindhi": "came/arrived",
        "ravatledu": "is not coming",
        "dabbu": "money",
        "dabbulu": "money",
        "cheppandi": "please tell",
        "chudandi": "please see",
        "eppudu": "when",
        "ekkada": "where",
        "enti": "what",
        "enduku": "why",
        "ela": "how",
        "kavali": "want/need",
        "vaddu": "do not want",
        "chala": "very/much",
        "ayindi": "happened/done",
        "avvaledu": "did not happen",
        "sare": "okay",
        "avunu": "yes",
    }

    # Common Kannada code-mixed markers
    KANNADA_MARKERS: Dict[str, str] = {
        "nanna": "my/mine",
        "nanage": "to me",
        "innu": "still/yet",
        "bandilla": "has not come",
        "baralla": "will not come",
        "aagilla": "did not happen",
        "illa": "no/not",
        "banthu": "came/arrived",
        "bandide": "has arrived",
        "barutte": "will come",
        "maadiddini": "I did/paid",
        "madilla": "did not do/pay",
        "maadalla": "will not do",
        "duddu": "money",
        "hana": "money",
        "heli": "please tell",
        "nodi": "please see",
        "yaavaga": "when",
        "elli": "where",
        "yenu": "what",
        "yaake": "why",
        "hege": "how",
        "beku": "want/need",
        "beda": "do not want",
        "thumba": "very/much",
        "tumba": "very/much",
        "aagide": "happened/done",
        "sari": "okay",
        "haudu": "yes",
    }

    # Common Malayalam code-mixed markers
    MALAYALAM_MARKERS: Dict[str, str] = {
        "ente": "my/mine",
        "enikku": "to me",
        "njangalude": "our",
        "njangal": "we",
        "ithuvare": "until now/yet",
        "ithu vare": "until now/yet",
        "innum": "still/yet",
        "vannilla": "has not come",
        "varilla": "will not come",
        "aayilla": "did not happen",
        "kittiyilla": "not received",
        "kittilla": "will not receive",
        "illa": "no/not",
        "vannu": "came/arrived",
        "ethiyilla": "has not reached",
        "cheythu": "I did/paid",
        "cheythilla": "did not do/pay",
        "paisa": "money",
        "panam": "money",
        "parayamo": "can you tell",
        "nokku": "please see",
        "eppol": "when",
        "evide": "where",
        "enthaanu": "what",
        "enthukondu": "why",
        "enganeya": "how",
        "venam": "want/need",
        "venda": "do not want",
        "valare": "very/much",
        "shari": "okay",
        "athe": "yes",
    }

    # Common Bengali code-mixed markers
    BENGALI_MARKERS: Dict[str, str] = {
        "amar": "my/mine",
        "amake": "to me",
        "ekhono": "still/yet",
        "ekhon": "now",
        "asheni": "has not come",
        "ashbe na": "will not come",
        "hoyni": "did not happen",
        "hoyeche": "happened/done",
        "peyechi": "got/received",
        "korechi": "I did/paid",
        "korini": "did not do/pay",
        "taka": "money",
        "poisa": "money",
        "bolun": "please tell",
        "dekhun": "please see",
        "kokhon": "when",
        "kothay": "where",
        "ki": "what",
        "keno": "why",
        "kivabe": "how",
        "chai": "want/need",
        "lagbe": "want/need",
        "dorkar": "need",
        "khub": "very/much",
        "deri": "late/delay",
        "thik": "okay/right",
        "hyan": "yes",
    }

    # Common Marathi code-mixed markers
    MARATHI_MARKERS: Dict[str, str] = {
        "maza": "my/mine",
        "mazi": "my/mine",
        "maze": "my/mine",
        "majha": "my/mine",
        "majhi": "my/mine",
        "majhe": "my/mine",
        "mala": "to me",
        "ajun": "still/yet",
        "ajunhi": "still/yet",
        "aala nahi": "has not come",
        "aali nahi": "has not come",
        "aala": "came/arrived",
        "nahi": "no/not",
        "zala nahi": "did not happen",
        "zala": "happened/done",
        "milaala": "got/received",
        "kela": "I did/paid",
        "kela nahi": "did not do/pay",
        "paise": "money",
        "saanga": "please tell",
        "bagha": "please see",
        "kadhi": "when",
        "kuthe": "where",
        "kay": "what",
        "kashala": "why",
        "kasa": "how",
        "pahije": "want/need",
        "nako": "do not want",
        "khup": "very/much",
        "ushir": "late/delay",
        "ahe": "is",
        "ho": "yes",
    }

    # Common Gujarati code-mixed markers
    GUJARATI_MARKERS: Dict[str, str] = {
        "maro": "my/mine",
        "mari": "my/mine",
        "maru": "my/mine",
        "mane": "to me",
        "haji": "still/yet",
        "haji sudhi": "until now/yet",
        "nathi aavyo": "has not come",
        "nathi aavi": "has not come",
        "nathi thayu": "did not happen",
        "thayu": "happened/done",
        "mali gayo": "got/received",
        "kari didhu": "I did/paid",
        "nathi karyu": "did not do/pay",
        "rupia": "money",
        "paisa": "money",
        "kaho": "please tell",
        "juo": "please see",
        "kyare": "when",
        "kya": "where",
        "shu": "what",
        "kem": "why",
        "kevi rite": "how",
        "joie": "want/need",
        "nathi joie": "do not want",
        "bahu": "very/much",
        "chhe": "is",
        "ha": "yes",
    }

    # Common Punjabi code-mixed markers
    PUNJABI_MARKERS: Dict[str, str] = {
        "mera": "my/mine",
        "meri": "my/mine",
        "mere": "my/mine",
        "mainu": "to me",
        "aje": "still/yet",
        "aje tak": "until now/yet",
        "nahi aaya": "has not come",
        "nahi aayi": "has not come",
        "nahi hoya": "did not happen",
        "ho gaya": "happened/done",
        "mil gaya": "got/received",
        "kar ditta": "I did/paid",
        "kar ditti": "I did/paid",
        "nahi kita": "did not do/pay",
        "paisa": "money",
        "paise": "money",
        "dasso": "please tell",
        "dekho": "please see",
        "kadon": "when",
        "kithay": "where",
        "ki": "what",
        "kyun": "why",
        "kiven": "how",
        "chahida": "want/need",
        "nahi chahida": "do not want",
        "bada": "very/much",
        "der": "late/delay",
        "haan": "yes",
    }

    def detect(self, text: str, contextual_preference: Optional[str] = None) -> LanguageDetectionResult:
        """
        Detect code-mixed languages and script types across pan-Indian languages.
        """
        result = LanguageDetectionResult()
        text_lower = text.lower()

        # Check for native scripts
        scripts = self._detect_scripts(text)
        result.script_types = scripts

        # Count markers for all 9 core languages
        tanglish_count = self._count_markers(text_lower, self.TANGLISH_MARKERS)
        hinglish_count = self._count_markers(text_lower, self.HINGLISH_MARKERS)
        telugu_count = self._count_markers(text_lower, self.TELUGU_MARKERS)
        kannada_count = self._count_markers(text_lower, self.KANNADA_MARKERS)
        malayalam_count = self._count_markers(text_lower, self.MALAYALAM_MARKERS)
        bengali_count = self._count_markers(text_lower, self.BENGALI_MARKERS)
        marathi_count = self._count_markers(text_lower, self.MARATHI_MARKERS)
        gujarati_count = self._count_markers(text_lower, self.GUJARATI_MARKERS)
        punjabi_count = self._count_markers(text_lower, self.PUNJABI_MARKERS)
        english_word_count = self._count_english_words(text_lower)

        has_tamil_script = "tamil" in scripts
        has_devanagari = "devanagari" in scripts
        has_kannada = "kannada" in scripts
        has_telugu = "telugu" in scripts
        has_bengali = "bengali" in scripts
        has_malayalam = "malayalam" in scripts
        has_gujarati = "gujarati" in scripts
        has_gurmukhi = "gurmukhi" in scripts
        has_odia = "odia" in scripts
        has_arabic = "arabic" in scripts
        has_latin = "latin" in scripts

        # Native script matching with specific cross-language distinctions
        dev_words = set(re.findall(r'[\u0900-\u097F]+', text))
        marathi_distinct = {"आहे", "आहेत", "नाही", "नाहीत", "झाला", "झाली", "झाले", "माझा", "माझी", "माझे", "मला", "आम्हाला", "तुम्हाला", "त्यांना", "कधी", "कुठे", "पाहिजे", "सांगा", "बघा", "अजून", "मिळाला", "मिळाली", "डिलिव्हरी"}
        hindi_distinct = {"है", "हैं", "नहीं", "ना", "हुआ", "हुई", "हुए", "मेरा", "मेरी", "मेरे", "मुझे", "हमें", "आपको", "कब", "कहाँ", "कहा", "चाहिए", "करो", "बताओ", "अभी", "तक", "आया", "आयी", "डिलीवरी"}
        marathi_match_count = len(dev_words & marathi_distinct)
        hindi_match_count = len(dev_words & hindi_distinct)
        is_marathi = marathi_match_count > hindi_match_count
        has_assamese_chars = any(c in text for c in ["\u09F0", "\u09F1"])

        if has_tamil_script:
            result.primary_language = "ta"
            if has_latin:
                result.mixed_with = ["en"]
                result.is_code_mixed = True
                result.code_mix_type = "tanglish"
                result.confidence = 0.96
            else:
                result.code_mix_type = "tamil"
                result.confidence = 0.98
        elif has_devanagari:
            if is_marathi:
                result.primary_language = "mr"
                if has_latin:
                    result.mixed_with = ["en"]
                    result.is_code_mixed = True
                    result.code_mix_type = "marathi_english"
                    result.confidence = 0.96
                else:
                    result.code_mix_type = "marathi"
                    result.confidence = 0.98
            else:
                result.primary_language = "hi"
                if has_latin:
                    result.mixed_with = ["en"]
                    result.is_code_mixed = True
                    result.code_mix_type = "hinglish"
                    result.confidence = 0.96
                else:
                    result.code_mix_type = "hindi"
                    result.confidence = 0.98
        elif has_kannada:
            result.primary_language = "kn"
            if has_latin:
                result.mixed_with = ["en"]
                result.is_code_mixed = True
                result.code_mix_type = "kannada_english"
                result.confidence = 0.95
            else:
                result.code_mix_type = "kannada"
                result.confidence = 0.98
        elif has_telugu:
            result.primary_language = "te"
            if has_latin:
                result.mixed_with = ["en"]
                result.is_code_mixed = True
                result.code_mix_type = "telugu_english"
                result.confidence = 0.95
            else:
                result.code_mix_type = "telugu"
                result.confidence = 0.98
        elif has_bengali:
            if has_assamese_chars:
                result.primary_language = "as"
                result.code_mix_type = "assamese"
                result.confidence = 0.95
            else:
                result.primary_language = "bn"
                if has_latin:
                    result.mixed_with = ["en"]
                    result.is_code_mixed = True
                    result.code_mix_type = "bengali_english"
                    result.confidence = 0.95
                else:
                    result.code_mix_type = "bengali"
                    result.confidence = 0.98
        elif has_malayalam:
            result.primary_language = "ml"
            if has_latin:
                result.mixed_with = ["en"]
                result.is_code_mixed = True
                result.code_mix_type = "malayalam_english"
                result.confidence = 0.95
            else:
                result.code_mix_type = "malayalam"
                result.confidence = 0.98
        elif has_gujarati:
            result.primary_language = "gu"
            if has_latin:
                result.mixed_with = ["en"]
                result.is_code_mixed = True
                result.code_mix_type = "gujarati_english"
                result.confidence = 0.95
            else:
                result.code_mix_type = "gujarati"
                result.confidence = 0.98
        elif has_gurmukhi:
            result.primary_language = "pa"
            if has_latin:
                result.mixed_with = ["en"]
                result.is_code_mixed = True
                result.code_mix_type = "punjabi_english"
                result.confidence = 0.95
            else:
                result.code_mix_type = "punjabi"
                result.confidence = 0.98
        elif has_odia:
            result.primary_language = "or"
            result.code_mix_type = "odia"
            result.confidence = 0.95
        elif has_arabic:
            result.primary_language = "ur"
            result.code_mix_type = "urdu"
            result.confidence = 0.95
        else:
            # Romanized code-mixing across all 9 core languages
            marker_scores = {
                "ta": ("tanglish", tanglish_count),
                "hi": ("hinglish", hinglish_count),
                "te": ("telugu_english", telugu_count),
                "kn": ("kannada_english", kannada_count),
                "ml": ("malayalam_english", malayalam_count),
                "bn": ("bengali_english", bengali_count),
                "mr": ("marathi_english", marathi_count),
                "gu": ("gujarati_english", gujarati_count),
                "pa": ("punjabi_english", punjabi_count),
            }
            best_lang, (best_code_mix, best_count) = max(marker_scores.items(), key=lambda item: item[1][1])

            if best_count > 0:
                result.primary_language = best_lang
                result.mixed_with = ["en"]
                result.is_code_mixed = True
                result.code_mix_type = best_code_mix
                result.confidence = min(0.60 + (best_count * 0.12), 0.96)
            else:
                # Morphological sub-word analysis for code-mix containing unseen vocabulary
                t_low = text.lower()
                tokens = set(re.findall(r"\b[a-z]+\b", t_low))
                common_en = {
                    "the", "is", "are", "was", "my", "i", "you", "we", "it",
                    "not", "but", "and", "or", "for", "to", "in", "on", "with",
                    "order", "payment", "delivery", "refund", "help", "need",
                    "please", "thank", "sorry", "problem", "issue", "open", "crash",
                    "have", "has", "can", "will", "would", "should", "could", "me", "this", "that"
                }
                non_en_tokens = [w for w in tokens if w not in common_en]

                tanglish_morph_patterns = [
                    r"\b\w+(?:unga|aachu|aayiduchu|aagala|iduchu|aam|aadh|adha|ren|rom|num|ley|leye|oda|kku|ukku)\b",
                    r"\b(?:naan|neenga|adh|idhu|edhu|yaar|enna|enga|eppo|eppadi|epdi|apdi|ipdi|oru|sila|nalla|romba|konjam|seri|sari|mudiy|theriy|puriy|saaman|porul|kaasu|panam|vandi|kadai|veedu|varal|vandh|anup)\w*\b"
                ]
                hinglish_morph_patterns = [
                    r"\b\w+(?:ega|egi|enge|iye|iyega|gaya|gayi|gaye|raha|rahi|rahe|wala|wali)\b",
                    r"\b\w+(?:kar|karta|karte|karti|hota|hote|hoti|jaata|jaate|jaati|aata|aate|aati)\b",
                    r"\b(?:main|hum|aap|tum|mera|meri|mere|tera|uska|iski|kya|kyun|kaise|kab|kahan|nahi|mat|haan|theek|accha|bahut|thoda|paisa|saman|cheez|bhejne|dena|lena|chahiye|lagega|lagenge)\b"
                ]
                telugu_morph_patterns = [
                    r"\b\w+(?:ledu|aledu|esanu|aadu|aaru|indi|adam|andi)\b",
                    r"\b(?:naa|naaku|inka|enti|enduku|ela|chala|dabbu|avunu|vaddu)\b"
                ]
                kannada_morph_patterns = [
                    r"\b\w+(?:illa|bandilla|iddini|aagide|utte|odu|alli)\b",
                    r"\b(?:nanna|nanage|innu|yenu|yaake|hege|tumba|thumba|duddu|haudu|beda)\b"
                ]

                has_tanglish_morph = False
                has_hinglish_morph = False
                has_telugu_morph = False
                has_kannada_morph = False
                if non_en_tokens:
                    non_en_text = " " + " ".join(non_en_tokens) + " "
                    has_tanglish_morph = any(re.search(pat, non_en_text) for pat in tanglish_morph_patterns)
                    has_hinglish_morph = any(re.search(pat, non_en_text) for pat in hinglish_morph_patterns)
                    has_telugu_morph = any(re.search(pat, non_en_text) for pat in telugu_morph_patterns)
                    has_kannada_morph = any(re.search(pat, non_en_text) for pat in kannada_morph_patterns)

                if has_tanglish_morph and not (has_hinglish_morph or has_telugu_morph or has_kannada_morph):
                    result.primary_language = "ta"
                    result.mixed_with = ["en"]
                    result.is_code_mixed = True
                    result.code_mix_type = "tanglish"
                    result.confidence = 0.85
                elif has_hinglish_morph and not (has_tanglish_morph or has_telugu_morph or has_kannada_morph):
                    result.primary_language = "hi"
                    result.mixed_with = ["en"]
                    result.is_code_mixed = True
                    result.code_mix_type = "hinglish"
                    result.confidence = 0.85
                elif has_telugu_morph:
                    result.primary_language = "te"
                    result.mixed_with = ["en"]
                    result.is_code_mixed = True
                    result.code_mix_type = "telugu_english"
                    result.confidence = 0.85
                elif has_kannada_morph:
                    result.primary_language = "kn"
                    result.mixed_with = ["en"]
                    result.is_code_mixed = True
                    result.code_mix_type = "kannada_english"
                    result.confidence = 0.85
                elif contextual_preference and contextual_preference.lower() in ("tanglish", "hinglish", "telugu_english", "kannada_english") and (
                    len(tokens) <= 7
                    or any(w in tokens for w in ["da", "bro", "machan", "machaan", "yaar", "pa", "ma", "la", "ah", "nu", "thaan", "na", "seri", "sari", "theek", "bhai", "next", "appo", "apram", "yen", "andi", "sare", "ayithe"])
                ):
                    pref_l = contextual_preference.lower()
                    result.primary_language = "ta" if "tanglish" in pref_l else ("te" if "telugu" in pref_l else ("kn" if "kannada" in pref_l else "hi"))
                    result.mixed_with = ["en"]
                    result.is_code_mixed = True
                    result.code_mix_type = pref_l
                    result.confidence = 0.80
                else:
                    result.primary_language = "en"
                    result.code_mix_type = "english"
                    result.confidence = 0.88

        return result

    def _detect_scripts(self, text: str) -> List[str]:
        scripts = []
        has_latin = False
        has_tamil = False
        has_devanagari = False
        has_kannada = False
        has_telugu = False
        has_bengali = False
        has_malayalam = False
        has_gujarati = False
        has_gurmukhi = False
        has_odia = False
        has_arabic = False

        for char in text:
            cp = ord(char)
            if self.TAMIL_RANGE[0] <= cp <= self.TAMIL_RANGE[1]:
                has_tamil = True
            elif self.DEVANAGARI_RANGE[0] <= cp <= self.DEVANAGARI_RANGE[1]:
                has_devanagari = True
            elif self.KANNADA_RANGE[0] <= cp <= self.KANNADA_RANGE[1]:
                has_kannada = True
            elif self.TELUGU_RANGE[0] <= cp <= self.TELUGU_RANGE[1]:
                has_telugu = True
            elif self.BENGALI_RANGE[0] <= cp <= self.BENGALI_RANGE[1]:
                has_bengali = True
            elif self.MALAYALAM_RANGE[0] <= cp <= self.MALAYALAM_RANGE[1]:
                has_malayalam = True
            elif self.GUJARATI_RANGE[0] <= cp <= self.GUJARATI_RANGE[1]:
                has_gujarati = True
            elif self.GURMUKHI_RANGE[0] <= cp <= self.GURMUKHI_RANGE[1]:
                has_gurmukhi = True
            elif self.ODIA_RANGE[0] <= cp <= self.ODIA_RANGE[1]:
                has_odia = True
            elif self.ARABIC_RANGE[0] <= cp <= self.ARABIC_RANGE[1]:
                has_arabic = True
            elif char.isalpha():
                has_latin = True

        if has_latin:
            scripts.append("latin")
        if has_tamil:
            scripts.append("tamil")
        if has_devanagari:
            scripts.append("devanagari")
        if has_kannada:
            scripts.append("kannada")
        if has_telugu:
            scripts.append("telugu")
        if has_bengali:
            scripts.append("bengali")
        if has_malayalam:
            scripts.append("malayalam")
        if has_gujarati:
            scripts.append("gujarati")
        if has_gurmukhi:
            scripts.append("gurmukhi")
        if has_odia:
            scripts.append("odia")
        if has_arabic:
            scripts.append("arabic")
        return scripts

    def _count_markers(self, text: str, markers: Dict[str, str]) -> int:
        count = 0
        words = set(re.findall(r'\b\w+\b', text))
        text_padded = f" {text} "
        for marker in markers:
            if " " in marker:
                if f" {marker} " in text_padded:
                    count += 1
            elif marker in words:
                count += 1
        return count

    def _count_english_words(self, text: str) -> int:
        common_english = {
            "the", "is", "are", "was", "my", "i", "you", "we", "it",
            "not", "but", "and", "or", "for", "to", "in", "on",
            "order", "payment", "delivery", "refund", "help",
            "please", "thank", "sorry", "problem", "issue", "open", "crash"
        }
        words = set(re.findall(r'\b[a-z]+\b', text))
        return len(words & common_english)


class IndianLanguageNormalizer:
    """
    Normalizes colloquial expressions while strictly preserving negation,
    question markers, entities, and intent context.
    """

    # Meaning-preserving synonym & loan mapping (does NOT globally destroy original words)
    COLLOQUIAL_MAP: Dict[str, str] = {
        # Tanglish
        "irukku": "is",
        "iruku": "is",
        "illa": "not",
        "illai": "not",
        "venum": "want",
        "pannunga": "please do",
        "pannanum": "have to do",
        "sollunga": "tell me",
        "solunga": "tell me",
        "sollu": "tell",
        "solren": "will tell",
        "paarunga": "check",
        "panam": "money",
        "kaasu": "money",
        "maranthuten": "forgot",
        "tholla": "problem",
        "kudunga": "give",
        "enna enna": "what all",
        "ena ena": "what all",
        "enna": "what",
        "ena": "what",
        "kitaa": "with you",
        "kitta": "with you",
        "eppadi": "how",
        "eppo": "when",
        "enga": "where",
        "pathi": "about",
        "pathii": "about",
        "unga": "your",
        "ungalukku": "to you",
        "enaku": "to me",
        "enakku": "to me",
        "namma": "our",
        "kulla": "within",
        # Hinglish
        "batao": "tell me",
        "dekho": "check",
        "chahiye": "want",
        "paisa": "money",
        "paise": "money",
        "bhool": "forgot",
        "badalna": "change",
        "kya": "what",
        "kaise": "how",
        "kab": "when",
        "kahan": "where",
        "baare": "about",
        "aapka": "your",
        "apna": "your",
        "mera": "my",
        # Telugu
        "raledu": "not arrived",
        "raaledu": "not arrived",
        "chesanu": "paid",
        "cheyaledu": "not paid",
        "vachindi": "arrived",
        "dabbu": "money",
        "cheppandi": "tell me",
        # Kannada
        "bandilla": "not arrived",
        "maadiddini": "paid",
        "madilla": "not paid",
        "banthu": "arrived",
        "duddu": "money",
        "heli": "tell me",
        # Malayalam
        "vannilla": "not arrived",
        "cheythu": "paid",
        "cheythilla": "not paid",
        "vannu": "arrived",
        "parayamo": "tell me",
        # Bengali
        "asheni": "not arrived",
        "korechi": "paid",
        "korini": "not paid",
        "peyechi": "received",
        "taka": "money",
        "bolun": "tell me",
        # Marathi
        "aala nahi": "not arrived",
        "kela": "paid",
        "kela nahi": "not paid",
        "milaala": "received",
        "saanga": "tell me",
        # Gujarati
        "nathi aavyo": "not arrived",
        "kari didhu": "paid",
        "nathi karyu": "not paid",
        "mali gayo": "received",
        "rupia": "money",
        "kaho": "tell me",
        # Punjabi
        "nahi aaya": "not arrived",
        "kar ditta": "paid",
        "nahi kita": "not paid",
        "mil gaya": "received",
        "dasso": "tell me",
    }

    def normalize(self, text: str, language_type: str = "tanglish") -> NormalizationResult:
        detector = CodeMixedLanguageDetector()
        lang_result = detector.detect(text)

        text_lower = text.lower()
        normalized = text_lower
        detected_slang: List[str] = []

        for code_word, standard_word in sorted(self.COLLOQUIAL_MAP.items(), key=lambda x: len(x[0]), reverse=True):
            pattern = r'\b' + re.escape(code_word) + r'\b'
            if re.search(pattern, normalized):
                detected_slang.append(code_word)
                normalized = re.sub(pattern, standard_word, normalized)

        # Normalize informal address words without altering meaning
        normalized = re.sub(r'\bbro\b', '', normalized)
        normalized = re.sub(r'\bda\b', '', normalized)
        normalized = re.sub(r'\byaar\b', '', normalized)
        normalized = re.sub(r'\s+', ' ', normalized).strip()

        return NormalizationResult(
            original=text,
            normalized=normalized,
            detected_slang=detected_slang,
            language_result=lang_result,
        )


class UniversalMeaningEngine:
    """
    Universal Multilingual Voice Understanding Engine.
    Interprets natural customer speech contextually without rigid keyword traps.
    Accurately handles:
    - Negation ('App open aagala' != 'App open aayiduchu')
    - Colloquial Tanglish, Hinglish, Tamil, Hindi, and Indian English
    - Open-ended support categories (Technical, Payment, Order, Account, Subscription, Warranty, Complaints, General)
    - Multi-turn conversation context and diagnostic follow-ups
    - Extraction of IDs, amounts, and dates
    """

    def __init__(self):
        self.detector = CodeMixedLanguageDetector()
        self.normalizer = IndianLanguageNormalizer()

    def detect_negation(self, text: str) -> bool:
        """
        Accurately identifies negative statements across Tamil/Tanglish, Hindi/Hinglish, and English.
        Crucially prevents mistaking 'not working / not opening' for positive actions.
        """
        t = f" {text.lower()} "

        # Tamil / Tanglish negation markers
        tamil_negations = [
            r"\baagala\b", r"\baagave\s+illa\b", r"\baagala\b", r"\billa\b", r"\billai\b",
            r"\bvarala\b", r"\bvarave\s+illa\b", r"\bvarave\s+illai\b", r"\bmudiyala\b", r"\bpanna\s+mudiyala\b",
            r"\bkedakkala\b", r"\bkedaikala\b", r"\bkedaikave\s+illa\b", r"\btheriyala\b", r"\bpuriyala\b", r"\bpannala\b",
            r"\bpannave\s+illa\b", r"\breach\s+aagala\b", r"\bdeliver\s+aagala\b",
            r"\bkudukkala\b", r"\bload\s+aagala\b", r"\bopen\s+aagala\b", r"\bwork\s+aagala\b",
            r"இல்லை", r"ஆகவில்லை", r"வரவில்லை", r"வரவே\s*இல்லை", r"முடியவில்லை", r"தெரியவில்லை",
            r"கிடைக்கவில்லை", r"சென்றடையவில்லை", r"வரல", r"பண்ணல", r"ஆகல"
        ]

        # Hindi / Hinglish negation markers
        hindi_negations = [
            r"\bnahi\b", r"\bnahi\s+hua\b", r"\bnahi\s+ho\s+raha\b", r"\bnahi\s+chal\s+raha\b",
            r"\bnahi\s+khul\s+raha\b", r"\bnahi\s+aaya\b", r"\bnahi\s+mila\b", r"\bnahi\s+mil\s+raha\b",
            r"\bruk\s+gaya\b", r"\bband\s+hai\b", r"नहीं", r"ना", r"मत"
        ]

        # Telugu negation markers
        telugu_negations = [
            r"\braledu\b", r"\braaledu\b", r"\braaledhu\b", r"\bkaledu\b", r"\bkaaledu\b",
            r"\bledu\b", r"\bledhu\b", r"\bkadhu\b", r"\bcheyaledu\b", r"\bravatledu\b",
            r"\bivvaledu\b", r"\bkalaedu\b", r"రాలేదు", r"కాలేదు", r"లేదు", r"చేయలేదు", r"కాదు"
        ]

        # Kannada negation markers
        kannada_negations = [
            r"\bbandilla\b", r"\bbaralla\b", r"\baagilla\b", r"\bmadilla\b", r"\bmaadilla\b",
            r"\billa\b", r"\bkottilla\b", r"\bsigilla\b",
            r"ಬಂದಿಲ್ಲ", r"ಆಗಿಲ್ಲ", r"ಇಲ್ಲ", r"ಮಾಡಿಲ್ಲ", r"ಬರಲ್ಲ"
        ]

        # Malayalam negation markers
        malayalam_negations = [
            r"\bvannilla\b", r"\bvarilla\b", r"\baayilla\b", r"\bcheythilla\b", r"\bethiyilla\b",
            r"\bkittiyilla\b", r"\billa\b",
            r"വന്നില്ല", r"ആയില്ല", r"ഇല്ല", r"ചെയ്തില്ല", r"എത്തിയില്ല"
        ]

        # Bengali negation markers
        bengali_negations = [
            r"\basheni\b", r"\bashbe na\b", r"\bhoyni\b", r"\bkorini\b", r"\bdeyni\b",
            r"\bpayni\b", r"\bnei\b", r"\bna\b",
            r"আসেনি", r"হয়নি", r"করিনি", r"দেয়নি", r"নেই", r"না"
        ]

        # Marathi negation markers
        marathi_negations = [
            r"\baala nahi\b", r"\baali nahi\b", r"\bzala nahi\b", r"\bkela nahi\b", r"\bdila nahi\b",
            r"\bmilaala nahi\b", r"\bnahi\b",
            r"आला नाही", r"आली नाही", r"झाला नाही", r"केला नाही", r"नाही"
        ]

        # Gujarati negation markers
        gujarati_negations = [
            r"\bnathi aavyo\b", r"\bnathi aavi\b", r"\bnathi thayu\b", r"\bnathi karyu\b", r"\bnathi aapyu\b",
            r"\bnathi malyo\b", r"\bnathi\b",
            r"નથી આવ્યો", r"નથી આવી", r"નથી થયું", r"નથી કર્યું", r"નથી"
        ]

        # Punjabi negation markers
        punjabi_negations = [
            r"\bnahi aaya\b", r"\bnahi aayi\b", r"\bnahi hoya\b", r"\bnahi kita\b", r"\bnahi ditta\b",
            r"\bnahi milya\b", r"\bnahi\b",
            r"ਨਹੀਂ ਆਇਆ", r"ਨਹੀਂ ਹੋਇਆ", r"ਨਹੀਂ ਕੀਤਾ", r"ਨਹੀਂ"
        ]

        # English negation markers
        english_negations = [
            r"\bnot\b", r"\bn['’]t\b", r"\bfailed\b", r"\bunable\b", r"\bcannot\b",
            r"\bcan['’]t\b", r"\bwon['’]t\b", r"\bdoesn['’]t\b", r"\bdidn['’]t\b",
            r"\bisn['’]t\b", r"\bhasn['’]t\b", r"\bbroken\b"
        ]

        all_patterns = (
            tamil_negations
            + hindi_negations
            + telugu_negations
            + kannada_negations
            + malayalam_negations
            + bengali_negations
            + marathi_negations
            + gujarati_negations
            + punjabi_negations
            + english_negations
        )
        for pat in all_patterns:
            if re.search(pat, t):
                return True
        return False

    @staticmethod
    def is_affirmative_confirmation(text: str) -> bool:
        """Determines if the customer's response is an affirmative confirmation across pan-Indian languages."""
        if not text:
            return False
        t_clean = re.sub(r"[^\w\s]", " ", text.strip().lower())
        words = t_clean.split()
        if not words:
            return False
        exact_affirmatives = {
            "yes", "yeah", "yep", "sure", "please", "ok", "okay", "y", "s",
            # Tamil
            "aama", "aamanga", "aamaa", "seri", "sari", "kandippa", "kudunga", "pannunga", "ஆம்", "சரி", "இணைக்கவும்",
            # Hindi
            "haan", "ha", "theek hai", "thik hai", "zaroor", "karo", "ji haan", "हाँ", "हां", "ठीक है", "अवश्य",
            # Telugu
            "avunu", "sare", "avunandi", "cheseddam", "అవును", "సరే",
            # Kannada
            "haudu", "sari", "maadi", "ಹೌದು", "ಸರಿ",
            # Malayalam
            "athe", "shari", "cheyyu", "അതെ", "ശരി",
            # Bengali
            "hyan", "thik ache", "bolun", "হ্যাঁ", "ঠিক আছে",
            # Marathi
            "ho", "thik ahe", "kara", "हो", "ठीक आहे",
            # Gujarati
            "ha", "saras", "karo", "હા", "બરાબર",
            # Punjabi
            "haan", "thik hai", "dasso", "ਹਾਂ", "ਠੀਕ ਹੈ"
        }
        if t_clean in exact_affirmatives or (" ".join(words) in exact_affirmatives):
            return True
        affirmative_patterns = [
            r"\b(?:connect\s+(?:pannunga|pannu|karo|me|pannalam|panna\s+mudiyuma|cheyandi|maadi|cheyyu))\b",
            r"\b(?:yes\s+(?:please|sure|do|connect|transfer|i\s+want))\b",
            r"\b(?:transfer\s+(?:me|pannunga|karo|cheyandi))\b",
            r"\b(?:aama\s+(?:connect|pannunga|kudunga|pesanum|seri))\b",
            r"\b(?:seri\s+(?:connect|pannunga|kudunga|pesanum))\b",
            r"\b(?:haan\s+(?:connect|karo|transfer|ji))\b",
            r"\b(?:human\s+(?:expert|agent)\s+(?:kitta|se|with|to|kooda)\s*(?:connect|pesanum|baat|matladali))\b",
            r"\b(?:go\s+ahead)\b",
            r"\b(?:call\s+(?:them|expert|human))\b",
        ]
        return any(re.search(pat, t_clean) for pat in affirmative_patterns)

    @staticmethod
    def is_negative_confirmation(text: str) -> bool:
        """Determines if the customer's response is a negative confirmation across pan-Indian languages."""
        if not text:
            return False
        t_clean = re.sub(r"[^\w\s]", " ", text.strip().lower())
        words = t_clean.split()
        if not words:
            return False
        exact_negatives = {
            "no", "nope", "nah", "n", "cancel",
            # Tamil
            "vendaam", "vendam", "venaam", "venam", "illa", "illai", "thevailla", "வேண்டாம்", "இல்லை", "இப்போது வேண்டாம்",
            # Hindi
            "nahi", "na", "mat", "nahin", "नहीं", "मत",
            # Telugu
            "vaddu", "ledu", "oddu", "వద్దు", "లేదు",
            # Kannada
            "beda", "illa", "bedave", "ಬೇಡ", "ಇಲ್ಲ",
            # Malayalam
            "venda", "illa", "vendathilla", "വേണ്ട", "ഇല്ല",
            # Bengali
            "na", "lagbe na", "দরকার নেই", "না",
            # Marathi
            "nako", "nahi", "नको", "नाही",
            # Gujarati
            "nathi joie", "na", "નથી જોઈતું", "ના",
            # Punjabi
            "nahi chahida", "nahi", "ਨਹੀਂ ਚਾਹੀਦਾ", "ਨਹੀਂ"
        }
        if t_clean in exact_negatives or (" ".join(words) in exact_negatives):
            return True
        negative_patterns = [
            r"\b(?:no\s+(?:thanks|thank\s+you|need|don'?t|not\s+now|dont))\b",
            r"\b(?:not\s+now)\b",
            r"\b(?:don'?t\s+connect)\b",
            r"\b(?:vendaam|vendam|venaam|venam)\b",
            r"\b(?:theva\s*illa|thevai\s*illai)\b",
            r"\b(?:ippo\s+(?:venaam|vendaam|thevailla|illa))\b",
            r"\b(?:abhi\s+(?:nahi|mat))\b",
            r"\b(?:nahi\s+(?:chahiye|karo|karna))\b",
            r"\b(?:mat\s+karo)\b",
            r"\b(?:vaddu\s+andi|vaddu)\b",
            r"\b(?:beda\s+nange|beda)\b",
            r"\b(?:venda\s+enikku|venda)\b",
            r"\b(?:nako\s+mala|nako)\b",
            r"\b(?:no\s+need)\b",
            r"\b(?:stay\s+here|keep\s+chatting|continue\s+here)\b",
            r"\b(?:naane\s+paathukren|naane\s+paakren)\b",
            r"\b(?:illa\s+(?:vendaam|venaam|thevailla|not\s+now|no))\b",
        ]
        return any(re.search(pat, t_clean) for pat in negative_patterns)

    def extract_entities(self, text: str, pending_entity: Optional[str] = None) -> Dict[str, Any]:
        """Extracts structured identifiers, monetary amounts, and references."""
        entities: Dict[str, Any] = {}
        t = text.strip()

        # Order IDs: ORD-10293, ORD88123, ORD 12345, ORD_9988, #ORD-12345, ORD-KN-101, ORD-SECRET-999
        ord_match = re.search(r'(?:#\s*)?(ORD[-\s_]?[A-Za-z0-9_-]{3,25})\b', t, re.IGNORECASE)
        if ord_match:
            raw_id = ord_match.group(1)
            entities["raw_order_id"] = raw_id.upper()
            entities["order_id"] = re.sub(r'[\s_]+', '-', raw_id).upper()
            if not entities["order_id"].startswith("ORD-") and entities["order_id"].startswith("ORD"):
                entities["order_id"] = "ORD-" + entities["order_id"][3:].lstrip("-")

        # Fallback for Order ID if pending_entity is "order_id" or user wrote "order id is 12345" or "#12345"
        if "order_id" not in entities:
            order_explicit_num = re.search(r'(?:order\s*(?:id|no|number)?\s*[:=]?\s*#?|#\s*)(\d{4,10})\b', t, re.IGNORECASE)
            if order_explicit_num:
                entities["order_id"] = f"ORD-{order_explicit_num.group(1)}"
            elif pending_entity == "order_id" and re.match(r'^\s*#?(\d{4,10})\s*$', t):
                num_only = re.sub(r'[^\d]', '', t)
                entities["order_id"] = f"ORD-{num_only}"

        # Transaction IDs: TXN-9988, TXN9988, TXN_9988, TXN-TE-505
        txn_match = re.search(r'(?:#\s*)?(TXN[-\s_]?[A-Za-z0-9_-]{3,25})\b', t, re.IGNORECASE)
        if txn_match:
            raw_id = txn_match.group(1)
            entities["raw_transaction_id"] = raw_id.upper()
            entities["transaction_id"] = re.sub(r'[\s_]+', '-', raw_id).upper()
            if not entities["transaction_id"].startswith("TXN-") and entities["transaction_id"].startswith("TXN"):
                entities["transaction_id"] = "TXN-" + entities["transaction_id"][3:].lstrip("-")

        # Ticket IDs: #102, Ticket-42
        tkt_match = re.search(r'#(\d{1,8})\b', t)
        if tkt_match:
            entities["ticket_id"] = int(tkt_match.group(1))

        # Currency & amounts: Rs. 500, 500 rupees, 500 roobai, 500 rupaai, 500 rupia, 500 taka, 500 paise, 500 dabbu, 500 duddu
        amt_match = re.search(r'(?:rs\.?|inr|₹|rupaai|roobai|rupia|rupees|duddu|taka|paise|dabbu|panam)\s*(\d+(?:\.\d{1,2})?)', t, re.IGNORECASE)
        if not amt_match:
            amt_match = re.search(r'(\d+(?:\.\d{1,2})?)\s*(?:rs\.?|inr|₹|rupaai|roobai|rupia|rupees|duddu|taka|paise|dabbu|panam)', t, re.IGNORECASE)
        if amt_match:
            entities["amount"] = float(amt_match.group(1))

        return entities

    def detect_communication_style(self, text: str) -> Dict[str, Any]:
        """
        Analyzes the customer's communication style: formality, brevity, urgency, sentiment.
        """
        t = text.lower().strip()
        words = re.findall(r'\b\w+\b', t)
        word_count = len(words)

        informal_markers = {"bro", "da", "yaar", "bhai", "dude", "thx", "pls", "plz", "pa", "ma", "machan", "yo", "k"}
        is_informal = bool(set(words) & informal_markers) or any(w.endswith("pa") or w.endswith("da") for w in words)
        formality = "informal" if is_informal else "neutral"

        if word_count <= 4:
            brevity = "concise"
        elif word_count <= 18:
            brevity = "moderate"
        else:
            brevity = "verbose"

        urgent_markers = {
            "urgent", "urgently", "immediately", "asap", "emergency",
            "seekiram", "udane", "jaldi", "abhi", "fast", "quick", "quickly"
        }
        urgency = "urgent" if bool(set(words) & urgent_markers) else "normal"

        frustrated_markers = {
            "ridiculous", "worst", "useless", "terrible", "horrible", "waste", "cheat",
            "fraud", "scam", "thala vali", "dimag kharab", "bakwas", "angry", "annoyed"
        }
        positive_markers = {
            "thanks", "thank", "great", "awesome", "excellent", "good", "perfect",
            "nandri", "magizhchi", "shukriya", "dhanyawad", "badhiya"
        }
        if any(m in t for m in frustrated_markers):
            sentiment = "frustrated"
        elif any(m in t for m in positive_markers):
            sentiment = "positive"
        else:
            sentiment = "neutral"

        return {
            "formality": formality,
            "brevity": brevity,
            "urgency": urgency,
            "sentiment": sentiment,
        }

    def detect_conversational_function(
        self,
        clean_text: str,
        norm_text: str,
        history: Optional[List[Dict[str, Any]]] = None,
        conversation_state: Optional[Any] = None,
        entities: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, float, Optional[str]]:
        """
        Discourse act classifier generalizing beyond fixed dictionaries:
        Returns (conversational_function, confidence, understood_meaning_override)
        """
        t_lower = clean_text.lower().strip()
        norm_lower = (norm_text or "").lower().strip()
        combined = f"{t_lower} {norm_lower}"
        words = re.findall(r'\b\w+\b', t_lower)
        word_count = len(words)
        entities = entities or {}

        # 1. Critical Safety (Fraud, theft, hack, unauthorized)
        from app.ai.intelligence.escalation_keywords import is_fraud_or_security, is_supervisor_demand
        if is_fraud_or_security(clean_text) or is_fraud_or_security(norm_text) or any(
            kw in combined for kw in ["hack", "unauthorized", "stolen", "stole", "fraud", "scam", "suspicious", "robbed"]
        ):
            return "CRITICAL_SAFETY", 1.0, "Customer reported suspected security breach, unauthorized access, or fraud"

        # 2. Explicit Escalation Request
        if is_supervisor_demand(clean_text) or is_supervisor_demand(norm_text):
            return "ESCALATION_REQUEST", 1.0, "Customer explicitly requested human expert escalation"

        # 3. Explicit Language Switch
        from app.conversations.service import ConversationService
        is_lang_req = ConversationService.detect_explicit_language_request(clean_text)
        has_business_kw = any(w in t_lower for w in ["order", "refund", "return", "policy", "delivery", "track", "package", "txn", "password", "ticket", "pay", "charge", "cancel"])
        if is_lang_req and not has_business_kw:
            return "LANGUAGE_SWITCH", 0.98, f"Customer requested language switch to {is_lang_req}"

        # 4. Clarification or Correction (e.g. "no, I meant ORD-456", "not refund, exchange", "illa adhu illa ORD-789")
        correction_starters = [
            r"^\s*(?:no|not|illa|illai|nahi|galat|wrong|actually|mistake|thappu|sorry)\b",
            r"\b(?:i meant|i mean|meant to say|adha illa|adhu illa|mera matlab|mistake ah|thappa solten|galat order)\b"
        ]
        is_correction = any(re.search(pat, t_lower) for pat in correction_starters)
        if is_correction and (entities.get("order_id") or entities.get("transaction_id") or word_count <= 8):
            return "CLARIFICATION_OR_CORRECTION", 0.95, "Customer corrected or clarified previously supplied information"

        # 4a. RC-3: Simplification request — customer asking for clearer/simpler explanation
        # Detected structurally: negation/confusion marker + simplify/explain/clear signal
        # Not phrase-matched — these are semantic patterns in any language variant.
        simplify_patterns = [
            r"\b(?:simple|simply|simpler|simply|clearly|clear|shorter|brief|brief(?:ly)?)\b.*\b(?:say|tell|explain|sollu|bolu|batao|soll|kol)\b",
            r"\b(?:simple\s+(?:ah|a|ga|ha|nga|na|la|uh)\s+(?:sollu|soll|kol|bolo|batao|explain|tell|say))\b",
            r"\b(?:oru\s+vaattu\s+soll|easy\s+(?:ah|a)\s+soll|easy\s+words|layman|simple\s+words|simple\s+language)\b",
            r"\b(?:puriyaama|puriyala|puriyathu)\b.*\b(?:sollu|explain|tell|batao|kol|bolo)\b",
            r"\b(?:samajh\s+nahi|samajha\s+nahi|understand\s+nahi)\b",
        ]
        if any(re.search(pat, combined, re.IGNORECASE) for pat in simplify_patterns):
            return "CLARIFICATION_OR_CORRECTION", 0.93, "Customer asked for a simpler or clearer explanation of the previous response"

        # 4b. RC-3: Disagreement / "I never said that" corrections
        # Structural pattern: negation + reference to a previous statement/question
        # Works for "Naa indha question kekave illaye", "Naan adha sollala", "I didn't ask that"
        denial_patterns = [
            r"\b(?:naa|naan|nah|i|main|mujhe)\b.*\b(?:kekave|sollala|kekala|ask|said|bola|boli|puchha)\b.*\b(?:illa|illai|illaye|nahi|not|never|didn.t|didn.t)\b",
            r"\b(?:illa|illai|nahi|not|never|didn.t)\b.{0,20}\b(?:kekaven|sollanen|asked|said|bola|puchha|meant)\b",
            r"\b(?:adha|adhu|usko|isko|that|this)\b.{0,15}\b(?:sollala|kekala|ask\s+(?:la|nahi|not)|nahi\s+(?:bola|puchha|kaha))\b",
        ]
        if any(re.search(pat, combined, re.IGNORECASE) for pat in denial_patterns):
            return "CLARIFICATION_OR_CORRECTION", 0.93, "Customer denied or corrected a previous assumption or question"

        # 5. Answer to Pending Agent Question
        pending_entity = getattr(conversation_state, "pending_entity", None) if conversation_state else None
        pending_q = getattr(conversation_state, "pending_question", None) if conversation_state else None
        last_agent_text = ""
        if history:
            for msg in reversed(history):
                sender = str(msg.get("sender_type", "")).upper()
                if sender in ("AI", "AGENT", "ASSISTANT"):
                    last_agent_text = str(msg.get("content", "")).lower()
                    break

        agent_asked_order = pending_entity == "order_id" or pending_q == "ask_order_id" or ("order id" in last_agent_text and ("provide" in last_agent_text or "need" in last_agent_text or "sollunga" in last_agent_text or "batayein" in last_agent_text))
        agent_asked_txn = pending_entity == "transaction_id" or pending_q == "ask_transaction_id" or ("transaction id" in last_agent_text or "txn" in last_agent_text)

        if entities.get("order_id") and (agent_asked_order or word_count <= 4):
            return "ANSWER_TO_PENDING", 0.98, f"Customer provided Order ID: {entities['order_id']}"
        if entities.get("transaction_id") and (agent_asked_txn or word_count <= 4):
            return "ANSWER_TO_PENDING", 0.98, f"Customer provided Transaction ID: {entities['transaction_id']}"

        is_loading_followup = any(w in t_lower for w in ["loading", "nikkudhu", "stuck", "screen", "freeze"])
        if is_loading_followup and ("loading" in last_agent_text or "error" in last_agent_text or "app" in last_agent_text):
            return "ANSWER_TO_PENDING", 0.95, "Customer confirms app is stuck on loading screen without progressing"

        # 6. Acknowledgment / Closing Generalization
        has_question = "?" in clean_text or any(
            re.search(r'\b' + q + r'\b', t_lower) for q in [
                "why", "what", "when", "how", "where", "who", "which",
                "enna", "eppo", "enga", "edhukku", "eppadi", "yaaru",
                "kyun", "kab", "kahan", "kaise", "kisne", "kya"
            ]
        )
        domain_substantive = {
            "order", "refund", "return", "cancel", "cancellation", "password", "login",
            "account", "delivery", "track", "tracking", "hack", "fraud", "stolen", "money",
            "charge", "charged", "deducted", "payment", "crash", "error", "broken",
            "stuck", "fail", "failed", "warranty", "replace", "replacement", "exchange"
        }
        has_domain = bool(set(words) & domain_substantive)

        if word_count <= 8 and not has_question and not has_domain:
            ack_patterns = [
                # English acknowledgments
                r"\b(?:ok|okay|okies|k|kk|thx|thanks|thank you|got it|noted|understood|fine|cool|great|awesome|sounds good|roger|right|alright|all right|done|perfect|sweet|sure|yep|yeah|done bro|correct|true|exactly)\b",
                # Tanglish / Tamil acknowledgments
                r"\b(?:seri|sari|sari pa|seri pa|sari ma|seri ma|sari bro|seri bro|purinjithu|purinjidhu|puriyudhu|puriyum|therinjidhu|theriyum|aama|aamam|ama|aama seri|nandri|romba nandri|magizhchi|paravala|paravalla|kanden|ok pa|seri da|seri nga|sari nga|k bro)\b",
                # Hinglish / Hindi acknowledgments
                r"\b(?:theek hai|thik hai|theek h|thik h|acha|achha|achha theek hai|acha theek hai|samajh gaya|samajh gayi|samajha|samjha|haan|haa|haanji|shukriya|dhanyawad|dhanyavad|sahi hai|badhiya|okay ji|haan okay)\b",
                # Comprehension sounds / brief interjections
                r"^\s*(?:hmm|ohh|oh|ah|haan|seri|sari|ok|k)(?:\s+(?:ok|okay|theek hai|bro|pa|ma|done|thx))?\s*$"
            ]
            if any(re.search(pat, t_lower) for pat in ack_patterns):
                return "ACKNOWLEDGMENT", 0.95, "Customer acknowledged previous answer or explanation"

        # 7. Emotional Reaction / Frustration
        frustrated_patterns = [
            r"\b(?:ridiculous|worst|waste\s+of|waste\s+service|useless|pathetic|hate this|terrible|horrible)\b",
            r"\b(?:thala\s*vali|thalavali|dimag\s*kharab|bakwas|gussa|ghatiya|bekaar|mosam)\b",
        ]
        if any(re.search(pat, t_lower) for pat in frustrated_patterns):
            return "EMOTIONAL_REACTION", 0.94, "Customer expressed emotional frustration"

        # 8. Follow-up Question
        follow_up_starters = [
            r"^\s*(?:why|why\?|why does|how come|what about|how about|and if|still same|already tried)\b",
            r"^\s*(?:adhukku apram|appuram enna|yen ipdi|edhukku avlo)\b",
            r"^\s*(?:aur kitna|kyun|lekin kyun|phir kya|aur ek baat)\b",
            r"^\s*(?:ena|enna|kya|what|edhukku|ethuku|yen|puriyala)\b",
            # RC-3: "appo" (Tamil: "then"/"so then") is a structural continuation marker equivalent
            # to Hindi "phir" and English "so then" — not a vocabulary expansion, just completing
            # the existing set of equivalent discourse connectives across languages.
            r"^\s*(?:appo|appoo|apo)\b",
        ]
        if any(re.search(pat, t_lower) for pat in follow_up_starters) or (history and t_lower.strip("?.! ") in ["ena", "enna", "kya", "what", "why", "edhukku", "ethuku", "yen"]):
            return "FOLLOW_UP", 0.92, "Customer asked a follow-up question related to current topic"

        # 9. Polite Greetings (only if no substantive domain inquiry)
        greeting_words = {"hi", "hello", "hey", "vanakkam", "வணக்கம்", "namaste", "नमस्ते"}
        tokens_set = set(words) | set(re.findall(r'[^\s\.,!\?]+', t_lower))
        multiword_greetings = ["good morning", "good evening", "good afternoon", "good day"]
        is_greeting = bool(tokens_set & greeting_words) or any(
            t_lower.startswith(g) or f" {g}" in t_lower for g in multiword_greetings
        )
        if is_greeting and not has_domain:
            return "GREETING", 0.96, "Customer greeting"

        # 10. Default: New Request / Continuation
        return "NEW_REQUEST", 0.85, None

    def _finalize(self, u: UniversalMeaningUnderstanding) -> UniversalMeaningUnderstanding:
        """Enriches the understanding with normalized search query and verified metadata."""
        if not u.normalized_search_query:
            from app.ai.intelligence.multilingual_engine import MultilingualEngineService
            u.normalized_search_query = MultilingualEngineService.generate_normalized_search_query(
                intent=u.intent,
                category=u.category,
                entities=u.entities,
                negation_detected=u.negation_detected,
                diagnostic_details=u.diagnostic_details,
            )
        u.diagnostic_details["normalized_search_query"] = u.normalized_search_query
        return u

    def understand_utterance(
        self,
        text: str,
        history: Optional[List[Dict[str, Any]]] = None,
        conversation_state: Optional[Any] = None,
    ) -> UniversalMeaningUnderstanding:
        """
        Deep contextual interpretation of a customer utterance across languages and turns.
        """
        raw = self._understand_utterance_impl(text, history=history, conversation_state=conversation_state)
        return self._finalize(raw)

    def _understand_utterance_impl(
        self,
        text: str,
        history: Optional[List[Dict[str, Any]]] = None,
        conversation_state: Optional[Any] = None,
    ) -> UniversalMeaningUnderstanding:
        """
        Deep contextual interpretation of a customer utterance across languages and turns.
        """
        clean_text = text.strip()
        contextual_pref = getattr(conversation_state, "language_preference", None) if conversation_state else None
        lang_res = self.detector.detect(clean_text, contextual_preference=contextual_pref)
        norm_res = self.normalizer.normalize(clean_text, language_type=lang_res.code_mix_type)
        negation = self.detect_negation(clean_text)
        pending_ent = getattr(conversation_state, "pending_entity", None) if conversation_state else None
        entities = self.extract_entities(clean_text, pending_entity=pending_ent)

        t_lower = clean_text.lower()
        norm_lower = norm_res.normalized.lower()
        combined = f"{t_lower} {norm_lower}"

        style = self.detect_communication_style(clean_text)
        conv_fn, fn_conf, fn_meaning = self.detect_conversational_function(
            clean_text, norm_res.normalized,
            history=history,
            conversation_state=conversation_state,
            entities=entities
        )

        understanding = UniversalMeaningUnderstanding(
            raw_transcript=clean_text,
            normalized_meaning=norm_res.normalized,
            primary_language=lang_res.primary_language,
            detected_script=lang_res.script_types[0] if lang_res.script_types else "latin",
            code_mix_type=lang_res.code_mix_type or "english",
            is_code_mixed=lang_res.is_code_mixed,
            negation_detected=negation,
            entities=entities,
            conversational_function=conv_fn,
            communication_style=style,
        )

        # Immediate dispatch for distinct conversational speech acts:
        if conv_fn == "ACKNOWLEDGMENT":
            understanding.intent = "ACKNOWLEDGMENT"
            understanding.category = "closing"
            understanding.intent_confidence = fn_conf
            understanding.clarification_needed = False
            understanding.understood_meaning = fn_meaning or "Customer acknowledged previous answer"
            return understanding

        if conv_fn == "EMOTIONAL_REACTION":
            understanding.intent = "EMOTIONAL_REACTION"
            understanding.category = "general"
            understanding.intent_confidence = fn_conf
            understanding.understood_meaning = fn_meaning or "Customer expressed frustration"
            return understanding

        if conv_fn == "ANSWER_TO_PENDING":
            if "order_id" in entities:
                understanding.intent = "ORDER_STATUS"
                understanding.category = "order"
                understanding.intent_confidence = fn_conf
                understanding.clarification_needed = False
                understanding.understood_meaning = f"Customer provided Order ID: {entities['order_id']}"
                return understanding
            if "transaction_id" in entities:
                understanding.intent = "PAYMENT_ISSUE"
                understanding.category = "payment"
                understanding.intent_confidence = fn_conf
                understanding.clarification_needed = False
                understanding.understood_meaning = f"Customer provided Transaction ID: {entities['transaction_id']}"
                return understanding

        if conv_fn == "CLARIFICATION_OR_CORRECTION":
            # RC-3: Simplification requests ("puriyala, simple ah sollu", "in simple words")
            is_simplify = (
                bool(re.search(r"\b(?:simple|layman|easy|puriyala|puriyavillai|samajh nahi|asani|aasaan)\b", combined))
                or (fn_meaning and "simpler" in fn_meaning.lower())
            )
            # RC-3: Denial / correction of misunderstanding ("Naa indha question kekave illaye", "Naan adha sollala")
            is_denial = (
                bool(re.search(r"\b(?:kekave|sollala|kekala|didn.?t ask|never asked|not what i|galat|thappu)\b", combined))
                or (fn_meaning and "denied" in fn_meaning.lower())
            )

            if is_simplify:
                prev_intent = getattr(conversation_state, "active_intent", None) if conversation_state else None
                understanding.intent = prev_intent if prev_intent and prev_intent not in ("GREETING", "GENERAL_QUERY", "ACKNOWLEDGMENT") else "CLARIFICATION_SIMPLIFY"
                understanding.category = "clarification"
                understanding.intent_confidence = 0.94
                understanding.diagnostic_details["needs_simplification"] = True
                understanding.understood_meaning = "Customer requested a simpler explanation of the previous response"
                return understanding
            elif is_denial:
                understanding.intent = "CORRECTION_RECONSIDER"
                understanding.category = "clarification"
                understanding.intent_confidence = 0.94
                understanding.diagnostic_details["is_misunderstanding_correction"] = True
                understanding.understood_meaning = "Customer indicated their question was misunderstood and requested re-evaluation"
                return understanding
            elif entities.get("order_id") or entities.get("transaction_id"):
                if entities.get("order_id"):
                    understanding.intent = "ORDER_STATUS"
                    understanding.category = "order"
                else:
                    understanding.intent = "PAYMENT_ISSUE"
                    understanding.category = "payment"
                understanding.intent_confidence = 0.95
                understanding.understood_meaning = fn_meaning or "Customer corrected previous details"
                return understanding

        # ── Turn History Context Analysis ──
        last_agent_text = ""
        if history:
            for msg in reversed(history):
                if str(msg.get("sender_type", "")).upper() in ["AI", "AGENT"]:
                    last_agent_text = str(msg.get("content", "")).lower()
                    break

        # Extract customer's specific item term if used
        customer_item_term = "order"
        item_words = [
            "saaman", "saamaan", "saman", "porul", "porutkal", "cheez", "cheezein",
            "parcel", "parsal", "box", "packet", "package", "dress", "shoes", "shirt",
            "phone", "watch", "goods", "item", "items", "product", "products"
        ]
        for iw in item_words:
            if iw in t_lower:
                customer_item_term = iw
                break
        understanding.diagnostic_details["customer_item_term"] = customer_item_term

        # Contextual short questions & disambiguation ("ena", "enna", "kya", "what", "why", "edhukku", etc.)
        short_tokens = {"ena", "enna", "kya", "what", "why", "edhukku", "ethuku", "kyun", "yen", "puriyala"}
        words_count = len(clean_text.split())
        has_domain_term = any(w in t_lower for w in ["return", "refund", "cancel", "delivery", "shipping", "payment", "login", "password", "ticket"])
        is_short_token = not has_domain_term and (
            t_lower.strip("?.! ") in short_tokens
            or "why do you need" in t_lower
            or "why is it need" in t_lower
            or "edhukku venum" in t_lower
            or "kyun chahiye" in t_lower
            or "why required" in t_lower
            or (words_count <= 6 and (
                any(t_lower.strip("?.! ").startswith(st) for st in ["why ", "what ", "edhukku ", "ethuku ", "kyun ", "yen "])
            ))
        )
        is_direct_order_id_why = (
            any(w in t_lower for w in ["why", "edhukku", "ethuku", "kyun", "yen", "idhu illama", "illama", "bina", "without"])
            and (
                any(term in t_lower for term in ["order id", "order number", "order details", "id", "details"])
                or any(w in t_lower for w in ["idhu illama", "bina id", "without id", "check panna mudiyadha", "check nahi ho sakta"])
            )
        )
        is_why_question = bool(re.search(r'\b(?:why|edhukku|ethuku|kyun|yen)\b', t_lower))
        if is_direct_order_id_why:
            understanding.intent = "CLARIFICATION_ORDER_ID_PURPOSE"
            understanding.category = "clarification"
            understanding.conversational_function = "FOLLOW_UP"
            understanding.diagnostic_details = {"clarification_target": "order_id_reason", "customer_item_term": customer_item_term}
            understanding.understood_meaning = "Customer is asking why Order ID is required or if check is possible without it"
            return understanding

        if is_short_token and last_agent_text:
            if "order id" in last_agent_text or "order number" in last_agent_text or "provide your order" in last_agent_text:
                understanding.intent = "CLARIFICATION_ORDER_ID_PURPOSE"
                understanding.category = "clarification"
                understanding.conversational_function = "FOLLOW_UP"
                understanding.diagnostic_details = {"clarification_target": "order_id_reason"}
                understanding.understood_meaning = "Customer is asking why Order ID is required or what details are needed"
                return understanding
            elif "policy" in last_agent_text:
                understanding.intent = "POLICY_QUERY"
                understanding.category = "policy"
                understanding.conversational_function = "FOLLOW_UP"
                if is_why_question:
                    understanding.diagnostic_details["explain_why"] = True
                    understanding.diagnostic_details["is_policy_overview"] = False
                    understanding.understood_meaning = "Customer is asking why the policy is so"
                else:
                    understanding.diagnostic_details = {"is_policy_overview": True}
                    understanding.understood_meaning = "Customer is inquiring about policy details"
                return understanding
            elif "transaction" in last_agent_text:
                understanding.intent = "PAYMENT_ISSUE"
                understanding.category = "payment"
                understanding.conversational_function = "FOLLOW_UP"
                understanding.diagnostic_details = {"clarification_target": "transaction_reason"}
                understanding.understood_meaning = "Customer is asking why transaction details are needed"
                return understanding
            else:
                prev_active = getattr(conversation_state, "active_intent", None) if conversation_state else None
                if prev_active and prev_active not in ("GREETING", "GENERAL_QUERY", "ACKNOWLEDGMENT", "UNCLEAR"):
                    understanding.intent = prev_active
                    understanding.category = getattr(conversation_state, "active_topic", "clarification")
                    understanding.diagnostic_details["explain_why"] = True
                else:
                    understanding.intent = "FOLLOW_UP_CLARIFICATION"
                    understanding.category = "clarification"
                understanding.conversational_function = "FOLLOW_UP"
                understanding.understood_meaning = "Customer asked for clarification on previous message"
                return understanding

        # RC-7: Alternative options request ("Idhukku vera edhavadhu vazhi irukka?")
        is_alternative_request = conv_fn == "REQUEST_ALTERNATIVE" or any(re.search(pat, combined, re.IGNORECASE) for pat in [
            r"\b(?:vera\s+(?:edhavadhu|edhavathu|edhadhu)?\s*(?:vazhi|vali|option|tareeka|way))\b",
            r"\b(?:any\s+(?:other\s+way|alternative|other\s+options|other\s+solution))\b",
            r"\b(?:koi\s+aur\s+(?:rasta|tareeka|upay|option))\b",
            r"\b(?:what\s+else\s+can\s+i\s+do|is\s+there\s+another\s+way)\b",
            r"\b(?:verenna\s+panna\s+mudiyum|verena\s+panradhu)\b",
        ])
        if is_alternative_request:
            prev_active = getattr(conversation_state, "active_intent", None) if conversation_state else None
            understanding.intent = prev_active or "REQUEST_ALTERNATIVE"
            understanding.category = getattr(conversation_state, "active_topic", "general")
            understanding.conversational_function = "FOLLOW_UP"
            understanding.diagnostic_details["is_request_alternative"] = True
            understanding.diagnostic_details["customer_item_term"] = customer_item_term
            understanding.understood_meaning = "Customer is asking for alternative solutions or methods"
            return understanding

        # RC-7: Delivery delay continuation / frustration across pan-Indian languages
        is_delay_reiteration = any(re.search(pat, combined, re.IGNORECASE) for pat in [
            r"\b(?:innum|innuma)\s+(?:varala|kedaikala|reach\s+aagala)\b",
            r"\b(?:inka|intha\s+varaku)\s+(?:raledu|raaledu|ravatledu)\b",
            r"\b(?:innu|innuu)\s+(?:bandilla|baralla)\b",
            r"\b(?:ithuvare|ithu\s+vare)\s+(?:vannilla|ethiyilla)\b",
            r"\b(?:ekhono|ekhon\s+o)\s+(?:asheni|ashbe\s+na)\b",
            r"\b(?:ajun|ajunhi)\s+(?:aala\s+nahi|aali\s+nahi)\b",
            r"\b(?:haji|haji\s+sudhi)\s+(?:nathi\s+aavyo|nathi\s+aavi)\b",
            r"\b(?:aje|aje\s+tak)\s+(?:nahi\s+aaya|nahi\s+aayi)\b",
            r"\b(?:abhi\s+tak\s+nahi\s+aaya)\b",
            r"\b(?:still\s+(?:hasn'?t|not|waiting))\b",
            r"\b(?:romba|very|too|bahut|chala|thumba|valare|khub|bahu|bada)\s+(?:late|slow|delay|neram|der|ushir)\b",
            r"\b(?:evlo\s+neram|eppo\s+dhaan\s+varum|eppodhaan\s+varum|eppudu\s+vastundi|yaavaga\s+barutte|eppol\s+varum)\b",
        ])
        if is_delay_reiteration and not any(w in combined for w in ["cancel", "refund", "return", "otp", "password", "login", "auth"]):
            understanding.intent = "DELIVERY_ISSUE"
            understanding.category = "delivery"
            understanding.conversational_function = "FOLLOW_UP"
            understanding.diagnostic_details["is_delay_continuation"] = True
            understanding.diagnostic_details["customer_item_term"] = customer_item_term
            understanding.understood_meaning = "Customer is following up on unresolved delivery delay with frustration"
            return understanding

        # RC-3: Next-steps or continuation follow-up (e.g. "appo next enna pannanum?", "what next?", "adhukku apram?")
        is_next_step = any(
            re.search(pat, t_lower)
            for pat in [
                r"\b(?:appo|apo|phir|then|next|after that|adhukku apram|apram|aur kya|ab kya)\b.*\b(?:enna|kya|what|do|pannanum|karein|karna|panradhu)\b",
                r"^\s*(?:appo|apo|next|what next|aur kya|ab kya)\s*[\?]?\s*$",
                r"\b(?:adhuku|adhukku)\s+apram\b"
            ]
        )
        if is_next_step or (conv_fn == "FOLLOW_UP" and any(w in t_lower for w in ["next", "apram", "after"])):
            prev_active = getattr(conversation_state, "active_intent", None) if conversation_state else None
            understanding.diagnostic_details["is_next_step"] = True
            understanding.diagnostic_details["customer_item_term"] = customer_item_term
            understanding.conversational_function = "FOLLOW_UP"
            if prev_active and prev_active not in ("GREETING", "GENERAL_QUERY", "ACKNOWLEDGMENT", "UNCLEAR"):
                understanding.intent = prev_active
                understanding.category = getattr(conversation_state, "active_topic", "general")
                understanding.understood_meaning = f"Customer asked for next steps on active {prev_active}"
            else:
                understanding.intent = "NEXT_STEPS"
                understanding.category = "general"
                understanding.understood_meaning = "Customer asked for next steps"
            return understanding

        # Check for direct short diagnostic answers to agent questions
        # e.g. Agent asked: "error varudha, illa loading-laye nikkudha?"
        # Customer responds: "Loading-laye nikkudhu."
        is_loading_followup = any(w in t_lower for w in ["loading", "nikkudhu", "stuck", "screen", "freeze"])
        if is_loading_followup and ("loading" in last_agent_text or "error" in last_agent_text or "app" in last_agent_text):
            understanding.intent = "TECHNICAL_ISSUE"
            understanding.category = "technical"
            understanding.intent_confidence = 0.95
            understanding.is_ambiguous = False
            understanding.clarification_needed = False
            understanding.diagnostic_details = {"symptom": "loading_freeze", "is_follow_up": True}
            understanding.understood_meaning = "Customer confirms app is stuck on loading screen without progressing"
            return understanding

        # 0. Explicit Language Switch request
        from app.conversations.service import ConversationService
        is_lang_req = ConversationService.detect_explicit_language_request(clean_text)
        has_business_kw = any(w in t_lower for w in ["order", "refund", "return", "policy", "delivery", "track", "package", "txn", "password", "ticket", "pay", "charge", "cancel"])
        if is_lang_req and not has_business_kw:
            understanding.intent = "LANGUAGE_SWITCH"
            understanding.category = "preference"
            understanding.intent_confidence = 0.98
            understanding.clarification_needed = False
            understanding.understood_meaning = f"Customer requested language switch to {is_lang_req}"
            return understanding

        # 1. Opening problem statement without details (e.g. "Enakku oru problem irukku")
        is_vague_problem = (
            any(w in t_lower for w in ["problem irukku", "oru problem", "dikkat hai", "problem hai", "have a problem", "need help", "oru help venum"])
            and not any(w in t_lower for w in ["open", "order", "delivery", "refund", "pay", "login", "password", "crash", "cancel"])
        )
        if is_vague_problem:
            understanding.intent = "OPENING_PROBLEM_STATEMENT"
            understanding.category = "general"
            understanding.intent_confidence = 0.95
            understanding.is_ambiguous = True
            understanding.clarification_needed = True
            understanding.understood_meaning = "Customer is reporting an unspecified problem and needs an opening question"
            return understanding

        # 2. Technical issues: App crash, not opening, frozen screen, loading loops
        is_technical = (
            any(kw in combined for kw in [
                "app open", "open aagala", "crash", "loading", "nikkudhu", "white screen",
                "black screen", "freeze", "stuck", "error varudhu", "app update", "software update", "not opening",
                "nahi khul", "nahi chal", "glitch", "bug", "force close", "கிராஷ்", "திறக்கவில்லை",
                "slow", "hang"
            ])
            and ("app" in combined or "screen" in combined or "phone" in combined or "slow" in combined or "crash" in combined or "open" in combined or "ஆப்" in combined or "கிராஷ்" in combined or "செயலி" in combined)
        )
        if is_technical:
            understanding.intent = "TECHNICAL_ISSUE"
            understanding.category = "technical"
            understanding.intent_confidence = 0.94
            if "loading" in combined or "nikkudhu" in combined:
                understanding.diagnostic_details["symptom"] = "loading_freeze"
            elif "crash" in combined:
                understanding.diagnostic_details["symptom"] = "application_crash"
            elif negation and ("open" in combined or "work" in combined):
                understanding.diagnostic_details["symptom"] = "launch_failure"
            return understanding

        # 3. Supervisor or Escalation demand (Highest Priority)
        from app.ai.intelligence.escalation_keywords import is_supervisor_demand, is_fraud_or_security
        if is_supervisor_demand(clean_text) or is_supervisor_demand(norm_res.normalized):
            understanding.intent = "ESCALATION_REQUEST"
            understanding.category = "escalation"
            understanding.intent_confidence = 1.0
            understanding.clarification_needed = False
            understanding.understood_meaning = "Customer explicitly requested human expert escalation"
            return understanding

        # 4. Security issues & Unauthorized access / Fraud (Mandatory Safety)
        if (
            is_fraud_or_security(clean_text)
            or is_fraud_or_security(norm_res.normalized)
            or any(kw in combined for kw in ["hack", "unauthorized", "stolen", "stole", "fraud", "scam", "suspicious", "robbed", "accessed my account"])
        ):
            understanding.intent = "SECURITY_ISSUE"
            understanding.category = "security"
            understanding.intent_confidence = 0.98
            understanding.clarification_needed = False
            understanding.understood_meaning = "Customer reported suspected security breach, unauthorized access, or fraud"
            return understanding

        # 4.5. Account & Details Update (Specific)
        if any(kw in combined for kw in ["update my", "update phone", "change phone", "change email", "update email", "update address", "change address", "update details", "phone to"]):
            understanding.intent = "UPDATE_ISSUE"
            understanding.category = "account"
            understanding.intent_confidence = 0.94
            return understanding

        # 5. Authentication & Login (Specific)
        if any(kw in combined for kw in [
            "password", "login", "locked", "access", "forgot", "maranthuten", "marandhuten", "otp", "bhool",
            "கடவுச்சொல்", "உள்நுழைய", "உள்நுழைவு", "மறந்துவிட்டது", "லாகின்"
        ]):
            understanding.intent = "LOGIN_ISSUE"
            understanding.category = "account"
            understanding.intent_confidence = 0.94
            return understanding

        # Root concept matching for South Asian & English colloquial speech
        return_roots = [
            "refund", "return", "money back", "paise wapas", "thirumba", "thiruppi", "thirupi",
            "thiruppa", "thirumbi", "wapas", "vapasi", "lautana", "badalna", "badal", "exchange",
            "replace", "replacement", "anupa", "anuppa", "anupanum", "anuppanum", "bhejna", "bhejo",
            "thara", "tharanum", "retun",
            # Tamil
            "ரீஃபண்ட்", "ரிட்டர்ன்", "திருப்பி", "பணம் திரும்ப",
            # Telugu
            "vachindi", "vachindhi", "raledu", "raaledu", "తిరిగి", "రీఫండ్", "వాపసు",
            # Kannada
            "banthu", "bandide", "bandilla", "ಮರಳಿ", "ರೀಫಂಡ್", "ವಾಪಸ್",
            # Malayalam
            "vannu", "vannilla", "തിരികെ", "റീഫണ്ട്", "മടക്കി",
            # Bengali
            "peyechi", "asheni", "ফেরত", "রিফান্ড",
            # Marathi
            "milaala", "aala nahi", "परत", "रिफंड",
            # Gujarati
            "mali gayo", "nathi malyo", "પાછું", "રીફંડ",
            # Punjabi
            "mil gaya", "nahi milya", "ਵਾਪਸ", "ਰੀਫੰਡ",
        ]
        duration_policy_roots = [
            "policy", "policies", "rules", "rule", "terms", "condition", "conditions", "polici", "vidhi", "niyam",
            "evlo naal", "evalo naal", "ethana naal", "ethana days", "kitne din", "kab tak", "time limit", "validity",
            "deadline", "duration", "days", "naatkal", "time irukku", "time hai", "how many days", "how long",
            "enni rojulu", "eshtu dina", "ethra divasam", "koto din", "kiti divas", "ketla divas", "kinne din"
        ]
        has_return_concept = any(kw in combined for kw in return_roots)
        has_duration_policy_concept = any(kw in combined for kw in duration_policy_roots) or "policy" in t_lower or "policies" in t_lower

        # 6. Refund & Returns & Policy Inquiries
        if has_return_concept and not any(kw in combined for kw in ["cancel", "shipping", "delivery", "warranty"]):
            is_refund_received = (
                not negation
                and any(kw in combined for kw in [
                    # English
                    "received", "got it", "got my", "credited",
                    # Tamil
                    "vandhuduchu", "vandhuruchu", "vandhachu", "aayiduchu", "வந்துவிட்டது", "கிடைத்துவிட்டது", "கிடைத்தது",
                    # Hindi
                    "mil gaya", "aa gaya",
                    # Telugu
                    "vachindi", "vachindhi", "వచ్చింది",
                    # Kannada
                    "banthu", "bandide", "ಬಂತು",
                    # Malayalam
                    "vannu", "ethiyittundu", "വന്നു",
                    # Bengali
                    "peyechi", "esheche", "পেয়েছি",
                    # Marathi
                    "milaala", "aala", "मिळाला",
                    # Gujarati
                    "mali gayo", "aavi gayo", "મળી ગયો",
                    # Punjabi
                    "mil gaya", "aa gaya", "ਮਿਲ ਗਿਆ",
                ])
                and not any(kw in combined for kw in [
                    "innum", "varala", "nahi", "not", "illa", "கெடைக்கல", "வரல",
                    "raledu", "raaledu", "bandilla", "vannilla", "asheni", "aala nahi", "nathi malyo", "nahi milya", "nahi mila",
                    "రాలేదు", "ಬಂದಿಲ್ಲ", "വന്നില്ല", "আসেনি", "आला नाही", "નથી મળ્યો", "ਨਹੀਂ ਮਿਲਿਆ"
                ])
            )
            if is_refund_received:
                understanding.intent = "REFUND_RECEIVED"
                understanding.category = "refund"
                understanding.understood_meaning = "Customer confirmed that refund has been received"
                understanding.intent_confidence = 0.95
                understanding.clarification_needed = False
                return understanding

            understanding.intent = "REFUND_ISSUE"
            understanding.category = "refund"
            understanding.diagnostic_details["is_policy_overview"] = has_duration_policy_concept
            understanding.diagnostic_details["policy_type"] = "return"
            understanding.diagnostic_details["customer_item_term"] = customer_item_term
            understanding.understood_meaning = "Customer is inquiring about return or refund policy/timeline/status"
            understanding.intent_confidence = 0.95
            understanding.clarification_needed = False
            return understanding

        if has_duration_policy_concept:
            if any(kw in combined for kw in ["cancel", "cancellation"]):
                understanding.intent = "ORDER_MANAGEMENT"
                understanding.category = "order"
            elif any(kw in combined for kw in ["shipping", "delivery", "shipment"]):
                understanding.intent = "DELIVERY_ISSUE"
                understanding.category = "delivery"
            else:
                understanding.intent = "POLICY_QUERY"
                understanding.category = "policy"
                is_overview = any(kw in combined for kw in [
                    "ena ena", "enna enna", "what all", "what policies", "what policy",
                    "available", "list", "irukku", "iruku", "kya kya", "kaunsi",
                    "pathii", "pathi", "sollunga", "solunga", "batao", "rules", "la iruku", "kitta", "kitaa", "unga"
                ]) or any(p in t_lower for p in ["what policies", "all policies", "policy list", "available policies", "ena ena policy", "enna policy"])
                if is_overview or has_duration_policy_concept:
                    understanding.diagnostic_details["is_policy_overview"] = True
                    understanding.diagnostic_details["customer_item_term"] = customer_item_term
                    understanding.understood_meaning = "Customer is inquiring about available company policies"
                else:
                    understanding.understood_meaning = "Customer is inquiring about company policy"
            understanding.intent_confidence = 0.95
            understanding.clarification_needed = False
            return understanding

        # 7. Payments & Billing (Specific)
        payment_roots = [
            # English
            "pay", "deducted", "deduct", "charged", "transaction", "double charge", "twice", "fail aayiduchu", "failed payment", "bank", "invoice", "receipt", "bill", "txn", "debit", "debited",
            # Tamil
            "paisa kat", "kaasu", "panam", "poiduchu", "poiruchu", "பணம்", "காசு", "செலுத்த", "கட்டணம்", "பரிவர்த்தனை",
            # Hindi
            "paisa", "paise", "kat gaya", "chala gaya",
            # Telugu
            "dabbu", "dabbulu", "chesanu", "cheyaledu", "డబ్బు", "పేమెంట్", "చెల్లింపు",
            # Kannada
            "duddu", "hana", "maadiddini", "madilla", "ದುಡ್ಡು", "ಪೇಮೆಂಟ್", "ಪಾವತಿ",
            # Malayalam
            "cheythu", "cheythilla", "പണം", "പേയ്മെന്റ്",
            # Bengali
            "taka", "korechi", "korini", "টাকা", "পেমেন্ট",
            # Marathi
            "kela", "kela nahi", "पैसे", "पेमेंट",
            # Gujarati
            "rupia", "kari didhu", "nathi karyu", "રૂપિયા", "પેમેન્ટ",
            # Punjabi
            "kar ditta", "kar ditti", "nahi kita", "ਪੈਸੇ", "ਪੇਮੈਂਟ"
        ]
        if any(kw in combined for kw in payment_roots):
            is_payment_confirmation = (
                not negation
                and any(kw in combined for kw in [
                    # English
                    "done", "paid", "sent", "transferred", "success", "successful", "completed",
                    # Tamil
                    "panniten", "pantaen", "panniyachu", "aayiduchu", "செலுத்திவிட்டேன்", "செலுத்தியாச்சு", "கட்டியாச்சு", "அனுப்பிவிட்டேன்",
                    # Hindi
                    "kar diya", "bhej diya", "ho gaya", "kar di",
                    # Telugu
                    "chesanu", "chesa", "kattanu", "చేసాను", "పేమెంట్ చేశాను",
                    # Kannada
                    "maadiddini", "madide", "kotte", "ಮಾಡಿದ್ದೇನೆ", "ಪೇಮೆಂಟ್ ಮಾಡಿದ್ದೇನೆ",
                    # Malayalam
                    "cheythu", "koduthu", "ചെയ്തു", "പേയ്മെന്റ് ചെയ്തു",
                    # Bengali
                    "korechi", "diyechi", "করেছি", "পেমেন্ট করেছি",
                    # Marathi
                    "kela", "kela ahe", "dila", "केला", "पेमेंट केला",
                    # Gujarati
                    "kari didhu", "aapi didhu", "કરી દીધું", "પેમેન્ટ કરી દીધું",
                    # Punjabi
                    "kar ditta", "kar ditti", "ਕਰ ਦਿੱਤਾ", "ਪੇਮੈਂਟ ਕਰ ਦਿੱਤੀ",
                ])
                and not any(kw in combined for kw in [
                    "fail", "failed", "cut", "deduct", "twice", "double", "kat gaya", "error", "problem", "varala",
                    "cheyaledu", "madilla", "cheythilla", "korini", "kela nahi", "nathi karyu", "nahi kita",
                    "చేయలేదు", "ಮಾಡಲಿಲ್ಲ", "ಮಾಡಲ್ಲ", "ചെയ്തില്ല", "করিনি", "केला नाही", "નથી કર્યું", "ਨਹੀਂ ਕੀਤਾ"
                ])
            )
            if is_payment_confirmation:
                understanding.intent = "PAYMENT_CONFIRMATION"
                understanding.category = "payment"
                understanding.understood_meaning = "Customer confirmed payment has been made"
                understanding.intent_confidence = 0.94
                return understanding

            understanding.intent = "PAYMENT_ISSUE"
            understanding.category = "payment"
            understanding.intent_confidence = 0.92
            return understanding

        # 8. Order Management: Address change, cancel, modify
        if any(kw in combined for kw in [
            "address change", "change panna", "cancel panna", "badalna", "modify order",
            "change address", "cancel order", "cancel eppadi", "cancel pannuradhu",
            "cancel pannanum", "cancel pannalaam", "how to cancel", "kaise cancel", "cancel"
        ]):
            understanding.intent = "ORDER_MANAGEMENT"
            understanding.category = "order"
            understanding.intent_confidence = 0.95
            understanding.clarification_needed = False
            understanding.understood_meaning = "Customer is inquiring about order cancellation or modification"
            return understanding

        # 8.5. Warranty, Damage, & Defective Products
        damage_roots = [
            "warranty", "repair", "replace", "damage", "damaged", "broken", "broke",
            "service center", "claim", "odanjurukku", "udanjirukku", "odanjuduchu",
            "tuta", "tuti", "toota", "tooti", "kharab", "defect", "defective", "faulty",
            "velai seiyala", "kaam nahi kar raha", "chal nahi raha"
        ]
        if any(kw in combined for kw in damage_roots):
            understanding.intent = "WARRANTY_SERVICE"
            understanding.category = "warranty"
            understanding.diagnostic_details["customer_item_term"] = customer_item_term
            understanding.intent_confidence = 0.91
            return understanding

        # 9. Delivery & Shipping issues across pan-Indian languages
        delivery_roots = [
            # English
            "deliver", "delivery", "track", "shipping", "courier", "dispatch", "package", "parcel", "consignment", "arrive", "arrival",
            # Tamil
            "late aayiduchu", "eppo varum", "reach aagala", "reach", "vandhuchu", "vandhuduchu", "varala", "vara maattengudhu", "varum",
            "kedaikala", "kedaikum", "kedaikkum", "innum varala", "varave illa", "varave illai", "varave", "டெலிவரி", "வரவில்லை", "வரல", "இன்னும் வரவில்லை",
            # Hindi
            "kab tak", "kahan pahuncha", "pahunch", "pahuncha", "pahunchi", "aaya", "aayi", "aayega", "milega", "mili", "ruk gaya", "atki",
            # Telugu
            "raledu", "raaledu", "raaledhu", "ravatledu", "eppudu vastundi", "inka raledu", "రాలేదు", "ఆర్డర్", "డెలివరీ",
            # Kannada
            "bandilla", "baralla", "yaavaga barutte", "innu bandilla", "ಬಂದಿಲ್ಲ", "ಆರ್ಡರ್", "ಡೆಲಿವರಿ",
            # Malayalam
            "vannilla", "varilla", "ethiyilla", "eppol varum", "ithuvare vannilla", "വന്നില്ല", "ഓർഡർ", "ഡെലിവറി",
            # Bengali
            "asheni", "ashbe na", "kokhon ashbe", "ekhono asheni", "আসেনি", "অর্ডার", "ডেলিভারি",
            # Marathi
            "aala nahi", "aali nahi", "kadhi yenar", "ajun aala nahi", "आला नाही", "ऑर्डर", "डिलिव्हरी",
            # Gujarati
            "nathi aavyo", "nathi aavi", "kyare aavshe", "haji sudhi nathi aavyo", "નથી આવ્યો", "ઓર્ડર", "ડિલિવરી",
            # Punjabi
            "nahi aaya", "nahi aayi", "kadon aayega", "aje tak nahi aaya", "ਨਹੀਂ ਆਇਆ", "ਆਰਡਰ", "ਡਿਲੀਵਰੀ",
            # General delay
            "late", "delay", "delayed", "not arrived", "reach aala", "reached", "not delivered", "haven't received", "hasn't arrived", "not received"
        ]
        item_roots = [
            "order", "item", "saaman", "saamaan", "saman", "porul", "porutkal", "cheez", "box",
            "parcel", "parsal", "consignment", "package", "product", "goods",
            "ஆர்டர்", "பொருள்", "பொருட்கள்", "பார்சல்", "சாமான்கள்",
            "ఆర్డర్", "వస్తువు", "ಆರ್ಡರ್", "ವಸ್ತು", "ഓർഡർ", "സാധനം",
            "অর্ডার", "পণ্য", "ऑर्डर", "वस्तू", "ઓર્ડર", "વસ્તુ", "ਆਰਡਰ", "ਚੀਜ਼"
        ]
        has_delivery_kw = any(kw in combined for kw in delivery_roots)
        has_item_kw = any(kw in combined for kw in item_roots)
        is_delivery = (
            has_delivery_kw
            or (has_item_kw and any(w in combined for w in [
                "where", "kahan", "enga", "varala", "varum", "late", "status", "reach",
                "kedaikum", "eppo", "kab", "aayega", "varave", "illa", "arrived", "reach aagala",
                "not arrived", "வரவில்லை", "வரல", "இன்னும்",
                "raledu", "bandilla", "vannilla", "asheni", "aala nahi", "nathi aavyo", "nahi aaya",
                "రాలేదు", "ಬಂದಿಲ್ಲ", "വന്നില്ല", "আসেনি", "आला नाही", "નથી આવ્યો", "ਨਹੀਂ ਆਇਆ"
            ]))
        )
        if is_delivery:
            understanding.intent = "DELIVERY_ISSUE"
            understanding.category = "delivery"
            understanding.diagnostic_details["customer_item_term"] = customer_item_term
            understanding.intent_confidence = 0.92
            return understanding

        # 10. Subscriptions & Plan Changes
        if any(kw in combined for kw in ["subscription", "plan", "membership", "renew", "upgrade", "downgrade"]):
            understanding.intent = "SUBSCRIPTION_ISSUE"
            understanding.category = "subscription"
            understanding.intent_confidence = 0.91
            return understanding

        # 12. Short follow-ups & confirmations
        if t_lower in ["why", "why?", "still same", "adhukku apram?", "i already tried that", "tried that", "haan", "aama", "illa"]:
            understanding.intent = "FOLLOW_UP_CLARIFICATION"
            understanding.category = "clarification"
            understanding.intent_confidence = 0.90
            return understanding

        # 13. Polite greetings (ONLY if utterance has no substantive domain question)
        has_substantive = any(kw in combined for kw in [
            "policy", "return", "refund", "order", "delivery", "track", "cancel", "pay", "payment",
            "money", "problem", "issue", "crash", "error", "password", "login", "account",
            "panam", "kaasu", "paisa", "paise", "stolen", "hack", "fraud"
        ])
        words_set = set(re.findall(r'\b\w+\b', t_lower)) | set(re.findall(r'[^\s\.,!\?]+', t_lower))
        greeting_words = {"hello", "hi", "hey", "vanakkam", "வணக்கம்", "namaste", "नमस्ते"}
        multiword_greetings = ["good morning", "good evening", "good afternoon", "good day"]
        has_greeting_word = bool(words_set & greeting_words) or any(
            t_lower.startswith(phrase) or f" {phrase}" in t_lower for phrase in multiword_greetings
        )
        if has_greeting_word and not has_substantive:
            understanding.intent = "GREETING"
            understanding.category = "greeting"
            understanding.intent_confidence = 0.96
            return understanding

        # 14. Direct entity provision (e.g., customer just supplies ORD-123 or TXN-456)
        if "order_id" in entities:
            understanding.intent = "ORDER_STATUS"
            understanding.category = "order"
            understanding.intent_confidence = 0.95
            understanding.clarification_needed = False
            understanding.understood_meaning = f"Customer provided Order ID: {entities['order_id']}"
            return understanding

        if "transaction_id" in entities:
            understanding.intent = "PAYMENT_ISSUE"
            understanding.category = "payment"
            understanding.intent_confidence = 0.95
            understanding.clarification_needed = False
            understanding.understood_meaning = f"Customer provided Transaction ID: {entities['transaction_id']}"
            return understanding

        # 15. Check for gibberish or unclear tokens (e.g. 'daaksakd', 'asdfghj', '???')
        words = re.findall(r'[a-zA-Z]+', t_lower)
        is_gibberish = False
        if words and len(words) <= 2:
            common_words = {
                "the", "be", "to", "of", "and", "a", "in", "that", "have", "i", "it", "for", "not", "on", "with",
                "he", "as", "you", "do", "at", "this", "but", "his", "by", "from", "they", "we", "say", "her",
                "she", "or", "an", "will", "my", "one", "all", "would", "there", "their", "what", "so", "up",
                "out", "if", "about", "who", "get", "which", "go", "me", "when", "make", "can", "like", "time",
                "no", "just", "him", "know", "take", "people", "into", "year", "your", "good", "some", "could",
                "them", "see", "other", "than", "then", "now", "look", "only", "come", "its", "over", "think",
                "also", "back", "after", "use", "two", "how", "our", "work", "first", "well", "way", "even",
                "new", "want", "because", "any", "these", "give", "day", "most", "us", "enna", "eppo", "varum",
                "aachu", "bro", "bhai", "sir", "madam", "help", "order", "status", "dikkat", "kripya", "zaroor"
            }
            has_common = any(w in common_words for w in words)
            # Only flag actual random character smash without vowels or 5+ consecutive consonants
            # Legitimate words with vowels must NEVER be marked as gibberish
            has_no_vowels = all(not re.search(r'[aeiou]', w) for w in words if len(w) >= 3)
            has_unnatural_consonants = any(re.search(r'[^aeiou]{5,}', w) for w in words)
            if not has_common and (has_no_vowels or has_unnatural_consonants):
                is_gibberish = True

        if is_gibberish or (len(clean_text) > 0 and not re.search(r'[a-zA-Z0-9\u0B80-\u0BFF\u0900-\u097F]', clean_text)):
            understanding.intent = "UNCLEAR"
            understanding.category = "clarification"
            understanding.intent_confidence = 0.95
            understanding.clarification_needed = True
            understanding.is_ambiguous = True
            understanding.understood_meaning = "Customer input is unclear or unrecognized"
            return understanding

        # Default: General open-ended query (never hallucinate a fixed category)
        # RC-3: If there is an active ongoing intent and the current message is short/ambiguous
        # without introducing a new domain topic, continue the active conversation context.
        if (
            conversation_state
            and getattr(conversation_state, "active_intent", None)
            and conversation_state.active_intent not in ("GREETING", "GENERAL_QUERY", "ACKNOWLEDGMENT", "UNCLEAR")
            and getattr(conversation_state, "resolution_status", "") != "resolved"
            and len(clean_text.split()) <= 8
            and not has_substantive
        ):
            understanding.intent = conversation_state.active_intent
            understanding.category = getattr(conversation_state, "active_topic", "general")
            understanding.conversational_function = "FOLLOW_UP"
            understanding.intent_confidence = 0.88
            understanding.clarification_needed = False
            if any(w in t_lower for w in ["why", "kyun", "yen", "edhukku"]):
                understanding.diagnostic_details["explain_why"] = True
            understanding.understood_meaning = f"Context continuation on active {conversation_state.active_intent}: {clean_text}"
            return understanding

        understanding.intent = "GENERAL_QUERY"
        understanding.category = "general"
        understanding.intent_confidence = 0.80
        understanding.clarification_needed = False
        return understanding


class CodeMixedIntentExtractor:
    """
    Backward-compatible intent extractor leveraging the UniversalMeaningEngine.
    """

    def __init__(self):
        self.engine = UniversalMeaningEngine()
        self.detector = self.engine.detector
        self.normalizer = self.engine.normalizer

    def extract_intent(
        self,
        text: str,
        history: Optional[List[Dict[str, Any]]] = None,
        conversation_state: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Extract intent, language, negation, and entities from colloquial speech.
        """
        u = self.engine.understand_utterance(text, history=history, conversation_state=conversation_state)
        return {
            "intent": u.intent,
            "category": u.category,
            "language": u.code_mix_type or u.primary_language,
            "is_code_mixed": u.is_code_mixed,
            "normalized_text": u.normalized_meaning,
            "entities": u.entities,
            "confidence": u.intent_confidence,
            "negation_detected": u.negation_detected,
            "is_ambiguous": u.is_ambiguous,
            "clarification_needed": u.clarification_needed,
            "diagnostic_details": u.diagnostic_details,
            "conversational_function": u.conversational_function,
            "communication_style": u.communication_style,
            "understood_meaning": u.understood_meaning,
        }


# ============================================================
# RESOLVEAI V2 — EXTRA VOCABULARY EXTENSION
# Append this block at the END of your existing Python file.
# Existing functions and logic remain unchanged.
# ============================================================


# 1. Additional Tanglish language-detection markers
CodeMixedLanguageDetector.TANGLISH_MARKERS.update({

    # Everyday conversation
    "ennanga": "what",
    "ennachu": "what happened",
    "ennaachu": "what happened",
    "epdi": "how",
    "eppadiyum": "anyway",
    "ethuku": "why",
    "yenna": "what",
    "yaarukku": "to whom",
    "evlo": "how much",
    "evalo": "how much",
    "engayo": "somewhere",
    "eppovume": "always",
    "ippo": "now",
    "ippa": "now",
    "inniku": "today",
    "naalaiku": "tomorrow",
    "nethu": "yesterday",
    "apdi": "like that",
    "ipdi": "like this",
    "appuram": "afterwards",
    "adhukapram": "after that",
    "illana": "otherwise",
    "aama": "yes",
    "ama": "yes",
    "aamaanga": "yes",
    "kandippa": "definitely",
    "nichayama": "certainly",
    "unmaiya": "really",
    "nijama": "really",
    "summa": "just",
    "correct ah": "is it correct",
    "puriyave": "at all understand",
    "theriyave": "at all know",
    "sari": "okay",
    "seri": "okay",
    "paravala": "no problem",
    "paravalla": "no problem",
    "aama seri": "yes okay",

    # Requests and actions
    "help pannunga": "please help",
    "udane pannunga": "please do it immediately",
    "seekiram pannunga": "please do it quickly",
    "check pannunga": "please check",
    "fix pannunga": "please fix",
    "solve pannunga": "please resolve",
    "explain pannunga": "please explain",
    "update pannunga": "please update",
    "confirm pannunga": "please confirm",
    "verify pannunga": "please verify",
    "cancel pannunga": "please cancel",
    "anupunga": "please send",
    "anuppunga": "please send",
    "thirumba anupunga": "please send again",
    "kaaminga": "please show",
    "eduthu sollunga": "please explain",
    "konjam wait": "please wait a little",
    "wait pannunga": "please wait",
    "try pannunga": "please try",
    "open pannunga": "please open",
    "close pannunga": "please close",
    "enable pannunga": "please enable",
    "disable pannunga": "please disable",
    "change pannanum": "need to change",
    "maathanum": "need to change",
    "maathunga": "please change",
    "delete pannanum": "need to delete",
    "remove pannunga": "please remove",
    "kudukka mudiyuma": "can you give",
    "panna mudiyuma": "can you do it",

    # Problems and emotions
    "problem irukku": "there is a problem",
    "periya problem": "a major problem",
    "chinna problem": "a small problem",
    "issue irukku": "there is an issue",
    "work aagala": "not working",
    "velai seiyala": "not working",
    "sariya illa": "not correct",
    "sariya varala": "not coming correctly",
    "thappu aagiduchu": "something went wrong",
    "thappa irukku": "it is incorrect",
    "romba kashtam": "very difficult",
    "romba neram": "a long time",
    "neraya neram": "a long time",
    "late aagudhu": "it is getting delayed",
    "innum varala": "has not arrived yet",
    "innum aagala": "has not happened yet",
    "marandhuten": "I forgot",
    "marandhuten pa": "I forgot",
    "kovama irukku": "I am angry",
    "erichala irukku": "I am frustrated",
    "veruppa irukku": "I am fed up",
    "nambikkai illa": "I have no confidence",
    "suthama work aagala": "not working at all",
    "ethuvume work aagala": "nothing is working",
    "same problem varudhu": "the same problem keeps occurring",
    "thirumba vandhuduchu": "it happened again",

    # Orders and delivery
    "order enga": "where is the order",
    "order varala": "order has not arrived",
    "order late": "order is delayed",
    "order cancel": "cancel the order",
    "order status": "order status",
    "delivery eppo": "when is the delivery",
    "delivery varuma": "will the delivery arrive",
    "parcel varala": "parcel has not arrived",
    "product varala": "product has not arrived",
    "wrong product": "incorrect product",
    "damage aagiduchu": "it got damaged",
    "return pannanum": "need to return",
    "replace pannanum": "need a replacement",
    "address maathanum": "need to change the address",
    "tracking varala": "tracking is unavailable",

    # Payment and refunds
    "amount debit aachu": "amount was debited",
    "amount cut aachu": "amount was deducted",
    "kaasu poiduchu": "money is gone",
    "payment fail aachu": "payment failed",
    "payment aagala": "payment did not go through",
    "rendu thadava": "twice",
    "double payment": "duplicate payment",
    "refund venum": "need a refund",
    "refund varala": "refund has not arrived",
    "refund eppo": "when is the refund",
    "cashback varala": "cashback has not arrived",
    "balance update aagala": "balance did not update",
    "extra amount cut aachu": "an extra amount was deducted",

    # Login and technology
    "login aagala": "login is not working",
    "password marandhuten": "I forgot my password",
    "otp varala": "OTP has not arrived",
    "account lock aagiduchu": "account got locked",
    "app open aagala": "app is not opening",
    "screen freeze aagudhu": "screen is freezing",
    "loading la nikkudhu": "stuck on loading",
    "network problem": "network problem",
    "internet slow": "internet is slow",
    "server down": "server is down",
    "voice kekkala": "cannot hear the voice",
    "mic work aagala": "microphone is not working",

    # Human support and escalation
    "expert kitta pesanum": "want to speak to an expert",
    "manager kitta pesanum": "want to speak to a manager",
    "human kitta pesanum": "want to speak to a human",
    "agent kitta pesanum": "want to speak to an agent",
    "real person venum": "want a real person",
    "complaint pannanum": "want to make a complaint",
    "supervisor venum": "want a supervisor",
})


# 2. Additional Hinglish language-detection markers
CodeMixedLanguageDetector.HINGLISH_MARKERS.update({

    # Everyday conversation
    "kya hua": "what happened",
    "kya karna": "what to do",
    "kaise karun": "how should I do it",
    "kaise karein": "how should we do it",
    "kab milega": "when will I get it",
    "kab aayega": "when will it arrive",
    "kahan hai": "where is it",
    "kidhar hai": "where is it",
    "kitna time": "how much time",
    "kitni der": "how long",
    "kyun nahi": "why not",
    "abhi tak": "until now",
    "abhi": "now",
    "turant": "immediately",
    "jaldi": "quickly",
    "dobara": "again",
    "phir se": "again",
    "bilkul": "absolutely",
    "sach mein": "really",
    "accha": "okay",
    "achha": "okay",
    "theek hai": "okay",
    "thik hai": "okay",
    "koi baat nahi": "no problem",
    "samajh gaya": "I understood",
    "samajh gayi": "I understood",
    "samajh nahi aaya": "I did not understand",
    "pata nahi": "I do not know",
    "mujhe batao": "tell me",
    "mujhe samjhao": "explain to me",

    # Requests and actions
    "madad karo": "please help",
    "help karo": "please help",
    "check karo": "please check",
    "dekh lo": "please check",
    "bata dijiye": "please tell me",
    "samjha dijiye": "please explain",
    "theek kar do": "please fix it",
    "solve karo": "please resolve it",
    "update karo": "please update",
    "confirm karo": "please confirm",
    "verify karo": "please verify",
    "cancel kar do": "please cancel",
    "bhej do": "please send",
    "dobara bhejo": "send again",
    "kholo": "open it",
    "band karo": "close it",
    "badalna hai": "need to change",
    "hata do": "please remove",
    "kar sakte ho": "can you do it",
    "kar sakte hain": "can you do it",
    "nahi kar pa raha": "unable to do it",

    # Problems and emotions
    "bahut pareshan": "very frustrated",
    "gussa aa raha": "feeling angry",
    "thak gaya": "fed up",
    "thak gayi": "fed up",
    "bahut dikkat": "a major problem",
    "badi problem": "a major problem",
    "choti problem": "a small problem",
    "kaam nahi kar raha": "not working",
    "kaam nahi ho raha": "not working",
    "sahi nahi hai": "not correct",
    "galat hai": "it is incorrect",
    "abhi tak nahi hua": "it has not happened yet",
    "baar baar ho raha": "happening repeatedly",
    "wahi problem": "the same problem",
    "phir se problem": "the problem happened again",
    "time waste": "wasted time",
    "bahut der ho gayi": "it has taken too long",
    "jaldi chahiye": "need it quickly",
    "abhi chahiye": "need it now",

    # Orders and delivery
    "order nahi aaya": "order has not arrived",
    "order kahan hai": "where is the order",
    "order cancel karna": "want to cancel the order",
    "order status batao": "tell me the order status",
    "delivery late hai": "delivery is delayed",
    "delivery kab hogi": "when will delivery happen",
    "parcel nahi mila": "parcel was not received",
    "galat product": "incorrect product",
    "product damage hai": "product is damaged",
    "return karna hai": "want to return it",
    "replacement chahiye": "need a replacement",
    "address badalna hai": "want to change the address",
    "tracking nahi ho rahi": "tracking is not working",

    # Payments and refunds
    "paisa kat gaya": "money was deducted",
    "paise kat gaye": "money was deducted",
    "amount debit ho gaya": "amount was debited",
    "payment fail ho gaya": "payment failed",
    "payment nahi hua": "payment did not go through",
    "double payment ho gaya": "duplicate payment occurred",
    "refund chahiye": "need a refund",
    "refund nahi mila": "refund was not received",
    "refund abhi tak nahi mila": "refund has still not arrived",
    "refund kab milega": "when will the refund arrive",
    "cashback nahi mila": "cashback was not received",
    "balance update nahi hua": "balance did not update",
    "extra charge laga": "an extra charge was applied",

    # Login and technology
    "login nahi ho raha": "login is not working",
    "password bhool gaya": "I forgot my password",
    "password bhool gayi": "I forgot my password",
    "otp nahi aaya": "OTP did not arrive",
    "account lock ho gaya": "account got locked",
    "app nahi khul raha": "app is not opening",
    "screen freeze ho gayi": "screen froze",
    "loading par atka": "stuck on loading",
    "internet slow hai": "internet is slow",
    "server down hai": "server is down",
    "voice nahi aa rahi": "voice is not audible",
    "mic kaam nahi kar raha": "microphone is not working",

    # Human support and escalation
    "expert se baat karni hai": "want to speak to an expert",
    "manager se baat karni hai": "want to speak to a manager",
    "insaan se baat karni hai": "want to speak to a human",
    "agent se baat karni hai": "want to speak to an agent",
    "real person chahiye": "want a real person",
    "complaint karni hai": "want to make a complaint",
    "supervisor chahiye": "want a supervisor",
})


# 3. Additional vocabulary for the existing normalizer
IndianLanguageNormalizer.COLLOQUIAL_MAP.update({

    # Tanglish: conversation and requests
    "ennanga": "what",
    "ennachu": "what happened",
    "enna aachu": "what happened",
    "epdi": "how",
    "ethuku": "why",
    "evlo": "how much",
    "aama": "yes",
    "ama": "yes",
    "inniku": "today",
    "naalaiku": "tomorrow",
    "nethu": "yesterday",
    "ippo": "now",
    "apdi": "like that",
    "ipdi": "like this",
    "illana": "otherwise",
    "paravala": "no problem",
    "unmaiya": "really",
    "nichayama": "definitely",
    "help pannunga": "please help",
    "check pannunga": "please check",
    "fix pannunga": "please fix",
    "solve pannunga": "please resolve",
    "explain pannunga": "please explain",
    "confirm pannunga": "please confirm",
    "verify pannunga": "please verify",
    "cancel pannunga": "please cancel",
    "update pannunga": "please update",
    "wait pannunga": "please wait",
    "try pannunga": "please try",
    "maathanum": "need to change",
    "maathunga": "please change",
    "thirumba anupunga": "please send again",

    # Tanglish: complaints
    "romba neram aachu": "it has taken a very long time",
    "neraya neram aachu": "it has taken a long time",
    "innum varala": "has not arrived yet",
    "innum aagala": "has not happened yet",
    "work aagala": "not working",
    "suthama work aagala": "not working at all",
    "same problem varudhu": "the same problem keeps occurring",
    "thirumba vandhuduchu": "it happened again",
    "thappa irukku": "it is incorrect",
    "romba kashtam": "very difficult",
    "kovama irukku": "I am angry",
    "erichala irukku": "I am frustrated",
    "veruppa irukku": "I am fed up",

    # Tanglish: order and delivery
    "order enga": "where is the order",
    "order varala": "order has not arrived",
    "order late": "order is delayed",
    "order cancel": "cancel the order",
    "delivery eppo": "when is the delivery",
    "delivery varuma": "will the delivery arrive",
    "parcel varala": "parcel has not arrived",
    "product varala": "product has not arrived",
    "wrong product": "incorrect product",
    "return pannanum": "need to return",
    "replace pannanum": "need a replacement",
    "address maathanum": "need to change the address",

    # Tanglish: payment
    "amount debit aachu": "amount was debited",
    "amount cut aachu": "amount was deducted",
    "kaasu poiduchu": "money is gone",
    "payment fail aachu": "payment failed",
    "payment aagala": "payment did not go through",
    "rendu thadava": "twice",
    "refund venum": "need a refund",
    "refund varala": "refund has not arrived",
    "refund eppo": "when is the refund",
    "cashback varala": "cashback has not arrived",

    # Tanglish: login and technology
    "login aagala": "login is not working",
    "password marandhuten": "I forgot my password",
    "otp varala": "OTP has not arrived",
    "account lock aagiduchu": "account got locked",
    "app open aagala": "app is not opening",
    "screen freeze aagudhu": "screen is freezing",
    "loading la nikkudhu": "stuck on loading",
    "internet slow": "internet is slow",
    "voice kekkala": "cannot hear the voice",
    "mic work aagala": "microphone is not working",

    # Tanglish: human handoff requests
    "expert kitta pesanum": "want to speak to an expert",
    "manager kitta pesanum": "want to speak to a manager",
    "human kitta pesanum": "want to speak to a human",
    "agent kitta pesanum": "want to speak to an agent",
    "real person venum": "want a real person",
    "complaint pannanum": "want to make a complaint",
    "supervisor venum": "want a supervisor",

    # Hinglish: conversation and requests
    "kya hua": "what happened",
    "kya karna": "what to do",
    "kaise karun": "how should I do it",
    "kab milega": "when will I get it",
    "kab aayega": "when will it arrive",
    "kahan hai": "where is it",
    "kitni der": "how long",
    "abhi tak": "until now",
    "turant": "immediately",
    "jaldi": "quickly",
    "phir se": "again",
    "sach mein": "really",
    "koi baat nahi": "no problem",
    "mujhe batao": "tell me",
    "mujhe samjhao": "explain to me",
    "madad karo": "please help",
    "help karo": "please help",
    "check karo": "please check",
    "theek kar do": "please fix it",
    "solve karo": "please resolve it",
    "update karo": "please update",
    "confirm karo": "please confirm",
    "verify karo": "please verify",
    "cancel kar do": "please cancel",
    "dobara bhejo": "send again",
    "hata do": "please remove",

    # Hinglish: complaints
    "bahut pareshan": "very frustrated",
    "gussa aa raha": "feeling angry",
    "thak gaya": "fed up",
    "thak gayi": "fed up",
    "bahut dikkat": "a major problem",
    "kaam nahi kar raha": "not working",
    "kaam nahi ho raha": "not working",
    "sahi nahi hai": "not correct",
    "galat hai": "it is incorrect",
    "abhi tak nahi hua": "it has not happened yet",
    "baar baar ho raha": "happening repeatedly",
    "wahi problem": "the same problem",
    "phir se problem": "the problem happened again",
    "bahut der ho gayi": "it has taken too long",
    "jaldi chahiye": "need it quickly",
    "abhi chahiye": "need it now",

    # Hinglish: orders and delivery
    "order nahi aaya": "order has not arrived",
    "order kahan hai": "where is the order",
    "order cancel karna": "want to cancel the order",
    "delivery late hai": "delivery is delayed",
    "delivery kab hogi": "when will delivery happen",
    "parcel nahi mila": "parcel was not received",
    "galat product": "incorrect product",
    "product damage hai": "product is damaged",
    "return karna hai": "want to return it",
    "replacement chahiye": "need a replacement",
    "address badalna hai": "want to change the address",
    "tracking nahi ho rahi": "tracking is not working",

    # Hinglish: payments
    "paisa kat gaya": "money was deducted",
    "paise kat gaye": "money was deducted",
    "amount debit ho gaya": "amount was debited",
    "payment fail ho gaya": "payment failed",
    "payment nahi hua": "payment did not go through",
    "double payment ho gaya": "duplicate payment occurred",
    "refund chahiye": "need a refund",
    "refund nahi mila": "refund was not received",
    "refund abhi tak nahi mila": "refund has still not arrived",
    "refund kab milega": "when will the refund arrive",
    "cashback nahi mila": "cashback was not received",
    "balance update nahi hua": "balance did not update",
    "extra charge laga": "an extra charge was applied",

    # Hinglish: login and technology
    "login nahi ho raha": "login is not working",
    "password bhool gaya": "I forgot my password",
    "password bhool gayi": "I forgot my password",
    "otp nahi aaya": "OTP did not arrive",
    "account lock ho gaya": "account got locked",
    "app nahi khul raha": "app is not opening",
    "screen freeze ho gayi": "screen froze",
    "loading par atka": "stuck on loading",
    "internet slow hai": "internet is slow",
    "server down hai": "server is down",
    "voice nahi aa rahi": "voice is not audible",
    "mic kaam nahi kar raha": "microphone is not working",

    # Hinglish: human handoff requests
    "expert se baat karni hai": "want to speak to an expert",
    "manager se baat karni hai": "want to speak to a manager",
    "insaan se baat karni hai": "want to speak to a human",
    "agent se baat karni hai": "want to speak to an agent",
    "real person chahiye": "want a real person",
    "complaint karni hai": "want to make a complaint",
    "supervisor chahiye": "want a supervisor",
})
