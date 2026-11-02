import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { VoiceCallPage } from "@/components/resolve/VoiceCallPage";
import { CallWithAgent } from "@/components/resolve/CallWithAgent";

// Mock auth
vi.mock("@/lib/auth", () => ({
  useAuth: () => ({
    user: { id: 1, role: "customer", full_name: "Jane Doe", email: "jane@example.com" },
    isLoading: false,
    logout: vi.fn(),
  }),
}));

// Mock WebSocket
const mockSubscribe = vi.fn((event: string, cb: any) => {
  return vi.fn();
});

vi.mock("@/lib/ws", () => ({
  useWebSocket: () => ({
    isConnected: true,
    subscribe: mockSubscribe,
    sendTyping: vi.fn(),
    sendVoiceCommand: vi.fn(),
    sendVoiceChunk: vi.fn(),
  }),
}));

// Mock API
const mockApiPost = vi.fn();
const mockApiGet = vi.fn().mockImplementation((url: string) => {
  if (url === "/conversations") {
    return Promise.resolve({
      data: [{ id: 42, status: "active", subject: "Order Delivery Question" }],
    });
  }
  return Promise.resolve({ data: {} });
});

vi.mock("@/lib/api", () => ({
  api: {
    get: (url: string) => mockApiGet(url),
    post: (url: string, data?: any, config?: any) => mockApiPost(url, data, config),
  },
}));

// Mock TanStack Router
vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => vi.fn(),
  Link: ({ children, to, params, ...props }: any) => (
    <a href={to} data-params={JSON.stringify(params)} {...props}>
      {children}
    </a>
  ),
}));

// Global mocks for SpeechRecognition and speechSynthesis
let mockRecognitionInstances: any[] = [];
class MockSpeechRecognition {
  continuous = true;
  interimResults = true;
  lang = "en-IN";
  onresult: ((event: any) => void) | null = null;
  onend: (() => void) | null = null;
  onerror: ((event: any) => void) | null = null;

  start = vi.fn();
  abort = vi.fn();
  stop = vi.fn();

  constructor() {
    mockRecognitionInstances.push(this);
  }
}

const mockCancelSpeech = vi.fn();
const mockSpeakSpeech = vi.fn((utterance: any) => {
  // Simulate async start & end
  setTimeout(() => {
    if (utterance.onstart) utterance.onstart();
    setTimeout(() => {
      if (utterance.onend) utterance.onend();
    }, 50);
  }, 10);
});

// Mock LiveKit
let mockRoomInstances: any[] = [];
let mockRoomEventHandlers: Record<string, Function[]> = {};

vi.mock("livekit-client", () => {
  class MockRoom {
    on = vi.fn((event: string, cb: Function) => {
      if (!mockRoomEventHandlers[event]) mockRoomEventHandlers[event] = [];
      mockRoomEventHandlers[event].push(cb);
    });
    connect = vi.fn().mockResolvedValue(undefined);
    disconnect = vi.fn();
    localParticipant = {
      setMicrophoneEnabled: vi.fn().mockResolvedValue(undefined),
    };

    constructor() {
      mockRoomInstances.push(this);
    }
  }

  return {
    Room: MockRoom,
    RoomEvent: {
      TrackSubscribed: "trackSubscribed",
      TrackUnsubscribed: "trackUnsubscribed",
      ActiveSpeakersChanged: "activeSpeakersChanged",
      Reconnecting: "reconnecting",
      Reconnected: "reconnected",
      Disconnected: "disconnected",
    },
    Track: {
      Kind: {
        Audio: "audio",
      },
    },
  };
});

describe("Multi-Turn Spoken Conversation Regression Suite", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockRecognitionInstances = [];
    mockRoomInstances = [];
    mockRoomEventHandlers = {};

    (window as any).SpeechRecognition = MockSpeechRecognition;
    (window as any).webkitSpeechRecognition = MockSpeechRecognition;

    window.speechSynthesis = {
      cancel: mockCancelSpeech,
      speak: vi.fn((utterance: any) => {
        // Auto-fire lifecycle callbacks so neural TTS browser fallback completes
        if (utterance.onstart) setTimeout(() => utterance.onstart(), 0);
        if (utterance.onend) setTimeout(() => utterance.onend(), 5);
      }),
      getVoices: vi.fn(() => []),
      paused: false,
      pending: false,
      speaking: false,
      onvoiceschanged: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
      pause: vi.fn(),
      resume: vi.fn(),
    } as any;

    (window as any).SpeechSynthesisUtterance = class {
      text: string;
      rate = 1.0;
      pitch = 1.0;
      voice = null;
      onstart: (() => void) | null = null;
      onend: (() => void) | null = null;
      onerror: (() => void) | null = null;
      constructor(text: string) {
        this.text = text;
      }
    };
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("1. handles five consecutive spoken turns in one connected call without tearing down room", async () => {
    mockApiPost.mockImplementation((url: string, data: any) => {
      if (url === "/audio/livekit/token") {
        return Promise.resolve({
          data: {
            server_url: "wss://test.livekit.cloud",
            token: "mock-livekit-token",
            room_name: "resolveai-convo-42",
          },
        });
      }
      if (url === "/audio/livekit/utterance") {
        return Promise.resolve({
          data: {
            status: "processed",
            ai_response: `AI response to: ${data.transcript}`,
            workflow_state: "asking_user",
          },
        });
      }
      return Promise.resolve({ data: {} });
    });

    render(<VoiceCallPage initialConversationId="42" autoStart={true} />);

    // Wait until connected and recognition initialized
    await waitFor(() => {
      expect(mockRoomInstances.length).toBe(1);
      expect(mockRecognitionInstances.length).toBe(1);
    });

    const room = mockRoomInstances[0];
    const recognition = mockRecognitionInstances[0];
    expect(room.connect).toHaveBeenCalled();
    expect(recognition.start).toHaveBeenCalled();

    const turns = [
      "Hello, I need help with order 123",
      "When will it be delivered?",
      "Can I change the delivery address?",
      "Does it require a signature?",
      "Thank you, that resolves my issue.",
    ];

    // Execute 5 consecutive turns
    for (let i = 0; i < turns.length; i++) {
      const turnText = turns[i];
      await act(async () => {
        recognition.onresult({
          resultIndex: 0,
          results: [
            Object.assign([{ transcript: turnText }], { isFinal: true }),
          ],
        });
      });

      await waitFor(() => {
        expect(mockApiPost).toHaveBeenCalledWith(
          "/audio/livekit/utterance",
          expect.objectContaining({
            conversation_id: 42,
            transcript: turnText,
          }),
          expect.anything()
        );
      });
    }

    // Crucial check: Room was NOT disconnected between turns!
    expect(room.disconnect).not.toHaveBeenCalled();
    // Recognition was NOT aborted between turns
    expect(recognition.abort).not.toHaveBeenCalled();
  }, 15000);

  it("2. preserves conversation history and displays follow-up turns in transcript log", async () => {
    mockApiPost.mockImplementation((url: string, data: any) => {
      if (url === "/audio/livekit/token") {
        return Promise.resolve({
          data: { server_url: "wss://test.livekit.cloud", token: "tok", room_name: "room-42" },
        });
      }
      if (url === "/audio/livekit/utterance") {
        return Promise.resolve({
          data: {
            status: "processed",
            ai_response: `Reply to: ${data.transcript}`,
          },
        });
      }
      return Promise.resolve({ data: {} });
    });

    render(<VoiceCallPage initialConversationId="42" autoStart={true} />);

    await waitFor(() => {
      expect(mockRecognitionInstances.length).toBe(1);
    });
    const recognition = mockRecognitionInstances[0];

    // Turn 1
    await act(async () => {
      recognition.onresult({
        resultIndex: 0,
        results: [Object.assign([{ transcript: "My card was charged twice" }], { isFinal: true })],
      });
    });

    await waitFor(() => {
      expect(mockApiPost).toHaveBeenCalledWith(
        "/audio/livekit/utterance",
        expect.objectContaining({ transcript: "My card was charged twice" }),
        expect.anything()
      );
    });

    // Turn 2 (Follow-up)
    await act(async () => {
      recognition.onresult({
        resultIndex: 0,
        results: [Object.assign([{ transcript: "Can I get an automatic refund?" }], { isFinal: true })],
      });
    });

    await waitFor(() => {
      expect(mockApiPost).toHaveBeenCalledWith(
        "/audio/livekit/utterance",
        expect.objectContaining({ transcript: "Can I get an automatic refund?" }),
        expect.anything()
      );
    });

    // Open live transcript drawer
    const transcriptBtn = await screen.findByRole("button", { name: /toggle live transcript/i });
    fireEvent.click(transcriptBtn);

    await waitFor(() => {
      const customerTurns = screen.getAllByText(/my card was charged twice/i);
      expect(customerTurns.length).toBeGreaterThanOrEqual(1);

      const followUpTurns = screen.getAllByText(/can i get an automatic refund/i);
      expect(followUpTurns.length).toBeGreaterThanOrEqual(1);
    });
  });

  it("3. barge-in: speaking while AI is speaking cancels speech synthesis immediately", async () => {
    mockApiPost.mockResolvedValue({
      data: { server_url: "wss://test.livekit.cloud", token: "tok", room_name: "room-42" },
    });

    render(<VoiceCallPage initialConversationId="42" autoStart={true} />);

    await waitFor(() => {
      expect(mockRecognitionInstances.length).toBe(1);
    });
    const recognition = mockRecognitionInstances[0];

    // Trigger AI speech
    act(() => {
      // simulate agent speaking
      const utterance = new (window as any).SpeechSynthesisUtterance("I am resolving your request now.");
      window.speechSynthesis.speak(utterance);
    });

    // Customer barges in with interruption
    act(() => {
      recognition.onresult({
        resultIndex: 0,
        results: [Object.assign([{ transcript: "Wait, cancel that!" }], { isFinal: false })],
      });
    });

    // Speech synthesis cancel must have been called immediately
    expect(mockCancelSpeech).toHaveBeenCalled();
  });

  it("4. mute and unmute toggles microphone without breaking continuous recognition", async () => {
    mockApiPost.mockResolvedValue({
      data: { server_url: "wss://test.livekit.cloud", token: "tok", room_name: "room-42" },
    });

    render(<VoiceCallPage initialConversationId="42" autoStart={true} />);

    await waitFor(() => {
      expect(mockRoomInstances.length).toBe(1);
      expect(mockRecognitionInstances.length).toBe(1);
    });

    const room = mockRoomInstances[0];
    const recognition = mockRecognitionInstances[0];

    const muteBtn = await screen.findByRole("button", { name: /mute microphone/i });
    fireEvent.click(muteBtn);

    // Microphone should be muted in LiveKit participant and recognition aborted
    await waitFor(() => {
      expect(room.localParticipant.setMicrophoneEnabled).toHaveBeenCalledWith(false);
      expect(recognition.abort).toHaveBeenCalled();
    });

    // Unmute
    const unmuteBtn = screen.getByRole("button", { name: /unmute microphone/i });
    fireEvent.click(unmuteBtn);

    await waitFor(() => {
      expect(room.localParticipant.setMicrophoneEnabled).toHaveBeenCalledWith(true);
      expect(recognition.start).toHaveBeenCalled();
    });
  });

  it("5. handles STT error and LLM 500 error gracefully without ending the call", async () => {
    mockApiPost.mockImplementation((url: string) => {
      if (url === "/audio/livekit/token") {
        return Promise.resolve({
          data: { server_url: "wss://test.livekit.cloud", token: "tok", room_name: "room-42" },
        });
      }
      if (url === "/audio/livekit/utterance") {
        return Promise.reject(new Error("LLM failure 500"));
      }
      return Promise.resolve({ data: {} });
    });

    render(<VoiceCallPage initialConversationId="42" autoStart={true} />);

    await waitFor(() => {
      expect(mockRecognitionInstances.length).toBe(1);
    });
    const recognition = mockRecognitionInstances[0];

    // Trigger STT warning (e.g. no-speech)
    act(() => {
      recognition.onerror({ error: "no-speech" });
    });

    // Call should stay connected
    expect(screen.getByRole("button", { name: /end call/i })).toBeInTheDocument();

    // Trigger turn that causes LLM failure
    await act(async () => {
      recognition.onresult({
        resultIndex: 0,
        results: [Object.assign([{ transcript: "Cause an error" }], { isFinal: true })],
      });
    });

    // Call should remain alive and not crash
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /end call/i })).toBeInTheDocument();
    });
  });

  it("6. rejects rapid duplicate utterances without sending second request", async () => {
    mockApiPost.mockImplementation((url: string) => {
      if (url === "/audio/livekit/token") {
        return Promise.resolve({
          data: { server_url: "wss://test.livekit.cloud", token: "tok", room_name: "room-42" },
        });
      }
      if (url === "/audio/livekit/utterance") {
        return Promise.resolve({
          data: { status: "processed", ai_response: "Response" },
        });
      }
      return Promise.resolve({ data: {} });
    });

    render(<VoiceCallPage initialConversationId="42" autoStart={true} />);

    await waitFor(() => {
      expect(mockRecognitionInstances.length).toBe(1);
    });
    const recognition = mockRecognitionInstances[0];

    // Fire identical utterance twice
    await act(async () => {
      recognition.onresult({
        resultIndex: 0,
        results: [Object.assign([{ transcript: "Same question" }], { isFinal: true })],
      });
    });

    await act(async () => {
      recognition.onresult({
        resultIndex: 0,
        results: [Object.assign([{ transcript: "Same question" }], { isFinal: true })],
      });
    });

    // API should only have been called once for this duplicate transcript
    await waitFor(() => {
      const utteranceCalls = mockApiPost.mock.calls.filter(
        (call) => call[0] === "/audio/livekit/utterance"
      );
      expect(utteranceCalls.length).toBe(1);
    });
  });

  it("7. handles CallWithAgent component multi-turn dialogue without room destruction", async () => {
    mockApiPost.mockImplementation((url: string) => {
      if (url === "/audio/livekit/token") {
        return Promise.resolve({
          data: { server_url: "wss://test.livekit.cloud", token: "tok", room_name: "room-42" },
        });
      }
      if (url === "/audio/livekit/utterance") {
        return Promise.resolve({
          data: { status: "processed", ai_response: "Understood." },
        });
      }
      if (url === "/audio/tts") {
        return Promise.resolve({
          data: { fallback: "browser", reason: "test" },
          headers: { "content-type": "application/json" },
        });
      }
      return Promise.resolve({ data: {} });
    });

    const onEndCall = vi.fn();
    render(<CallWithAgent conversationId="42" onEndCall={onEndCall} />);

    await waitFor(() => {
      expect(mockRoomInstances.length).toBe(1);
      expect(mockRecognitionInstances.length).toBe(1);
    });

    const room = mockRoomInstances[0];
    const recognition = mockRecognitionInstances[0];

    // Turn 1
    await act(async () => {
      recognition.onresult({
        resultIndex: 0,
        results: [Object.assign([{ transcript: "Turn one message" }], { isFinal: true })],
      });
    });

    // Turn 2
    await act(async () => {
      recognition.onresult({
        resultIndex: 0,
        results: [Object.assign([{ transcript: "Turn two message" }], { isFinal: true })],
      });
    });

    // Verify room was NOT disconnected and onEndCall was NOT called
    expect(room.disconnect).not.toHaveBeenCalled();
    expect(onEndCall).not.toHaveBeenCalled();
  });

  it("8. executes ten consecutive turns in a single session without page refresh or room teardown", async () => {
    mockApiPost.mockImplementation((url: string, data: any) => {
      if (url === "/audio/livekit/token") {
        return Promise.resolve({
          data: {
            server_url: "wss://test.livekit.cloud",
            token: "mock-livekit-token-10-turns",
            room_name: "resolveai-convo-42",
          },
        });
      }
      if (url === "/audio/livekit/utterance") {
        return Promise.resolve({
          data: {
            status: "processed",
            ai_response: `AI response to turn: ${data.transcript}`,
            workflow_state: "asking_user",
            emotion: "frustrated",
            emotion_confidence: 0.88,
            language: "tanglish",
            latency_ms: 125,
          },
        });
      }
      return Promise.resolve({ data: {} });
    });

    render(<VoiceCallPage initialConversationId="42" autoStart={true} />);

    await waitFor(() => {
      expect(mockRoomInstances.length).toBe(1);
      expect(mockRecognitionInstances.length).toBe(1);
    });

    const room = mockRoomInstances[0];
    const recognition = mockRecognitionInstances[0];

    const tenQuestions = [
      "Turn 1: Where is my order ORD-111?",
      "Turn 2: Payment deduct aayiduchu but status is pending.",
      "Turn 3: Can I change delivery address?",
      "Turn 4: What is the estimated arrival time?",
      "Turn 5: I already tried tracking on courier website.",
      "Turn 6: Does it require OTP at delivery?",
      "Turn 7: My neighbor can receive it if I am away.",
      "Turn 8: Can I pay remaining amount via cash?",
      "Turn 9: Actually the order ID is ORD-222 not ORD-111.",
      "Turn 10: Thank you, that answers all my questions.",
    ];

    for (let i = 0; i < tenQuestions.length; i++) {
      const turnMsg = tenQuestions[i];
      await act(async () => {
        recognition.onresult({
          resultIndex: 0,
          results: [
            Object.assign([{ transcript: turnMsg }], { isFinal: true }),
          ],
        });
      });

      await waitFor(() => {
        expect(mockApiPost).toHaveBeenCalledWith(
          "/audio/livekit/utterance",
          expect.objectContaining({
            conversation_id: 42,
            transcript: turnMsg,
          }),
          expect.anything()
        );
      });
    }

    // Crucial check: After all 10 turns, session is alive without disconnect
    expect(room.disconnect).not.toHaveBeenCalled();
    expect(recognition.abort).not.toHaveBeenCalled();

    // Verify emotion badge, confidence, latency, and language badge are rendered in UI
    await waitFor(() => {
      expect(screen.getByText(/frustrated/i)).toBeInTheDocument();
      expect(screen.getByText(/88%/i)).toBeInTheDocument();
      expect(screen.getByTestId("language-badge")).toHaveTextContent(/tanglish/i);
    });
  });
});

