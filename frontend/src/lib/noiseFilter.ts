/**
 * ResolveAIV2 — Voice Input & STT Noise / Hallucination Filter
 *
 * Prevents ambient noise, background conversations, TV audio, and STT hallucinations
 * from reaching the LLM while strictly preserving:
 * 1. Legitimate short answers (e.g., "yes", "no", "stop", "cancel", "help", "seri", "haan")
 * 2. All 22 supported Indian languages, native scripts, and code-mixed speech (Tanglish, Hinglish)
 * 3. Natural customer utterances with pauses
 */

export interface UtteranceValidationResult {
  isValid: boolean;
  reason?: string;
  cleanedText: string;
  isShortAnswer: boolean;
  needsConfirmation?: boolean;
}

/**
 * Normalized Whitelist of Valid Short Answers and Commands.
 * Stored in lowercase, stripped of surrounding punctuation.
 * Covers English, Tanglish, Hinglish, Tamil, Hindi, Kannada, Telugu,
 * Malayalam, Bengali, Marathi, Gujarati, Punjabi, Odia, Urdu,
 * in both Latin transliteration and native Indic scripts.
 */
export const WHITELISTED_SHORT_UTTERANCES = new Set<string>([
  // ── English ──
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

  // ── Tamil & Tanglish ──
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
  // Tamil Script
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

  // ── Hindi & Hinglish ──
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
  // Hindi Devanagari Script
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

  // ── Kannada & Kanglish ──
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
  // Kannada Script
  "ಹೌದು",
  "ಇಲ್ಲ",
  "ಸರಿ",
  "ನಿಲ್ಲಿಸಿ",
  "ಸಹಾಯ",
  "ನಮಸ್ಕಾರ",
  "ಧನ್ಯವಾದಗಳು",

  // ── Telugu & Tenglish ──
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
  // Telugu Script
  "అవును",
  "కాదు",
  "సరే",
  "ఆపు",
  "ఆగండి",
  "సహాయం",
  "నమస్కారం",
  "ధన్యవాదాలు",

  // ── Malayalam & Manglish ──
  "athe",
  "alla",
  "seri",
  "nirthu",
  "nilkku",
  "sahayam",
  "namaskaram",
  "nanni",
  "parayu",
  // Malayalam Script
  "അതെ",
  "അല്ല",
  "ശരി",
  "നിർത്തൂ",
  "സഹായം",
  "നമസ്കാരം",
  "നന്ദി",

  // ── Bengali ──
  "hyan",
  "na",
  "thik achhe",
  "thamo",
  "sahajjo",
  "namaskar",
  "dhonnobad",
  // Bengali Script
  "হ্যাঁ",
  "না",
  "ঠিক আছে",
  "থামো",
  "সাহায্য",
  "নমস্কার",
  "ধন্যবাদ",

  // ── Marathi ──
  "ho",
  "nahi",
  "thik ahe",
  "thamba",
  "madat",
  "dhanyavad",
  // Marathi Script
  "हो",
  "नाही",
  "ठीक आहे",
  "थांबा",
  "मदत",

  // ── Gujarati ──
  "haa",
  "na",
  "barobar",
  "madad",
  "aabhar",
  // Gujarati Script
  "હા",
  "ના",
  "બરાબર",
  "મદદ",
  "આભાર",

  // ── Punjabi ──
  "haanji",
  "theek ae",
  "roko",
  "sat sri akal",
  // Punjabi Script
  "ਹਾਂ",
  "ਨਹੀਂ",
  "ਠੀਕ ਹੈ",
  "ਰੋਕੋ",
  "ਮਦਦ",
  "ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ",

  // ── Odia ──
  "thik achhi",
  // Odia Script
  "ହଁ",
  "ନା",
  "ଠିକ ଅଛି",
  "ସାହାଯ୍ୟ",

  // ── Urdu ──
  // Urdu Script
  "ہاں",
  "نہیں",
  "شکریہ",
  "مدد",
  "ٹھیک ہے",
  "آداب",
]);

/**
 * Bracketed non-speech sound descriptors (common in Whisper, YouTube data, and Saaras).
 */
const BRACKETED_NOISE_REGEX = /^(\[|\()(music|applause|laughter|laughter and applause|cheering|cough|coughing|throat clearing|groan|sigh|gasp|screaming|snicker|crying|noise|background noise|whisper|chatter|inaudible|unintelligible|bell|silence)(\]|\))$/i;

/**
 * Common subtitle / video training corpus hallucinations.
 */
const CORPUS_HALLUCINATIONS = [
  "thank you for watching",
  "thanks for watching",
  "subtitles by",
  "please subscribe",
  "like and subscribe",
  "translated by",
  "all rights reserved",
  "watching this video",
  "see you next time",
];

/**
 * Isolated non-lexical filler murmurs that do not constitute meaningful speech.
 */
const ISOLATED_FILLERS = new Set<string>([
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
]);

/**
 * Validate customer utterance before sending to the LLM or triggering an agent response.
 *
 * @param text The transcribed text from STT (Browser SpeechRecognition, Saaras, Whisper, etc.)
 * @param confidence Optional provider confidence score [0.0, 1.0]
 * @returns UtteranceValidationResult indicating whether to process or ignore
 */
export function validateCustomerUtterance(
  text: string,
  confidence?: number | null
): UtteranceValidationResult {
  const raw = (text || "").trim();

  // 1. Reject empty or whitespace-only
  if (!raw) {
    return {
      isValid: false,
      reason: "empty_or_whitespace",
      cleanedText: "",
      isShortAnswer: false,
    };
  }

  // Normalize punctuation for matching
  const stripped = raw
    .toLowerCase()
    .replace(/^[.,\/#!$%\^&\*;:{}=\-_`~()?"'–—\s]+|[.,\/#!$%\^&\*;:{}=\-_`~()?"'–—\s]+$/g, "")
    .trim();

  if (!stripped) {
    return {
      isValid: false,
      reason: "punctuation_only",
      cleanedText: raw,
      isShortAnswer: false,
    };
  }

  // 2. Strict Whitelist Check: Valid short answers must always pass!
  if (WHITELISTED_SHORT_UTTERANCES.has(stripped)) {
    return {
      isValid: true,
      cleanedText: raw,
      isShortAnswer: true,
      needsConfirmation: false,
    };
  }

  // 3. Bracketed audio/sound tag hallucinations (e.g. [music], (applause))
  if (BRACKETED_NOISE_REGEX.test(raw) || BRACKETED_NOISE_REGEX.test(stripped)) {
    return {
      isValid: false,
      reason: "bracketed_noise_tag",
      cleanedText: raw,
      isShortAnswer: false,
    };
  }

  // 4. Corpus / subtitle hallucination phrases
  const lowerText = raw.toLowerCase();
  for (const hallucination of CORPUS_HALLUCINATIONS) {
    if (lowerText === hallucination || lowerText.startsWith(hallucination + ".") || lowerText.endsWith(hallucination)) {
      return {
        isValid: false,
        reason: "corpus_hallucination",
        cleanedText: raw,
        isShortAnswer: false,
      };
    }
  }

  // 5. Isolated filler murmurs (e.g., "uh", "hmm", "um" alone)
  if (ISOLATED_FILLERS.has(stripped)) {
    return {
      isValid: false,
      reason: "isolated_filler_noise",
      cleanedText: raw,
      isShortAnswer: false,
    };
  }

  // 6. Single character fragment (except for digits 0-9)
  if (stripped.length === 1 && !/^\d$/.test(stripped)) {
    return {
      isValid: false,
      reason: "single_char_fragment",
      cleanedText: raw,
      isShortAnswer: false,
    };
  }

  // 7. Repetitive noise characters (e.g. ".....", "zzzzz", "?????")
  if (/^(.)\1{3,}$/.test(stripped)) {
    return {
      isValid: false,
      reason: "repetitive_character_noise",
      cleanedText: raw,
      isShortAnswer: false,
    };
  }

  // 8. Low-Confidence Safety Check (when provider exposes confidence)
  // Confidence < 0.35 on a non-whitelisted utterance is almost always noise/hallucination
  if (confidence !== null && confidence !== undefined) {
    if (confidence < 0.35) {
      return {
        isValid: false,
        reason: "low_stt_confidence",
        cleanedText: raw,
        isShortAnswer: false,
      };
    }
    // Ambiguous confidence (0.35 - 0.60): flag for confirmation prompt
    if (confidence < 0.60) {
      return {
        isValid: true,
        reason: "borderline_confidence",
        cleanedText: raw,
        isShortAnswer: false,
        needsConfirmation: true,
      };
    }
  }

  // Passed all filters: legitimate customer utterance
  return {
    isValid: true,
    cleanedText: raw,
    isShortAnswer: false,
    needsConfirmation: false,
  };
}

