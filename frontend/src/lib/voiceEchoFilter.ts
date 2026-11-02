/**
 * ResolveAIV2 — Voice Echo Filter & Turn Coordinator (Milestone P2.5)
 *
 * Prevents the agent from hearing its own speech on laptop speakers:
 * 1. Blocks any turn while agent audio is playing, plus a 300 ms acoustic reverberation tail.
 * 2. Echo filter with token overlap and substring matching for neural audio transcripts.
 * 3. Barge-in on sustained speech (>= 400 ms) that does not match recent agent text.
 * 4. Dev timing logger: tracks speech end, final transcript, request sent, TTS chunks,
 *    and every recognition result with `agent_audio_was_playing` and `echo_filter_dropped`.
 */

export interface VoiceDevLogEntry {
  event: string;
  timestamp: string;
  data: Record<string, any>;
}

export const GREETINGS_BY_LANGUAGE: Record<string, string> = {
  "en-IN": "Hello! I am ResolveAI. How can I help you today?",
  "ta-IN": "Vanakkam! Naan ResolveAI. Ungalukku enna help venum?",
  "hi-IN": "Namaste! Main ResolveAI hoon. Main aapki kya help kar sakta hoon?",
  "kn-IN": "Namaskara! Naanu ResolveAI. Nimage hege help madli?",
  "te-IN": "Namaskaram! Nenu ResolveAI. Meeku ela help cheyagalanu?",
  "ml-IN": "Namaskaram! Njan ResolveAI. Ningalkku engane help venam?",
  "bn-IN": "Nomoshkar! Aami ResolveAI. Apanake kibhabe help korte pari?",
  "mr-IN": "Namaskar! Me ResolveAI ahe. Me tumhala kashi help karu shakto?",
  "gu-IN": "Namaste! Hu ResolveAI chhu. Hu tamari kevi rite help kari shaku?",
  "pa-IN": "Sat Sri Akal! Main ResolveAI haan. Main tuhadi ki help kar sakda haan?",
  "od-IN": "Nomoshkar! Mu ResolveAI. Mun apananku kipari sahayya kariparibi?",
  "or-IN": "Nomoshkar! Mu ResolveAI. Mun apananku kipari sahayya kariparibi?",
  "as-IN": "Nomoskar! Moi ResolveAI. Moi aponak kenekoi roxai koribo paru?",
  "ur-IN": "Aadaab! Main ResolveAI hoon. Main aapki kya madad kar sakta hoon?",
  "en-US": "Hello! I am ResolveAI. How can I help you today?",
  "tanglish": "Vanakkam! Naan ResolveAI. Ungalukku enna help venum?",
  "tamil": "வணக்கம்! நான் ResolveAI. உங்களுக்கு என்ன உதவி வேண்டும்?",
  "hindi": "नमस्ते! मैं ResolveAI हूँ। मैं आपकी क्या मदद कर सकता हूँ?",
  "hinglish": "Namaste! Main ResolveAI hoon. Main aapki kya help kar sakta hoon?",
  "english": "Hello! I am ResolveAI. How can I help you today?",
  "kannada": "ನಮಸ್ಕಾರ! ನಾನು ResolveAI. ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಬಹುದು?",
  "kanglish": "Namaskara! Naanu ResolveAI. Nimage hege help madli?",
  "telugu": "నమస్కారం! నేను ResolveAI. మీకు ఎలా సహాయపడగలను?",
  "tenglish": "Namaskaram! Nenu ResolveAI. Meeku ela help cheyagalanu?",
  "malayalam": "നമസ്കാരം! ഞാൻ ResolveAI. ഞാൻ എങ്ങനെ സഹായിക്കണം?",
  "manglish": "Namaskaram! Njan ResolveAI. Ningalkku engane help venam?",
  "bengali": "নমস্কার! আমি ResolveAI। আমি আপনাকে কীভাবে সাহায্য করতে পারি?",
  "benglish": "Nomoshkar! Aami ResolveAI. Apanake kibhabe help korte pari?",
  "marathi": "नमस्कार! मी ResolveAI आहे. मी तुम्हाला कशी मदत करू शकतो?",
  "marathish": "Namaskar! Me ResolveAI ahe. Me tumhala kashi help karu shakto?",
  "gujarati": "નમસ્તે! હું ResolveAI છું. હું તમારી કેવી રીતે મદદ કરી શકું?",
  "gujlish": "Namaste! Hu ResolveAI chhu. Hu tamari kevi rite help kari shaku?",
  "punjabi": "ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ! ਮੈਂ ResolveAI ਹਾਂ। ਮੈਂ ਤੁਹਾਡੀ ਕੀ ਮਦਦ ਕਰ ਸਕਦਾ ਹਾਂ?",
  "punglish": "Sat Sri Akal! Main ResolveAI haan. Main tuhadi ki help kar sakda haan?",
  "odia": "ନମସ୍କାର! ମୁଁ ResolveAI। ମୁଁ ଆପଣଙ୍କୁ କିପରି ସାହାଯ୍ୟ କରିପାରିବି?",
  "assamese": "নমস্কাৰ! মই ResolveAI। মই আপোনাক কেনেকৈ সহায় কৰিব পাৰোঁ?",
  "urdu": "آداب! میں ResolveAI ہوں۔ میں آپ کی کیا مدد کر سکتا ہوں؟",
};

export function resolveBcp47(bcp47Code?: string, languageName?: string): string {
  if (bcp47Code && bcp47Code.trim()) {
    const code = bcp47Code.trim();
    if (code.toLowerCase() === "or-in" || code.toLowerCase() === "od-in") return "od-IN";
    return code;
  }
  if (!languageName) return "en-IN";
  const l = languageName.toLowerCase().trim();
  if (l.includes("tanglish") || l.includes("tamil") || l === "ta" || l === "ta-in") return "ta-IN";
  if (l.includes("hinglish") || l.includes("hindi") || l === "hi" || l === "hi-in") return "hi-IN";
  if (l.includes("kanglish") || l.includes("kannada") || l === "kn" || l === "kn-in") return "kn-IN";
  if (l.includes("tenglish") || l.includes("telugu") || l === "te" || l === "te-in") return "te-IN";
  if (l.includes("manglish") || l.includes("malayalam") || l === "ml" || l === "ml-in") return "ml-IN";
  if (l.includes("benglish") || l.includes("bengali") || l.includes("bangla") || l === "bn" || l === "bn-in") return "bn-IN";
  if (l.includes("marathish") || l.includes("marathi") || l === "mr" || l === "mr-in") return "mr-IN";
  if (l.includes("gujlish") || l.includes("gujarati") || l === "gu" || l === "gu-in") return "gu-IN";
  if (l.includes("punglish") || l.includes("punjabi") || l === "pa" || l === "pa-in") return "pa-IN";
  if (l.includes("odia") || l.includes("oriya") || l === "or" || l === "or-in" || l === "od" || l === "od-in") return "od-IN";
  if (l.includes("assamese") || l === "as" || l === "as-in") return "as-IN";
  if (l.includes("urdu") || l === "ur" || l === "ur-in") return "ur-IN";
  return "en-IN";
}

export function getGreetingForLanguage(lang: string): string {
  const normalized = (lang || "en-IN").toLowerCase().trim();
  return GREETINGS_BY_LANGUAGE[normalized] || GREETINGS_BY_LANGUAGE["en-IN"];
}

/** Tokenize and normalize text for acoustic echo comparison */
export function normalizeForEcho(text: string): string {
  if (!text) return "";
  return text
    .toLowerCase()
    .replace(/[^\w\s\u0900-\u0D7F\u0600-\u06FF]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Checks whether heardText is an acoustic echo of the agent's recent text.
 * Distinguishes genuine speaker echo fragments from valid concise user responses.
 */
export function isEchoOfAgentText(heardText: string, agentText: string): boolean {
  const normHeard = normalizeForEcho(heardText);
  const normAgent = normalizeForEcho(agentText);

  if (!normHeard || !normAgent) return false;

  // Exact match: definitely echo
  if (normAgent === normHeard) return true;

  // Microphone captured the full agent sentence with slight extra noise
  if (normHeard.includes(normAgent)) return true;

  const heardTokens = normHeard.split(" ").filter((t) => t.length > 0);
  const agentTokensList = normAgent.split(" ").filter((t) => t.length > 0);
  const agentTokens = new Set(agentTokensList);

  if (heardTokens.length === 0) return false;

  // Substring match: only for multi-word phrases (>= 3 words)
  // Prevents single/two-word user answers (e.g. "refund", "cancel order", "yes", "status")
  // from being falsely dropped as echo of a long agent sentence.
  if (normAgent.includes(normHeard)) {
    if (heardTokens.length >= 3) {
      return true;
    }
    // For 1-2 words, only consider echo if the agent utterance was also very short (<= 3 words)
    if (agentTokensList.length <= 3) {
      return true;
    }
    return false;
  }

  // Token overlap check: only apply to multi-word phrases (>= 3 tokens)
  if (heardTokens.length >= 3) {
    let matchCount = 0;
    for (const token of heardTokens) {
      if (agentTokens.has(token)) {
        matchCount++;
      }
    }
    const overlapRatio = matchCount / heardTokens.length;
    if (overlapRatio >= 0.5) {
      return true;
    }
  }

  return false;
}

export interface RecognitionEvaluation {
  allowTurn: boolean;
  isEcho: boolean;
  isBargeIn: boolean;
  agentAudioWasPlaying: boolean;
  echoFilterDropped: boolean;
  dropReason?: string;
}

export class VoiceTurnCoordinator {
  private isAgentSpeaking: boolean = false;
  private agentAudioTailUntil: number = 0;
  private lastSpokenAgentText: string = "";
  private bargeInCandidateStart: number | null = null;
  private tailDurationMs: number = 300;
  private sustainedBargeInThresholdMs: number = 400;

  constructor(options?: { tailDurationMs?: number; sustainedBargeInThresholdMs?: number }) {
    if (options?.tailDurationMs !== undefined) this.tailDurationMs = options.tailDurationMs;
    if (options?.sustainedBargeInThresholdMs !== undefined) {
      this.sustainedBargeInThresholdMs = options.sustainedBargeInThresholdMs;
    }
  }

  public setLastSpokenAgentText(text: string) {
    this.lastSpokenAgentText = text;
  }

  public getLastSpokenAgentText(): string {
    return this.lastSpokenAgentText;
  }

  public onAgentAudioStart(text: string) {
    this.isAgentSpeaking = true;
    this.lastSpokenAgentText = text;
    this.agentAudioTailUntil = Date.now() + this.tailDurationMs;
    this.bargeInCandidateStart = null;
  }

  public onAgentAudioChunkEnd() {
    this.agentAudioTailUntil = Date.now() + this.tailDurationMs;
  }

  public onAgentAudioAllFinished() {
    this.isAgentSpeaking = false;
    this.agentAudioTailUntil = Date.now() + this.tailDurationMs;
    this.bargeInCandidateStart = null;
  }

  public isAgentAudioActive(): boolean {
    return this.isAgentSpeaking || Date.now() < this.agentAudioTailUntil;
  }

  public getTailRemainingMs(): number {
    return Math.max(0, this.agentAudioTailUntil - Date.now());
  }

  /**
   * Evaluates incoming speech recognition results against active audio and recent agent text.
   */
  public evaluateRecognitionResult(transcript: string, now: number = Date.now()): RecognitionEvaluation {
    const clean = transcript.trim();
    const agentActive = this.isAgentSpeaking || now < this.agentAudioTailUntil;

    if (!clean) {
      return {
        allowTurn: false,
        isEcho: false,
        isBargeIn: false,
        agentAudioWasPlaying: agentActive,
        echoFilterDropped: true,
        dropReason: "empty_transcript",
      };
    }

    const isEcho = isEchoOfAgentText(clean, this.lastSpokenAgentText);

    if (agentActive) {
      if (isEcho) {
        this.bargeInCandidateStart = null;
        return {
          allowTurn: false,
          isEcho: true,
          isBargeIn: false,
          agentAudioWasPlaying: true,
          echoFilterDropped: true,
          dropReason: "echo_of_agent_audio",
        };
      }

      // Not an echo, but agent audio or reverberation tail is active
      if (this.bargeInCandidateStart === null) {
        this.bargeInCandidateStart = now;
      }

      const effectiveBargeInThreshold =
        typeof window !== "undefined" && (window as any).__BARGE_IN_MS !== undefined
          ? (window as any).__BARGE_IN_MS
          : this.sustainedBargeInThresholdMs;

      const sustainedMs = now - this.bargeInCandidateStart;
      if (sustainedMs >= effectiveBargeInThreshold) {
        // Sustained human speech detected while agent was speaking -> REAL BARGE-IN!
        this.isAgentSpeaking = false;
        this.agentAudioTailUntil = 0;
        this.bargeInCandidateStart = null;
        return {
          allowTurn: true,
          isEcho: false,
          isBargeIn: true,
          agentAudioWasPlaying: true,
          echoFilterDropped: false,
        };
      } else {
        // Speech not yet sustained for >= 400 ms: hold without interrupting
        return {
          allowTurn: false,
          isEcho: false,
          isBargeIn: false,
          agentAudioWasPlaying: true,
          echoFilterDropped: true,
          dropReason: `held_for_sustained_barge_in_${sustainedMs}ms_lt_${effectiveBargeInThreshold}ms`,
        };
      }
    }

    // Agent audio is inactive (past the 300 ms reverberation tail)
    this.bargeInCandidateStart = null;
    return {
      allowTurn: true,
      isEcho: false,
      isBargeIn: false,
      agentAudioWasPlaying: false,
      echoFilterDropped: false,
    };
  }

  /**
   * Determines if a customer turn should be dispatched when silence timer fires.
   */
  public canDispatchTurn(transcript: string, now: number = Date.now()): { canDispatch: boolean; reason?: string } {
    if (this.isAgentSpeaking) {
      return { canDispatch: false, reason: "agent_is_currently_speaking" };
    }
    const effectiveTail =
      typeof window !== "undefined" && (window as any).__TAIL_MS !== undefined
        ? (window as any).__TAIL_MS
        : this.tailDurationMs;

    if (effectiveTail > 0 && now < this.agentAudioTailUntil) {
      return { canDispatch: false, reason: `within_300ms_acoustic_tail (${this.agentAudioTailUntil - now}ms remaining)` };
    }

    if (this.dispatchedTurns.length > 0) {
      const lastTurn = this.dispatchedTurns[this.dispatchedTurns.length - 1];
      if (lastTurn.toLowerCase() === transcript.trim().toLowerCase()) {
        return { canDispatch: false, reason: "duplicate_turn" };
      }
    }

    return { canDispatch: true };
  }

  // Alias helper for start
  public onAgentAudioStarted(text: string) {
    this.onAgentAudioStart(text);
  }

  private dispatchedTurns: string[] = [];
  public onTurnDispatched(text: string) {
    this.dispatchedTurns.push(text);
  }

  public getDispatchedTurnCount(): number {
    return this.dispatchedTurns.length;
  }
}

/**
 * Strips previously dispatched turn prefixes from speech recognition transcripts.
 * When the browser's SpeechRecognition instance is continuous, event.results may retain
 * previous phrases. This helper strips those dispatched phrases from the start of the transcript.
 */
export function stripDispatchedPrefix(text: string, dispatched: string): string {
  if (!text || !dispatched) return text;
  const cleanDispatched = dispatched.trim().toLowerCase().replace(/[.,!?;:]+$/, "").trim();
  const cleanText = text.trim();
  const lowerText = cleanText.toLowerCase();

  if (cleanDispatched.length > 0 && lowerText.startsWith(cleanDispatched)) {
    let remainder = cleanText.slice(cleanDispatched.length).trim();
    remainder = remainder.replace(/^[.,!?;:\s]+/, "").trim();
    return remainder;
  }
  return cleanText;
}

/**
 * Iteratively strips all previously dispatched turn prefixes in historical order.
 */
export function stripAllDispatchedPrefixes(text: string, dispatchedList: string[]): string {
  if (!text || !dispatchedList || dispatchedList.length === 0) return text;
  let result = text;
  for (const dispatched of dispatchedList) {
    result = stripDispatchedPrefix(result, dispatched);
  }
  return result;
}

