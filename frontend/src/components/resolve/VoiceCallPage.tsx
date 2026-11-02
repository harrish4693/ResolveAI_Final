import { useState, useEffect, useRef, useCallback } from "react";
import { useNeuralTTS } from "@/hooks/useNeuralTTS";
import { Link, useNavigate } from "@tanstack/react-router";
import {
  Phone,
  PhoneOff,
  PhoneCall,
  Mic,
  MicOff,
  Volume2,
  VolumeX,
  Loader2,
  AlertCircle,
  Bot,
  User,
  Sparkles,
  FileText,
  Clock,
  Radio,
  ArrowRight,
  ArrowLeft,
  RotateCcw,
  MessageSquare,
  ShieldCheck,
  CheckCircle2,
  Copy,
  Check,
  Star,
  UserRound,
  Wrench,
  AlertTriangle,
  Sliders,
  Globe,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmationModal } from "@/components/ui/ConfirmationModal";
import { Textarea } from "@/components/ui/textarea";
import { Workspace } from "./workspace";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useWebSocket } from "@/lib/ws";
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

interface TranscriptTurn {
  id: string;
  sender: "customer" | "agent" | "expert";
  text: string;
  timestamp: string;
  isProvisional?: boolean;
}

interface OpenConversation {
  id: number;
  subject?: string;
  status: string;
  workflow_state?: string;
  created_at: string;
}

interface PendingConfirmation {
  executionId: string;
  toolName: string;
}

interface VoiceCallPageProps {
  initialConversationId?: string;
  autoStart?: boolean;
}

function getFriendlyWorkflowState(state?: string) {
  switch (state) {
    case "understanding":
      return "Understanding request…";
    case "searching_knowledge":
    case "deciding":
      return "Checking knowledge base…";
    case "asking_user":
      return "Waiting for your response";
    case "tool_requested":
    case "executing_tool":
      return "Executing agentic action…";
    case "awaiting_confirmation":
      return "Authorization required…";
    case "resolving":
      return "Resolving issue…";
    case "escalating":
    case "waiting_for_expert":
      return "Connecting to human expert…";
    case "with_expert":
      return "Connected to support expert";
    case "resolved":
      return "Resolved";
    default:
      return state || "Active";
  }
}

export const VOICE_LANGUAGES = [
  { code: "en-IN", label: "English (India)", badge: "EN-IN" },
  { code: "ta-IN", label: "Tamil (தமிழ்) / Tanglish", badge: "தமிழ்" },
  { code: "hi-IN", label: "Hindi (हिन्दी) / Hinglish", badge: "हिन्दी" },
  { code: "kn-IN", label: "Kannada (ಕನ್ನಡ) / Kanglish", badge: "ಕನ್ನಡ" },
  { code: "te-IN", label: "Telugu (తెలుగు) / Tenglish", badge: "తెలుగు" },
  { code: "ml-IN", label: "Malayalam (മലയാളം) / Manglish", badge: "മലയാളം" },
  { code: "bn-IN", label: "Bengali (বাংলা) / Benglish", badge: "বাংলা" },
  { code: "mr-IN", label: "Marathi (मराठी) / Marathish", badge: "मराठी" },
  { code: "gu-IN", label: "Gujarati (ગુજરાતી) / Gujlish", badge: "ગુજરાતી" },
  { code: "pa-IN", label: "Punjabi (ਪੰਜਾਬੀ) / Punglish", badge: "ਪੰਜਾਬੀ" },
  { code: "od-IN", label: "Odia (ଓଡ଼ିଆ)", badge: "ଓଡ଼ିଆ" },
  { code: "as-IN", label: "Assamese (অসমীয়া)", badge: "অসমীয়া" },
  { code: "ur-IN", label: "Urdu (اردو)", badge: "اردو" },
  { code: "en-US", label: "English (US)", badge: "EN-US" },
] as const;

export function selectNaturalVoice(
  voices: SpeechSynthesisVoice[],
  langCode: string,
  text: string
): SpeechSynthesisVoice | undefined {
  if (!voices || voices.length === 0) return undefined;

  const isTamilScript = /[\u0B80-\u0BFF]/.test(text) || langCode.startsWith("ta");
  const isHindiScript = /[\u0900-\u097F]/.test(text) || langCode.startsWith("hi") || langCode.startsWith("mr");
  const isKannadaScript = /[\u0C80-\u0CFF]/.test(text) || langCode.startsWith("kn");
  const isTeluguScript = /[\u0C00-\u0C7F]/.test(text) || langCode.startsWith("te");
  const isMalayalamScript = /[\u0D00-\u0D7F]/.test(text) || langCode.startsWith("ml");
  const isBengaliScript = /[\u0980-\u09FF]/.test(text) || langCode.startsWith("bn") || langCode.startsWith("as");
  const isGujaratiScript = /[\u0A80-\u0AFF]/.test(text) || langCode.startsWith("gu");
  const isGurmukhiScript = /[\u0A00-\u0A7F]/.test(text) || langCode.startsWith("pa");
  const isOdiaScript = /[\u0B00-\u0B7F]/.test(text) || langCode.startsWith("od") || langCode.startsWith("or");
  const isUrduScript = /[\u0600-\u06FF]/.test(text) || langCode.startsWith("ur");

  const targetPrefix = isTamilScript ? "ta" :
    isKannadaScript ? "kn" :
    isTeluguScript ? "te" :
    isMalayalamScript ? "ml" :
    isBengaliScript ? (langCode.startsWith("as") ? "as" : "bn") :
    isGujaratiScript ? "gu" :
    isGurmukhiScript ? "pa" :
    isOdiaScript ? "od" :
    isUrduScript ? "ur" :
    isHindiScript ? (langCode.startsWith("mr") ? "mr" : "hi") :
    langCode.split("-")[0].toLowerCase();

  const scoreVoice = (v: SpeechSynthesisVoice): number => {
    let score = 0;
    const nameLower = v.name.toLowerCase();
    const langLower = v.lang.toLowerCase();

    // 1. Language matching
    if (langLower === langCode.toLowerCase()) {
      score += 120;
    } else if (langLower.startsWith(targetPrefix)) {
      score += 80;
    } else if (targetPrefix === "en" && langLower.startsWith("en")) {
      score += 40;
    } else {
      score -= 60;
    }

    // 2. High-quality human neural / natural / online voices (drastic upgrade from robotic desktop)
    if (nameLower.includes("natural") || nameLower.includes("neural")) {
      score += 90;
    }
    if (nameLower.includes("online")) {
      score += 50;
    }
    if (nameLower.includes("google")) {
      score += 40;
    }

    // 3. Indian & English lifelike voice models
    if (
      nameLower.includes("neerja") ||
      nameLower.includes("prabhat") ||
      nameLower.includes("pallavi") ||
      nameLower.includes("swara") ||
      nameLower.includes("madhur") ||
      nameLower.includes("sapna") ||
      nameLower.includes("gagan") ||
      nameLower.includes("shruti") ||
      nameLower.includes("mohan") ||
      nameLower.includes("sobhana") ||
      nameLower.includes("midhun") ||
      nameLower.includes("tanishaa") ||
      nameLower.includes("bashkar") ||
      nameLower.includes("aarohi") ||
      nameLower.includes("manohar") ||
      nameLower.includes("dhwani") ||
      nameLower.includes("niranjan") ||
      nameLower.includes("raavi") ||
      nameLower.includes("gul") ||
      nameLower.includes("salman") ||
      nameLower.includes("valluvar") ||
      nameLower.includes("jenny") ||
      nameLower.includes("guy")
    ) {
      score += 70;
    }

    // 4. Heavily penalize legacy robotic desktop synthesizers (Windows SAPI 5 / eSpeak)
    if (
      nameLower.includes("desktop") ||
      nameLower.includes("david") ||
      nameLower.includes("george") ||
      nameLower.includes("hazel") ||
      nameLower.includes("zira")
    ) {
      score -= 60;
    }

    return score;
  };

  const ranked = [...voices].sort((a, b) => scoreVoice(b) - scoreVoice(a));
  return ranked[0];
}

export function cleanTextForSpeech(text: string): string {
  if (!text) return "";
  let cleaned = text;
  // Strip code blocks and inline code
  cleaned = cleaned.replace(/```[\s\S]*?```/g, "");
  cleaned = cleaned.replace(/`([^`]+)`/g, "$1");
  // Strip markdown bold / italics
  cleaned = cleaned.replace(/\*\*([^*]+)\*\*/g, "$1");
  cleaned = cleaned.replace(/\*([^*]+)\*/g, "$1");
  // Strip markdown headers and list bullet markers
  cleaned = cleaned.replace(/^#+\s*/gm, "");
  cleaned = cleaned.replace(/^\s*[-*•]\s+/gm, "");
  // Replace links with friendly speech word
  cleaned = cleaned.replace(/https?:\/\/\S+/g, "link");
  // Strip policy tag metadata like [CORE], [EXT]
  cleaned = cleaned.replace(/\[(?:CORE|EXT|INFO)[^\]]*\]/gi, "");
  // Strip JSON-like curly brackets
  cleaned = cleaned.replace(/\{[^}]*\}/g, "");
  // Space out technical identifiers and codes for natural phone pronunciation
  cleaned = cleaned.replace(/\b(TXN)(\d+)\b/gi, (_m, _p, d) => `T X N ${d.split("").join(" ")}`);
  cleaned = cleaned.replace(/\b(ORD)(\d+)\b/gi, (_m, _p, d) => `O R D ${d.split("").join(" ")}`);
  // Expand common abbreviations for natural speech
  cleaned = cleaned.replace(/\be\.g\./gi, "for example");
  cleaned = cleaned.replace(/\bi\.e\./gi, "that is");
  cleaned = cleaned.replace(/\bID\b/g, "I D");
  // Tanglish & Hinglish natural conversational pauses
  cleaned = cleaned.replace(/\b(Aiyo)([,.!?\s])/gi, "$1, ");
  cleaned = cleaned.replace(/\b(Arre)([,.!?\s])/gi, "$1, ");
  // Normalize whitespace
  cleaned = cleaned.replace(/\s+/g, " ").trim();
  return cleaned;
}


export function VoiceCallPage({
  initialConversationId,
  autoStart = false,
}: VoiceCallPageProps) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { subscribe, isConnected: isWsConnected, sendTranscriptUpdate } = useWebSocket();

  // Call lifecycle: idle -> initializing -> connecting -> connected -> listening -> finalizing -> transcribing -> thinking -> speaking -> reconnecting -> ended / error
  const [callState, setCallState] = useState<
    | "idle"
    | "initializing"
    | "connecting"
    | "connected"
    | "listening"
    | "finalizing"
    | "transcribing"
    | "thinking"
    | "speaking"
    | "reconnecting"
    | "ended"
    | "error"
  >(initialConversationId || autoStart ? "initializing" : "idle");

  const [activeConversationId, setActiveConversationId] = useState<string | null>(
    initialConversationId && initialConversationId !== "new" ? initialConversationId : null
  );

  const [errorMessage, setErrorMessage] = useState("");
  const [isMuted, setIsMuted] = useState(false);
  const [isSpeakerMuted, setIsSpeakerMuted] = useState(false);
  const [isAgentSpeaking, setIsAgentSpeaking] = useState(false);
  const [isProcessingTurn, setIsProcessingTurn] = useState(false);
  const [currentCustomerTranscript, setCurrentCustomerTranscript] = useState("");
  const [remoteProvisionalTurn, setRemoteProvisionalTurn] = useState<TranscriptTurn | null>(null);
  const activeTurnIdRef = useRef<string>("");
  const [lastAgentReply, setLastAgentReply] = useState("");
  const [transcriptLog, setTranscriptLog] = useState<TranscriptTurn[]>([]);
  const [callDuration, setCallDuration] = useState(0);
  const [showTranscriptDrawer, setShowTranscriptDrawer] = useState(false);
  const [copiedTranscript, setCopiedTranscript] = useState(false);

  // Full Chatbot Parity: Workflow state, tools, confirmations, and handoffs
  const [workflowState, setWorkflowState] = useState<string>("idle");
  const [activeToolActivity, setActiveToolActivity] = useState<{
    tool_name?: string;
    status?: string;
  } | null>(null);
  const [pendingConfirmation, setPendingConfirmation] = useState<PendingConfirmation | null>(null);
  const [isConfirmingTool, setIsConfirmingTool] = useState(false);
  const [isWithExpert, setIsWithExpert] = useState(false);

  // Customer Feedback & Rating
  const [rating, setRating] = useState(0);
  const [feedbackComment, setFeedbackComment] = useState("");
  const [feedbackSubmitted, setFeedbackSubmitted] = useState(false);
  const [isSubmittingFeedback, setIsSubmittingFeedback] = useState(false);

  // Pre-call open conversations selection
  const [recentConversations, setRecentConversations] = useState<OpenConversation[]>([]);
  const [loadingRecent, setLoadingRecent] = useState(false);

  // Stable refs for audio, speech, livekit to eliminate teardown / closure issues
  const roomRef = useRef<any>(null);
  const audioElRef = useRef<HTMLAudioElement | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const recognitionRef = useRef<any>(null);
  const isCallActiveRef = useRef<boolean>(false);
  const isAgentSpeakingRef = useRef<boolean>(false);
  isAgentSpeakingRef.current = isAgentSpeaking;
  const isSpeakerMutedRef = useRef<boolean>(false);
  isSpeakerMutedRef.current = isSpeakerMuted;
  const isProcessingTurnRef = useRef<boolean>(false);
  const isMutedRef = useRef<boolean>(false);
  const restartTimerRef = useRef<any>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const lastSpokenAgentTextRef = useRef<string>("");
  const lastProcessedTranscriptRef = useRef<string>("");
  const lastProcessedTurnRef = useRef<{ text: string; timestamp: number }>({ text: "", timestamp: 0 });
  const activeCidRef = useRef<string | null>(activeConversationId);
  const hasPriorHistoryRef = useRef<boolean>(false);
  const [detectedEmotion, setDetectedEmotion] = useState<string>("calm");
  const [emotionConfidence, setEmotionConfidence] = useState<number>(0.85);
  const [detectedLanguage, setDetectedLanguage] = useState<string>("");
  const [turnLatencyMs, setTurnLatencyMs] = useState<number | null>(null);
  const detectedEmotionRef = useRef<string>("calm");
  detectedEmotionRef.current = detectedEmotion;

  const processCustomerTurnRef = useRef<(text: string, cid: string) => Promise<void>>(async () => {});
  const processCustomerAudioTurnRef = useRef<(wavBlob: Blob, cid: string) => Promise<void>>(async () => {});
  const speakAgentResponseRef = useRef<(text: string, emotion?: string) => void>(() => {});
  const handleEndCallRef = useRef<() => void>(() => {});

  // Real microphone audio capture and Client VAD refs
  const audioContextRef = useRef<AudioContext | null>(null);
  const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const processorNodeRef = useRef<ScriptProcessorNode | null>(null);
  const gainNodeRef = useRef<GainNode | null>(null);
  const vadStateRef = useRef<ClientVADState | null>(null);
  const bargeInFramesRef = useRef<number>(0);

  // Language state for speech recognition and natural voice synthesis
  const [callLanguage, setCallLanguage] = useState<string>("en-IN");
  const callLanguageRef = useRef<string>("en-IN");
  callLanguageRef.current = callLanguage;
  const startBrowserRecognitionRef = useRef<(lang: string, targetCid: string) => void>(() => {});
  const silenceTimerRef = useRef<any>(null);
  const pendingInterimRef = useRef<string>("");
  const accumulatedTranscriptRef = useRef<string>("");
  const currentSessionTranscriptRef = useRef<string>("");
  const currentSessionFinalsRef = useRef<string>("");
  const currentSessionInterimRef = useRef<string>("");
  const dispatchedTurnsHistoryRef = useRef<string[]>([]);

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

  // ── Neural TTS (server-side Sarvam voice) with browser fallback ──
  const browserFallbackRef = useRef<(text: string, emotion?: string) => void>(() => {});
  const neuralTTS = useNeuralTTS({
    conversationId: activeConversationId,
    language: callLanguage,
    emotion: detectedEmotion,
    onFirstAudioPlay: (latencyMs) => {
      setTurnLatencyMs(latencyMs);
    },
    onSpeakingStart: (text) => {
      turnCoordinatorRef.current.onAgentAudioStart(text);
      isAgentSpeakingRef.current = true;
      setIsAgentSpeaking(true);
      setCallState("speaking");
      setLastAgentReply(text);
      setTranscriptLog((prev) => [
        ...prev,
        {
          id: `agent_${Date.now()}`,
          sender: "agent",
          text,
          timestamp: new Date().toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
          }),
        },
      ]);
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
        if (!isMutedRef.current && activeCidRef.current) {
          startBrowserRecognitionRef.current(callLanguageRef.current, activeCidRef.current);
        }
      }
    },
    browserFallback: (text, emotion) => {
      browserFallbackRef.current(text, emotion);
    },
  });


  // Load recent conversations for quick pre-call selection
  useEffect(() => {
    let mounted = true;
    async function loadRecent() {
      try {
        setLoadingRecent(true);
        const res = await api.get("/conversations");
        if (mounted && Array.isArray(res.data)) {
          const activeOnes = res.data.filter(
            (c: any) => c.status !== "resolved" && c.status !== "closed"
          );
          setRecentConversations(activeOnes.slice(0, 4));
        }
      } catch (err) {
        console.warn("Failed to fetch recent conversations for voice call", err);
      } finally {
        if (mounted) setLoadingRecent(false);
      }
    }
    if (callState === "idle") {
      loadRecent();
    }
    return () => {
      mounted = false;
    };
  }, [callState]);

  const handleLanguageChange = (newLang: string) => {
    setCallLanguage(newLang);
    callLanguageRef.current = newLang;
    if (isCallActiveRef.current && !isMutedRef.current && activeCidRef.current) {
      startBrowserRecognitionRef.current(newLang, activeCidRef.current);
    }
  };

  // Pre-load natural speech synthesis voices
  useEffect(() => {
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.getVoices();
      const handleVoices = () => {
        window.speechSynthesis.getVoices();
      };
      window.speechSynthesis.addEventListener("voiceschanged", handleVoices);
      return () => {
        window.speechSynthesis.removeEventListener("voiceschanged", handleVoices);
      };
    }
  }, []);

  // Browser TTS fallback (original speechSynthesis path — unchanged)
  const speakWithBrowserTTS = useCallback((text: string, emotion?: string) => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) {
      setCallState("listening");
      return;
    }
    if (isSpeakerMutedRef.current) {
      setCallState("listening");
      return;
    }

    try {
      window.speechSynthesis.cancel();
      const cleaned = cleanTextForSpeech(text);
      lastSpokenAgentTextRef.current = cleaned.toLowerCase().trim();
      const utterance = new SpeechSynthesisUtterance(cleaned);

      // Emotion-adaptive natural human prosody
      const emo = (emotion || detectedEmotionRef.current || "calm").toLowerCase();
      if (emo === "frustrated") {
        utterance.rate = 0.96;
        utterance.pitch = 0.98;
      } else if (emo === "confused") {
        utterance.rate = 0.94;
        utterance.pitch = 1.0;
      } else if (emo === "urgent") {
        utterance.rate = 1.06;
        utterance.pitch = 1.02;
      } else if (emo === "satisfied") {
        utterance.rate = 1.02;
        utterance.pitch = 1.02;
      } else {
        utterance.rate = 1.01;
        utterance.pitch = 1.0;
      }

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
        setTranscriptLog((prev) => [
          ...prev,
          {
            id: `agent_${Date.now()}`,
            sender: "agent",
            text,
            timestamp: new Date().toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
              second: "2-digit",
            }),
          },
        ]);
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
            } catch {
              // Ignore if recognition is already running
            }
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

  // Wire the browser fallback ref so the neural TTS hook can call it
  browserFallbackRef.current = speakWithBrowserTTS;

  // Primary speak function: neural TTS first, browser fallback if unavailable
  const speakAgentResponse = useCallback((text: string, emotion?: string) => {
    if (isSpeakerMutedRef.current) {
      setCallState("listening");
      return;
    }
    lastSpokenAgentTextRef.current = cleanTextForSpeech(text).toLowerCase().trim();
    // Try neural TTS (server-side Sarvam); it auto-falls back to browser
    neuralTTS.speak(text);
  }, [neuralTTS]);

  speakAgentResponseRef.current = speakAgentResponse;

  // WebSocket Subscription for Real-Time Tool Execution, Confirmation, Handoff & Updates
  useEffect(() => {
    if (!activeConversationId) return;
    const cid = parseInt(activeConversationId);
    if (isNaN(cid)) return;

    // 1. Tool execution activity (e.g. check order, refund, profile)
    const unsubTool = subscribe("AGENTIC_TOOL_ACTIVITY", (event) => {
      if (event.conversation_id !== cid) return;
      const data = event.data as any;
      setActiveToolActivity(data);
      if (data?.tool_name && data?.status === "started") {
        setWorkflowState("executing_tool");
      } else if (data?.status === "completed") {
        setTimeout(() => setActiveToolActivity(null), 3000);
      }
    });

    // 2. Sensitive Tool Confirmation Required (e.g. refund authorization)
    const unsubConfirm = subscribe("TOOL_CONFIRMATION_REQUIRED", (event) => {
      if (event.conversation_id !== cid) return;
      const data = event.data as any;
      if (data.execution_id && data.tool_name) {
        setPendingConfirmation({
          executionId: data.execution_id,
          toolName: data.tool_name,
        });
        setWorkflowState("awaiting_confirmation");
        speakAgentResponse(
          `I need your confirmation before I can proceed with ${data.tool_name.replace(/_/g, " ")}. Please confirm on your screen.`
        );
      }
    });

    // 3. Conversation & Workflow State Updates
    const unsubUpdated = subscribe("CONVERSATION_UPDATED", (event) => {
      if (event.conversation_id !== cid) return;
      const data = event.data as any;
      if (data?.workflow_state) {
        setWorkflowState(data.workflow_state);
        if (data.workflow_state === "with_expert" || data.workflow_state === "waiting_for_expert") {
          setIsWithExpert(true);
        }
      }
    });

    // 4. Live Message from Agent or Human Expert
    const unsubMsg = subscribe("NEW_MESSAGE", (event) => {
      if (event.conversation_id !== cid) return;
      const msg = event.data as any;
      if (!msg) return;
      // Parity Row 12: Expert internal notes must never be spoken or displayed to caller
      if (msg.is_internal) return;

      const sender = (msg.sender_type || "").toLowerCase();
      if (sender === "expert") {
        setIsWithExpert(true);
        setTranscriptLog((prev) => [
          ...prev,
          {
            id: `msg_${msg.id || Date.now()}`,
            sender: "expert",
            text: msg.content,
            timestamp: new Date().toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
              second: "2-digit",
            }),
          },
        ]);
        speakAgentResponse(`Expert says: ${msg.content}`);
      }
    });

    // 5. Remote call termination (Customer or Expert cut the call)
    const unsubCallEnded = subscribe("VOICE_CALL_ENDED", (event) => {
      if (event.conversation_id !== cid) return;
      handleEndCallRef.current();
    });

    // 6. Real-time incremental transcript stream from remote participant
    const unsubTranscriptStream = subscribe("TRANSCRIPT_STREAM", (event) => {
      if (event.conversation_id !== cid) return;
      const data = event.data as any;
      if (!data) return;
      const { turn_id, sender_type, text, is_final } = data;
      if (!text) return;

      if (is_final) {
        setTranscriptLog((prev) => {
          if (prev.some((t) => t.id === turn_id)) return prev;
          return [
            ...prev,
            {
              id: turn_id,
              sender: sender_type === "expert" ? "expert" : "customer",
              text,
              timestamp: new Date().toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
              }),
              isProvisional: false,
            },
          ];
        });
        setRemoteProvisionalTurn(null);
      } else {
        setRemoteProvisionalTurn({
          id: turn_id,
          sender: sender_type === "expert" ? "expert" : "customer",
          text,
          timestamp: "Speaking now…",
          isProvisional: true,
        });
      }
    });

    return () => {
      unsubTool();
      unsubConfirm();
      unsubUpdated();
      unsubMsg();
      unsubCallEnded();
      unsubTranscriptStream();
    };
  }, [activeConversationId, subscribe, speakAgentResponse]);

  // Handle Tool Confirmation (Accept / Reject)
  const handleToolConfirm = async (action: "accept" | "reject") => {
    if (!pendingConfirmation || !activeConversationId || isConfirmingTool) return;
    setIsConfirmingTool(true);
    try {
      await api.post(
        `/conversations/${activeConversationId}/tools/${pendingConfirmation.executionId}/confirm`,
        { action }
      );
      setPendingConfirmation(null);
      speakAgentResponse(
        action === "accept"
          ? "Thank you. Proceeding with the action now."
          : "Action has been cancelled."
      );
    } catch (err: any) {
      console.error("Failed to confirm tool action:", err);
      speakAgentResponse("There was an error confirming the action. Please try again.");
    } finally {
      setIsConfirmingTool(false);
    }
  };

  // Process customer spoken turn through LiveKit utterance pipeline
  const processCustomerTurn = useCallback(
    async (text: string, cid: string) => {
      const clean = text.trim();
      if (!clean || isProcessingTurnRef.current || !isCallActiveRef.current) return;

      // Noise & hallucination filter: reject non-speech tags, isolated fillers, corpus artifacts
      const validation = validateCustomerUtterance(clean);
      if (!validation.isValid) {
        voiceDiagnostics.logEvent({
          event: "TURN_BLOCKED_BY_NOISE_FILTER",
          state: "listening",
          conversationId: cid,
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
          conversationId: cid,
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

      const isExpertUser = user?.role === "expert";
      const turnTimestamp = new Date().toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });

      setTranscriptLog((prev) => [
        ...prev,
        {
          id: `${isExpertUser ? "exp" : "cust"}_${Date.now()}`,
          sender: isExpertUser ? "expert" : "customer",
          text: clean,
          timestamp: turnTimestamp,
        },
      ]);

      // Abort controller for barge-in cancellation of obsolete AI responses
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
          conversationId: cid,
          details: {
            transcriptLength: clean.length,
            isExpert: isExpertUser,
          },
        });

        if (isExpertUser) {
          // Expert speech is saved directly to conversation, no AI TTS response needed
          await api.post(`/conversations/${cid}/messages`, {
            content: clean,
          });
          setCallState("listening");
        } else {
          const res = await api.post(
            "/audio/livekit/utterance",
            {
              conversation_id: parseInt(cid),
              utterance_id: `livekit_turn_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
              transcript: clean,
            },
            { signal: abortCtrl.signal }
          );

          if (abortCtrl.signal.aborted) return;

          voiceDiagnostics.logEvent({
            event: "AI_RESPONSE_RECEIVED",
            state: "thinking",
            conversationId: cid,
            details: {
              roundtripMs: Date.now() - turnStartMs,
              serverLatencyMs: res.data?.latency_ms,
              hasAiResponse: Boolean(res.data?.ai_response),
            },
          });

          if (res.data?.workflow_state) {
            setWorkflowState(res.data.workflow_state);
          }

          if (res.data?.emotion) {
            setDetectedEmotion(res.data.emotion);
            detectedEmotionRef.current = res.data.emotion;
            setEmotionConfidence(res.data.emotion_confidence || 0.85);
          }

          if (res.data?.language) {
            setDetectedLanguage(res.data.language);
            const newBcp47 = resolveBcp47(res.data.bcp47_code, res.data.language);
            if (newBcp47 && newBcp47 !== callLanguageRef.current) {
              setCallLanguage(newBcp47);
              callLanguageRef.current = newBcp47;
            }
          }

          if (res.data?.latency_ms !== undefined) {
            setTurnLatencyMs(Math.round(res.data.latency_ms));
          }

          const reply = res.data?.ai_response;
          if (reply) {
            speakAgentResponseRef.current(reply, res.data?.emotion);
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
          conversationId: cid,
          error: err.message || String(err),
          reason: failureCategory,
        });
        console.error("Failed to process customer spoken turn", err);
        setCallState("listening");
      } finally {
        isProcessingTurnRef.current = false;
        setIsProcessingTurn(false);
        setCurrentCustomerTranscript("");
        accumulatedTranscriptRef.current = "";
        currentSessionFinalsRef.current = "";
        currentSessionInterimRef.current = "";
        currentSessionTranscriptRef.current = "";
      }
    },
    [user]
  );
  processCustomerTurnRef.current = processCustomerTurn;

  // Cleanup Web Audio nodes and mic stream
  const cleanupAudioCapture = useCallback(() => {
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
    if (audioContextRef.current && audioContextRef.current.state !== "closed") {
      try {
        audioContextRef.current.close().catch(() => {});
      } catch {}
      audioContextRef.current = null;
    }
    if (micStreamRef.current) {
      try {
        micStreamRef.current.getTracks().forEach((t) => t.stop());
      } catch {}
      micStreamRef.current = null;
    }
    if (vadStateRef.current) {
      vadStateRef.current.reset();
    }
  }, []);

  // Process raw microphone audio turn via server-side Saaras v4 STT & intelligence pipeline
  const processCustomerAudioTurn = useCallback(
    async (wavBlob: Blob, cid: string) => {
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
        conversationId: cid,
        utteranceId,
        details: {
          payloadBytes: wavBlob.size,
          mimeType: wavBlob.type,
          audioContextState: audioContextRef.current?.state,
        },
      });

      const isExpertUser = user?.role === "expert";

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
          parseInt(cid),
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
            conversationId: cid,
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
            conversationId: cid,
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
          setCurrentCustomerTranscript(recognizedText);
          const turnTimestamp = new Date().toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
          });

          setTranscriptLog((prev) => [
            ...prev,
            {
              id: `${isExpertUser ? "exp" : "cust"}_${Date.now()}`,
              sender: isExpertUser ? "expert" : "customer",
              text: recognizedText,
              timestamp: turnTimestamp,
            },
          ]);
        }

        if (res.language || res.bcp47_code) {
          setDetectedLanguage(res.language || "English");
          const newBcp47 = resolveBcp47(res.bcp47_code, res.language);
          if (newBcp47 && newBcp47 !== callLanguageRef.current) {
            setCallLanguage(newBcp47);
            callLanguageRef.current = newBcp47;
          }
        }

        if (res.workflow_state) {
          setWorkflowState(res.workflow_state);
        }

        if (res.emotion) {
          setDetectedEmotion(res.emotion);
          detectedEmotionRef.current = res.emotion;
          setEmotionConfidence(0.9);
        }

        if (res.latency_ms !== undefined) {
          setTurnLatencyMs(Math.round(res.latency_ms));
        }

        voiceDiagnostics.logEvent({
          event: "AI_RESPONSE_RECEIVED",
          state: "thinking",
          conversationId: cid,
          utteranceId,
          details: {
            roundtripMs: Date.now() - turnStartMs,
            transcriptCharCount: recognizedText.length,
            aiResponseCharCount: (res.ai_response || "").length,
          },
        });

        const reply = res.ai_response;
        if (reply && !isExpertUser) {
          speakAgentResponseRef.current(reply, res.emotion);
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
          conversationId: cid,
          utteranceId,
          error: err.message || String(err),
          reason: failureCategory,
        });
        console.error("Failed to process customer audio turn", err);
        setCallState("listening");
      } finally {
        isProcessingTurnRef.current = false;
        setIsProcessingTurn(false);
        setCurrentCustomerTranscript("");
        accumulatedTranscriptRef.current = "";
        currentSessionFinalsRef.current = "";
        currentSessionInterimRef.current = "";
        currentSessionTranscriptRef.current = "";
      }
    },
    [user]
  );
  processCustomerAudioTurnRef.current = processCustomerAudioTurn;

  // Browser Web Speech Recognition manager (ensures fresh instances across restarts)
  const startBrowserRecognition = useCallback((lang: string, targetCid: string, retryAttempt: number = 0) => {
    if (typeof window === "undefined") return;
    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) return;

    logSTTDiagnostic({
      sessionId: targetCid || "call_page",
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
          sessionId: targetCid || "call_page",
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
          sessionId: targetCid || "call_page",
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
          neuralTTS.stop();
          if (typeof window !== "undefined" && "speechSynthesis" in window) {
            window.speechSynthesis.cancel();
          }
          turnCoordinatorRef.current.onAgentAudioAllFinished();
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

        // Update live transcript display for customer
        setCurrentCustomerTranscript(fullAccumulated);

        // Stream incremental transcription over WebSocket to other participants
        if (targetCid && sendTranscriptUpdate) {
          sendTranscriptUpdate(parseInt(targetCid), activeTurnIdRef.current, fullAccumulated, false);
        }

        // Silence timer management:
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
            if (
              !isProcessingTurnRef.current &&
              isCallActiveRef.current
            ) {
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
                setCurrentCustomerTranscript("");
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
                setCurrentCustomerTranscript("");
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
              if (targetCid && sendTranscriptUpdate && activeTurnIdRef.current) {
                sendTranscriptUpdate(parseInt(targetCid), activeTurnIdRef.current, toSend, true);
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

              processCustomerTurnRef.current(toSend, targetCid);
            }
          }, silenceDelay);
        }
      };

      recognition.onerror = (event: any) => {
        logSTTDiagnostic({
          sessionId: targetCid || "call_page",
          feature: "call_agent",
          event: "ONERROR",
          selectedLang: lang,
          error: event.error,
        });
        if (event.error !== "no-speech" && event.error !== "aborted") {
          console.warn("Speech recognition warning:", event.error);
        }
        if (event.error === "network") {
          if (isCallActiveRef.current && !isMutedRef.current) {
            setTimeout(() => {
              if (isCallActiveRef.current && !isMutedRef.current) {
                startBrowserRecognitionRef.current(callLanguageRef.current, targetCid);
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
          sessionId: targetCid || "call_page",
          feature: "call_agent",
          event: "ONEND",
          selectedLang: callLanguageRef.current,
          committedText: accumulatedTranscriptRef.current,
        });

        // Automatically restart recognition while call is active with a FRESH instance
        if (isCallActiveRef.current && !isMutedRef.current) {
          if (restartTimerRef.current) clearTimeout(restartTimerRef.current);
          logSTTDiagnostic({
            sessionId: targetCid || "call_page",
            feature: "call_agent",
            event: "RESTART_SCHEDULED",
            selectedLang: callLanguageRef.current,
          });
          restartTimerRef.current = setTimeout(() => {
            if (isCallActiveRef.current && !isMutedRef.current) {
              logSTTDiagnostic({
                sessionId: targetCid || "call_page",
                feature: "call_agent",
                event: "RESTART_TRIGGERED",
                selectedLang: callLanguageRef.current,
              });
              startBrowserRecognitionRef.current(callLanguageRef.current, targetCid);
            }
          }, 220);
        }
      };

      try {
        recognition.start();
        recognitionRef.current = recognition;
        logSTTDiagnostic({
          sessionId: targetCid || "call_page",
          feature: "call_agent",
          event: "START_SUCCESS",
          selectedLang: lang,
        });
      } catch (err: any) {
        logSTTDiagnostic({
          sessionId: targetCid || "call_page",
          feature: "call_agent",
          event: "START_EXCEPTION",
          selectedLang: lang,
          error: err?.message || String(err),
        });
        console.warn("SpeechRecognition start error:", err);
        if (isCallActiveRef.current && !isMutedRef.current && retryAttempt < 3) {
          const delay = 250 * Math.pow(2, retryAttempt);
          logSTTDiagnostic({
            sessionId: targetCid || "call_page",
            feature: "call_agent",
            event: "RESTART_SCHEDULED",
            selectedLang: lang,
            details: { retryAttempt: retryAttempt + 1, delay },
          });
          setTimeout(() => {
            if (isCallActiveRef.current && !isMutedRef.current) {
              startBrowserRecognitionRef.current(lang, targetCid, retryAttempt + 1);
            }
          }, delay);
        }
      }
    } catch (err: any) {
      console.warn("SpeechRecognition start error:", err);
    }
  }, [sendTranscriptUpdate, neuralTTS]);
  startBrowserRecognitionRef.current = startBrowserRecognition;

  // Start the voice call session
  const startCall = useCallback(
    async (convoIdToUse?: string) => {
      try {
        setCallState("connecting");
        setErrorMessage("");
        setCallDuration(0);
        setTranscriptLog([]);
        setWorkflowState("understanding");
        setIsWithExpert(false);

        let targetCid = convoIdToUse || activeCidRef.current;

        // If no conversation exists yet, create one directly with channel="voice" and no dummy text
        if (!targetCid || targetCid === "new") {
          const createRes = await api.post("/conversations", {
            channel: "voice",
            subject: `Voice Call with ResolveAI`,
          });
          targetCid = String(createRes.data.id);
          setActiveConversationId(targetCid);
          activeCidRef.current = targetCid;
          hasPriorHistoryRef.current = false;
        } else {
          try {
            const [histRes, convoRes] = await Promise.all([
              api.get(`/conversations/${targetCid}/messages`),
              api.get(`/conversations/${targetCid}`),
            ]);
            hasPriorHistoryRef.current = Array.isArray(histRes.data) && histRes.data.length > 0;
            if (convoRes.data?.preferred_language) {
              const newBcp47 = resolveBcp47(undefined, convoRes.data.preferred_language);
              setCallLanguage(newBcp47);
              callLanguageRef.current = newBcp47;
            }
          } catch {
            hasPriorHistoryRef.current = false;
          }
        }

        // 1. Fetch short-lived token from LiveKit backend endpoint
        const res = await api.post("/audio/livekit/token", {
          conversation_id: parseInt(targetCid),
        });

        const { server_url, token } = res.data;

        // 2. Dynamically import LiveKit client
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

        // 3. Audio subscriptions
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
          setCallState("reconnecting");
        });

        room.on(RoomEvent.Reconnected, () => {
          setCallState("listening");
        });

        // Instant peer-to-peer termination
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
                  console.warn("Could not resume AudioContext immediately in VoiceCallPage:", resErr);
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
                conversationId: targetCid!,
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
                      neuralTTS.stop();
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
                        conversationId: targetCid!,
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
                  processCustomerAudioTurnRef.current(wavBlob, targetCid!);
                }
              };

              source.connect(processor);
            }
          } catch (e) {
            console.warn("Microphone AudioContext setup fallback:", e);
          }
        }

        // 4. Connect to WebRTC room (with graceful fallback to direct voice pipeline)
        let livekitConnected = false;
        try {
          await room.connect(server_url, token);
          livekitConnected = true;
        } catch (webrtcErr) {
          console.warn("LiveKit WebRTC connection failed, running in direct voice mode:", webrtcErr);
        }

        // 5. Enable microphone safely without crashing the call if permissions are pending or denied
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

        isCallActiveRef.current = true;

        setCallState("listening");
        setWorkflowState("asking_user");

        // Start call timer
        timerRef.current = setInterval(() => {
          setCallDuration((prev) => prev + 1);
        }, 1000);

        // Initial welcome greeting from agent only if there is no prior history and user is not an expert
        if (!hasPriorHistoryRef.current && user?.role !== "expert") {
          const initialGreeting = getGreetingForLanguage(callLanguageRef.current);
          speakAgentResponseRef.current(initialGreeting);
        }

        // 6. Start continuous natural speech recognition
        startBrowserRecognitionRef.current(callLanguageRef.current, targetCid!);
      } catch (err: any) {
        console.error("Voice call connection failed:", err);
        let detail = "Failed to establish live voice connection. Please check your internet connection or server status.";
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
    },
    []
  );

  // Auto-start call if triggered via route or prop
  useEffect(() => {
    if (callState === "initializing") {
      startCall();
    }
  }, [callState, startCall]);

  // Clean teardown on unmount
  useEffect(() => {
    return () => {
      isCallActiveRef.current = false;
      dispatchedTurnsHistoryRef.current = [];
      cleanupAudioCapture();
      if (restartTimerRef.current) {
        clearTimeout(restartTimerRef.current);
        restartTimerRef.current = null;
      }
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
      neuralTTS.stop();
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
    };
  }, [cleanupAudioCapture]);

  // Controls: toggle mute
  const toggleMute = async () => {
    const nextMuted = !isMuted;
    setIsMuted(nextMuted);
    isMutedRef.current = nextMuted;

    if (micStreamRef.current) {
      micStreamRef.current.getAudioTracks().forEach((track) => {
        track.enabled = !nextMuted;
      });
    }

    if (roomRef.current?.localParticipant) {
      try {
        await roomRef.current.localParticipant.setMicrophoneEnabled(!nextMuted);
      } catch (err) {
        console.warn("Failed to set LiveKit mic enabled state:", err);
      }
    }

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
  };

  // Controls: toggle speaker output
  const toggleSpeaker = () => {
    const next = !isSpeakerMuted;
    setIsSpeakerMuted(next);
    isSpeakerMutedRef.current = next;
    if (next) {
      neuralTTS.stop();
      if (typeof window !== "undefined" && "speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
      setIsAgentSpeaking(false);
      isAgentSpeakingRef.current = false;
    }
  };

  // End call
  const handleEndCall = () => {
    // 1. Notify peer immediately over WebRTC data channel
    if (roomRef.current?.localParticipant) {
      try {
        const payload = new TextEncoder().encode(
          JSON.stringify({ type: "CALL_ENDED", ended_by: user?.role === "expert" ? "expert" : "customer" })
        );
        roomRef.current.localParticipant.publishData(payload, { reliable: true });
      } catch {}
    }

    // 2. Notify backend to broadcast VOICE_CALL_ENDED via WS and delete LiveKit room
    const targetCid = activeConversationId || activeCidRef.current;
    const cid = targetCid ? parseInt(targetCid) : NaN;
    if (!isNaN(cid)) {
      api.post("/audio/livekit/end-call", { conversation_id: cid }).catch(() => {});
    }

    isCallActiveRef.current = false;
    dispatchedTurnsHistoryRef.current = [];
    cleanupAudioCapture();
    if (restartTimerRef.current) {
      clearTimeout(restartTimerRef.current);
      restartTimerRef.current = null;
    }
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }
    pendingInterimRef.current = "";
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    neuralTTS.stop();
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
    if (roomRef.current) {
      try {
        roomRef.current.disconnect();
      } catch {}
      roomRef.current = null;
    }
    setIsAgentSpeaking(false);
    isAgentSpeakingRef.current = false;
    setIsProcessingTurn(false);
    isProcessingTurnRef.current = false;
    setCallState("ended");
  };
  handleEndCallRef.current = handleEndCall;


  // Submit Feedback & Rating
  const submitFeedback = async () => {
    if (rating === 0 || !activeConversationId || isSubmittingFeedback) return;
    setIsSubmittingFeedback(true);
    try {
      await api.post(`/conversations/${activeConversationId}/feedback`, {
        rating,
        comment: feedbackComment,
      });
      setFeedbackSubmitted(true);
    } catch (err: any) {
      if (err.response?.status === 409) {
        setFeedbackSubmitted(true);
      } else {
        console.error("Failed to submit feedback:", err);
      }
    } finally {
      setIsSubmittingFeedback(false);
    }
  };

  const isCallConnected =
    callState === "connected" ||
    callState === "listening" ||
    callState === "finalizing" ||
    callState === "transcribing" ||
    callState === "thinking" ||
    callState === "speaking" ||
    callState === "reconnecting";

  // Format call duration MM:SS
  const formatDuration = (secs: number) => {
    const mins = Math.floor(secs / 60);
    const remainder = secs % 60;
    return `${mins.toString().padStart(2, "0")}:${remainder.toString().padStart(2, "0")}`;
  };

  // Copy full transcript text
  const handleCopyTranscript = () => {
    const text = transcriptLog
      .map((t) => `[${t.timestamp}] ${t.sender.toUpperCase()}: ${t.text}`)
      .join("\n");
    navigator.clipboard.writeText(text);
    setCopiedTranscript(true);
    setTimeout(() => setCopiedTranscript(false), 2000);
  };

  return (
    <Workspace
      title="Voice Call"
      active="Voice Call"
      role={user?.role === "expert" ? "expert" : user?.role === "admin" ? "admin" : "customer"}
    >
      <div className="max-w-5xl mx-auto px-4 py-6 w-full flex flex-col min-h-[calc(100vh-120px)] justify-between relative">
        {/* Top Bar Header */}
        <div className="flex items-center justify-between pb-4 border-b border-border/80">
          <div className="flex items-center gap-3">
            <span className="size-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary shadow-xs">
              <PhoneCall className="size-5" />
            </span>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-lg font-semibold tracking-tight text-foreground">
                  Voice Call with ResolveAI
                </h1>
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-primary/10 text-primary border border-primary/20">
                  <Radio className="size-3 animate-pulse" />
                  Live WebRTC
                </span>
                {isWithExpert && (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-blue-500/10 text-blue-600 border border-blue-500/20">
                    <UserRound className="size-3" />
                    Expert Connected
                  </span>
                )}
              </div>
              <p className="text-xs text-muted-foreground">
                Autonomous agentic intelligence · Multilingual English, Tanglish, Hinglish · Tools & RAG
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 sm:gap-3 flex-wrap justify-end">
            {/* Language Selector for STT and Natural Human TTS */}
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-border bg-card shadow-2xs text-xs">
              <Globe className="size-3.5 text-primary shrink-0" />
              <select
                aria-label="Call language"
                value={callLanguage}
                onChange={(e) => handleLanguageChange(e.target.value)}
                className="bg-transparent text-xs font-medium text-foreground cursor-pointer focus:outline-hidden pr-1"
                title="Choose spoken language (English, Tamil, Hindi, Tanglish/Hinglish)"
              >
                {VOICE_LANGUAGES.map((l) => (
                  <option key={l.code} value={l.code} className="bg-popover text-popover-foreground">
                    {l.label}
                  </option>
                ))}
              </select>
            </div>

            {isCallConnected && (
              <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-background border border-border shadow-xs text-xs font-mono font-medium">
                <Clock className="size-3.5 text-muted-foreground" />
                <span>{formatDuration(callDuration)}</span>
              </div>
            )}

            {activeConversationId ? (
              <Button
                variant="outline"
                size="sm"
                asChild
                className="h-8 gap-1.5 text-xs text-muted-foreground hover:text-foreground"
              >
                {user?.role === "expert" ? (
                  <Link to="/expert/chat/$id" params={{ id: activeConversationId }}>
                    <ArrowLeft className="size-3.5" />
                    <span>Expert Console</span>
                  </Link>
                ) : (
                  <Link to="/chat/$id" params={{ id: activeConversationId }}>
                    <MessageSquare className="size-3.5" />
                    <span>Open Chat</span>
                  </Link>
                )}
              </Button>
            ) : user?.role === "expert" ? (
              <Button
                variant="outline"
                size="sm"
                asChild
                className="h-8 gap-1.5 text-xs text-muted-foreground hover:text-foreground"
              >
                <Link to="/expert/queue">
                  <ArrowLeft className="size-3.5" />
                  <span>Case Queue</span>
                </Link>
              </Button>
            ) : null}
          </div>
        </div>

        {/* ══════════════════════════════════════════════════════════════
            1. IDLE / PRE-CALL VIEW (Direct Entry Screen)
            ══════════════════════════════════════════════════════════════ */}
        {callState === "idle" && (
          <div className="my-auto py-10 flex flex-col items-center text-center max-w-2xl mx-auto">
            <div className="relative mb-6">
              <div className="size-32 rounded-full bg-primary/10 border-2 border-primary/30 flex items-center justify-center shadow-xl shadow-primary/10 animate-in zoom-in-95 duration-500">
                <PhoneCall className="size-14 text-primary" />
              </div>
              <span className="absolute bottom-1 right-1 size-5 rounded-full bg-emerald-500 border-2 border-background animate-pulse" />
            </div>

            <h2 className="text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
              Talk directly with ResolveAI
            </h2>
            <p className="text-sm text-muted-foreground mt-2.5 max-w-lg leading-relaxed">
              No need to type. Full agentic support: search knowledge, execute verified tools (order status, refunds, updates), or escalate to human experts in real time.
            </p>

            <div className="flex flex-wrap items-center justify-center gap-2 mt-4 text-xs text-muted-foreground">
              <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-muted border border-border">
                <ShieldCheck className="size-3.5 text-emerald-500" />
                Autonomous RAG & Tools
              </span>
              <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-muted border border-border">
                <Sparkles className="size-3.5 text-primary" />
                Multilingual AI Intelligence
              </span>
              <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-muted border border-border">
                <Radio className="size-3.5 text-blue-500" />
                Live Barge-in Interruption
              </span>
            </div>

            <div className="mt-8 flex flex-col items-center gap-4 w-full">
              <Button
                size="lg"
                onClick={() => startCall()}
                className="h-14 px-8 rounded-full text-base font-semibold gap-3 shadow-lg hover:shadow-xl hover:scale-105 transition-all bg-primary text-primary-foreground"
              >
                <Phone className="size-5" />
                <span>Start Voice Call Now</span>
              </Button>
              <p className="text-[11px] text-muted-foreground">
                Your browser will request microphone permission to connect the call.
              </p>
            </div>

            {/* Quick Open Tickets to Continue via Voice */}
            {recentConversations.length > 0 && (
              <div className="w-full mt-10 text-left border-t border-border pt-6">
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">
                  Or call about an ongoing ticket:
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {recentConversations.map((c) => (
                    <button
                      key={c.id}
                      type="button"
                      onClick={() => startCall(String(c.id))}
                      className="p-3.5 rounded-xl border border-border bg-card hover:bg-accent/40 text-left transition-all flex items-center justify-between group cursor-pointer"
                    >
                      <div className="min-w-0 pr-2">
                        <span className="text-[11px] font-mono text-primary font-medium">
                          Ticket #{c.id}
                        </span>
                        <p className="text-xs font-medium text-foreground truncate mt-0.5">
                          {c.subject || `Conversation #${c.id}`}
                        </p>
                      </div>
                      <span className="size-8 rounded-full bg-primary/10 text-primary flex items-center justify-center shrink-0 group-hover:bg-primary group-hover:text-primary-foreground transition-colors">
                        <Phone className="size-3.5" />
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ══════════════════════════════════════════════════════════════
            2. CONNECTING / INITIALIZING VIEW
            ══════════════════════════════════════════════════════════════ */}
        {(callState === "initializing" || callState === "connecting") && (
          <div className="my-auto py-16 flex flex-col items-center text-center">
            <div className="relative size-32 rounded-full bg-primary/10 border-2 border-primary/30 flex items-center justify-center mb-6">
              <Loader2 className="size-12 text-primary animate-spin" />
              <div className="absolute inset-0 rounded-full border-2 border-primary/40 animate-ping" />
            </div>

            <h3 className="text-xl font-semibold text-foreground">
              Connecting to agent…
            </h3>
            <p className="text-xs text-muted-foreground mt-2 max-w-sm">
              Connecting you with ResolveAI voice agent. Please hold on a moment…
            </p>

            <Button
              variant="outline"
              size="sm"
              onClick={handleEndCall}
              className="mt-6 rounded-full text-xs"
            >
              Cancel Call
            </Button>
          </div>
        )}

        {/* ══════════════════════════════════════════════════════════════
            3. ACTIVE IN-CALL VIEW (Dedicated Full Voice Experience)
            ══════════════════════════════════════════════════════════════ */}
        {isCallConnected && (
          <div className="flex-1 my-6 flex flex-col lg:flex-row items-center justify-center gap-8 relative">
            {/* Main Stage: Animated Voice Orb & Live Dialogue */}
            <div className="flex-1 flex flex-col items-center justify-center text-center max-w-xl w-full">
              {/* Badges Bar: Workflow Status, Emotion Awareness, Measured Latency, Detected Language */}
              <div className="flex flex-wrap items-center justify-center gap-2 mb-4">
                {/* Agentic Workflow Status Pill */}
                <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-card border border-border shadow-xs text-xs font-medium">
                  <span
                    className={`size-2 rounded-full ${
                      isMuted
                        ? "bg-amber-500"
                        : callState === "speaking"
                          ? "bg-primary animate-pulse"
                          : callState === "thinking" || callState === "transcribing"
                            ? "bg-amber-500 animate-spin"
                            : callState === "finalizing"
                              ? "bg-amber-500 animate-pulse"
                              : callState === "reconnecting"
                                ? "bg-amber-500 animate-pulse"
                                : "bg-emerald-500 animate-pulse"
                    }`}
                  />
                  <span className="text-foreground">
                    {isMuted
                      ? "Microphone Muted"
                      : callState === "reconnecting"
                        ? "Reconnecting Audio..."
                        : callState === "speaking"
                          ? "ResolveAI Speaking…"
                          : callState === "thinking"
                            ? "ResolveAI Thinking…"
                            : callState === "transcribing"
                              ? "Transcribing speech…"
                              : callState === "finalizing"
                                ? "Finalizing speech…"
                                : getFriendlyWorkflowState(workflowState)}
                  </span>
                </div>

                {/* Emotion Awareness Pill */}
                {detectedEmotion && (
                  <div
                    data-testid="emotion-badge"
                    className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border ${
                      detectedEmotion === "frustrated"
                        ? "bg-rose-500/10 border-rose-500/30 text-rose-600 dark:text-rose-400"
                        : detectedEmotion === "urgent"
                          ? "bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400"
                          : detectedEmotion === "confused"
                            ? "bg-purple-500/10 border-purple-500/30 text-purple-600 dark:text-purple-400"
                            : detectedEmotion === "satisfied"
                              ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400"
                              : "bg-card border-border text-foreground"
                    }`}
                  >
                    <span className="capitalize">{detectedEmotion}</span>
                    {emotionConfidence ? (
                      <span className="opacity-70 text-[10px]">
                        ({Math.round(emotionConfidence * 100)}%)
                      </span>
                    ) : null}
                  </div>
                )}

                {/* Measured Latency Pill */}
                {turnLatencyMs !== null && (
                  <div
                    data-testid="latency-badge"
                    className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-full bg-card border border-border text-[11px] font-mono text-muted-foreground shadow-xs"
                  >
                    <Clock className="size-3 text-primary" />
                    <span>{turnLatencyMs}ms</span>
                  </div>
                )}

                {/* Neural TTS Dev Readout */}
                {neuralTTS.ttsProvider !== "pending" && (
                  <div
                    data-testid="tts-provider-badge"
                    className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-full text-[11px] font-mono shadow-xs border ${
                      neuralTTS.ttsProvider === "sarvam"
                        ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400"
                        : "bg-muted border-border text-muted-foreground"
                    }`}
                  >
                    <Sparkles className="size-3" />
                    <span>TTS: {neuralTTS.ttsProvider}</span>
                    {neuralTTS.ttsLatencyMs !== null && (
                      <span className="opacity-70">({neuralTTS.ttsLatencyMs}ms)</span>
                    )}
                  </div>
                )}

                {/* Language / Code-Mix Pill */}
                {detectedLanguage && detectedLanguage !== "en-IN" && (
                  <div
                    data-testid="language-badge"
                    className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-full bg-primary/10 border border-primary/20 text-[11px] font-medium text-primary shadow-xs"
                  >
                    <Globe className="size-3" />
                    <span>{detectedLanguage}</span>
                  </div>
                )}
              </div>


              {/* Active Agentic Tool Execution Pill */}
              {activeToolActivity && (
                <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary/10 border border-primary/20 text-xs text-primary font-medium mb-4 animate-in fade-in">
                  <Wrench className="size-3.5 animate-spin" />
                  <span>
                    Executing tool:{" "}
                    <strong className="capitalize">
                      {(activeToolActivity.tool_name || "action").replace(/_/g, " ")}
                    </strong>
                  </span>
                </div>
              )}

              {/* Central Glowing Acoustic Visualizer */}
              <div className="relative size-48 sm:size-56 flex items-center justify-center mb-6">
                {/* Outermost ambient glow aura */}
                <div
                  className={`absolute inset-0 rounded-full blur-3xl opacity-30 transition-all duration-700 pointer-events-none ${
                    isAgentSpeaking
                      ? "bg-primary scale-125"
                      : isMuted
                        ? "bg-amber-500 scale-90"
                        : isWithExpert
                          ? "bg-blue-500 scale-110"
                          : "bg-emerald-500 scale-100"
                  }`}
                />

                {/* Animated Concentric Wave Rings */}
                <div
                  className={`absolute inset-4 rounded-full border border-primary/20 transition-all duration-500 ${
                    isAgentSpeaking ? "animate-ping scale-110 opacity-40" : "scale-100 opacity-20"
                  }`}
                />
                <div
                  className={`absolute inset-8 rounded-full border border-primary/30 transition-all duration-300 ${
                    isAgentSpeaking ? "scale-105 opacity-60" : "scale-100 opacity-30"
                  }`}
                />

                {/* Center Core Avatar */}
                <div
                  className={`relative size-28 sm:size-32 rounded-full flex flex-col items-center justify-center border-2 transition-all duration-300 shadow-xl ${
                    isAgentSpeaking
                      ? "bg-primary/20 border-primary text-primary shadow-primary/30 scale-105"
                      : isProcessingTurn
                        ? "bg-amber-500/10 border-amber-500/40 text-amber-500 animate-pulse"
                        : isMuted
                          ? "bg-muted border-amber-500/30 text-muted-foreground"
                          : isWithExpert
                            ? "bg-blue-500/10 border-blue-500 text-blue-600"
                            : "bg-card border-border text-foreground shadow-sm"
                  }`}
                >
                  {isProcessingTurn ? (
                    <Loader2 className="size-12 animate-spin text-amber-500" />
                  ) : isWithExpert ? (
                    <UserRound className="size-12 text-blue-600 animate-pulse" />
                  ) : (
                    <Bot
                      className={`size-12 transition-transform duration-300 ${
                        isAgentSpeaking ? "scale-110 text-primary" : "text-foreground"
                      }`}
                    />
                  )}

                  <span className="text-[10px] font-semibold tracking-wider uppercase mt-1">
                    {isAgentSpeaking
                      ? "Speaking"
                      : isMuted
                        ? "Muted"
                        : isWithExpert
                          ? "Expert"
                          : "Active"}
                  </span>
                </div>
              </div>

              {/* Dynamic Sound Wave Bars Animation */}
              <div className="flex items-center gap-1.5 h-8 mb-6">
                {[40, 70, 100, 60, 90, 50, 80].map((height, i) => (
                  <span
                    key={i}
                    className={`w-1 rounded-full transition-all duration-150 ${
                      isAgentSpeaking
                        ? "bg-primary animate-pulse"
                        : isMuted
                          ? "bg-muted-foreground/30 h-2"
                          : isWithExpert
                            ? "bg-blue-500"
                            : "bg-emerald-500/60"
                    }`}
                    style={{
                      height: isAgentSpeaking
                        ? `${Math.max(12, (height * (i % 2 === 0 ? 0.9 : 1.2)) % 32)}px`
                        : "6px",
                    }}
                  />
                ))}
              </div>

              {/* Real-time Customer & Agent Live Speech Feedback */}
              <div className="w-full max-w-md space-y-2 min-h-[72px]">
                {currentCustomerTranscript && (
                  <div className="p-3 rounded-xl bg-background border border-border text-xs text-foreground flex items-start gap-2 shadow-xs text-left animate-in fade-in slide-in-from-bottom-1">
                    <User className="size-3.5 text-primary shrink-0 mt-0.5" />
                    <div>
                      <span className="font-semibold text-[11px] text-muted-foreground flex items-center gap-1.5">
                        <span>You're saying:</span>
                        <span className="inline-flex items-center gap-1 text-[10px] text-amber-500 font-medium animate-pulse">
                          <span className="size-1.5 rounded-full bg-amber-500" />
                          Live
                        </span>
                      </span>
                      <p className="italic font-medium">"{currentCustomerTranscript}"</p>
                    </div>
                  </div>
                )}

                {lastAgentReply && isAgentSpeaking && (
                  <div className="p-3 rounded-xl bg-primary/10 border border-primary/20 text-xs text-primary flex items-start gap-2 text-left animate-in fade-in slide-in-from-bottom-1">
                    <Bot className="size-3.5 shrink-0 mt-0.5" />
                    <div>
                      <span className="font-semibold text-[11px] text-primary/80 block">
                        ResolveAI Agent:
                      </span>
                      <p className="leading-relaxed">"{lastAgentReply}"</p>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Collapsible / Slide-Out Real-Time Transcript Drawer */}
            {showTranscriptDrawer && (
              <div className="w-full lg:w-96 rounded-2xl bg-card border border-border shadow-md flex flex-col h-[420px] animate-in fade-in slide-in-from-right-2">
                <div className="p-3.5 border-b border-border flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <FileText className="size-4 text-primary" />
                    <span className="text-xs font-semibold text-foreground">
                      Live Call Transcript ({transcriptLog.length + (currentCustomerTranscript || remoteProvisionalTurn ? 1 : 0)})
                    </span>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={handleCopyTranscript}
                    className="size-7"
                    title="Copy transcript"
                  >
                    {copiedTranscript ? (
                      <Check className="size-3.5 text-emerald-500" />
                    ) : (
                      <Copy className="size-3.5" />
                    )}
                  </Button>
                </div>

                <div className="flex-1 p-3 overflow-y-auto space-y-3 text-xs">
                  {(() => {
                    const allTurns: TranscriptTurn[] = [...transcriptLog];
                    if (remoteProvisionalTurn) {
                      allTurns.push(remoteProvisionalTurn);
                    } else if (currentCustomerTranscript && isCallActiveRef.current) {
                      allTurns.push({
                        id: "local_provisional",
                        sender: user?.role === "expert" ? "expert" : "customer",
                        text: currentCustomerTranscript,
                        timestamp: "Speaking now…",
                        isProvisional: true,
                      });
                    }

                    if (allTurns.length === 0) {
                      return (
                        <div className="h-full flex flex-col items-center justify-center text-center text-muted-foreground p-4">
                          <Mic className="size-6 mb-2 opacity-40" />
                          <p>Start speaking to see real-time transcription here.</p>
                        </div>
                      );
                    }

                    return allTurns.map((turn) => (
                      <div
                        key={turn.id}
                        className={`p-2.5 rounded-xl text-left transition-all ${
                          turn.isProvisional
                            ? "bg-amber-500/10 border border-dashed border-amber-500/40"
                            : turn.sender === "customer"
                              ? "bg-muted/70 border border-border"
                              : turn.sender === "expert"
                                ? "bg-blue-500/10 border border-blue-500/20"
                                : "bg-primary/10 border border-primary/20"
                        }`}
                      >
                        <div className="flex items-center justify-between text-[10px] text-muted-foreground mb-1">
                          <span className="font-semibold uppercase tracking-wider flex items-center gap-1.5">
                            {turn.sender === "customer"
                              ? user?.full_name || "You"
                              : turn.sender === "expert"
                                ? "Support Expert"
                                : "ResolveAI"}
                            {turn.isProvisional && (
                              <span className="inline-flex items-center gap-1 text-[10px] text-amber-600 dark:text-amber-400 font-medium normal-case animate-pulse">
                                <span className="size-1.5 rounded-full bg-amber-500" />
                                Speaking…
                              </span>
                            )}
                          </span>
                          <span>{turn.timestamp}</span>
                        </div>
                        <p className={`text-foreground leading-relaxed ${turn.isProvisional ? "italic text-foreground/90" : ""}`}>
                          {turn.text}
                        </p>
                      </div>
                    ));
                  })()}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ══════════════════════════════════════════════════════════════
            4. CALL CONTROLS DOCK (When In-Call)
            ══════════════════════════════════════════════════════════════ */}
        {isCallConnected && (
          <div className="py-4 border-t border-border flex items-center justify-center gap-4">
            {/* Mic Toggle */}
            <Button
              type="button"
              variant="outline"
              size="icon"
              onClick={toggleMute}
              className={`size-12 rounded-full border transition-all ${
                isMuted
                  ? "bg-amber-500/15 border-amber-500/40 text-amber-600 hover:bg-amber-500/25"
                  : "hover:bg-muted"
              }`}
              title={isMuted ? "Unmute microphone" : "Mute microphone"}
              aria-label={isMuted ? "Unmute microphone" : "Mute microphone"}
            >
              {isMuted ? <MicOff className="size-5" /> : <Mic className="size-5" />}
            </Button>

            {/* Speaker Toggle */}
            <Button
              type="button"
              variant="outline"
              size="icon"
              onClick={toggleSpeaker}
              className={`size-12 rounded-full border transition-all ${
                isSpeakerMuted
                  ? "bg-amber-500/15 border-amber-500/40 text-amber-600 hover:bg-amber-500/25"
                  : "hover:bg-muted"
              }`}
              title={isSpeakerMuted ? "Unmute agent voice" : "Mute agent voice"}
              aria-label={isSpeakerMuted ? "Unmute agent voice" : "Mute agent voice"}
            >
              {isSpeakerMuted ? <VolumeX className="size-5" /> : <Volume2 className="size-5" />}
            </Button>

            {/* Transcript Drawer Toggle */}
            <Button
              type="button"
              variant="outline"
              size="icon"
              onClick={() => setShowTranscriptDrawer((prev) => !prev)}
              className={`size-12 rounded-full border transition-all ${
                showTranscriptDrawer
                  ? "bg-primary text-primary-foreground border-primary"
                  : "hover:bg-muted"
              }`}
              title="Toggle Live Transcript"
              aria-label="Toggle Live Transcript"
            >
              <FileText className="size-5" />
            </Button>

            {/* End Call Button */}
            <Button
              type="button"
              variant="destructive"
              onClick={handleEndCall}
              className="h-12 px-7 rounded-full font-semibold gap-2 shadow-md hover:shadow-lg transition-all"
            >
              <PhoneOff className="size-4" />
              <span>End Call</span>
            </Button>
          </div>
        )}

        {/* ══════════════════════════════════════════════════════════════
            5. POST-CALL SUMMARY VIEW & RESOLUTION FEEDBACK
            ══════════════════════════════════════════════════════════════ */}
        {callState === "ended" && (
          <div className="my-auto py-8 flex flex-col items-center text-center max-w-lg mx-auto animate-in zoom-in-95 duration-300">
            <span className="size-16 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-600 flex items-center justify-center mb-4">
              <CheckCircle2 className="size-8" />
            </span>

            <h3 className="text-xl font-bold text-foreground">Voice Call Completed</h3>
            <p className="text-xs text-muted-foreground mt-1.5">
              Thank you for calling ResolveAI. Your session transcript and updates have been saved.
            </p>

            <div className="w-full my-5 p-4 rounded-2xl bg-card border border-border shadow-xs space-y-2 text-xs text-left">
              <div className="flex justify-between py-1 border-b border-border/60">
                <span className="text-muted-foreground">Call Duration</span>
                <span className="font-semibold font-mono text-foreground">
                  {formatDuration(callDuration)}
                </span>
              </div>
              <div className="flex justify-between py-1 border-b border-border/60">
                <span className="text-muted-foreground">Turns Exchanged</span>
                <span className="font-semibold text-foreground">
                  {transcriptLog.length} turns
                </span>
              </div>
              {activeConversationId && (
                <div className="flex justify-between py-1">
                  <span className="text-muted-foreground">Associated Ticket</span>
                  <span className="font-semibold text-primary">
                    Ticket #{activeConversationId}
                  </span>
                </div>
              )}
            </div>

            {/* Resolution Customer Feedback Rating (Only shown to customers) */}
            {activeConversationId && user?.role !== "expert" && (
              <div className="w-full p-4 mb-6 rounded-2xl bg-card border border-border shadow-xs text-left">
                <h4 className="text-xs font-semibold text-foreground mb-1">
                  How was your call experience?
                </h4>
                <p className="text-[11px] text-muted-foreground mb-3">
                  Your feedback helps us train and improve our voice models.
                </p>

                {feedbackSubmitted ? (
                  <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-600 text-xs flex items-center gap-2">
                    <CheckCircle2 className="size-4 shrink-0" />
                    <span>Feedback submitted. Thank you for helping us improve!</span>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <div className="flex items-center gap-1.5">
                      {[1, 2, 3, 4, 5].map((star) => (
                        <button
                          key={star}
                          type="button"
                          onClick={() => setRating(star)}
                          className={`size-8 rounded-lg flex items-center justify-center transition-all ${
                            rating >= star
                              ? "text-amber-500 bg-amber-500/10"
                              : "text-muted-foreground hover:bg-muted"
                          }`}
                        >
                          <Star
                            className={`size-4 ${rating >= star ? "fill-amber-500" : ""}`}
                          />
                        </button>
                      ))}
                    </div>

                    <Textarea
                      placeholder="Add any comments on voice clarity, accuracy, or speed… (optional)"
                      value={feedbackComment}
                      onChange={(e) => setFeedbackComment(e.target.value)}
                      rows={2}
                      className="text-xs"
                    />

                    <Button
                      size="sm"
                      onClick={submitFeedback}
                      disabled={rating === 0 || isSubmittingFeedback}
                      className="w-full h-8 text-xs rounded-lg"
                    >
                      {isSubmittingFeedback ? (
                        <>
                          <Loader2 className="size-3 animate-spin mr-1.5" />
                          Submitting…
                        </>
                      ) : (
                        "Submit Feedback"
                      )}
                    </Button>
                  </div>
                )}
              </div>
            )}

            <div className="flex flex-col sm:flex-row gap-3 w-full">
              {user?.role === "expert" ? (
                <>
                  {activeConversationId ? (
                    <Button asChild className="flex-1 gap-2 rounded-full">
                      <Link to="/expert/chat/$id" params={{ id: activeConversationId }}>
                        <ArrowLeft className="size-3.5" />
                        <span>Return to Expert Console</span>
                      </Link>
                    </Button>
                  ) : null}
                  <Button variant="outline" asChild className="flex-1 gap-2 rounded-full">
                    <Link to="/expert/queue">
                      <span>Back to Queue</span>
                    </Link>
                  </Button>
                </>
              ) : (
                <>
                  <Button
                    variant="outline"
                    onClick={() => {
                      setCallState("idle");
                      setActiveConversationId(null);
                      setFeedbackSubmitted(false);
                      setRating(0);
                      setFeedbackComment("");
                    }}
                    className="flex-1 gap-2 rounded-full"
                  >
                    <RotateCcw className="size-3.5" />
                    <span>Start New Call</span>
                  </Button>

                  {activeConversationId ? (
                    <Button asChild className="flex-1 gap-2 rounded-full">
                      <Link to="/chat/$id" params={{ id: activeConversationId }}>
                        <MessageSquare className="size-3.5" />
                        <span>View in Chat</span>
                      </Link>
                    </Button>
                  ) : (
                    <Button asChild className="flex-1 gap-2 rounded-full">
                      <Link to="/dashboard">
                        <span>Back to Dashboard</span>
                      </Link>
                    </Button>
                  )}
                </>
              )}
            </div>
          </div>
        )}

        {/* ══════════════════════════════════════════════════════════════
            6. ERROR VIEW
            ══════════════════════════════════════════════════════════════ */}
        {callState === "error" && (
          <div className="my-auto py-10 flex flex-col items-center text-center max-w-md mx-auto">
            <span className="size-16 rounded-full bg-destructive/10 border border-destructive/20 text-destructive flex items-center justify-center mb-4">
              <AlertCircle className="size-8" />
            </span>

            <h3 className="text-xl font-bold text-foreground">Voice Connection Error</h3>
            <p className="text-xs text-muted-foreground mt-2 leading-relaxed">
              {errorMessage || "Unable to establish live audio session with the LiveKit voice server."}
            </p>

            <div className="flex gap-3 mt-6">
              <Button
                variant="outline"
                onClick={() => setCallState("idle")}
                className="rounded-full text-xs"
              >
                Back to Voice Hub
              </Button>
              <Button
                onClick={() => startCall()}
                className="rounded-full text-xs gap-1.5"
              >
                <RotateCcw className="size-3.5" />
                Retry Call
              </Button>
            </div>
          </div>
        )}

        {/* ══════════════════════════════════════════════════════════════
            7. ACTION AUTHORIZATION CONFIRMATION MODAL (Parity with Chatbot)
            ══════════════════════════════════════════════════════════════ */}
        {pendingConfirmation && (
          <ConfirmationModal
            toolName={pendingConfirmation.toolName}
            onAccept={() => handleToolConfirm("accept")}
            onReject={() => handleToolConfirm("reject")}
            isConfirming={isConfirmingTool}
          />
        )}
      </div>
    </Workspace>
  );
}
