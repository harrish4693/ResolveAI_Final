import { useEffect, useState, useRef, useCallback } from "react";
import { useNeuralTTS } from "@/hooks/useNeuralTTS";
import { Link } from "@tanstack/react-router";
import {
  PhoneOff,
  Mic,
  MicOff,
  Volume2,
  VolumeX,
  Loader2,
  AlertCircle,
  Headphones,
  Sparkles,
  Bot,
  User,
  Maximize2,
  Radio,
  Globe,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useWebSocket } from "@/lib/ws";
import { selectNaturalVoice, cleanTextForSpeech, VOICE_LANGUAGES } from "./VoiceCallPage";
import {
  VoiceTurnCoordinator,
  isEchoOfAgentText,
  getGreetingForLanguage,
  resolveBcp47,
  stripAllDispatchedPrefixes,
} from "@/lib/voiceEchoFilter";
import {
  ClientVADState,
  calculateRMS,
  downsampleTo16k,
  submitAudioTurn,
  validateCustomerUtterance,
} from "@/lib/clientVAD";
import {
  voiceDiagnostics,
  logSTTDiagnostic,
  logVoiceDiagnostic,
} from "@/lib/voiceDiagnostics";

export type CallState =
  | "idle"
  | "requesting_permission"
  | "connecting"
  | "connected"
  | "listening"
  | "finalizing"
  | "transcribing"
  | "thinking"
  | "speaking"
  | "reconnecting"
  | "error";

interface CallWithAgentProps {
  conversationId: string;
  onEndCall: () => void;
  customerName?: string;
  isExpert?: boolean;
  initialLanguage?: string;
  preferredLanguage?: string;
}

export function CallWithAgent({
  conversationId,
  onEndCall,
  customerName,
  isExpert = false,
  initialLanguage,
  preferredLanguage,
}: CallWithAgentProps) {
  // Call lifecycle states: connecting -> listening -> finalizing -> transcribing -> thinking -> speaking -> listening | error
  const [callState, setCallState] = useState<CallState>("connecting");
  const [errorMessage, setErrorMessage] = useState("");
  const [isMuted, setIsMuted] = useState(false);
  const [isAgentSpeaking, setIsAgentSpeaking] = useState(false);
  const [isProcessingTurn, setIsProcessingTurn] = useState(false);
  const [currentTranscript, setCurrentTranscript] = useState("");
  const [lastAgentReply, setLastAgentReply] = useState("");
  const [callDuration, setCallDuration] = useState(0);

  const resolveInitialLang = (lang?: string, pref?: string) => {
    return resolveBcp47(undefined, pref || lang);
  };

  const [callLanguage, setCallLanguage] = useState<string>(() =>
    resolveInitialLang(initialLanguage, preferredLanguage)
  );
  const callLanguageRef = useRef<string>(callLanguage);
  callLanguageRef.current = callLanguage;
  const startBrowserRecognitionRef = useRef<(lang: string) => void>(() => {});

  const { subscribe, sendTranscriptUpdate } = useWebSocket();
  const handleEndCallRef = useRef<() => void>(() => {});

  // Stable refs to prevent React hook recreation and room teardown loops
  const isCallActiveRef = useRef<boolean>(false);
  const isAgentSpeakingRef = useRef<boolean>(false);
  const isProcessingTurnRef = useRef<boolean>(false);
  const isMutedRef = useRef<boolean>(false);
  const restartTimerRef = useRef<any>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const lastSpokenAgentTextRef = useRef<string>("");
  const lastProcessedTranscriptRef = useRef<string>("");
  const lastProcessedTurnRef = useRef<{ text: string; timestamp: number }>({ text: "", timestamp: 0 });
  const activeTurnIdRef = useRef<string>("");

  // Real microphone audio capture and Client VAD refs
  const audioContextRef = useRef<AudioContext | null>(null);
  const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const processorNodeRef = useRef<ScriptProcessorNode | null>(null);
  const gainNodeRef = useRef<GainNode | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const vadStateRef = useRef<ClientVADState | null>(null);
  const bargeInFramesRef = useRef<number>(0);
  const processCustomerAudioTurnRef = useRef<(wavBlob: Blob) => Promise<void>>(async () => {});

  const roomRef = useRef<any>(null);
  const audioElRef = useRef<HTMLAudioElement | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const silenceTimerRef = useRef<any>(null);
  const accumulatedTranscriptRef = useRef<string>("");
  const currentSessionTranscriptRef = useRef<string>("");
  const currentSessionFinalsRef = useRef<string>("");
  const currentSessionInterimRef = useRef<string>("");
  const dispatchedTurnsHistoryRef = useRef<string[]>([]);
  const [remoteSpeakerTranscript, setRemoteSpeakerTranscript] = useState<string>("");
  const recognitionRef = useRef<any>(null);
  const processCustomerTurnRef = useRef<(text: string) => Promise<void>>(async () => {});
  const onEndCallRef = useRef(onEndCall);
  onEndCallRef.current = onEndCall;

  const isTest = typeof process !== "undefined" && process.env?.NODE_ENV === "test";
  const tailDuration = typeof window !== "undefined" && (window as any).__TAIL_MS !== undefined
    ? (window as any).__TAIL_MS
    : (isTest ? 0 : 300);
  const bargeInDuration = typeof window !== "undefined" && (window as any).__BARGE_IN_MS !== undefined
    ? (window as any).__BARGE_IN_MS
    : (isTest ? 0 : 400);

  const turnCoordinatorRef = useRef<VoiceTurnCoordinator>(
    new VoiceTurnCoordinator({ tailDurationMs: tailDuration, sustainedBargeInThresholdMs: bargeInDuration })
  );

  // Browser TTS fallback (original speechSynthesis path — unchanged)
  const speakWithBrowserTTS = useCallback((text: string, _emotion?: string) => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) {
      setCallState("listening");
      return;
    }

    try {
      window.speechSynthesis.cancel();
      const cleaned = cleanTextForSpeech(text);
      lastSpokenAgentTextRef.current = cleaned.toLowerCase().trim();
      const utterance = new SpeechSynthesisUtterance(cleaned);
      utterance.rate = 1.03;
      utterance.pitch = 1.0;

      // Select natural lifelike voice
      const voices = window.speechSynthesis.getVoices();
      const preferredVoice = selectNaturalVoice(voices, callLanguageRef.current, cleaned);
      if (preferredVoice) {
        utterance.voice = preferredVoice;
      }

      utterance.onstart = () => {
        turnCoordinatorRef.current.onAgentAudioStart(cleaned);
        isAgentSpeakingRef.current = true;
        setIsAgentSpeaking(true);
        setCallState("speaking");
        setLastAgentReply(text);
      };

      const finishSpeaking = () => {
        turnCoordinatorRef.current.onAgentAudioAllFinished();
        isAgentSpeakingRef.current = false;
        setIsAgentSpeaking(false);
        vadStateRef.current?.reset();
        bargeInFramesRef.current = 0;
        if (audioContextRef.current && audioContextRef.current.state === "suspended") {
          audioContextRef.current.resume().catch(() => {});
        }
        if (isCallActiveRef.current) {
          setCallState("listening");
          if (recognitionRef.current && !isMutedRef.current) {
            try {
              recognitionRef.current.start();
            } catch {}
          }
        }
      };

      utterance.onend = finishSpeaking;
      utterance.onerror = finishSpeaking;

      window.speechSynthesis.speak(utterance);
      if (process.env.NODE_ENV === "test") {
        setTimeout(() => {
          finishSpeaking();
        }, 10);
      }
    } catch {
      setCallState("listening");
    }
  }, []);

  // Neural TTS hook with browser fallback
  const browserFallbackRef = useRef<(text: string, emotion?: string) => void>(() => {});
  browserFallbackRef.current = speakWithBrowserTTS;

  const neuralTTS = useNeuralTTS({
    conversationId: conversationId,
    language: callLanguage,
    emotion: "calm",
    onSpeakingStart: (text) => {
      turnCoordinatorRef.current.onAgentAudioStart(text);
      isAgentSpeakingRef.current = true;
      setIsAgentSpeaking(true);
      setCallState("speaking");
      setLastAgentReply(text);
    },
    onFinished: () => {
      turnCoordinatorRef.current.onAgentAudioAllFinished();
      isAgentSpeakingRef.current = false;
      setIsAgentSpeaking(false);
      vadStateRef.current?.reset();
      bargeInFramesRef.current = 0;
      if (audioContextRef.current && audioContextRef.current.state === "suspended") {
        audioContextRef.current.resume().catch(() => {});
      }
      if (isCallActiveRef.current) {
        setCallState("listening");
        if (!isMutedRef.current) {
          startBrowserRecognitionRef.current(callLanguageRef.current);
        }
      }
    },
    browserFallback: (text, emotion) => {
      browserFallbackRef.current(text, emotion);
    },
  });

  const neuralTTSRef = useRef(neuralTTS);
  neuralTTSRef.current = neuralTTS;

  // Primary speak function: try neural TTS, auto-falls back to browser
  const speakAgentResponse = useCallback((text: string) => {
    lastSpokenAgentTextRef.current = cleanTextForSpeech(text).toLowerCase().trim();
    neuralTTSRef.current.speak(text);
  }, []);
  const speakAgentResponseRef = useRef(speakAgentResponse);
  speakAgentResponseRef.current = speakAgentResponse;

  // Dispatch customer spoken turn into ResolveAI intelligence pipeline
  const processCustomerTurn = useCallback(
    async (text: string) => {
      const clean = text.trim();
      if (!clean || isProcessingTurnRef.current || !isCallActiveRef.current) return;

      // Noise & hallucination filter: reject non-speech tags, isolated fillers, corpus artifacts
      const validation = validateCustomerUtterance(clean);
      if (!validation.isValid) {
        voiceDiagnostics.logEvent({
          event: "TURN_BLOCKED_BY_NOISE_FILTER",
          state: "listening",
          conversationId,
          reason: validation.reason,
          details: { text: clean },
        });
        return;
      }

      // Utterance deduplication: avoid processing the exact same turn twice within 2.5s
      const now = Date.now();
      if (
        clean.toLowerCase() === lastProcessedTurnRef.current.text.toLowerCase() &&
        now - lastProcessedTurnRef.current.timestamp < 2500
      ) {
        return;
      }

      // Turn coordinator echo guard: ensure agent is not speaking and user text is not echo
      const canDispatch = turnCoordinatorRef.current.canDispatchTurn(clean);
      if (!canDispatch.canDispatch) {
        voiceDiagnostics.logEvent({
          event: "TURN_BLOCKED_BY_ECHO_FILTER",
          state: "listening",
          conversationId,
          reason: canDispatch.reason,
          details: { text: clean },
        });
        return;
      }

      lastProcessedTurnRef.current = { text: clean, timestamp: now };
      lastProcessedTranscriptRef.current = clean;
      if (!dispatchedTurnsHistoryRef.current.includes(clean)) {
        dispatchedTurnsHistoryRef.current.push(clean);
      }
      isProcessingTurnRef.current = true;
      setIsProcessingTurn(true);
      setCallState("thinking");
      setCurrentTranscript(clean);

      // Setup abort controller for barge-in cancellation
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      const abortCtrl = new AbortController();
      abortControllerRef.current = abortCtrl;

      try {
        const turnStartMs = Date.now();
        voiceDiagnostics.logEvent({
          event: "UTTERANCE_SENT",
          state: "thinking",
          conversationId,
          details: {
            transcriptLength: clean.length,
            isExpert,
          },
        });

        if (isExpert) {
          // Expert speech: save as expert message in the conversation, do not trigger AI TTS
          await api.post(`/conversations/${conversationId}/messages`, {
            content: clean,
          });
          setCallState("listening");
        } else {
          const res = await api.post(
            "/audio/livekit/utterance",
            {
              conversation_id: parseInt(conversationId),
              utterance_id: `livekit_turn_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
              transcript: clean,
            },
            { signal: abortCtrl.signal }
          );

          if (abortCtrl.signal.aborted) return;

          voiceDiagnostics.logEvent({
            event: "AI_RESPONSE_RECEIVED",
            state: "thinking",
            conversationId,
            details: {
              roundtripMs: Date.now() - turnStartMs,
              serverLatencyMs: res.data?.latency_ms,
              hasAiResponse: Boolean(res.data?.ai_response),
            },
          });

          const reply = res.data?.ai_response;
          if (reply) {
            if (res.data?.bcp47_code || res.data?.language) {
              const newBcp47 = resolveBcp47(res.data.bcp47_code, res.data.language);
              if (newBcp47 && newBcp47 !== callLanguageRef.current) {
                setCallLanguage(newBcp47);
                callLanguageRef.current = newBcp47;
              }
            }
            speakAgentResponseRef.current(reply);
          } else {
            setCallState("listening");
          }
        }
      } catch (err: any) {
        if (err.name === "CanceledError" || err.name === "AbortError") {
          return;
        }
        const failureCategory = voiceDiagnostics.categorizeFailure(err);
        voiceDiagnostics.logEvent({
          event: "ERROR",
          state: "error",
          conversationId,
          error: err.message || String(err),
          reason: failureCategory,
        });
        console.error("Failed to process spoken turn", err);
        setCallState("listening");
      } finally {
        isProcessingTurnRef.current = false;
        setIsProcessingTurn(false);
        setCurrentTranscript("");
        accumulatedTranscriptRef.current = "";
        currentSessionFinalsRef.current = "";
        currentSessionInterimRef.current = "";
        currentSessionTranscriptRef.current = "";
      }
    },
    [conversationId, isExpert]
  );
  processCustomerTurnRef.current = processCustomerTurn;

  // Process raw microphone audio turn via server-side Saaras v4 STT & intelligence pipeline
  const processCustomerAudioTurn = useCallback(
    async (wavBlob: Blob) => {
      if (!wavBlob || wavBlob.size === 0 || isProcessingTurnRef.current || !isCallActiveRef.current) return;

      const utteranceId = `livekit_audio_turn_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;
      isProcessingTurnRef.current = true;
      setIsProcessingTurn(true);
      setCallState("transcribing");

      // Reset speech recognition buffers so browser STT does not retain audio turn words
      accumulatedTranscriptRef.current = "";
      currentSessionFinalsRef.current = "";
      currentSessionInterimRef.current = "";
      currentSessionTranscriptRef.current = "";

      voiceDiagnostics.logEvent({
        event: "AUDIO_TURN_SUBMITTED",
        state: "transcribing",
        conversationId,
        utteranceId,
        details: {
          payloadBytes: wavBlob.size,
          mimeType: wavBlob.type,
          audioContextState: audioContextRef.current?.state,
        },
      });

      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      const abortCtrl = new AbortController();
      abortControllerRef.current = abortCtrl;

      try {
        const turnStartMs = Date.now();
        const audioLang = resolveBcp47(callLanguageRef.current);
        const res = await submitAudioTurn(
          wavBlob,
          parseInt(conversationId),
          utteranceId,
          audioLang,
          "translit", // translit mode for Tanglish/Hinglish normalization
          abortCtrl.signal
        );

        if (abortCtrl.signal.aborted) return;

        if (res.status === "ignored") {
          voiceDiagnostics.logEvent({
            event: "TURN_COMPLETED",
            state: "listening",
            conversationId,
            utteranceId,
            reason: res.message || "STT returned empty transcript or ignored",
          });
          setCallState("listening");
          return;
        }

        const recognizedText = (res.transcript || "").trim();
        const validation = validateCustomerUtterance(recognizedText, res.stt_confidence);
        if (!validation.isValid) {
          voiceDiagnostics.logEvent({
            event: "TURN_BLOCKED_BY_NOISE_FILTER",
            state: "listening",
            conversationId,
            utteranceId,
            reason: validation.reason,
            details: { text: recognizedText },
          });
          setCallState("listening");
          return;
        }

        if (recognizedText) {
          lastProcessedTurnRef.current = { text: recognizedText, timestamp: Date.now() };
          lastProcessedTranscriptRef.current = recognizedText;
          if (!dispatchedTurnsHistoryRef.current.includes(recognizedText)) {
            dispatchedTurnsHistoryRef.current.push(recognizedText);
          }
          setCurrentTranscript(recognizedText);
        }

        voiceDiagnostics.logEvent({
          event: "AI_RESPONSE_RECEIVED",
          state: "thinking",
          conversationId,
          utteranceId,
          details: {
            roundtripMs: Date.now() - turnStartMs,
            transcriptCharCount: recognizedText.length,
            aiResponseCharCount: (res.ai_response || "").length,
          },
        });

        const reply = res.ai_response;
        if (reply && !isExpert) {
          if (res.bcp47_code || res.language) {
            const newBcp47 = resolveBcp47(res.bcp47_code, res.language);
            if (newBcp47 && newBcp47 !== callLanguageRef.current) {
              setCallLanguage(newBcp47);
              callLanguageRef.current = newBcp47;
            }
          }
          speakAgentResponseRef.current(reply);
        } else {
          setCallState("listening");
        }
      } catch (err: any) {
        if (err.name === "CanceledError" || err.name === "AbortError") {
          return;
        }
        const failureCategory = voiceDiagnostics.categorizeFailure(err);
        voiceDiagnostics.logEvent({
          event: "ERROR",
          state: "error",
          conversationId,
          utteranceId,
          error: err.message || String(err),
          reason: failureCategory,
        });
        console.error("Failed to process audio turn in CallWithAgent:", err);
        setCallState("listening");
      } finally {
        isProcessingTurnRef.current = false;
        setIsProcessingTurn(false);
        setCurrentTranscript("");
        accumulatedTranscriptRef.current = "";
        currentSessionFinalsRef.current = "";
        currentSessionInterimRef.current = "";
        currentSessionTranscriptRef.current = "";
      }
    },
    [conversationId, isExpert]
  );
  processCustomerAudioTurnRef.current = processCustomerAudioTurn;

  // Browser Web Speech Recognition manager (ensures fresh instances across restarts)
  const startBrowserRecognition = useCallback((lang: string, retryAttempt: number = 0) => {
    if (typeof window === "undefined") return;
    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) return;

    logSTTDiagnostic({
      sessionId: conversationId || "call",
      feature: "call_agent",
      event: "START_ATTEMPT",
      selectedLang: lang,
      details: { retryAttempt },
    });

    if (recognitionRef.current) {
      try {
        recognitionRef.current.onstart = null;
        recognitionRef.current.onresult = null;
        recognitionRef.current.onerror = null;
        recognitionRef.current.onend = null;
        recognitionRef.current.abort();
      } catch {}
      recognitionRef.current = null;
    }

    try {
      const recognition = new SpeechRecognition();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = lang;

      recognition.onstart = () => {
        logSTTDiagnostic({
          sessionId: conversationId || "call",
          feature: "call_agent",
          event: "ONSTART",
          selectedLang: lang,
          micLive: true,
        });
      };

      recognition.onresult = (event: any) => {
        let sessionFinals = "";
        let sessionInterim = "";

        for (let i = 0; i < event.results.length; i++) {
          const item = event.results[i];
          const text = (item[0]?.transcript || "").trim();
          if (item.isFinal) {
            sessionFinals += (sessionFinals ? " " : "") + text;
          } else {
            sessionInterim += (sessionInterim ? " " : "") + text;
          }
        }

        // Strip any previously dispatched turns from continuous SpeechRecognition results
        sessionFinals = stripAllDispatchedPrefixes(sessionFinals, dispatchedTurnsHistoryRef.current);
        accumulatedTranscriptRef.current = stripAllDispatchedPrefixes(accumulatedTranscriptRef.current, dispatchedTurnsHistoryRef.current);

        currentSessionFinalsRef.current = sessionFinals;
        currentSessionInterimRef.current = sessionInterim;
        const currentSessionTotal = [sessionFinals, sessionInterim].filter(Boolean).join(" ").trim();
        currentSessionTranscriptRef.current = currentSessionTotal;

        const fullAccumulated = [
          accumulatedTranscriptRef.current,
          sessionFinals,
          sessionInterim,
        ].filter(Boolean).join(" ").trim();

        const latestItem = event.results[event.results.length - 1];
        const latestChunk = latestItem?.[0]?.transcript || "";
        const isFinal = latestItem?.isFinal ?? false;

        logSTTDiagnostic({
          sessionId: conversationId || "call",
          feature: "call_agent",
          event: "ONRESULT",
          selectedLang: lang,
          resultIndex: event.resultIndex,
          resultsLength: event.results?.length,
          resultChunk: latestChunk,
          isFinal: isFinal,
          committedLength: accumulatedTranscriptRef.current.length,
          committedText: fullAccumulated,
        });

        const evalRes = turnCoordinatorRef.current.evaluateRecognitionResult(fullAccumulated);

        if (typeof window !== "undefined" && (window as any).__VOICE_DEV_LOG !== false) {
          console.log(`[VOICE_DEV ${new Date().toISOString()}] [STT_RESULT]`, {
            isFinal,
            latestChunk,
            fullAccumulated,
            agent_audio_was_playing: evalRes.agentAudioWasPlaying,
            echo_filter_dropped: evalRes.echoFilterDropped,
            reason: evalRes.dropReason,
          });
        }

        // Sustained speech barge-in (>= 400ms non-matching speech)
        if (evalRes.isBargeIn) {
          if (typeof window !== "undefined" && (window as any).__VOICE_DEV_LOG !== false) {
            console.log(`[VOICE_DEV ${new Date().toISOString()}] [BARGE_IN_TRIGGERED]`, {
              detectedText: fullAccumulated,
            });
          }
          neuralTTSRef.current.stop();
          if (typeof window !== "undefined" && "speechSynthesis" in window) {
            window.speechSynthesis.cancel();
          }
          isAgentSpeakingRef.current = false;
          setIsAgentSpeaking(false);
          if (abortControllerRef.current) {
            abortControllerRef.current.abort();
          }
          setCallState("listening");
        }

        if (!activeTurnIdRef.current) {
          activeTurnIdRef.current = `turn_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`;
        }
        setCurrentTranscript(fullAccumulated);
        if (conversationId && sendTranscriptUpdate) {
          sendTranscriptUpdate(parseInt(conversationId), activeTurnIdRef.current, fullAccumulated, false);
        }

        // Silence timer: reset on every speech result
        if (silenceTimerRef.current) {
          clearTimeout(silenceTimerRef.current);
          silenceTimerRef.current = null;
        }

        const silenceDelay =
          typeof window !== "undefined" && (window as any).__SILENCE_TIMEOUT_MS !== undefined
            ? (window as any).__SILENCE_TIMEOUT_MS
            : (process.env.NODE_ENV === "test" ? 30 : 1800);

        if (fullAccumulated && !isProcessingTurnRef.current && isCallActiveRef.current) {
          silenceTimerRef.current = setTimeout(() => {
            if (!isProcessingTurnRef.current && isCallActiveRef.current) {
              const toSend = fullAccumulated.trim();
              if (!toSend) return;

              // Noise & hallucination filter check
              const validation = validateCustomerUtterance(toSend);
              if (!validation.isValid) {
                if (typeof window !== "undefined" && (window as any).__VOICE_DEV_LOG !== false) {
                  console.log(`[VOICE_DEV ${new Date().toISOString()}] [TURN_BLOCKED_BY_NOISE_FILTER]`, {
                    text: toSend,
                    reason: validation.reason,
                  });
                }
                accumulatedTranscriptRef.current = "";
                currentSessionFinalsRef.current = "";
                currentSessionInterimRef.current = "";
                currentSessionTranscriptRef.current = "";
                setCurrentTranscript("");
                activeTurnIdRef.current = "";
                return;
              }

              const canDispatch = turnCoordinatorRef.current.canDispatchTurn(toSend);
              if (!canDispatch.canDispatch) {
                if (typeof window !== "undefined" && (window as any).__VOICE_DEV_LOG !== false) {
                  console.log(`[VOICE_DEV ${new Date().toISOString()}] [TURN_BLOCKED_BY_ECHO_FILTER]`, {
                    text: toSend,
                    reason: canDispatch.reason,
                  });
                }
                accumulatedTranscriptRef.current = "";
                currentSessionFinalsRef.current = "";
                currentSessionInterimRef.current = "";
                currentSessionTranscriptRef.current = "";
                setCurrentTranscript("");
                activeTurnIdRef.current = "";
                return;
              }

              if (typeof window !== "undefined" && (window as any).__VOICE_DEV_LOG !== false) {
                console.log(`[VOICE_DEV ${new Date().toISOString()}] [SPEECH_END]`, {
                  text: toSend,
                  silenceMs: silenceDelay,
                });
                console.log(`[VOICE_DEV ${new Date().toISOString()}] [FINAL_TRANSCRIPT]`, {
                  transcript: toSend,
                  isFinal: true,
                });
              }

              // Broadcast final commit via WebSocket
              if (conversationId && sendTranscriptUpdate && activeTurnIdRef.current) {
                sendTranscriptUpdate(parseInt(conversationId), activeTurnIdRef.current, toSend, true);
              }
              activeTurnIdRef.current = "";

              if (!dispatchedTurnsHistoryRef.current.includes(toSend)) {
                dispatchedTurnsHistoryRef.current.push(toSend);
              }

              // Clear buffers
              accumulatedTranscriptRef.current = "";
              currentSessionFinalsRef.current = "";
              currentSessionInterimRef.current = "";
              currentSessionTranscriptRef.current = "";

              processCustomerTurnRef.current(toSend);
            }
          }, silenceDelay);
        }
      };

      recognition.onerror = (event: any) => {
        logSTTDiagnostic({
          sessionId: conversationId || "call",
          feature: "call_agent",
          event: "ONERROR",
          selectedLang: lang,
          error: event.error,
        });
        if (event.error !== "no-speech" && event.error !== "aborted") {
          console.warn("Speech recognition warning in call", event.error);
        }
        if (event.error === "network") {
          // Retry after network interruption
          if (isCallActiveRef.current && !isMutedRef.current) {
            setTimeout(() => {
              if (isCallActiveRef.current && !isMutedRef.current) {
                startBrowserRecognitionRef.current(callLanguageRef.current);
              }
            }, 500);
          }
        }
      };

      recognition.onend = () => {
        // If turn is currently being processed or AI is speaking, do not fold into accumulated buffer!
        if (isProcessingTurnRef.current) {
          currentSessionFinalsRef.current = "";
          currentSessionInterimRef.current = "";
          currentSessionTranscriptRef.current = "";
          return;
        }

        // Fold BOTH finalized text AND uncommitted interim into accumulated buffer across restarts!
        // In Chrome, Web Speech frequently ends the session during pauses before marking interim as isFinal.
        const sessionSpoken = [
          currentSessionFinalsRef.current,
          currentSessionInterimRef.current,
        ].filter(Boolean).join(" ").trim();

        if (sessionSpoken) {
          accumulatedTranscriptRef.current = [
            accumulatedTranscriptRef.current,
            sessionSpoken,
          ].filter(Boolean).join(" ").trim();
          currentSessionFinalsRef.current = "";
          currentSessionInterimRef.current = "";
        }
        currentSessionTranscriptRef.current = "";
        accumulatedTranscriptRef.current = stripAllDispatchedPrefixes(accumulatedTranscriptRef.current, dispatchedTurnsHistoryRef.current);

        logSTTDiagnostic({
          sessionId: conversationId || "call",
          feature: "call_agent",
          event: "ONEND",
          selectedLang: callLanguageRef.current,
          committedText: accumulatedTranscriptRef.current,
        });

        // Automatically restart recognition with a FRESH instance to keep the call continuous
        if (isCallActiveRef.current && !isMutedRef.current) {
          if (restartTimerRef.current) clearTimeout(restartTimerRef.current);
          logSTTDiagnostic({
            sessionId: conversationId || "call",
            feature: "call_agent",
            event: "RESTART_SCHEDULED",
            selectedLang: callLanguageRef.current,
          });
          restartTimerRef.current = setTimeout(() => {
            if (isCallActiveRef.current && !isMutedRef.current) {
              logSTTDiagnostic({
                sessionId: conversationId || "call",
                feature: "call_agent",
                event: "RESTART_TRIGGERED",
                selectedLang: callLanguageRef.current,
              });
              startBrowserRecognitionRef.current(callLanguageRef.current);
            }
          }, 220);
        }
      };

      try {
        recognition.start();
        recognitionRef.current = recognition;
        logSTTDiagnostic({
          sessionId: conversationId || "call",
          feature: "call_agent",
          event: "START_SUCCESS",
          selectedLang: lang,
        });
      } catch (err: any) {
        logSTTDiagnostic({
          sessionId: conversationId || "call",
          feature: "call_agent",
          event: "START_EXCEPTION",
          selectedLang: lang,
          error: err?.message || String(err),
        });
        console.warn("SpeechRecognition start failed:", err);
        if (isCallActiveRef.current && !isMutedRef.current && retryAttempt < 3) {
          const delay = 250 * Math.pow(2, retryAttempt);
          logSTTDiagnostic({
            sessionId: conversationId || "call",
            feature: "call_agent",
            event: "RESTART_SCHEDULED",
            selectedLang: lang,
            details: { retryAttempt: retryAttempt + 1, delay },
          });
          setTimeout(() => {
            if (isCallActiveRef.current && !isMutedRef.current) {
              startBrowserRecognitionRef.current(lang, retryAttempt + 1);
            }
          }, delay);
        }
      }
    } catch (err: any) {
      console.warn("SpeechRecognition start failed:", err);
    }
  }, [conversationId, sendTranscriptUpdate]);
  startBrowserRecognitionRef.current = startBrowserRecognition;

  const handleLanguageChange = (newLang: string) => {
    setCallLanguage(newLang);
    callLanguageRef.current = newLang;
    if (isCallActiveRef.current && !isMutedRef.current) {
      startBrowserRecognitionRef.current(newLang);
    }
  };

  // Single mount effect: connects LiveKit room and keeps continuous voice active
  useEffect(() => {
    let mounted = true;

    async function initLiveKitCall() {
      try {
        setCallState("connecting");
        setErrorMessage("");

        // 1. Fetch short-lived token from ResolveAI backend
        const res = await api.post("/audio/livekit/token", {
          conversation_id: parseInt(conversationId),
        });

        if (!mounted) return;

        const { server_url, token } = res.data;

        // 2. Initialize LiveKit Room dynamically
        const { Room, RoomEvent, Track } = await import("livekit-client");
        const room = new Room({
          adaptiveStream: true,
          dynacast: true,
          audioCaptureDefaults: {
            autoGainControl: true,
            echoCancellation: true,
            noiseSuppression: true,
          },
        });
        roomRef.current = room;

        // 3. Audio track subscriptions
        room.on(RoomEvent.TrackSubscribed, (track: any) => {
          if (track.kind === Track.Kind.Audio) {
            if (!audioElRef.current) {
              const el = document.createElement("audio");
              el.autoplay = true;
              audioElRef.current = el;
              document.body.appendChild(el);
            }
            track.attach(audioElRef.current);
          }
        });

        room.on(RoomEvent.TrackUnsubscribed, (track: any) => {
          track.detach();
        });

        room.on(RoomEvent.ActiveSpeakersChanged, (speakers: any[]) => {
          const remoteSpeaking = speakers.some((s) => !s.isLocal);
          if (remoteSpeaking) {
            setIsAgentSpeaking(true);
            setCallState("speaking");
          }
        });

        room.on(RoomEvent.Reconnecting, () => {
          if (mounted) setCallState("reconnecting");
        });

        room.on(RoomEvent.Reconnected, () => {
          if (mounted) setCallState("listening");
        });

        // Peer-to-peer data packet (instant peer termination)
        room.on(RoomEvent.DataReceived, (payload: Uint8Array) => {
          try {
            const data = JSON.parse(new TextDecoder().decode(payload));
            if (data?.type === "CALL_ENDED") {
              handleEndCallRef.current();
            }
          } catch {}
        });

        // Remote participant hung up or disconnected
        room.on(RoomEvent.ParticipantDisconnected, (participant: any) => {
          if (participant?.identity?.startsWith("expert-") || participant?.identity?.startsWith("admin-")) {
            handleEndCallRef.current();
          }
        });

        room.on(RoomEvent.Disconnected, () => {
          console.warn("LiveKit room disconnected");
        });

        // Check if conversation already has prior messages
        let hasPriorHistory = false;
        try {
          const histRes = await api.get(`/conversations/${conversationId}/messages`);
          hasPriorHistory = Array.isArray(histRes.data) && histRes.data.length > 0;
        } catch {
          hasPriorHistory = false;
        }

        // 4. Connect to WebRTC room (with graceful fallback to direct voice pipeline)
        let livekitConnected = false;
        try {
          await room.connect(server_url, token);
          livekitConnected = true;
        } catch (webrtcErr) {
          console.warn("LiveKit WebRTC connection failed, continuing in direct voice mode:", webrtcErr);
        }

        // 5. Enable Local Microphone safely
        if (livekitConnected && room.localParticipant) {
          try {
            await room.localParticipant.setMicrophoneEnabled(true);
            setIsMuted(false);
            isMutedRef.current = false;
          } catch (micErr) {
            console.warn("Microphone access failed or denied:", micErr);
            setIsMuted(true);
            isMutedRef.current = true;
          }
        } else {
          setIsMuted(false);
          isMutedRef.current = false;
        }

        if (mounted) {
          isCallActiveRef.current = true;
          setCallState("listening");
          setIsMuted(false);
          isMutedRef.current = false;

          timerRef.current = setInterval(() => {
            setCallDuration((prev) => prev + 1);
          }, 1000);

          // Initial greeting only when conversation has no prior history and caller is a customer
          if (!hasPriorHistory && !isExpert) {
            speakAgentResponseRef.current(getGreetingForLanguage(callLanguageRef.current));
          }

          // Real microphone audio capture and Client VAD setup
          if (typeof navigator !== "undefined" && navigator?.mediaDevices?.getUserMedia) {
            try {
              const stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                  echoCancellation: true,
                  noiseSuppression: true,
                  autoGainControl: true,
                },
              });
              micStreamRef.current = stream;

              const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
              if (AudioCtx) {
                const audioCtx = new AudioCtx();
                if (audioCtx.state === "suspended") {
                  try {
                    await audioCtx.resume();
                  } catch (resErr) {
                    console.warn("Could not resume AudioContext immediately:", resErr);
                  }
                }
                audioContextRef.current = audioCtx;
                const source = audioCtx.createMediaStreamSource(stream);
                sourceNodeRef.current = source;
                const processor = audioCtx.createScriptProcessor(2048, 1, 1);
                processorNodeRef.current = processor;

                // Create muted gain node to avoid routing microphone back to local speakers
                if (typeof audioCtx.createGain === "function") {
                  const gain = audioCtx.createGain();
                  gain.gain.value = 0;
                  gainNodeRef.current = gain;
                  try {
                    processor.connect(gain);
                    if (audioCtx.destination) {
                      gain.connect(audioCtx.destination);
                    }
                  } catch {}
                }

                vadStateRef.current = new ClientVADState({
                  sampleRate: 16000,
                  preRollMs: 300,
                  minSpeechMs: 250,
                  endSilenceMs: 700,
                  maxUtteranceMs: 25000,
                  speechEnergyThreshold: 0.015,
                  snrFactor: 2.2,
                  speechOnsetConfirmationFrames: 2,
                });

                voiceDiagnostics.logEvent({
                  event: "MIC_STARTED",
                  state: "listening",
                  conversationId,
                  details: {
                    sampleRate: audioCtx.sampleRate,
                    channels: stream.getAudioTracks().length,
                    trackLabel: stream.getAudioTracks()[0]?.label,
                  },
                });

                processor.onaudioprocess = (e) => {
                  if (!isCallActiveRef.current || isMutedRef.current) return;

                  const rawSamples = e.inputBuffer.getChannelData(0);
                  const rms = calculateRMS(rawSamples);

                  // Barge-in interruption detection while agent is speaking
                  if (isAgentSpeakingRef.current) {
                    if (rms >= 0.03) {
                      bargeInFramesRef.current += 1;
                      if (bargeInFramesRef.current >= 4) {
                        neuralTTSRef.current.stop();
                        if (typeof window !== "undefined" && "speechSynthesis" in window) {
                          window.speechSynthesis.cancel();
                        }
                        turnCoordinatorRef.current.onAgentAudioAllFinished();
                        isAgentSpeakingRef.current = false;
                        setIsAgentSpeaking(false);
                        bargeInFramesRef.current = 0;
                        vadStateRef.current?.reset();
                        if (abortControllerRef.current) {
                          abortControllerRef.current.abort();
                        }
                        setCallState("listening");
                        voiceDiagnostics.logEvent({
                          event: "BARGE_IN_TRIGGERED",
                          state: "listening",
                          conversationId,
                          details: { rms, frames: 4 },
                        });
                      }
                    } else {
                      bargeInFramesRef.current = 0;
                    }
                    return; // Echo filter: avoid recording agent speaker audio
                  }
                  bargeInFramesRef.current = 0;

                  const samples16k = downsampleTo16k(rawSamples, audioCtx.sampleRate);
                  const frameDurationMs = Math.round((samples16k.length / 16000) * 1000);
                  const wavBlob = vadStateRef.current?.processFrame(samples16k, frameDurationMs);
                  if (wavBlob && !isProcessingTurnRef.current && isCallActiveRef.current) {
                    setCallState("finalizing");
                    processCustomerAudioTurnRef.current(wavBlob);
                  }
                };

                source.connect(processor);
              }
            } catch (e) {
              console.warn("Microphone AudioContext setup in CallWithAgent fallback:", e);
            }
          }

          // 6. Start continuous natural spoken conversation loop (fallback / testing)
          startBrowserRecognitionRef.current(callLanguageRef.current);
        }
      } catch (err: any) {
        if (!mounted) return;
        console.error("LiveKit Call Connection Error", err);
        let detail = "Failed to establish live voice connection. Please check your connection or credentials.";
        if (err.name === "NotAllowedError" || err.message?.includes("Permission denied")) {
          detail = "Microphone access was denied. Please allow microphone permissions in your browser to speak.";
        } else if (err.response?.status === 401) {
          detail = "Your session has expired. Please sign in again to start a voice call.";
        } else if (!navigator.onLine || err.code === "ERR_NETWORK" || err.message?.includes("Network Error")) {
          detail = "Network connection lost. Please check your internet connection and try again.";
        } else if (err.response?.data?.detail) {
          detail = err.response.data.detail;
        } else if (err.message) {
          detail = err.message;
        }
        setErrorMessage(detail);
        setCallState("error");
      }
    }

    initLiveKitCall();

    return () => {
      mounted = false;
      isCallActiveRef.current = false;
      dispatchedTurnsHistoryRef.current = [];
      if (silenceTimerRef.current) {
        clearTimeout(silenceTimerRef.current);
        silenceTimerRef.current = null;
      }
      accumulatedTranscriptRef.current = "";
      currentSessionTranscriptRef.current = "";
      if (restartTimerRef.current) {
        clearTimeout(restartTimerRef.current);
        restartTimerRef.current = null;
      }
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
      neuralTTSRef.current.stop();
      if (typeof window !== "undefined" && "speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      if (recognitionRef.current) {
        try {
          recognitionRef.current.onstart = null;
          recognitionRef.current.onresult = null;
          recognitionRef.current.onerror = null;
          recognitionRef.current.onend = null;
          recognitionRef.current.abort();
        } catch {}
        recognitionRef.current = null;
      }
      if (roomRef.current) {
        try {
          roomRef.current.disconnect();
        } catch {}
        roomRef.current = null;
      }
      if (audioElRef.current) {
        try {
          audioElRef.current.remove();
        } catch {}
        audioElRef.current = null;
      }
      if (processorNodeRef.current) {
        try {
          processorNodeRef.current.disconnect();
        } catch {}
        processorNodeRef.current = null;
      }
      if (sourceNodeRef.current) {
        try {
          sourceNodeRef.current.disconnect();
        } catch {}
        sourceNodeRef.current = null;
      }
      if (gainNodeRef.current) {
        try {
          gainNodeRef.current.disconnect();
        } catch {}
        gainNodeRef.current = null;
      }
      if (audioContextRef.current) {
        try {
          audioContextRef.current.close();
        } catch {}
        audioContextRef.current = null;
      }
      if (micStreamRef.current) {
        try {
          micStreamRef.current.getTracks().forEach((t) => t.stop());
        } catch {}
        micStreamRef.current = null;
      }
    };
  }, [conversationId]);

  // Toggle Mute / Unmute
  const toggleMute = async () => {
    const nextMuted = !isMuted;
    try {
      if (roomRef.current?.localParticipant) {
        await roomRef.current.localParticipant.setMicrophoneEnabled(!nextMuted);
      }
      if (micStreamRef.current) {
        micStreamRef.current.getAudioTracks().forEach((t) => {
          t.enabled = !nextMuted;
        });
      }
      setIsMuted(nextMuted);
      isMutedRef.current = nextMuted;

      if (nextMuted) {
        vadStateRef.current?.reset();
      } else {
        if (audioContextRef.current && audioContextRef.current.state === "suspended") {
          await audioContextRef.current.resume().catch(() => {});
        }
      }

      if (recognitionRef.current) {
        if (nextMuted) {
          try {
            recognitionRef.current.abort();
          } catch {}
        } else {
          try {
            recognitionRef.current.start();
          } catch {}
        }
      }
    } catch (err) {
      console.error("Failed to toggle mute", err);
    }
  };

  // Explicit End Call
  const handleEndCall = () => {
    // 1. Notify peer immediately over WebRTC data channel
    if (roomRef.current?.localParticipant) {
      try {
        const payload = new TextEncoder().encode(
          JSON.stringify({ type: "CALL_ENDED", ended_by: isExpert ? "expert" : "customer" })
        );
        roomRef.current.localParticipant.publishData(payload, { reliable: true });
      } catch {}
    }

    // 2. Notify backend to broadcast VOICE_CALL_ENDED via WS and delete LiveKit room
    const cid = parseInt(conversationId);
    if (!isNaN(cid)) {
      api.post("/audio/livekit/end-call", { conversation_id: cid })?.catch?.(() => {});
    }

    isCallActiveRef.current = false;
    dispatchedTurnsHistoryRef.current = [];
    if (restartTimerRef.current) {
      clearTimeout(restartTimerRef.current);
      restartTimerRef.current = null;
    }
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    neuralTTSRef.current.stop();
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (recognitionRef.current) {
      try {
        recognitionRef.current.abort();
      } catch {}
      recognitionRef.current = null;
    }
    if (processorNodeRef.current) {
      try {
        processorNodeRef.current.disconnect();
      } catch {}
      processorNodeRef.current = null;
    }
    if (audioContextRef.current) {
      try {
        audioContextRef.current.close();
      } catch {}
      audioContextRef.current = null;
    }
    if (micStreamRef.current) {
      try {
        micStreamRef.current.getTracks().forEach((t) => t.stop());
      } catch {}
      micStreamRef.current = null;
    }
    if (roomRef.current) {
      try {
        roomRef.current.disconnect();
      } catch {}
      roomRef.current = null;
    }
    onEndCallRef.current();
  };
  handleEndCallRef.current = handleEndCall;

  // Listen for remote call termination & remote participant live transcripts via WebSocket
  useEffect(() => {
    const cid = parseInt(conversationId);
    if (isNaN(cid)) return;
    const unsubCallEnded = subscribe("VOICE_CALL_ENDED", (event: any) => {
      if (event?.conversation_id === cid) {
        handleEndCallRef.current();
      }
    });

    const unsubTranscriptStream = subscribe("TRANSCRIPT_STREAM", (event: any) => {
      if (event?.conversation_id !== cid) return;
      const data = event?.data;
      if (!data) return;
      const { text, is_final, sender_type } = data;
      const isRemote = isExpert ? sender_type !== "expert" : sender_type !== "customer";
      if (isRemote) {
        if (is_final) {
          setRemoteSpeakerTranscript("");
        } else {
          setRemoteSpeakerTranscript(text || "");
        }
      }
    });

    return () => {
      unsubCallEnded();
      unsubTranscriptStream();
    };
  }, [conversationId, isExpert, subscribe]);

  const formatDuration = (secs: number) => {
    const mins = Math.floor(secs / 60);
    const remainderSecs = secs % 60;
    return `${mins.toString().padStart(2, "0")}:${remainderSecs.toString().padStart(2, "0")}`;
  };

  const isConnected =
    callState === "connected" ||
    callState === "listening" ||
    callState === "finalizing" ||
    callState === "transcribing" ||
    callState === "thinking" ||
    callState === "speaking" ||
    callState === "reconnecting";

  return (
    <div
      role="region"
      aria-label="Active voice call with ResolveAI"
      className="p-6 rounded-2xl bg-gradient-to-b from-card to-muted border border-border shadow-md flex flex-col items-center justify-between text-center relative overflow-hidden my-4"
    >
      {/* Background ambient pulse */}
      <div
        className={`absolute -top-24 size-48 rounded-full blur-3xl opacity-20 pointer-events-none transition-all duration-700 ${
          callState === "speaking"
            ? "bg-primary scale-150"
            : callState === "thinking" || callState === "transcribing" || callState === "finalizing"
              ? "bg-amber-500 scale-125"
              : "bg-emerald-500 scale-100"
        }`}
      />

      {/* Header / Call Status */}
      <div className="space-y-1.5 z-10">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-background border border-border text-xs font-medium">
          <span
            className={`size-2 rounded-full ${
              callState === "error"
                ? "bg-destructive"
                : callState === "connecting"
                  ? "bg-amber-500 animate-ping"
                  : callState === "reconnecting"
                    ? "bg-amber-500 animate-pulse"
                    : callState === "thinking" || callState === "transcribing"
                      ? "bg-amber-500 animate-spin"
                      : callState === "finalizing"
                        ? "bg-amber-500 animate-pulse"
                        : callState === "speaking"
                          ? "bg-primary animate-pulse"
                          : isMuted
                            ? "bg-muted-foreground"
                            : "bg-emerald-500 animate-pulse"
            }`}
          />
          {callState === "connecting" && "Connecting to agent..."}
          {callState === "reconnecting" && "Reconnecting Audio..."}
          {callState === "error" && "Call Disconnected"}
          {isConnected &&
            (callState === "speaking"
              ? "ResolveAI Speaking…"
              : callState === "thinking"
                ? "ResolveAI Thinking…"
                : callState === "transcribing"
                  ? "Transcribing speech…"
                  : callState === "finalizing"
                    ? "Finalizing speech…"
                    : isMuted
                      ? "Microphone Muted"
                      : "Listening to you…")}
        </div>
        <div className="flex items-center justify-center gap-2 flex-wrap">
          <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-background border border-border text-[11px] font-medium shadow-2xs">
            <Globe className="size-3 text-primary shrink-0" />
            <select
              aria-label="Call recognition language"
              value={callLanguage}
              onChange={(e) => handleLanguageChange(e.target.value)}
              className="bg-transparent text-[11px] text-foreground cursor-pointer focus:outline-hidden"
              title="Spoken language recognition"
            >
              {VOICE_LANGUAGES.map((l) => (
                <option key={l.code} value={l.code} className="bg-popover text-popover-foreground">
                  {l.label}
                </option>
              ))}
            </select>
          </div>
          <p className="text-xs text-muted-foreground font-mono">
            {isConnected ? formatDuration(callDuration) : "Secure WebRTC Voice Channel"}
          </p>
        </div>
      </div>

      {/* Center Voice Avatar / Visualizer */}
      <div className="my-6 z-10 flex flex-col items-center gap-3">
        <div
          className={`relative size-24 rounded-full flex items-center justify-center transition-all duration-300 border-2 ${
            callState === "speaking"
              ? "bg-primary/20 border-primary shadow-lg shadow-primary/30 scale-110"
              : callState === "thinking"
                ? "bg-amber-500/10 border-amber-500/40 animate-pulse"
                : isMuted
                  ? "bg-muted border-border"
                  : "bg-card border-border shadow-sm scale-100"
          }`}
        >
          {callState === "thinking" ? (
            <Loader2 className="size-10 text-amber-500 animate-spin" />
          ) : isExpert ? (
            <Headphones
              className={`size-10 transition-colors ${
                callState === "speaking" ? "text-primary animate-bounce" : "text-primary"
              }`}
            />
          ) : (
            <Bot
              className={`size-10 transition-colors ${
                callState === "speaking" ? "text-primary animate-bounce" : "text-muted-foreground"
              }`}
            />
          )}
          {callState === "speaking" && (
            <span className="absolute -bottom-1 px-2 py-0.5 rounded-full bg-primary text-primary-foreground text-[10px] font-semibold tracking-wider uppercase">
              {isExpert ? "Customer Speaking" : "Speaking"}
            </span>
          )}
        </div>

        <div>
          <h3 className="font-semibold text-base text-foreground">
            {isExpert ? "Live Customer Voice Call" : "ResolveAI Voice Assistant"}
          </h3>
          <p className="text-xs text-muted-foreground">
            {isExpert
              ? "Real-time human-to-human audio connection · Live WebRTC"
              : "Bilingual Natural Spoken Support · Continuous Multi-Turn Dialogue"}
          </p>
        </div>

        {/* Live speech feedback previews */}
        {currentTranscript && (
          <div className="max-w-md px-3.5 py-2 rounded-xl bg-background/90 border border-border text-xs text-foreground flex items-center gap-2 shadow-xs animate-in fade-in">
            <span className="size-2 rounded-full bg-amber-500 animate-pulse shrink-0" />
            <User className="size-3.5 text-primary shrink-0" />
            <span className="font-semibold text-[11px] text-muted-foreground">You:</span>
            <span className="italic truncate font-medium">"{currentTranscript}"</span>
            <span className="text-[10px] text-amber-600 dark:text-amber-400 font-mono uppercase ml-auto shrink-0">
              Live
            </span>
          </div>
        )}

        {remoteSpeakerTranscript && (
          <div className="max-w-md px-3.5 py-2 rounded-xl bg-blue-500/10 border border-blue-500/20 text-xs text-blue-700 dark:text-blue-300 flex items-center gap-2 shadow-xs animate-in fade-in">
            <span className="size-2 rounded-full bg-blue-500 animate-pulse shrink-0" />
            <Headphones className="size-3.5 text-blue-600 shrink-0" />
            <span className="font-semibold text-[11px]">{isExpert ? "Customer:" : "Expert:"}</span>
            <span className="italic truncate font-medium">"{remoteSpeakerTranscript}"</span>
            <span className="text-[10px] text-blue-600 uppercase font-mono ml-auto shrink-0">Live</span>
          </div>
        )}

        {lastAgentReply && callState === "speaking" && (
          <div className="max-w-md px-3 py-1.5 rounded-lg bg-primary/10 border border-primary/20 text-xs text-primary flex items-center gap-1.5 animate-in fade-in">
            <Bot className="size-3 shrink-0" />
            <span className="truncate">"{lastAgentReply}"</span>
          </div>
        )}
      </div>

      {/* Error Alert Display */}
      {callState === "error" && (
        <div className="z-10 w-full max-w-md p-3 mb-4 rounded-xl bg-destructive/10 border border-destructive/20 text-destructive text-xs flex items-start gap-2 text-left">
          <AlertCircle className="size-4 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <span className="font-semibold">Unable to connect voice session:</span>
            <p className="text-[11px] leading-relaxed">{errorMessage}</p>
          </div>
        </div>
      )}

      {/* Call Actions */}
      <div className="flex items-center gap-4 z-10 mt-2">
        {isConnected && (
          <Button
            type="button"
            variant="outline"
            size="icon"
            onClick={toggleMute}
            className={`size-11 rounded-full border transition-all ${
              isMuted
                ? "bg-amber-500/10 border-amber-500/40 text-amber-600 hover:bg-amber-500/20"
                : "hover:bg-muted"
            }`}
            title={isMuted ? "Unmute microphone" : "Mute microphone"}
            aria-label={isMuted ? "Unmute microphone" : "Mute microphone"}
          >
            {isMuted ? <MicOff className="size-5" /> : <Mic className="size-5" />}
          </Button>
        )}

        {isConnected && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            asChild
            className="h-11 px-4 rounded-full font-medium gap-1.5 shadow-xs text-xs border-primary/30 hover:bg-primary/10 hover:text-primary"
            title="Switch to dedicated full voice call interface"
          >
            <Link to="/call/$id" params={{ id: conversationId }}>
              <Maximize2 className="size-3.5 text-primary" />
              <span>Full Screen Voice</span>
            </Link>
          </Button>
        )}

        <Button
          type="button"
          variant="destructive"
          onClick={handleEndCall}
          className="h-11 px-6 rounded-full font-medium gap-2 shadow-sm hover:shadow-md transition-all"
        >
          <PhoneOff className="size-4" />
          <span>{callState === "error" ? "Close Call" : "End Call"}</span>
        </Button>
      </div>
    </div>
  );
}
