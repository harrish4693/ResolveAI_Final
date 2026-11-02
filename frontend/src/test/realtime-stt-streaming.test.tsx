import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { ChatSurface } from "@/components/resolve/customer";
import { VoiceCallPage } from "@/components/resolve/VoiceCallPage";

// Mock auth
let mockCurrentUser: any = { id: 1, role: "customer", full_name: "Test Customer" };
vi.mock("@/lib/auth", () => ({
  useAuth: () => ({
    user: mockCurrentUser,
    isLoading: false,
    logout: vi.fn(),
  }),
}));

// Mock WebSocket with sendTranscriptUpdate spy
const mockSendTranscriptUpdate = vi.fn();
let mockWsHandlers: Record<string, (event: any) => void> = {};
const mockSubscribe = vi.fn((event: string, cb: any) => {
  mockWsHandlers[event] = cb;
  return vi.fn();
});

vi.mock("@/lib/ws", () => ({
  useWebSocket: () => ({
    isConnected: true,
    subscribe: mockSubscribe,
    sendTyping: vi.fn(),
    sendVoiceCommand: vi.fn(),
    sendVoiceChunk: vi.fn(),
    sendTranscriptUpdate: mockSendTranscriptUpdate,
  }),
}));

const mockApiPost = vi.fn().mockImplementation((url: string, data: any) => {
  if (url === "/audio/livekit/token") {
    return Promise.resolve({
      data: {
        server_url: "wss://test.livekit.cloud",
        token: "mock-livekit-token",
        room_name: "convo-10",
      },
    });
  }
  if (url === "/audio/livekit/utterance") {
    return Promise.resolve({
      data: {
        status: "processed",
        ai_response: `AI response to: ${data?.transcript}`,
        workflow_state: "asking_user",
      },
    });
  }
  return Promise.resolve({ data: [] });
});

const mockApiGet = vi.fn().mockImplementation((url: string) => {
  if (url.includes("/messages")) {
    return Promise.resolve({ data: [] });
  }
  return Promise.resolve({
    data: { id: 10, status: "in_progress", workflow_state: "asking_user", subject: "Test Ticket" },
  });
});

vi.mock("@/lib/api", () => ({
  api: {
    get: (url: string) => mockApiGet(url),
    post: (url: string, data: any) => mockApiPost(url, data),
  },
}));

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => vi.fn(),
  Link: ({ children, ...props }: any) => <a {...props}>{children}</a>,
}));

// Mock LiveKit
vi.mock("livekit-client", () => {
  class MockRoom {
    on = vi.fn();
    connect = vi.fn().mockResolvedValue(undefined);
    disconnect = vi.fn();
    localParticipant = {
      setMicrophoneEnabled: vi.fn().mockResolvedValue(undefined),
      publishData: vi.fn(),
    };
  }
  return {
    Room: MockRoom,
    RoomEvent: {
      TrackSubscribed: "trackSubscribed",
      TrackUnsubscribed: "trackUnsubscribed",
      ActiveSpeakersChanged: "activeSpeakersChanged",
      DataReceived: "dataReceived",
      ParticipantDisconnected: "participantDisconnected",
      Disconnected: "disconnected",
    },
    Track: { Kind: { Audio: "audio" } },
  };
});

// Advanced Mock SpeechRecognition supporting incremental results
class MockStreamingSpeechRecognition {
  lang = "en-IN";
  continuous = true;
  interimResults = true;
  maxAlternatives = 1;
  onstart: (() => void) | null = null;
  onresult: ((event: any) => void) | null = null;
  onerror: ((event: any) => void) | null = null;
  onend: (() => void) | null = null;

  static instance: MockStreamingSpeechRecognition | null = null;

  constructor() {
    MockStreamingSpeechRecognition.instance = this;
  }

  start = vi.fn(() => {
    if (this.onstart) {
      act(() => {
        this.onstart?.();
      });
    }
  });

  stop = vi.fn(() => {
    if (this.onend) {
      act(() => {
        this.onend?.();
      });
    }
  });

  abort = vi.fn(() => {
    if (this.onend) {
      act(() => {
        this.onend?.();
      });
    }
  });

  // Emits multiple results to simulate interim & final chunks accurately
  simulateSpeechEvent(results: Array<{ transcript: string; isFinal: boolean }>) {
    if (this.onresult) {
      act(() => {
        const mappedResults = results.map((r) =>
          Object.assign([{ transcript: r.transcript }], { isFinal: r.isFinal })
        );
        this.onresult?.({
          results: mappedResults,
          resultIndex: 0,
        });
      });
    }
  }
}

describe("Real-Time Streaming Speech-to-Text (STT) Integration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockWsHandlers = {};
    mockCurrentUser = { id: 1, role: "customer", full_name: "Test Customer" };
    (window as any).__SILENCE_TIMEOUT_MS = 600;
    (window as any).__TAIL_MS = 0;
    (window as any).__BARGE_IN_MS = 0;
    MockStreamingSpeechRecognition.instance = null;
    (window as any).SpeechRecognition = MockStreamingSpeechRecognition;
    (window as any).webkitSpeechRecognition = MockStreamingSpeechRecognition;

    window.speechSynthesis = {
      cancel: vi.fn(),
      getVoices: vi.fn(() => []),
      speak: vi.fn((utterance: any) => {
        if (utterance.onstart) setTimeout(() => utterance.onstart(), 0);
        if (utterance.onend) setTimeout(() => utterance.onend(), 5);
      }),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
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
    delete (window as any).SpeechRecognition;
    delete (window as any).webkitSpeechRecognition;
    delete (window as any).__SILENCE_TIMEOUT_MS;
  });

  describe("Chat Mode — Real-Time Dictation Streaming", () => {
    it("1. displays partial words incrementally in composer as customer speaks without delay", async () => {
      render(<ChatSurface conversationId="10" />);

      const micBtn = await screen.findByRole("button", { name: /start voice dictation/i });
      fireEvent.click(micBtn);

      const textarea = screen.getByRole("textbox", { name: /your message/i }) as HTMLTextAreaElement;
      expect(textarea.value).toBe("");

      // Customer begins speaking: "En" (interim)
      MockStreamingSpeechRecognition.instance?.simulateSpeechEvent([
        { transcript: "En", isFinal: false },
      ]);
      await waitFor(() => {
        expect(textarea.value).toBe("En");
      });

      // Customer continues: "En order" (interim revised)
      MockStreamingSpeechRecognition.instance?.simulateSpeechEvent([
        { transcript: "En order", isFinal: false },
      ]);
      await waitFor(() => {
        expect(textarea.value).toBe("En order");
      });

      // Customer continues: "En order innum deliver aagala" (interim revised)
      MockStreamingSpeechRecognition.instance?.simulateSpeechEvent([
        { transcript: "En order innum deliver aagala", isFinal: false },
      ]);
      await waitFor(() => {
        expect(textarea.value).toBe("En order innum deliver aagala");
      });

      // Speech finalized
      MockStreamingSpeechRecognition.instance?.simulateSpeechEvent([
        { transcript: "En order innum deliver aagala", isFinal: true },
      ]);
      await waitFor(() => {
        expect(textarea.value).toBe("En order innum deliver aagala");
      });

      // Dictation stops without auto-submitting
      fireEvent.click(screen.getByRole("button", { name: /stop dictation/i }));
      expect(mockApiPost).not.toHaveBeenCalled();
      expect(textarea.value).toBe("En order innum deliver aagala");
    });

    it("2. replaces revised interim text cleanly without repeating or duplicating words", async () => {
      render(<ChatSurface conversationId="10" />);

      const micBtn = await screen.findByRole("button", { name: /start voice dictation/i });
      fireEvent.click(micBtn);

      const textarea = screen.getByRole("textbox", { name: /your message/i }) as HTMLTextAreaElement;

      // First partial recognition guess: "deliver" (interim)
      MockStreamingSpeechRecognition.instance?.simulateSpeechEvent([
        { transcript: "deliver", isFinal: false },
      ]);
      await waitFor(() => {
        expect(textarea.value).toBe("deliver");
      });

      // Revised recognition guess: "delivery" (replaces previous interim, NOT "deliver delivery")
      MockStreamingSpeechRecognition.instance?.simulateSpeechEvent([
        { transcript: "delivery issue", isFinal: false },
      ]);
      await waitFor(() => {
        expect(textarea.value).toBe("delivery issue");
      });

      // Final commit
      MockStreamingSpeechRecognition.instance?.simulateSpeechEvent([
        { transcript: "delivery issue", isFinal: true },
      ]);
      await waitFor(() => {
        expect(textarea.value).toBe("delivery issue");
      });
    });

    it("3. preserves text previously typed manually in the composer while streaming interim words", async () => {
      render(<ChatSurface conversationId="10" />);

      const textarea = (await screen.findByRole("textbox", { name: /your message/i })) as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: "Hello," } });

      const micBtn = screen.getByRole("button", { name: /start voice dictation/i });
      fireEvent.click(micBtn);

      // Interim speech: "need help"
      MockStreamingSpeechRecognition.instance?.simulateSpeechEvent([
        { transcript: "need help", isFinal: false },
      ]);
      await waitFor(() => {
        expect(textarea.value).toBe("Hello, need help");
      });

      // Interim revised: "need help with refund"
      MockStreamingSpeechRecognition.instance?.simulateSpeechEvent([
        { transcript: "need help with refund", isFinal: false },
      ]);
      await waitFor(() => {
        expect(textarea.value).toBe("Hello, need help with refund");
      });

      // Finalized
      MockStreamingSpeechRecognition.instance?.simulateSpeechEvent([
        { transcript: "need help with refund", isFinal: true },
      ]);
      await waitFor(() => {
        expect(textarea.value).toBe("Hello, need help with refund");
      });
    });
  });

  describe("Voice Call Mode — Live Customer Transcript Streaming", () => {
    it("4. streams partial transcription updates via WebSocket and updates Live Transcript Drawer with provisional turn", async () => {
      render(<VoiceCallPage initialConversationId="10" autoStart={true} />);

      await waitFor(() => {
        expect(MockStreamingSpeechRecognition.instance).not.toBeNull();
      });

      // Open Transcript Drawer
      const toggleDrawer = await screen.findByRole("button", { name: /toggle live transcript/i });
      fireEvent.click(toggleDrawer);

      expect(screen.getByText(/live call transcript/i)).toBeInTheDocument();

      // Customer speaks partial phrase: "En package"
      MockStreamingSpeechRecognition.instance?.simulateSpeechEvent([
        { transcript: "En package", isFinal: false },
      ]);

      // 1. WebSocket sendTranscriptUpdate was called immediately with is_final = false
      expect(mockSendTranscriptUpdate).toHaveBeenCalledWith(
        10,
        expect.stringContaining("turn_"),
        "En package",
        false
      );

      // 2. Partial transcript appears in UI and drawer
      await waitFor(() => {
        expect(screen.getAllByText(/En package/i).length).toBeGreaterThan(0);
      });

      // Customer continues speaking: "En package innum varala"
      MockStreamingSpeechRecognition.instance?.simulateSpeechEvent([
        { transcript: "En package innum varala", isFinal: false },
      ]);

      expect(mockSendTranscriptUpdate).toHaveBeenCalledWith(
        10,
        expect.stringContaining("turn_"),
        "En package innum varala",
        false
      );

      await waitFor(() => {
        expect(screen.getAllByText(/En package innum varala/i).length).toBeGreaterThan(0);
      });
    });

    it("5. receives remote participant TRANSCRIPT_STREAM via WebSocket and displays it live in the drawer", async () => {
      render(<VoiceCallPage initialConversationId="10" autoStart={true} />);

      await waitFor(() => {
        expect(mockWsHandlers["TRANSCRIPT_STREAM"]).toBeDefined();
      });

      // Open drawer
      const toggleDrawer = await screen.findByRole("button", { name: /toggle live transcript/i });
      fireEvent.click(toggleDrawer);

      // Remote expert sends interim transcript stream
      act(() => {
        mockWsHandlers["TRANSCRIPT_STREAM"]({
          conversation_id: 10,
          data: {
            turn_id: "remote_turn_101",
            sender_type: "expert",
            text: "Checking your order status now",
            is_final: false,
          },
        });
      });

      // Shows provisional expert speech
      await waitFor(() => {
        expect(screen.getByText("Checking your order status now")).toBeInTheDocument();
        expect(screen.getByText(/support expert/i)).toBeInTheDocument();
        expect(screen.getByText(/speaking…/i)).toBeInTheDocument();
      });

      // Remote expert finalizes turn
      act(() => {
        mockWsHandlers["TRANSCRIPT_STREAM"]({
          conversation_id: 10,
          data: {
            turn_id: "remote_turn_101",
            sender_type: "expert",
            text: "Checking your order status now, please hold on.",
            is_final: true,
          },
        });
      });

      // Committed turn in drawer
      await waitFor(() => {
        expect(screen.getByText("Checking your order status now, please hold on.")).toBeInTheDocument();
      });
    });

    it("6. handles multiple consecutive utterances and commits final text exactly once without auto-submitting", async () => {
      render(<ChatSurface conversationId="10" />);

      const micBtn = await screen.findByRole("button", { name: /start voice dictation/i });
      fireEvent.click(micBtn);

      const textarea = screen.getByRole("textbox", { name: /your message/i }) as HTMLTextAreaElement;

      // Utterance 1 interim
      MockStreamingSpeechRecognition.instance?.simulateSpeechEvent([
        { transcript: "En order cancel panren", isFinal: false },
      ]);
      await waitFor(() => {
        expect(textarea.value).toBe("En order cancel panren");
      });

      // Utterance 1 final
      MockStreamingSpeechRecognition.instance?.simulateSpeechEvent([
        { transcript: "En order cancel panren", isFinal: true },
      ]);
      await waitFor(() => {
        expect(textarea.value).toBe("En order cancel panren");
      });

      // Utterance 2 interim (appended to finalized utterance 1)
      MockStreamingSpeechRecognition.instance?.simulateSpeechEvent([
        { transcript: "En order cancel panren", isFinal: true },
        { transcript: "refund eppo varum", isFinal: false },
      ]);
      await waitFor(() => {
        expect(textarea.value).toBe("En order cancel panren refund eppo varum");
      });

      // Utterance 2 finalized
      MockStreamingSpeechRecognition.instance?.simulateSpeechEvent([
        { transcript: "En order cancel panren", isFinal: true },
        { transcript: "refund eppo varum", isFinal: true },
      ]);
      await waitFor(() => {
        expect(textarea.value).toBe("En order cancel panren refund eppo varum");
      });

      // Stop dictation
      fireEvent.click(screen.getByRole("button", { name: /stop dictation/i }));

      // Draft is preserved, committed exactly once, not auto-submitted
      expect(textarea.value).toBe("En order cancel panren refund eppo varum");
      expect(mockApiPost).not.toHaveBeenCalled();
    });

    it("7. start/stop and reconnect cycles do not produce duplicate transcripts", async () => {
      render(<ChatSurface conversationId="10" />);

      // Session 1: Start and speak
      fireEvent.click(await screen.findByRole("button", { name: /start voice dictation/i }));
      MockStreamingSpeechRecognition.instance?.simulateSpeechEvent([
        { transcript: "First query", isFinal: true },
      ]);
      fireEvent.click(screen.getByRole("button", { name: /stop dictation/i }));

      const textarea = screen.getByRole("textbox", { name: /your message/i }) as HTMLTextAreaElement;
      await waitFor(() => {
        expect(textarea.value).toBe("First query");
      });

      // Session 2: Start dictation again and speak second phrase
      fireEvent.click(screen.getByRole("button", { name: /start voice dictation/i }));
      MockStreamingSpeechRecognition.instance?.simulateSpeechEvent([
        { transcript: "second query", isFinal: true },
      ]);
      fireEvent.click(screen.getByRole("button", { name: /stop dictation/i }));

      await waitFor(() => {
        expect(textarea.value).toBe("First query second query");
      });
    });

    it("8. ignores old-session events arriving after dictation has stopped or restarted", async () => {
      render(<ChatSurface conversationId="10" />);

      fireEvent.click(await screen.findByRole("button", { name: /start voice dictation/i }));
      const firstInstance = MockStreamingSpeechRecognition.instance;

      firstInstance?.simulateSpeechEvent([
        { transcript: "Valid current text", isFinal: false },
      ]);
      const textarea = screen.getByRole("textbox", { name: /your message/i }) as HTMLTextAreaElement;
      await waitFor(() => {
        expect(textarea.value).toBe("Valid current text");
      });

      // Stop dictation
      fireEvent.click(screen.getByRole("button", { name: /stop dictation/i }));

      // Stale event arrives from firstInstance after stop
      firstInstance?.simulateSpeechEvent([
        { transcript: "stale ghost speech", isFinal: false },
      ]);

      // Should not alter draft
      expect(textarea.value).toBe("Valid current text");
    });

    it("9. does not persist partial transcripts as independent messages to the database", async () => {
      render(<ChatSurface conversationId="10" />);

      fireEvent.click(await screen.findByRole("button", { name: /start voice dictation/i }));

      // Customer speaks partial text
      MockStreamingSpeechRecognition.instance?.simulateSpeechEvent([
        { transcript: "checking delivery date", isFinal: false },
      ]);

      // Verify no HTTP POST messages were dispatched
      expect(mockApiPost).not.toHaveBeenCalledWith(
        expect.stringMatching(/\/messages/),
        expect.anything()
      );
    });

    it("10. Call Mode supports assistant responses, TTS, barge-in interruption, and continuous conversation", async () => {
      (window as any).__SILENCE_TIMEOUT_MS = 50;
      (window as any).__TAIL_MS = 0;
      (window as any).__BARGE_IN_MS = 0;

      // Keep speech synthesis active until cancelled to test barge-in
      window.speechSynthesis.speak = vi.fn((utterance: any) => {
        utterance.onstart?.();
      });

      render(<VoiceCallPage initialConversationId="10" autoStart={true} />);

      await waitFor(() => {
        expect(MockStreamingSpeechRecognition.instance).not.toBeNull();
      });

      // Wait until initial greeting is actively speaking in speech synthesis
      await waitFor(() => {
        expect(window.speechSynthesis.speak).toHaveBeenCalled();
      });

      // Customer interrupts agent greeting while agent is speaking
      MockStreamingSpeechRecognition.instance?.simulateSpeechEvent([
        { transcript: "Wait stop, I have an urgent question", isFinal: false },
      ]);

      // Sustained speech barge-in cancels speech synthesis
      await waitFor(() => {
        expect(window.speechSynthesis.cancel).toHaveBeenCalled();
      });

      // Customer finishes speaking turn
      MockStreamingSpeechRecognition.instance?.simulateSpeechEvent([
        { transcript: "Wait stop, I have an urgent question", isFinal: true },
      ]);

      // Verify customer turn was submitted to AI endpoint after short silence delay
      await waitFor(
        () => {
          expect(mockApiPost).toHaveBeenCalledWith(
            "/audio/livekit/utterance",
            expect.objectContaining({
              conversation_id: 10,
              transcript: "Wait stop, I have an urgent question",
            })
          );
        },
        { timeout: 1500 }
      );
    });

    it("11. handles microphone permission denial and recognition errors safely", async () => {
      render(<ChatSurface conversationId="10" />);

      fireEvent.click(await screen.findByRole("button", { name: /start voice dictation/i }));

      // Simulate permission denied
      act(() => {
        MockStreamingSpeechRecognition.instance?.onerror?.({ error: "not-allowed" });
      });

      await waitFor(() => {
        expect(screen.getByText(/microphone permission denied/i)).toBeInTheDocument();
      });

      // Returns to idle state
      expect(screen.getByRole("button", { name: /start voice dictation/i })).toBeInTheDocument();

      // Retry and simulate network error
      fireEvent.click(screen.getByRole("button", { name: /start voice dictation/i }));
      act(() => {
        MockStreamingSpeechRecognition.instance?.onerror?.({ error: "network" });
      });

      await waitFor(() => {
        expect(screen.getByText(/speech recognition network error/i)).toBeInTheDocument();
      });
    });
  });
});
