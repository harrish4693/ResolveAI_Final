import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { ChatSurface } from "@/components/resolve/customer";
import { VoiceCallPage } from "@/components/resolve/VoiceCallPage";
import { stripDispatchedPrefix, stripAllDispatchedPrefixes } from "@/lib/voiceEchoFilter";

// Mock auth
vi.mock("@/lib/auth", () => ({
  useAuth: () => ({
    user: { id: 1, role: "customer", full_name: "Test Customer" },
    isLoading: false,
    logout: vi.fn(),
  }),
}));

// Mock WebSocket
const mockSendTranscriptUpdate = vi.fn();
vi.mock("@/lib/ws", () => ({
  useWebSocket: () => ({
    isConnected: true,
    subscribe: vi.fn(() => vi.fn()),
    sendTyping: vi.fn(),
    sendVoiceCommand: vi.fn(),
    sendVoiceChunk: vi.fn(),
    sendTranscriptUpdate: mockSendTranscriptUpdate,
  }),
}));

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

const mockApiPost = vi.fn().mockImplementation((url: string, data: any) => {
  if (url.includes("/messages")) {
    return Promise.resolve({
      data: [
        {
          id: 101,
          sender_type: "CUSTOMER",
          content: data.content,
          created_at: new Date().toISOString(),
        },
      ],
    });
  }
  if (url === "/audio/livekit/token") {
    return Promise.resolve({
      data: {
        server_url: "wss://test.livekit.cloud",
        token: "mock-token",
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

const mockApiGet = vi.fn().mockImplementation((url: string) => {
  if (url === "/conversations") {
    return Promise.resolve({
      data: [{ id: 42, status: "active", subject: "Order Delivery Question" }],
    });
  }
  if (url.includes("/messages")) {
    return Promise.resolve({ data: [] });
  }
  return Promise.resolve({
    data: { id: 42, status: "in_progress", workflow_state: "asking_user", subject: "Test Ticket" },
  });
});

vi.mock("@/lib/api", () => ({
  api: {
    get: (url: string) => mockApiGet(url),
    post: (url: string, data?: any, config?: any) => mockApiPost(url, data, config),
  },
}));

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => vi.fn(),
  Link: ({ children, to, params, ...props }: any) => (
    <a href={to} data-params={JSON.stringify(params)} {...props}>
      {children}
    </a>
  ),
}));

// Global mocks for SpeechRecognition
let mockRecognitionInstances: any[] = [];
class MockSpeechRecognition {
  continuous = true;
  interimResults = true;
  lang = "en-IN";
  onresult: ((event: any) => void) | null = null;
  onend: (() => void) | null = null;
  onstart: (() => void) | null = null;
  onerror: ((event: any) => void) | null = null;
  start = vi.fn();
  stop = vi.fn();
  abort = vi.fn();

  constructor() {
    mockRecognitionInstances.push(this);
  }

  simulateResult(transcript: string, isFinal = true) {
    if (this.onresult) {
      act(() => {
        this.onresult?.({
          results: [Object.assign([{ transcript }], { isFinal })],
          resultIndex: 0,
        });
      });
    }
  }

  simulateOnEnd() {
    if (this.onend) {
      act(() => {
        this.onend?.();
      });
    }
  }
}

describe("Voice Input & Call Agent Turn Isolation Regression Suite", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockRecognitionInstances = [];
    mockRoomInstances = [];
    mockRoomEventHandlers = {};
    (window as any).SpeechRecognition = MockSpeechRecognition;
    (window as any).webkitSpeechRecognition = MockSpeechRecognition;

    window.speechSynthesis = {
      cancel: vi.fn(),
      speak: vi.fn((utterance: any) => {
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
    delete (window as any).SpeechRecognition;
    delete (window as any).webkitSpeechRecognition;
  });

  describe("1. Pure Unit Tests: stripDispatchedPrefix & stripAllDispatchedPrefixes", () => {
    it("strips exact previous turn prefix from incoming text", () => {
      const result = stripDispatchedPrefix(
        "Where is my order? I want to cancel it",
        "Where is my order?"
      );
      expect(result).toBe("I want to cancel it");
    });

    it("strips prefix regardless of trailing punctuation difference (. vs ?)", () => {
      const result = stripDispatchedPrefix(
        "Where is my order. I want to cancel it",
        "Where is my order?"
      );
      expect(result).toBe("I want to cancel it");
    });

    it("strips multiple sequentially dispatched turns in historical order", () => {
      const history = ["Turn 1: Hello", "Turn 2: What is my tracking number?"];
      const text = "Turn 1: Hello. Turn 2: What is my tracking number? Turn 3: When does it arrive?";
      const result = stripAllDispatchedPrefixes(text, history);
      expect(result).toBe("Turn 3: When does it arrive?");
    });

    it("leaves text untouched when it does not match previous turns", () => {
      const history = ["Where is my order?"];
      const text = "Can I change my delivery address?";
      const result = stripAllDispatchedPrefixes(text, history);
      expect(result).toBe("Can I change my delivery address?");
    });

    it("returns empty string if incoming text is solely the previous turn", () => {
      const result = stripDispatchedPrefix("Where is my order?", "Where is my order?");
      expect(result).toBe("");
    });
  });

  describe("2. Chat Mode Dictation Lifecycle & Stale Text Prevention", () => {
    it("Scenario A: speaks message A -> sends -> speaks message B -> composer contains ONLY message B", async () => {
      render(<ChatSurface conversationId="10" />);

      const textarea = (await screen.findByRole("textbox", {
        name: /your message/i,
      })) as HTMLTextAreaElement;

      // 1. Speak message A
      const micBtn = screen.getByRole("button", { name: /start voice dictation/i });
      fireEvent.click(micBtn);

      await waitFor(() => {
        expect(mockRecognitionInstances.length).toBeGreaterThanOrEqual(1);
      });

      const recognition1 = mockRecognitionInstances[mockRecognitionInstances.length - 1];
      act(() => {
        recognition1.simulateResult("Where is my order?", true);
      });

      expect(textarea.value).toBe("Where is my order?");

      // 2. Click Send while dictation is active
      const sendBtn = screen.getByRole("button", { name: /send/i });
      await act(async () => {
        fireEvent.click(sendBtn);
      });

      // Verify composer is cleared immediately
      expect(textarea.value).toBe("");
      expect(mockApiPost).toHaveBeenCalledWith(
        "/conversations/10/messages",
        expect.objectContaining({ content: "Where is my order?" }),
        undefined
      );

      // 3. Start a new voice dictation session for message B
      const micBtn2 = screen.getByRole("button", { name: /start voice dictation/i });
      await act(async () => {
        fireEvent.click(micBtn2);
      });

      await waitFor(() => {
        expect(mockRecognitionInstances.length).toBeGreaterThanOrEqual(2);
      });

      const recognition2 = mockRecognitionInstances[mockRecognitionInstances.length - 1];
      // 4. Speak message B
      act(() => {
        recognition2.simulateResult("I want to cancel it", true);
      });

      // Crucial assertion: Composer contains ONLY message B, NOT message A + B!
      expect(textarea.value).toBe("I want to cancel it");
      expect(textarea.value).not.toContain("Where is my order");
    });

    it("Scenario B: types message A -> sends -> starts dictation -> speaks message B -> composer contains ONLY message B", async () => {
      render(<ChatSurface conversationId="10" />);

      const textarea = (await screen.findByRole("textbox", {
        name: /your message/i,
      })) as HTMLTextAreaElement;

      // 1. User types message A
      fireEvent.change(textarea, { target: { value: "My card was charged twice" } });
      expect(textarea.value).toBe("My card was charged twice");

      // 2. User sends message A
      const sendBtn = screen.getByRole("button", { name: /send/i });
      await act(async () => {
        fireEvent.click(sendBtn);
      });

      expect(textarea.value).toBe("");

      // 3. User starts voice dictation and speaks message B
      const micBtn = screen.getByRole("button", { name: /start voice dictation/i });
      await act(async () => {
        fireEvent.click(micBtn);
      });

      await waitFor(() => {
        expect(mockRecognitionInstances.length).toBeGreaterThanOrEqual(1);
      });

      const recognition = mockRecognitionInstances[mockRecognitionInstances.length - 1];
      act(() => {
        recognition.simulateResult("Please refund the duplicate charge", true);
      });

      // Crucial assertion: Composer contains ONLY message B, message A is NOT prepended
      expect(textarea.value).toBe("Please refund the duplicate charge");
      expect(textarea.value).not.toContain("charged twice");
    });

    it("Scenario C: types unsent draft prefix -> dictates speech -> appends correctly without re-using sent messages", async () => {
      render(<ChatSurface conversationId="10" />);

      const textarea = (await screen.findByRole("textbox", {
        name: /your message/i,
      })) as HTMLTextAreaElement;

      // User types an unsent prefix
      fireEvent.change(textarea, { target: { value: "Draft Note:" } });

      // User clicks mic and speaks
      const micBtn = screen.getByRole("button", { name: /start voice dictation/i });
      await act(async () => {
        fireEvent.click(micBtn);
      });

      await waitFor(() => {
        expect(mockRecognitionInstances.length).toBeGreaterThanOrEqual(1);
      });

      const recognition = mockRecognitionInstances[mockRecognitionInstances.length - 1];
      act(() => {
        recognition.simulateResult("customer requested invoice", true);
      });

      expect(textarea.value).toBe("Draft Note: customer requested invoice");

      // Send the message
      const sendBtn = screen.getByRole("button", { name: /send/i });
      await act(async () => {
        fireEvent.click(sendBtn);
      });

      expect(textarea.value).toBe("");

      // Now start dictation again on clean slate
      await act(async () => {
        fireEvent.click(micBtn);
      });

      await waitFor(() => {
        expect(mockRecognitionInstances.length).toBeGreaterThanOrEqual(2);
      });

      const recognition2 = mockRecognitionInstances[mockRecognitionInstances.length - 1];
      act(() => {
        recognition2.simulateResult("Second question here", true);
      });

      // Should ONLY contain "Second question here", NOT "Draft Note: customer requested invoice"
      expect(textarea.value).toBe("Second question here");
      expect(textarea.value).not.toContain("Draft Note");
    });

    it("Scenario D: delayed recognition.onend event firing after send does NOT restore sent message into draft", async () => {
      render(<ChatSurface conversationId="10" />);

      const textarea = (await screen.findByRole("textbox", {
        name: /your message/i,
      })) as HTMLTextAreaElement;

      // Start dictation
      const micBtn = screen.getByRole("button", { name: /start voice dictation/i });
      fireEvent.click(micBtn);

      await waitFor(() => {
        expect(mockRecognitionInstances.length).toBeGreaterThanOrEqual(1);
      });

      const activeRecognition = mockRecognitionInstances[mockRecognitionInstances.length - 1];
      act(() => {
        activeRecognition.simulateResult("Important urgent message", true);
      });

      expect(textarea.value).toBe("Important urgent message");

      // Send the message
      const sendBtn = screen.getByRole("button", { name: /send/i });
      await act(async () => {
        fireEvent.click(sendBtn);
      });

      expect(textarea.value).toBe("");

      // Simulate browser firing onend *after* message has been sent
      act(() => {
        activeRecognition.simulateOnEnd();
      });

      // Crucial assertion: draft remains empty, sent message is NOT resurrected
      expect(textarea.value).toBe("");
    });

    it("Scenario E: prevents double-click submission race conditions", async () => {
      render(<ChatSurface conversationId="10" />);

      const textarea = (await screen.findByRole("textbox", {
        name: /your message/i,
      })) as HTMLTextAreaElement;

      fireEvent.change(textarea, { target: { value: "Single dispatch message" } });

      const sendBtn = screen.getByRole("button", { name: /send/i });

      // Click rapidly twice
      await act(async () => {
        fireEvent.click(sendBtn);
        fireEvent.click(sendBtn);
      });

      // Only one network post was made
      expect(mockApiPost).toHaveBeenCalledTimes(1);
      expect(textarea.value).toBe("");
    });
  });

  describe("3. Call Agent Multi-Turn Isolation & Prefix Stripping", () => {
    it("Scenario F: continuous SpeechRecognition accumulates Turn 1 and Turn 2 -> Turn 2 strips Turn 1 prefix", async () => {
      render(<VoiceCallPage initialConversationId="42" autoStart={true} />);

      await waitFor(() => {
        expect(mockRoomInstances.length).toBe(1);
        expect(mockRecognitionInstances.length).toBe(1);
      });

      const recognition = mockRecognitionInstances[0];

      // Turn 1
      await act(async () => {
        recognition.onresult({
          resultIndex: 0,
          results: [
            Object.assign([{ transcript: "Where is my order?" }], { isFinal: true }),
          ],
        });
      });

      await waitFor(() => {
        expect(mockApiPost).toHaveBeenCalledWith(
          "/audio/livekit/utterance",
          expect.objectContaining({
            conversation_id: 42,
            transcript: "Where is my order?",
          }),
          expect.anything()
        );
      });

      // Turn 2: Browser Web Speech API with continuous: true retains Turn 1 in event.results
      await act(async () => {
        recognition.onresult({
          resultIndex: 0,
          results: [
            Object.assign([{ transcript: "Where is my order?" }], { isFinal: true }),
            Object.assign([{ transcript: "I want to cancel it" }], { isFinal: true }),
          ],
        });
      });

      await waitFor(() => {
        // Crucial assertion: Turn 2 is dispatched with ONLY "I want to cancel it", NOT the concatenated text!
        expect(mockApiPost).toHaveBeenCalledWith(
          "/audio/livekit/utterance",
          expect.objectContaining({
            conversation_id: 42,
            transcript: "I want to cancel it",
          }),
          expect.anything()
        );
      });

      // Verify Turn 2 payload did NOT contain "Where is my order?"
      const secondCall = mockApiPost.mock.calls.find(
        (call: any[]) =>
          call[0] === "/audio/livekit/utterance" &&
          call[1]?.transcript === "I want to cancel it"
      );
      expect(secondCall).toBeTruthy();
      expect(secondCall[1].transcript).not.toContain("Where is my order");
    });

    it("Scenario G: three consecutive turns in one call session each dispatch only their respective words", async () => {
      render(<VoiceCallPage initialConversationId="42" autoStart={true} />);

      await waitFor(() => {
        expect(mockRoomInstances.length).toBe(1);
        expect(mockRecognitionInstances.length).toBe(1);
      });

      const recognition = mockRecognitionInstances[0];

      // Turn 1
      await act(async () => {
        recognition.onresult({
          resultIndex: 0,
          results: [
            Object.assign([{ transcript: "Turn one message" }], { isFinal: true }),
          ],
        });
      });

      await waitFor(() => {
        expect(mockApiPost).toHaveBeenCalledWith(
          "/audio/livekit/utterance",
          expect.objectContaining({ transcript: "Turn one message" }),
          expect.anything()
        );
      });

      // Turn 2: Browser event.results accumulates Turn 1 and Turn 2
      await act(async () => {
        recognition.onresult({
          resultIndex: 0,
          results: [
            Object.assign([{ transcript: "Turn one message" }], { isFinal: true }),
            Object.assign([{ transcript: "Turn two message" }], { isFinal: true }),
          ],
        });
      });

      await waitFor(() => {
        expect(mockApiPost).toHaveBeenCalledWith(
          "/audio/livekit/utterance",
          expect.objectContaining({ transcript: "Turn two message" }),
          expect.anything()
        );
      });

      // Turn 3: Browser event.results accumulates Turn 1, Turn 2, and Turn 3
      await act(async () => {
        recognition.onresult({
          resultIndex: 0,
          results: [
            Object.assign([{ transcript: "Turn one message" }], { isFinal: true }),
            Object.assign([{ transcript: "Turn two message" }], { isFinal: true }),
            Object.assign([{ transcript: "Turn three message" }], { isFinal: true }),
          ],
        });
      });

      await waitFor(() => {
        expect(mockApiPost).toHaveBeenCalledWith(
          "/audio/livekit/utterance",
          expect.objectContaining({ transcript: "Turn three message" }),
          expect.anything()
        );
      });

      // Check utterance IDs are distinct
      const utteranceCalls = mockApiPost.mock.calls.filter(
        (call: any[]) => call[0] === "/audio/livekit/utterance"
      );
      expect(utteranceCalls.length).toBe(3);
      const id1 = utteranceCalls[0][1].utterance_id;
      const id2 = utteranceCalls[1][1].utterance_id;
      const id3 = utteranceCalls[2][1].utterance_id;

      expect(id1).not.toBe(id2);
      expect(id2).not.toBe(id3);
    });
  });
});
