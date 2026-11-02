/**
 * ResolveAIV2 — Voice Diagnostics Logger
 *
 * In development mode, records structured diagnostic events for both
 * Chat Mode Voice Dictation and Call with Agent.
 *
 * Captures frame counts, sample rates, RMS/peak levels, payload sizes,
 * upload times, STT times, AI/TTS latencies, state transitions, and
 * failure classifications without logging sensitive customer speech.
 */

export type VoiceFeature = "chat_dictation" | "call_agent";

export type VoiceFailureCategory =
  | "mic_never_started"
  | "no_frames_received"
  | "audio_silent"
  | "payload_invalid"
  | "upload_never_started"
  | "upload_failed"
  | "backend_rejected"
  | "stt_failed_or_timeout"
  | "stt_empty_transcript"
  | "transcript_succeeded_ai_failed"
  | "ai_succeeded_tts_failed"
  | "listening_turn_not_resumed";

export interface VoiceDiagnosticEvent {
  timestamp: string;
  feature: VoiceFeature;
  sessionId: string;
  utteranceId: string;
  state: string;
  transitionReason?: string;
  micTrackState?: string;
  audioContextState?: string;
  frameCount?: number;
  sampleRate?: number;
  channelCount?: number;
  audioDurationSeconds?: number;
  rms?: number;
  peak?: number;
  payloadBytes?: number;
  uploadDurationMs?: number;
  httpStatus?: number;
  sttProvider?: string;
  sttDurationMs?: number;
  sttStatus?: "success" | "empty" | "error" | "timeout" | "fallback";
  transcriptCharCount?: number;
  aiDurationMs?: number;
  ttsDurationMs?: number;
  errorReason?: string;
  failureCategory?: VoiceFailureCategory;
}

// In-memory ring buffer for recent diagnostic events (up to 100 entries)
const recentDiagnostics: VoiceDiagnosticEvent[] = [];
const MAX_DIAGNOSTICS = 100;

export function logVoiceDiagnostic(event: Omit<VoiceDiagnosticEvent, "timestamp">): VoiceDiagnosticEvent {
  const fullEvent: VoiceDiagnosticEvent = {
    ...event,
    timestamp: new Date().toISOString(),
  };

  recentDiagnostics.push(fullEvent);
  if (recentDiagnostics.length > MAX_DIAGNOSTICS) {
    recentDiagnostics.shift();
  }

  const isDev =
    typeof window !== "undefined" &&
    ((window as any).__VOICE_DEV_LOG !== false ||
      (typeof process !== "undefined" && process.env?.NODE_ENV !== "production"));

  if (isDev) {
    const featureStr = (fullEvent.feature || "voice").toUpperCase();
    const stateStr = fullEvent.state || "info";
    const prefix = `[VOICE_DIAGNOSTIC ${fullEvent.timestamp}] [${featureStr}] [${stateStr}]`;
    if (fullEvent.failureCategory || fullEvent.errorReason) {
      console.warn(`${prefix} ⚠️ FAILURE: ${fullEvent.failureCategory || "unknown"}`, fullEvent);
    } else {
      console.log(`${prefix}`, fullEvent);
    }
  }

  return fullEvent;
}

export function categorizeFailure(err: any): VoiceFailureCategory {
  if (!err) return "backend_rejected";
  const msg = (typeof err === "string" ? err : err.message || err.detail || "").toLowerCase();
  if (msg.includes("permission") || msg.includes("notallowed") || msg.includes("mic_never_started")) {
    return "mic_never_started";
  }
  if (msg.includes("silent") || msg.includes("audio_silent")) {
    return "audio_silent";
  }
  if (msg.includes("empty audio") || msg.includes("no frames") || msg.includes("no_frames_received")) {
    return "no_frames_received";
  }
  if (msg.includes("payload") || msg.includes("invalid") || msg.includes("wav")) {
    return "payload_invalid";
  }
  if (msg.includes("network") || msg.includes("failed to fetch") || msg.includes("econnrefused")) {
    return "upload_failed";
  }
  if (msg.includes("timeout") || msg.includes("stt_failed") || msg.includes("502") || msg.includes("504")) {
    return "stt_failed_or_timeout";
  }
  if (msg.includes("no speech") || msg.includes("empty transcript")) {
    return "stt_empty_transcript";
  }
  if (msg.includes("ai") || msg.includes("llm") || msg.includes("500") || msg.includes("pipeline")) {
    return "transcript_succeeded_ai_failed";
  }
  if (msg.includes("tts") || msg.includes("speech synthesis")) {
    return "ai_succeeded_tts_failed";
  }
  return "backend_rejected";
}

export function getRecentVoiceDiagnostics(): VoiceDiagnosticEvent[] {
  return [...recentDiagnostics];
}

export function clearVoiceDiagnostics(): void {
  recentDiagnostics.length = 0;
}

export interface STTDiagnosticLogEntry {
  timestamp: string;
  sessionId: string;
  feature: VoiceFeature;
  event:
    | "START_ATTEMPT"
    | "START_SUCCESS"
    | "START_EXCEPTION"
    | "ONSTART"
    | "ONRESULT"
    | "ONERROR"
    | "ONEND"
    | "RESTART_SCHEDULED"
    | "RESTART_TRIGGERED"
    | "RESTART_SKIPPED"
    | "RESTART_FAILED"
    | "USER_STOP";
  selectedLang?: string;
  resultIndex?: number;
  resultsLength?: number;
  resultChunk?: string;
  isFinal?: boolean;
  committedLength?: number;
  committedText?: string;
  interimText?: string;
  error?: string;
  micLive?: boolean;
  details?: Record<string, any>;
}

const recentSTTDiagnostics: STTDiagnosticLogEntry[] = [];
const MAX_STT_DIAGNOSTICS = 200;

export function logSTTDiagnostic(entry: Omit<STTDiagnosticLogEntry, "timestamp">): STTDiagnosticLogEntry {
  const fullEntry: STTDiagnosticLogEntry = {
    ...entry,
    timestamp: new Date().toISOString(),
  };

  recentSTTDiagnostics.push(fullEntry);
  if (recentSTTDiagnostics.length > MAX_STT_DIAGNOSTICS) {
    recentSTTDiagnostics.shift();
  }

  if (typeof window !== "undefined") {
    (window as any).__STT_LOGS = recentSTTDiagnostics;
    (window as any).__LATEST_STT_EVENT = fullEntry;
  }

  const isDev =
    typeof window !== "undefined" &&
    ((window as any).__VOICE_DEV_LOG !== false ||
      (typeof process !== "undefined" && process.env?.NODE_ENV !== "production"));

  if (isDev) {
    const prefix = `[STT_DIAGNOSTIC ${fullEntry.timestamp}] [${fullEntry.feature.toUpperCase()}] [${fullEntry.event}]`;
    if (fullEntry.event === "ONERROR" || fullEntry.event === "START_EXCEPTION" || fullEntry.event === "RESTART_FAILED") {
      console.warn(prefix, fullEntry);
    } else {
      console.log(prefix, fullEntry);
    }
  }

  return fullEntry;
}

export function getRecentSTTDiagnostics(): STTDiagnosticLogEntry[] {
  return [...recentSTTDiagnostics];
}

export function clearSTTDiagnostics(): void {
  recentSTTDiagnostics.length = 0;
  if (typeof window !== "undefined") {
    (window as any).__STT_LOGS = [];
  }
}

export const voiceDiagnostics = {
  logEvent: (params: {
    event: string;
    state: string;
    conversationId?: string | number;
    utteranceId?: string;
    reason?: string;
    error?: string;
    details?: Record<string, any>;
    feature?: VoiceFeature;
  }) => {
    return logVoiceDiagnostic({
      feature: params.feature || "call_agent",
      sessionId: String(params.conversationId || "session"),
      utteranceId: params.utteranceId || `utt_${Date.now()}`,
      state: params.state,
      transitionReason: params.event,
      errorReason: params.error,
      failureCategory: params.reason ? (params.reason as VoiceFailureCategory) : undefined,
      ...params.details,
    });
  },
  categorizeFailure,
  getRecentEvents: getRecentVoiceDiagnostics,
  clearEvents: clearVoiceDiagnostics,
  logSTTEvent: logSTTDiagnostic,
  getRecentSTTEvents: getRecentSTTDiagnostics,
  clearSTTEvents: clearSTTDiagnostics,
};
