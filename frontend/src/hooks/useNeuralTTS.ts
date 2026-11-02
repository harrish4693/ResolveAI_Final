/**
 * ResolveAIV2 — Neural TTS Audio Queue Hook (Fast-Path)
 *
 * Splits agent replies into sentences, requests /api/audio/tts for each,
 * plays them in order with overlap (sentence N+1 fetches while N plays).
 * Falls back to browser speechSynthesis if the server returns {fallback: "browser"}.
 *
 * Provides barge-in via stop() — clears the queue and halts the audio element.
 */

import { useRef, useCallback, useState } from "react";
import { api } from "@/lib/api";

interface UseNeuralTTSOptions {
  /** Conversation ID for the TTS API call */
  conversationId: string | null;
  /** Current call language (BCP-47: en-IN, ta-IN, hi-IN) */
  language: string;
  /** Detected customer emotion for pace adaptation */
  emotion?: string;
  /** Callback when the first audio chunk starts playing (for latency measurement) */
  onFirstAudioPlay?: (latencyMs: number) => void;
  /** Callback when all sentences have finished playing */
  onFinished?: () => void;
  /** Callback when speaking starts */
  onSpeakingStart?: (text: string) => void;
  /** Fallback: call browser speechSynthesis for this text */
  browserFallback: (text: string, emotion?: string) => void;
}

/** 
 * Split text into spoken sentences.
 * Rules (Milestone P2.5):
 * - Split ONLY at sentence-ending punctuation: . ! ? and the Hindi danda । (\u0964).
 * - NEVER split at commas (,), semicolons (;), or hyphens (-).
 * - Short sentences (<= ~120 characters) go to TTS as one request, keeping them joined.
 */
function splitIntoSentences(text: string): string[] {
  if (!text || !text.trim()) return [];

  // Split only on sentence-ending punctuation (. ! ? । …) followed by whitespace or end of string
  const rawChunks = text.match(/[^.!?।…]+[.!?।…]+[\s]?|[^.!?।…]+$/g) || [text];
  const sentences: string[] = [];
  let buffer = "";

  for (const chunk of rawChunks) {
    const trimmed = chunk.trim();
    if (!trimmed) continue;

    if (!buffer) {
      buffer = trimmed;
    } else {
      // If adding this chunk keeps the combined buffer <= 120 chars, group as one request!
      if ((buffer + " " + trimmed).length <= 120) {
        buffer = `${buffer} ${trimmed}`;
      } else {
        sentences.push(buffer);
        buffer = trimmed;
      }
    }
  }

  if (buffer.trim()) {
    // If leftover buffer is short (< 40 chars) and we already have sentences, merge if total <= 200 chars
    if (sentences.length > 0 && buffer.length < 40 && (sentences[sentences.length - 1] + " " + buffer).length <= 200) {
      sentences[sentences.length - 1] += " " + buffer.trim();
    } else {
      sentences.push(buffer.trim());
    }
  }

  return sentences.filter((s) => s.length > 0);
}

export function useNeuralTTS(options: UseNeuralTTSOptions) {
  const {
    conversationId,
    language,
    emotion,
    onFirstAudioPlay,
    onFinished,
    onSpeakingStart,
    browserFallback,
  } = options;

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const queueRef = useRef<string[]>([]);
  const abortRef = useRef<AbortController | null>(null);
  const isPlayingRef = useRef(false);
  const replyReceivedAtRef = useRef<number>(0);
  const firstChunkPlayedRef = useRef(false);
  const chunkIndexRef = useRef<number>(0);
  const lastChunkEndTimeRef = useRef<number>(0);
  const prefetchPromiseRef = useRef<{
    sentence: string;
    promise: Promise<Blob | null>;
    abort: AbortController;
  } | null>(null);

  const [ttsLatencyMs, setTtsLatencyMs] = useState<number | null>(null);
  const [ttsProvider, setTtsProvider] = useState<string>("pending");

  const isDevLogging = typeof window !== "undefined" && ((window as any).__VOICE_DEV_LOG !== false);

  /** Fetch audio for a single sentence from the backend TTS endpoint */
  const fetchSentenceAudio = useCallback(
    async (sentence: string, signal: AbortSignal): Promise<Blob | null> => {
      if (!conversationId) return null;

      try {
        const reqStart = Date.now();
        if (isDevLogging) {
          console.log(`[VOICE_DEV ${new Date().toISOString()}] [TTS_REQUEST_START]`, {
            sentence: sentence.slice(0, 50),
            conversationId,
          });
        }

        const res = await api.post(
          "/audio/tts",
          {
            conversation_id: parseInt(conversationId),
            text: sentence.slice(0, 400),
            emotion: emotion || "calm",
            language: language || "en-IN",
          },
          {
            responseType: "blob",
            signal,
            timeout: 8000,
          }
        );

        if (isDevLogging) {
          console.log(`[VOICE_DEV ${new Date().toISOString()}] [TTS_FIRST_BYTE]`, {
            latencyMs: Date.now() - reqStart,
            size: res.data instanceof Blob ? res.data.size : 0,
          });
        }

        // Validate response is actually a Blob (not a mock/JSON response)
        const data = res.data;
        if (!(data instanceof Blob)) {
          try {
            const parsed = typeof data === "object" ? data : JSON.parse(String(data));
            if (parsed?.fallback === "browser") {
              setTtsProvider("browser");
            }
          } catch {}
          return null;
        }

        // Check if it's a JSON fallback response (content-type: application/json)
        const contentType = res.headers?.["content-type"] || "";
        if (contentType.includes("application/json")) {
          try {
            const text = await data.text();
            const json = JSON.parse(text);
            if (json.fallback === "browser") {
              setTtsProvider("browser");
              return null;
            }
          } catch {}
          return null;
        }

        // Ensure blob has content
        if (data.size === 0) return null;

        setTtsProvider(res.headers?.["x-tts-provider"] || "sarvam");
        return data;
      } catch {
        return null;
      }
    },
    [conversationId, emotion, language, isDevLogging]
  );

  /** Play the next sentence in the queue with concurrent prefetch */
  const playNext = useCallback(async () => {
    if (queueRef.current.length === 0) {
      isPlayingRef.current = false;
      onFinished?.();
      return;
    }

    const sentence = queueRef.current.shift()!;
    const currentChunkIdx = chunkIndexRef.current++;
    let blob: Blob | null = null;

    // Use prefetched audio if available for this sentence
    if (prefetchPromiseRef.current && prefetchPromiseRef.current.sentence === sentence) {
      const prefetched = prefetchPromiseRef.current;
      prefetchPromiseRef.current = null;
      abortRef.current = prefetched.abort;
      blob = await prefetched.promise;
    } else {
      const controller = new AbortController();
      abortRef.current = controller;
      blob = await fetchSentenceAudio(sentence, controller.signal);
    }

    if (!isPlayingRef.current || abortRef.current?.signal.aborted) {
      return;
    }

    if (!blob) {
      if (!isPlayingRef.current || abortRef.current?.signal.aborted) return;
      // Fallback to browser TTS for the entire remaining text
      const remaining = [sentence, ...queueRef.current].join(" ");
      queueRef.current = [];
      isPlayingRef.current = false;
      browserFallback(remaining, emotion);
      return;
    }

    // Immediately prefetch sentence N+1 while sentence N plays (eliminates audio gap!)
    if (queueRef.current.length > 0) {
      const nextSentence = queueRef.current[0];
      const nextCtrl = new AbortController();
      prefetchPromiseRef.current = {
        sentence: nextSentence,
        promise: fetchSentenceAudio(nextSentence, nextCtrl.signal),
        abort: nextCtrl,
      };
    }

    // Create or reuse audio element
    if (!audioRef.current) {
      audioRef.current = new Audio();
    }
    audioRef.current.playbackRate = 1.0;
    audioRef.current.defaultPlaybackRate = 1.0;
    if ("preservesPitch" in audioRef.current) {
      audioRef.current.preservesPitch = true;
    }

    let url: string;
    try {
      url = URL.createObjectURL(blob);
    } catch {
      const remaining = [sentence, ...queueRef.current].join(" ");
      queueRef.current = [];
      isPlayingRef.current = false;
      browserFallback(remaining, emotion);
      return;
    }
    audioRef.current.src = url;
    let chunkStartTime = Date.now();

    audioRef.current.onplay = () => {
      chunkStartTime = Date.now();
      const gapFromPreviousChunkMs = lastChunkEndTimeRef.current > 0
        ? Math.max(0, chunkStartTime - lastChunkEndTimeRef.current)
        : 0;

      if (isDevLogging) {
        console.log(`[VOICE_DEV ${new Date().toISOString()}] [AUDIO_CHUNK_START]`, {
          chunkIndex: currentChunkIdx,
          sentence: sentence.slice(0, 50),
          gapFromPreviousChunkMs,
          latencyFromReplyMs: Date.now() - replyReceivedAtRef.current,
        });
      }

      if (!firstChunkPlayedRef.current) {
        firstChunkPlayedRef.current = true;
        const latency = Date.now() - replyReceivedAtRef.current;
        setTtsLatencyMs(latency);
        onFirstAudioPlay?.(latency);
      }
    };

    audioRef.current.onended = () => {
      const chunkDurationMs = Date.now() - chunkStartTime;
      lastChunkEndTimeRef.current = Date.now();

      if (isDevLogging) {
        console.log(`[VOICE_DEV ${new Date().toISOString()}] [AUDIO_CHUNK_END]`, {
          chunkIndex: currentChunkIdx,
          durationMs: chunkDurationMs,
        });
      }

      URL.revokeObjectURL(url);
      playNext();
    };

    audioRef.current.onerror = () => {
      URL.revokeObjectURL(url);
      const remaining = [...queueRef.current].join(" ");
      queueRef.current = [];
      isPlayingRef.current = false;
      if (remaining) {
        browserFallback(remaining, emotion);
      } else {
        onFinished?.();
      }
    };

    try {
      await audioRef.current.play();
    } catch {
      URL.revokeObjectURL(url);
      const remaining = [sentence, ...queueRef.current].join(" ");
      queueRef.current = [];
      isPlayingRef.current = false;
      browserFallback(remaining, emotion);
    }
  }, [fetchSentenceAudio, browserFallback, emotion, onFirstAudioPlay, onFinished, isDevLogging]);

  /** Speak the full agent reply using the neural TTS queue */
  const speak = useCallback(
    (text: string) => {
      replyReceivedAtRef.current = Date.now();
      firstChunkPlayedRef.current = false;
      chunkIndexRef.current = 0;
      lastChunkEndTimeRef.current = 0;
      if (prefetchPromiseRef.current) {
        prefetchPromiseRef.current.abort.abort();
        prefetchPromiseRef.current = null;
      }
      setTtsLatencyMs(null);
      setTtsProvider("pending");

      onSpeakingStart?.(text);

      const sentences = splitIntoSentences(text);

      if (sentences.length === 0) {
        onFinished?.();
        return;
      }

      queueRef.current = sentences;
      isPlayingRef.current = true;
      playNext();
    },
    [playNext, onSpeakingStart, onFinished]
  );

  /** Barge-in: immediately stop audio and clear the queue */
  const stop = useCallback(() => {
    if (prefetchPromiseRef.current) {
      prefetchPromiseRef.current.abort.abort();
      prefetchPromiseRef.current = null;
    }
    queueRef.current = [];
    chunkIndexRef.current = 0;
    lastChunkEndTimeRef.current = 0;
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
      audioRef.current.src = "";
    }
    isPlayingRef.current = false;
  }, []);

  const isSpeaking = isPlayingRef.current;

  return {
    speak,
    stop,
    isSpeaking,
    ttsLatencyMs,
    ttsProvider,
  };
}

export { splitIntoSentences };
