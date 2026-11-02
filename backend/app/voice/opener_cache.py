"""
ResolveAIV2 — Milestone P1.7 Cached Voice Opener & Filler Audio Store

Caches pre-synthesized audio for fixed neutral acknowledgments, openers,
and conversational backchannels. Serving from memory/disk eliminates the
~1,000 ms HTTPS network round-trip to the TTS provider on the first audible sound path.
"""

import os
import hashlib
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent / "cached_openers"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# In-memory audio byte buffer: (speaker, language_code, normalized_text) -> bytes
_MEMORY_CACHE: Dict[str, bytes] = {}

# Standard Greetings per Language (Played as ONE clip with 0 network calls)
STANDARD_GREETINGS = {
    "English": "Hello! I am ResolveAI. How can I help you today?",
    "Tanglish": "Vanakkam! Naan ResolveAI. Ungalukku enna help venum?",
    "Tamil": "வணக்கம்! நான் ResolveAI. உங்களுக்கு என்ன உதவி வேண்டும்?",
    "Hindi": "नमस्ते! मैं ResolveAI हूँ। मैं आपकी क्या मदद कर सकता हूँ?",
    "Hinglish": "Namaste! Main ResolveAI hoon. Main aapki kya help kar sakta hoon?",
    "Telugu": "నమస్కారం! నేను ResolveAI. మీకు ఎలా సహాయపడగలను?",
    "Tenglish": "Namaskaram! Nenu ResolveAI. Meeku ela help cheyagalanu?",
    "Kannada": "ನಮಸ್ಕಾರ! ನಾನು ResolveAI. ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಬಹುದು?",
    "Kanglish": "Namaskara! Naanu ResolveAI. Nimage hege help madli?",
    "Malayalam": "നമസ്കാരം! ഞാൻ ResolveAI. ഞാൻ എങ്ങനെ സഹായിക്കണം?",
    "Manglish": "Namaskaram! Njan ResolveAI. Ningalkku engane help venam?",
    "Bengali": "নমস্কার! আমি ResolveAI। আমি আপনাকে কীভাবে সাহায্য করতে পারি?",
    "Benglish": "Nomoshkar! Ami ResolveAI. Apanake kibhabe help korte pari?",
    "Marathi": "नमस्कार! मी ResolveAI आहे. मी तुम्हाला कशी मदत करू शकतो?",
    "Marathish": "Namaskar! Me ResolveAI ahe. Me tumhala kashi help karu shakto?",
    "Gujarati": "નમસ્તે! હું ResolveAI છું. હું તમારી કેવી રીતે મદદ કરી શકું?",
    "Gujlish": "Namaste! Hu ResolveAI chhu. Hu tamari kevi rite help kari shaku?",
    "Punjabi": "ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ! ਮੈਂ ResolveAI ਹਾਂ। ਮੈਂ ਤੁਹਾਡੀ ਕੀ ਮਦਦ ਕਰ ਸਕਦਾ ਹਾਂ?",
    "Punglish": "Sat Sri Akal! Main ResolveAI haan. Main tuhadi ki help kar sakda haan?",
    "Odia": "ନମସ୍କାର! ମୁଁ ResolveAI। ମୁଁ ଆପଣଙ୍କୁ କିପରି ସାହାଯ୍ୟ କରିପାରିବି?",
    "Assamese": "নমস্কাৰ! মই ResolveAI। মই আপোনাক কেনেকৈ সহায় কৰিব পাৰোঁ?",
    "Urdu": "آداب! میں ResolveAI ہوں۔ میں آپ کی کیا مدد کر سکتا ہوں؟",
}

# Standard Voice Fillers / Backchannels per Language
STANDARD_FILLERS = {
    "English": ["Right.", "Got it.", "Okay.", "Sure.", "One moment."],
    "Tanglish": ["Seri bro.", "Kandippa.", "Kettukren.", "Oru nimisham."],
    "Tamil": ["சரி.", "நிச்சயமாக.", "கேட்கிறேன்.", "ஒரு நிமிடம்."],
    "Hindi": ["हाँ जी।", "ठीक है।", "बिल्कुल।", "एक सेकंड।"],
    "Hinglish": ["Haan ji.", "Theek hai.", "Bilkul.", "Ek second."],
    "Telugu": ["సరేనండి.", "ఖచ్చితంగా.", "వింటున్నాను.", "ఒక్క నిమిషం."],
    "Tenglish": ["Sare andi.", "Kachithanga.", "Vintunnanu.", "Okka nimisham."],
    "Kannada": ["ಸರಿ.", "ಖಂಡಿತ.", "ಕೇಳ್ತಾ ಇದ್ದೀನಿ.", "ಒಂದು ನಿಮಿಷ."],
    "Kanglish": ["Sari.", "Kanditha.", "Keltha iddini.", "Ondu nimisha."],
    "Malayalam": ["ശരി.", "തീർച്ചയായും.", "കേൾക്കുന്നുണ്ട്.", "ഒരു നിമിഷം."],
    "Manglish": ["Sheri.", "Theerchayayum.", "Kelkkunnundu.", "Oru nimisham."],
    "Bengali": ["ঠিক আছে।", "অবশ্যই।", "শুনছি।", "এক মিনিট।"],
    "Benglish": ["Thik ache.", "Nishchoi.", "Shunchhi.", "Ek minute."],
    "Marathi": ["ठीक आहे.", "नक्कीच.", "ऐकतोय.", "एक मिनिट."],
    "Marathish": ["Theek ahe.", "Nakkich.", "Aaiktoy.", "Ek minute."],
    "Gujarati": ["બરાબર.", "ચોક્કસ.", "સાંભળું છું.", "એક મિનિટ."],
    "Gujlish": ["Barabar.", "Chokkas.", "Sambhalu chhu.", "Ek minute."],
    "Punjabi": ["ਠੀਕ ਹੈ।", "ਜ਼ਰੂਰ।", "ਸੁਣ ਰਿਹਾ ਹਾਂ।", "ਇੱਕ ਮਿੰਟ।"],
    "Punglish": ["Theek hai.", "Zaroor.", "Sun reha haan.", "Ik minute."],
    "Odia": ["ଠିକ୍ ଅଛି।", "ନିଶ୍ଚିତ।", "ଶୁଣୁଛି।", "ଗୋଟିଏ ମିନିଟ୍।"],
    "Assamese": ["ঠিক আছে।", "নিশ্চয়।", "শুনি আছোঁ।", "এক মিনিট।"],
    "Urdu": ["ٹھیک ہے۔", "ضرور۔", "سن رہا ہوں۔", "ایک منٹ۔"],
}

# Standard Escalation lines per Language (Instant playback when handoff occurs)
STANDARD_ESCALATIONS = {
    "English": "I need to connect you with an expert to assist you securely.",
    "Tanglish": "Ungalukku help panna naan oru human expert kitta connect panren.",
    "Tamil": "உங்களுக்கு உதவ நான் ஒரு நிபுணருடன் இணைக்கிறேன்.",
    "Hindi": "मैं आपको सुरक्षित सहायता के लिए एक विशेषज्ञ से जोड़ रहा हूँ।",
    "Hinglish": "Main aapko safely assist karne ke liye ek expert se connect kar raha hoon.",
    "Telugu": "మీకు సహాయం చేయడానికి నేను ఒక నిపుణుడితో కనెక్ట్ చేస్తున్నాను.",
    "Tenglish": "Meeku help cheyadaniki nenu oka human expert tho connect chestunnanu.",
    "Kannada": "ನಿಮಗೆ ಸಹಾಯ ಮಾಡಲು ನಾನು ಒಬ್ಬ ತಜ್ಞರೊಂದಿಗೆ ಸಂಪರ್ಕಿಸುತ್ತೇನೆ.",
    "Kanglish": "Nimage help madoke naanu obba human expert jothe connect madthini.",
    "Malayalam": "നിങ്ങളെ സഹായിക്കാൻ ഞാൻ ഒരു വിദഗ്ദ്ധനുമായി ബന്ധിപ്പിക്കുന്നു.",
    "Manglish": "Ningalkku help cheyyan njan oru expert-umaayi connect cheyyaam.",
    "Bengali": "আপনাকে সহায়তা করার জন্য আমি একজন বিশেষজ্ঞের সাথে যুক্ত করছি।",
    "Benglish": "Apanake help korar jonno ami ekjon human expert er sathe connect korchhi.",
    "Marathi": "तुम्हाला मदत करण्यासाठी मी एका तज्ज्ञाशी संपर्क साधून देतो.",
    "Marathish": "Tumhala help karnyasathi me eka human expert shi connect karto.",
    "Gujarati": "તમને મદદ કરવા માટે હું એક નિષ્ણાત સાથે કનેક્ટ કરી રહ્યો છું.",
    "Gujlish": "Tamne help karva mate hu ek human expert saathe connect kari rahyo chhu.",
    "Punjabi": "ਤੁਹਾਡੀ ਮਦਦ ਲਈ ਮੈਂ ਤੁਹਾਨੂੰ ਇੱਕ ਮਾਹਰ ਨਾਲ ਜੋੜ ਰਿਹਾ ਹਾਂ।",
    "Punglish": "Tuhadi help layi main tuhanu ik human expert naal connect kar reha haan.",
    "Odia": "ଆପଣଙ୍କୁ ସାହାଯ୍ୟ କରିବା ପାଇଁ ମୁଁ ଜଣେ ବିଶେଷଜ୍ଞଙ୍କ ସହିତ ସଂଯୋଗ କରୁଛି।",
    "Assamese": "আপোনাক সহায় কৰিবলৈ মই এজন বিশেষজ্ঞৰ সৈতে সংযোগ কৰি আছোঁ।",
    "Urdu": "آپ کی مدد کے لیے میں آپ کو ایک ماہر سے جوڑ رہا ہوں۔",
}

LANGUAGE_CODE_MAP = {
    "english": "en-IN",
    "en": "en-IN",
    "en-in": "en-IN",
    "en-us": "en-IN",
    "tanglish": "ta-IN",
    "tamil": "ta-IN",
    "ta": "ta-IN",
    "ta-in": "ta-IN",
    "hindi": "hi-IN",
    "hinglish": "hi-IN",
    "hi": "hi-IN",
    "hi-in": "hi-IN",
    "telugu": "te-IN",
    "tenglish": "te-IN",
    "te": "te-IN",
    "te-in": "te-IN",
    "kannada": "kn-IN",
    "kanglish": "kn-IN",
    "kn": "kn-IN",
    "kn-in": "kn-IN",
    "malayalam": "ml-IN",
    "manglish": "ml-IN",
    "ml": "ml-IN",
    "ml-in": "ml-IN",
    "bengali": "bn-IN",
    "benglish": "bn-IN",
    "bangla": "bn-IN",
    "bn": "bn-IN",
    "bn-in": "bn-IN",
    "marathi": "mr-IN",
    "marathish": "mr-IN",
    "mr": "mr-IN",
    "mr-in": "mr-IN",
    "gujarati": "gu-IN",
    "gujlish": "gu-IN",
    "gu": "gu-IN",
    "gu-in": "gu-IN",
    "punjabi": "pa-IN",
    "punglish": "pa-IN",
    "pa": "pa-IN",
    "pa-in": "pa-IN",
    "odia": "od-IN",
    "odlish": "od-IN",
    "oriya": "od-IN",
    "od": "od-IN",
    "od-in": "od-IN",
    "or": "od-IN",
    "or-in": "od-IN",
    "assamese": "as-IN",
    "as": "as-IN",
    "as-in": "as-IN",
    "urdu": "ur-IN",
    "ur": "ur-IN",
    "ur-in": "ur-IN",
}


def _cache_key(speaker: str, language_code: str, text: str) -> str:
    norm_text = " ".join(text.lower().strip().split())
    text_hash = hashlib.md5(norm_text.encode("utf-8")).hexdigest()[:10]
    return f"{speaker.lower()}_{language_code.lower()}_{text_hash}"


def get_cached_opener_audio(
    text: str,
    speaker: str = "kavya",
    language_code: str = "en-IN"
) -> Optional[bytes]:
    """
    Retrieves pre-synthesized audio bytes from memory or disk cache in < 0.1 ms.
    Returns None if not yet cached.
    """
    key = _cache_key(speaker, language_code, text)
    
    # 1. Memory cache hit
    if key in _MEMORY_CACHE:
        return _MEMORY_CACHE[key]
        
    # 2. Disk cache hit
    disk_path = CACHE_DIR / f"{key}.mp3"
    if disk_path.exists():
        try:
            data = disk_path.read_bytes()
            _MEMORY_CACHE[key] = data
            return data
        except Exception as e:
            logger.warning(f"Error reading opener disk cache: {e}")
            
    return None


def store_cached_opener_audio(
    text: str,
    audio_bytes: bytes,
    speaker: str = "kavya",
    language_code: str = "en-IN"
) -> None:
    """Stores synthesized audio bytes in memory and disk cache."""
    if not audio_bytes:
        return
    key = _cache_key(speaker, language_code, text)
    _MEMORY_CACHE[key] = audio_bytes
    try:
        disk_path = CACHE_DIR / f"{key}.mp3"
        disk_path.write_bytes(audio_bytes)
    except Exception as e:
        logger.warning(f"Error persisting opener audio to disk: {e}")


async def warm_opener_cache_if_needed(speaker: str = "kavya"):
    """
    Pre-warms the opener and filler audio cache lazily or during startup.
    Synthesizes each unique opener once, eliminating TTS network wait on live calls.
    """
    from app.voice.sarvam_tts import synthesize_sarvam
    from app.conversations.service import ConversationService
    
    pools = ConversationService.OPENER_POOLS
    for lang, categories in pools.items():
        lang_code = LANGUAGE_CODE_MAP.get(lang.lower(), "en-IN")
        all_phrases = categories.get("neutral", []) + categories.get("frustrated", [])
        for phrase in all_phrases:
            if not get_cached_opener_audio(phrase, speaker, lang_code):
                try:
                    b = await synthesize_sarvam(phrase, language_code=lang_code)
                    store_cached_opener_audio(phrase, b, speaker, lang_code)
                    logger.info(f"Cached opener audio: '{phrase}' ({lang_code}) - {len(b)} bytes")
                except Exception as e:
                    logger.warning(f"Failed to pre-cache opener '{phrase}': {e}")

    for lang, fillers in STANDARD_FILLERS.items():
        lang_code = LANGUAGE_CODE_MAP.get(lang.lower(), "en-IN")
        for phrase in fillers:
            if not get_cached_opener_audio(phrase, speaker, lang_code):
                try:
                    b = await synthesize_sarvam(phrase, language_code=lang_code)
                    store_cached_opener_audio(phrase, b, speaker, lang_code)
                    logger.info(f"Cached filler audio: '{phrase}' ({lang_code}) - {len(b)} bytes")
                except Exception as e:
                    logger.warning(f"Failed to pre-cache filler '{phrase}': {e}")

    for lang, greeting in STANDARD_GREETINGS.items():
        lang_code = LANGUAGE_CODE_MAP.get(lang.lower(), "en-IN")
        if not get_cached_opener_audio(greeting, speaker, lang_code):
            try:
                b = await synthesize_sarvam(greeting, language_code=lang_code)
                store_cached_opener_audio(greeting, b, speaker, lang_code)
                logger.info(f"Cached greeting audio: '{greeting}' ({lang_code}) - {len(b)} bytes")
            except Exception as e:
                logger.warning(f"Failed to pre-cache greeting '{greeting}': {e}")

    for lang, escalation in STANDARD_ESCALATIONS.items():
        lang_code = LANGUAGE_CODE_MAP.get(lang.lower(), "en-IN")
        if not get_cached_opener_audio(escalation, speaker, lang_code):
            try:
                b = await synthesize_sarvam(escalation, language_code=lang_code)
                store_cached_opener_audio(escalation, b, speaker, lang_code)
                logger.info(f"Cached escalation audio: '{escalation}' ({lang_code}) - {len(b)} bytes")
            except Exception as e:
                logger.warning(f"Failed to pre-cache escalation '{escalation}': {e}")
