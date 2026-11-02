/**
 * ResolveAIV2 — Client Voice Activity Detection (VAD) & 16kHz Mono WAV Recorder
 *
 * Implements:
 * 1. Pre-roll buffer (~300ms ring buffer) ensuring onset consonants are preserved.
 * 2. Adaptive ambient noise floor with minimum speech threshold (>= 250ms sustained audio).
 * 3. End silence threshold (~700ms) triggering utterance completion.
 * 4. 16kHz mono WAV encoding for Sarvam Saaras STT API.
 * 5. Low-confidence (< 0.60) safety net with localized confirmation prompts.
 * 6. AudioCaptureSession managing getUserMedia lifecycle, suspended AudioContext resumption,
 *    mute gain nodes to prevent feedback, and reliable 10-step audio finalization.
 */

import {
  logVoiceDiagnostic,
  VoiceDiagnosticEvent,
  VoiceFailureCategory,
} from "./voiceDiagnostics";
import {
  validateCustomerUtterance,
  WHITELISTED_SHORT_UTTERANCES,
  UtteranceValidationResult,
} from "./noiseFilter";

export { logVoiceDiagnostic, validateCustomerUtterance, WHITELISTED_SHORT_UTTERANCES };
export type { VoiceDiagnosticEvent, VoiceFailureCategory, UtteranceValidationResult };

export interface VADConfig {
  sampleRate?: number;
  preRollMs?: number;
  minSpeechMs?: number;
  endSilenceMs?: number;
  speechEnergyThreshold?: number;
  snrFactor?: number;
  speechOnsetConfirmationFrames?: number;
  maxUtteranceMs?: number;
}

export interface STTResponse {
  transcript: string;
  language_code?: string;
  confidence?: number | null;
  provider?: string;
  fallback?: string;
  reason?: string;
  needsConfirmation?: boolean;
  confirmationPrompt?: string;
}

export interface AudioTurnResponse {
  status: string;
  transcript?: string;
  ai_response?: string;
  workflow_state?: string;
  stt_language_code?: string;
  stt_confidence?: number | null;
  stt_mode?: string;
  message?: string;
  latency_ms?: number;
  emotion?: string;
  fallback?: string;
}

export interface FinalizedAudio {
  wavBlob: Blob;
  sampleCount: number;
  durationSeconds: number;
  rms: number;
  peak: number;
  sampleRate: number;
  isSilent: boolean;
  utteranceId: string;
}

/**
 * Returns localized confirmation prompt when STT confidence is < 0.60
 * or transcript is ambiguous.
 */
export function getConfirmationPrompt(transcript: string, language: string): string {
  const lang = (language || "english").toLowerCase();
  const cleanTranscript = (transcript || "").trim();

  if (lang.includes("tanglish")) {
    return `Neenga "${cleanTranscript}" nu sonneengala?`;
  } else if (lang.includes("tamil") || lang === "ta" || lang === "ta-in") {
    return `நீங்கள் "${cleanTranscript}" என்று சொன்னீர்களா?`;
  } else if (lang.includes("hinglish")) {
    return `Aapne "${cleanTranscript}" bola kya?`;
  } else if (lang.includes("hindi") || lang === "hi" || lang === "hi-in") {
    return `क्या आपने "${cleanTranscript}" कहा?`;
  } else if (lang.includes("kanglish")) {
    return `Neevu "${cleanTranscript}" antha helidra?`;
  } else if (lang.includes("kannada") || lang === "kn" || lang === "kn-in") {
    return `ನೀವು "${cleanTranscript}" ಎಂದು ಹೇಳಿದ್ದೀರಾ?`;
  } else if (lang.includes("tenglish")) {
    return `Meeru "${cleanTranscript}" ani cheppara?`;
  } else if (lang.includes("telugu") || lang === "te" || lang === "te-in") {
    return `మీరు "${cleanTranscript}" అని చెప్పారా?`;
  } else if (lang.includes("manglish")) {
    return `Ningal "${cleanTranscript}" ennaano paranjath?`;
  } else if (lang.includes("malayalam") || lang === "ml" || lang === "ml-in") {
    return `നിങ്ങൾ "${cleanTranscript}" എന്നാണോ പറഞ്ഞത്?`;
  } else if (lang.includes("benglish")) {
    return `Apni ki "${cleanTranscript}" bolechen?`;
  } else if (lang.includes("bengali") || lang === "bn" || lang === "bn-in") {
    return `আপনি কি "${cleanTranscript}" বলেছেন?`;
  } else if (lang.includes("marathish")) {
    return `Tumhi "${cleanTranscript}" mhanalat ka?`;
  } else if (lang.includes("marathi") || lang === "mr" || lang === "mr-in") {
    return `तुम्ही "${cleanTranscript}" म्हणालात का?`;
  } else if (lang.includes("gujlish")) {
    return `Tame "${cleanTranscript}" kahyu?`;
  } else if (lang.includes("gujarati") || lang === "gu" || lang === "gu-in") {
    return `તમે "${cleanTranscript}" કહ્યું?`;
  } else if (lang.includes("punglish")) {
    return `Tusi "${cleanTranscript}" keha si?`;
  } else if (lang.includes("punjabi") || lang === "pa" || lang === "pa-in") {
    return `ਕੀ ਤੁਸੀਂ "${cleanTranscript}" ਕਿਹਾ ਸੀ?`;
  } else if (lang.includes("odia") || lang === "or" || lang === "or-in" || lang === "od" || lang === "od-in") {
    return `ଆପଣ "${cleanTranscript}" କହିଲେ କି?`;
  } else if (lang.includes("assamese") || lang === "as" || lang === "as-in") {
    return `আপুনি "${cleanTranscript}" ক'লে নেকি?`;
  } else if (lang.includes("urdu") || lang === "ur" || lang === "ur-in") {
    return `کیا آپ نے "${cleanTranscript}" کہا؟`;
  } else {
    return `Did you mean "${cleanTranscript}"?`;
  }
}

/**
 * Downsamples audio from any browser input sample rate (e.g. 44.1kHz, 48kHz)
 * to standard 16kHz mono PCM for Sarvam Saaras STT API.
 */
export function downsampleTo16k(samples: Float32Array, inputSampleRate: number = 44100): Float32Array {
  if (inputSampleRate === 16000) return samples;
  if (samples.length === 0) return new Float32Array(0);
  const ratio = inputSampleRate / 16000;
  const newLength = Math.round(samples.length / ratio);
  const result = new Float32Array(newLength);
  let offsetResult = 0;
  let offsetBuffer = 0;
  while (offsetResult < result.length) {
    const nextOffsetBuffer = Math.round((offsetResult + 1) * ratio);
    let accum = 0;
    let count = 0;
    for (let i = offsetBuffer; i < nextOffsetBuffer && i < samples.length; i++) {
      accum += samples[i];
      count++;
    }
    result[offsetResult] = count > 0 ? accum / count : 0;
    offsetResult++;
    offsetBuffer = nextOffsetBuffer;
  }
  return result;
}

/**
 * Encodes Float32 audio samples into a standard 16-bit PCM 16kHz mono WAV ArrayBuffer.
 */
export function encodeWAVBuffer(samples: Float32Array, sampleRate: number = 16000): ArrayBuffer {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);

  function writeString(view: DataView, offset: number, string: string) {
    for (let i = 0; i < string.length; i++) {
      view.setUint8(offset + i, string.charCodeAt(i));
    }
  }

  // RIFF header
  writeString(view, 0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeString(view, 8, "WAVE");

  // "fmt " sub-chunk
  writeString(view, 12, "fmt ");
  view.setUint32(16, 16, true); // Subchunk1Size (16 for PCM)
  view.setUint16(20, 1, true); // AudioFormat (1 = PCM)
  view.setUint16(22, 1, true); // NumChannels (1 = Mono)
  view.setUint32(24, sampleRate, true); // SampleRate
  view.setUint32(28, sampleRate * 2, true); // ByteRate (SampleRate * NumChannels * BitsPerSample/8)
  view.setUint16(32, 2, true); // BlockAlign (NumChannels * BitsPerSample/8)
  view.setUint16(34, 16, true); // BitsPerSample (16 bits)

  // "data" sub-chunk
  writeString(view, 36, "data");
  view.setUint32(40, samples.length * 2, true);

  // PCM samples write
  let offset = 44;
  for (let i = 0; i < samples.length; i++, offset += 2) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }

  return buffer;
}

/**
 * Encodes Float32 audio samples into a standard 16-bit PCM 16kHz mono WAV Blob.
 */
export function encodeWAV(samples: Float32Array, sampleRate: number = 16000): Blob {
  const buffer = encodeWAVBuffer(samples, sampleRate);
  return new Blob([buffer], { type: "audio/wav" });
}

/**
 * Calculate Zero Crossing Rate (ZCR) of an audio buffer.
 * Human voiced speech typically has moderate ZCR (0.02 - 0.45).
 * High-frequency static, hiss, and transient clicks have high ZCR (> 0.52).
 */
export function calculateZCR(samples: Float32Array): number {
  if (samples.length < 2) return 0;
  let crossings = 0;
  for (let i = 1; i < samples.length; i++) {
    if ((samples[i] >= 0 && samples[i - 1] < 0) || (samples[i] < 0 && samples[i - 1] >= 0)) {
      crossings++;
    }
  }
  return crossings / (samples.length - 1);
}

/**
 * Distinguish probable speech from non-speech impulses, high-frequency hiss, or static.
 */
export function isProbableSpeech(samples: Float32Array): boolean {
  if (samples.length === 0) return false;
  const zcr = calculateZCR(samples);
  // Sharp non-speech impulses, clicks, or static hiss have ZCR > 0.52
  return zcr <= 0.52;
}

/**
 * Calculate Root Mean Square (RMS) energy of an audio buffer.
 */
export function calculateRMS(samples: Float32Array): number {
  if (samples.length === 0) return 0;
  let sum = 0;
  for (let i = 0; i < samples.length; i++) {
    sum += samples[i] * samples[i];
  }
  return Math.sqrt(sum / samples.length);
}

/**
 * Calculate peak amplitude of an audio buffer.
 */
export function calculatePeak(samples: Float32Array): number {
  let peak = 0;
  for (let i = 0; i < samples.length; i++) {
    const abs = Math.abs(samples[i]);
    if (abs > peak) peak = abs;
  }
  return peak;
}

/**
 * Helper to obtain active auth headers
 */
function getAuthHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("access_token");
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
  }
  return headers;
}

/**
 * Client-side Voice Activity Detector (VAD) state machine.
 * Supports adaptive noise floor tracking, onset consonant preservation via pre-roll,
 * speech onset confirmation to ignore background noise / transient clicks,
 * and reliable utterance finalization.
 */
export class ClientVADState {
  private config: Required<VADConfig>;
  private isSpeaking: boolean = false;
  private speechDurationMs: number = 0;
  private silenceDurationMs: number = 0;
  private consecutiveSpeechFrames: number = 0;
  private onsetCandidateFrames: Float32Array[] = [];
  private preRollBuffer: Float32Array[] = [];
  private speechFrames: Float32Array[] = [];
  private maxPreRollChunks: number;
  private noiseFloor: number = 0.005;
  private peakRms: number = 0;

  constructor(config?: VADConfig) {
    this.config = {
      sampleRate: config?.sampleRate ?? 16000,
      preRollMs: config?.preRollMs ?? 300,
      minSpeechMs: config?.minSpeechMs ?? 250,
      endSilenceMs: config?.endSilenceMs ?? 700,
      speechEnergyThreshold: config?.speechEnergyThreshold ?? 0.015,
      snrFactor: config?.snrFactor ?? 2.2,
      speechOnsetConfirmationFrames: config?.speechOnsetConfirmationFrames ?? 2,
      maxUtteranceMs: config?.maxUtteranceMs ?? 25000,
    };
    // Assuming ~50ms frame chunks
    this.maxPreRollChunks = Math.max(1, Math.ceil(this.config.preRollMs / 50));
  }

  /**
   * Feed a new frame of audio samples.
   * Returns an encoded WAV Blob if utterance just completed, or null.
   */
  public processFrame(frame: Float32Array, frameDurationMs: number = 50): Blob | null {
    const rms = calculateRMS(frame);
    if (rms > this.peakRms) this.peakRms = rms;

    // Adaptive noise floor tracking during confirmed non-speech intervals
    if (!this.isSpeaking && this.consecutiveSpeechFrames === 0) {
      this.noiseFloor = this.noiseFloor * 0.95 + rms * 0.05;
    }

    // Dynamic threshold: scale above room noise floor by SNR factor, bounded by speechEnergyThreshold
    const dynamicThreshold = Math.max(
      this.config.speechEnergyThreshold,
      this.noiseFloor * this.config.snrFactor
    );

    const isVoicedCandidate = isProbableSpeech(frame);
    const isAboveThreshold = rms >= dynamicThreshold && isVoicedCandidate;

    if (isAboveThreshold) {
      if (!this.isSpeaking) {
        this.consecutiveSpeechFrames++;
        this.onsetCandidateFrames.push(new Float32Array(frame));

        // Require sustained speech onset confirmation (e.g. >= 2 frames / ~100ms)
        // to filter out single-frame clicks, fan hums, or brief background noise
        if (this.consecutiveSpeechFrames >= this.config.speechOnsetConfirmationFrames) {
          this.isSpeaking = true;
          this.speechDurationMs = this.consecutiveSpeechFrames * frameDurationMs;
          this.silenceDurationMs = 0;
          this.speechFrames = [...this.preRollBuffer, ...this.onsetCandidateFrames];
          this.onsetCandidateFrames = [];
        }
      } else {
        this.speechDurationMs += frameDurationMs;
        this.silenceDurationMs = 0;
        this.speechFrames.push(new Float32Array(frame));

        // 30-second REST limit safety guard: truncate and emit when reaching maxUtteranceMs
        if (this.speechDurationMs >= this.config.maxUtteranceMs) {
          const framesToEncode = [...this.speechFrames];
          this.resetState();
          return this.concatAndEncode(framesToEncode);
        }
      }
    } else {
      if (this.isSpeaking) {
        this.silenceDurationMs += frameDurationMs;
        this.speechFrames.push(new Float32Array(frame));

        // Check if silence exceeded end silence threshold
        if (this.silenceDurationMs >= this.config.endSilenceMs) {
          const totalSpeechMs = this.speechDurationMs;
          const framesToEncode = [...this.speechFrames];

          this.resetState();

          // Only return utterance if speech lasted at least minSpeechMs
          if (totalSpeechMs >= this.config.minSpeechMs) {
            return this.concatAndEncode(framesToEncode);
          }
        }
      } else {
        // Discard candidate onset frames if speech was not sustained
        if (this.consecutiveSpeechFrames > 0) {
          this.consecutiveSpeechFrames = 0;
          this.onsetCandidateFrames = [];
        }

        // Update pre-roll ring buffer
        this.preRollBuffer.push(new Float32Array(frame));
        if (this.preRollBuffer.length > this.maxPreRollChunks) {
          this.preRollBuffer.shift();
        }
      }
    }

    return null;
  }

  /**
   * Manually flush and finalize any captured speech frames immediately (e.g. on manual Stop).
   */
  public forceFinalize(): Blob | null {
    if (this.speechFrames.length === 0 && this.onsetCandidateFrames.length === 0) {
      this.resetState();
      return null;
    }
    const framesToEncode = this.speechFrames.length > 0
      ? [...this.speechFrames]
      : [...this.preRollBuffer, ...this.onsetCandidateFrames];
    this.resetState();
    return this.concatAndEncode(framesToEncode);
  }

  public getPeakRMS(): number {
    return this.peakRms;
  }

  public isCurrentlySpeaking(): boolean {
    return this.isSpeaking;
  }

  public reset(): void {
    this.resetState();
    this.preRollBuffer = [];
    this.noiseFloor = 0.005;
    this.peakRms = 0;
  }

  private resetState(): void {
    this.isSpeaking = false;
    this.speechDurationMs = 0;
    this.silenceDurationMs = 0;
    this.consecutiveSpeechFrames = 0;
    this.onsetCandidateFrames = [];
    this.speechFrames = [];
  }

  private concatAndEncode(chunks: Float32Array[]): Blob {
    let totalLength = 0;
    for (const c of chunks) {
      totalLength += c.length;
    }
    const merged = new Float32Array(totalLength);
    let offset = 0;
    for (const c of chunks) {
      merged.set(c, offset);
      offset += c.length;
    }
    return encodeWAV(merged, this.config.sampleRate);
  }
}

/**
 * Options for starting an AudioCaptureSession.
 */
export interface AudioCaptureOptions {
  onFrame?: (samples: Float32Array, rms: number, peak: number, durationMs: number) => void;
  onTrackEnded?: () => void;
  onTrackMuted?: () => void;
  onTrackUnmuted?: () => void;
  speechEnergyThreshold?: number;
}

/**
 * Shared, robust AudioCaptureSession.
 * Manages:
 * - getUserMedia request with echo cancellation, noise suppression, AGC
 * - AudioContext creation and guaranteed resumption (awaiting suspended state)
 * - Safe routing through a mute GainNode (gain=0) to prevent speaker feedback
 * - Persistent references to prevent V8 garbage collection
 * - Comprehensive 10-step finalization process
 */
export class AudioCaptureSession {
  private stream: MediaStream | null = null;
  private audioCtx: AudioContext | null = null;
  private sourceNode: MediaStreamAudioSourceNode | null = null;
  private processorNode: ScriptProcessorNode | null = null;
  private muteGainNode: GainNode | null = null;
  private chunks: Float32Array[] = [];
  private isCapturing: boolean = false;
  private isFinalizing: boolean = false;
  private finalizePromise: Promise<FinalizedAudio | null> | null = null;
  private sampleRate: number = 44100;
  private totalSamples: number = 0;
  private utteranceId: string = "";

  public getIsCapturing(): boolean {
    return this.isCapturing;
  }

  public async start(utteranceId: string, options?: AudioCaptureOptions): Promise<void> {
    if (this.isCapturing) return;

    this.utteranceId = utteranceId;
    this.chunks = [];
    this.totalSamples = 0;
    this.isFinalizing = false;
    this.finalizePromise = null;

    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      throw new Error("navigator.mediaDevices.getUserMedia is not supported in this environment");
    }

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
    } catch {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
    }
    this.stream = stream;

    // Track state listeners
    const audioTrack = typeof stream.getAudioTracks === "function"
      ? stream.getAudioTracks()[0]
      : (typeof stream.getTracks === "function" ? stream.getTracks()[0] : null);

    const trackSettings = audioTrack?.getSettings ? audioTrack.getSettings() : undefined;
    logVoiceDiagnostic({
      feature: "chat_dictation",
      sessionId: utteranceId || "session",
      utteranceId: utteranceId || "mic",
      state: "listening",
      transitionReason: "mic_started",
      sampleRate: trackSettings?.sampleRate || this.sampleRate,
      channelCount: trackSettings?.channelCount || 1,
    });

    if (audioTrack) {
      audioTrack.onended = () => {
        options?.onTrackEnded?.();
      };
      audioTrack.onmute = () => {
        options?.onTrackMuted?.();
      };
      audioTrack.onunmute = () => {
        options?.onTrackUnmuted?.();
      };
    }

    const AudioCtxClass = window.AudioContext || (window as any).webkitAudioContext;
    if (!AudioCtxClass) {
      throw new Error("Web Audio API is not supported in this browser");
    }

    const audioCtx = new AudioCtxClass();
    this.audioCtx = audioCtx;
    this.sampleRate = audioCtx.sampleRate || 44100;

    // CRITICAL FIX: Ensure suspended AudioContext is resumed immediately!
    if (audioCtx.state === "suspended" && typeof audioCtx.resume === "function") {
      try {
        await audioCtx.resume();
      } catch (resumeErr) {
        console.warn("AudioContext resume warning:", resumeErr);
      }
    }

    const source = audioCtx.createMediaStreamSource(stream);
    this.sourceNode = source;

    // 2048 buffer size gives ~46ms chunks at 44.1kHz
    const processor = audioCtx.createScriptProcessor(2048, 1, 1);
    this.processorNode = processor;

    processor.onaudioprocess = (e) => {
      if (!this.isCapturing || this.isFinalizing) return;
      const channel = e.inputBuffer.getChannelData(0);
      const copy = new Float32Array(channel);
      this.chunks.push(copy);
      this.totalSamples += copy.length;

      const rms = calculateRMS(copy);
      const peak = calculatePeak(copy);
      const durationMs = Math.round((copy.length / this.sampleRate) * 1000);
      options?.onFrame?.(copy, rms, peak, durationMs);
    };

    if (typeof source.connect === "function") {
      source.connect(processor);
    }

    // Mute gain node prevents microphone howling through laptop speakers
    if (typeof audioCtx.createGain === "function") {
      const muteGain = audioCtx.createGain();
      if (muteGain && muteGain.gain) {
        muteGain.gain.value = 0;
      }
      this.muteGainNode = muteGain;
      if (typeof processor.connect === "function" && muteGain) {
        processor.connect(muteGain);
      }
      if (muteGain && typeof muteGain.connect === "function" && audioCtx.destination) {
        muteGain.connect(audioCtx.destination);
      }
    } else if (audioCtx.destination && typeof processor.connect === "function") {
      processor.connect(audioCtx.destination);
    }

    this.isCapturing = true;
  }

  /**
   * Idempotent 10-step audio finalization process:
   * 1. Stop accepting new frames.
   * 2. Wait for pending audio callbacks.
   * 3. Collect all valid frames.
   * 4. Downsample to 16kHz mono.
   * 5. Encode to WAV.
   * 6. Validate sample count, duration, payload size, silence.
   * 7. Clean up audio nodes and media tracks.
   */
  public stop(): Promise<FinalizedAudio | null> {
    if (this.finalizePromise) {
      return this.finalizePromise;
    }

    this.finalizePromise = this.executeFinalize();
    return this.finalizePromise;
  }

  private async executeFinalize(): Promise<FinalizedAudio | null> {
    // 1. Stop accepting new incoming frames
    this.isFinalizing = true;
    this.isCapturing = false;

    // 2. Allow queued in-flight audio callback to finish (50ms micro-wait)
    await new Promise((resolve) => setTimeout(resolve, 50));

    // 3. Disconnect audio graph and stop tracks
    if (this.processorNode) {
      try { this.processorNode.disconnect(); } catch {}
      this.processorNode.onaudioprocess = null;
      this.processorNode = null;
    }
    if (this.sourceNode) {
      try { this.sourceNode.disconnect(); } catch {}
      this.sourceNode = null;
    }
    if (this.muteGainNode) {
      try { this.muteGainNode.disconnect(); } catch {}
      this.muteGainNode = null;
    }
    if (this.audioCtx && this.audioCtx.state !== "closed") {
      try { await this.audioCtx.close(); } catch {}
      this.audioCtx = null;
    }
    if (this.stream) {
      try {
        this.stream.getTracks().forEach((t) => t.stop());
      } catch {}
      this.stream = null;
    }

    // 4. Collect every valid captured frame
    const collectedChunks = [...this.chunks];
    this.chunks = [];

    if (collectedChunks.length === 0) {
      return null;
    }

    let totalLength = 0;
    for (const c of collectedChunks) totalLength += c.length;
    const merged = new Float32Array(totalLength);
    let offset = 0;
    for (const c of collectedChunks) {
      merged.set(c, offset);
      offset += c.length;
    }

    // 5. Downsample to standard 16kHz mono
    const samples16k = downsampleTo16k(merged, this.sampleRate);
    if (samples16k.length < 400) {
      // Less than 25ms of audio
      return null;
    }

    const rms = calculateRMS(samples16k);
    const peak = calculatePeak(samples16k);
    const durationSeconds = samples16k.length / 16000;
    const isSilent = rms < 0.001 && peak < 0.004;

    // 6. Encode complete audio buffer to 16-bit PCM 16kHz mono WAV
    const wavBlob = encodeWAV(samples16k, 16000);

    return {
      wavBlob,
      sampleCount: samples16k.length,
      durationSeconds,
      rms,
      peak,
      sampleRate: 16000,
      isSilent,
      utteranceId: this.utteranceId,
    };
  }

  public abort(): void {
    this.isCapturing = false;
    this.isFinalizing = false;
    this.chunks = [];
    if (this.processorNode) {
      try { this.processorNode.disconnect(); } catch {}
      this.processorNode.onaudioprocess = null;
      this.processorNode = null;
    }
    if (this.sourceNode) {
      try { this.sourceNode.disconnect(); } catch {}
      this.sourceNode = null;
    }
    if (this.muteGainNode) {
      try { this.muteGainNode.disconnect(); } catch {}
      this.muteGainNode = null;
    }
    if (this.audioCtx && this.audioCtx.state !== "closed") {
      try { this.audioCtx.close().catch(() => {}); } catch {}
      this.audioCtx = null;
    }
    if (this.stream) {
      try {
        this.stream.getTracks().forEach((t) => t.stop());
      } catch {}
      this.stream = null;
    }
  }

  public isActive(): boolean {
    return this.isCapturing;
  }
}

/**
 * Transcribe an audio utterance using Server STT (POST /api/audio/stt),
 * checking confidence and attaching localized confirmation when < 0.60.
 * Automatically attaches Authorization header from active session.
 */
export async function transcribeUtterance(
  wavBlob: Blob,
  language: string = "unknown",
  mode: string = "translit",
  signal?: AbortSignal
): Promise<STTResponse> {
  const formData = new FormData();
  formData.append("file", wavBlob, "utterance.wav");
  formData.append("language_code", language);
  formData.append("mode", mode);

  const headers = getAuthHeaders();

  try {
    const res = await fetch("/api/audio/stt", {
      method: "POST",
      headers,
      body: formData,
      signal,
    });

    if (!res.ok) {
      return {
        transcript: "",
        fallback: "browser",
        reason: `Server returned HTTP ${res.status}`,
      };
    }

    const data: STTResponse = await res.json();
    if (data.fallback) {
      return data;
    }

    // Safety net: check confidence
    const conf = data.confidence;
    if (conf !== null && conf !== undefined && conf < 0.60 && data.transcript) {
      data.needsConfirmation = true;
      data.confirmationPrompt = getConfirmationPrompt(data.transcript, language);
    }

    return data;
  } catch (err: any) {
    return {
      transcript: "",
      fallback: "browser",
      reason: err?.message || "STT network request failed",
    };
  }
}

/**
 * Submits an audio utterance directly to POST /api/audio/livekit/audio-turn,
 * running server-side Saaras v4 transcription and intelligence pipeline execution.
 * Automatically attaches Authorization header from active session.
 */
export async function submitAudioTurn(
  wavBlob: Blob,
  conversationId: number,
  utteranceId: string,
  language: string = "unknown",
  mode: string = "translit",
  signal?: AbortSignal
): Promise<AudioTurnResponse> {
  const formData = new FormData();
  formData.append("file", wavBlob, "utterance.wav");
  formData.append("conversation_id", String(conversationId));
  formData.append("utterance_id", utteranceId);
  formData.append("language_code", language);
  formData.append("mode", mode);

  const headers = getAuthHeaders();

  const res = await fetch("/api/audio/livekit/audio-turn", {
    method: "POST",
    headers,
    body: formData,
    signal,
  });

  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`Audio turn failed (HTTP ${res.status}): ${errorText}`);
  }

  return await res.json();
}
