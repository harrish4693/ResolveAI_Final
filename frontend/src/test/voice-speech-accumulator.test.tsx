import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, waitFor, act } from "@testing-library/react";
import { VoiceCallPage } from "@/components/resolve/VoiceCallPage";

// Mock auth
vi.mock("@/lib/auth", () => ({
  useAuth: () => ({
    user: { id: 1, role: "customer", full_name: "Jane Doe", email: "jane@example.com" },
    isLoading: false,
    logout: vi.fn(),
  }),
}));

// Mock WebSocket
vi.mock("@/lib/ws", () => ({
  useWebSocket: () => ({
    isConnected: true,
    subscribe: vi.fn(() => vi.fn()),
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
      data: [{ id: 42, status: "active", subject: "Order Question" }],
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

// Mock SpeechRecognition and SpeechSynthesis
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

// Mock LiveKit
let mockRoomInstances: any[] = [];
vi.mock("livekit-client", () => {
  class MockRoom {
    on = vi.fn();
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
    Track: { Kind: { Audio: "audio" } },
  };
});

describe("Voice Speech Accumulator & Silence Timer Suite (Fake Timers)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockRecognitionInstances = [];
    mockRoomInstances = [];

    (window as any).SpeechRecognition = MockSpeechRecognition;
    (window as any).webkitSpeechRecognition = MockSpeechRecognition;
    (window as any).__SILENCE_TIMEOUT_MS = 1000;
    (window as any).__VOICE_DEV_LOG = true;

    window.speechSynthesis = {
      cancel: vi.fn(),
      speak: vi.fn(),
      getVoices: vi.fn(() => []),
      paused: false,
      pending: false,
      speaking: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    } as any;

    (window as any).SpeechSynthesisUtterance = class {
      text: string;
      constructor(text: string) {
        this.text = text;
      }
    };

    mockApiPost.mockImplementation((url: string, data: any) => {
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
      if (url === "/audio/tts") {
        return Promise.resolve({
          data: { fallback: "browser" },
          headers: { "content-type": "application/json" },
        });
      }
      return Promise.resolve({ data: {} });
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    delete (window as any).__SILENCE_TIMEOUT_MS;
  });

  it("1. pause mid-sentence: accumulates 15 words across a 400ms pause and sends only after 1000ms of final silence", async () => {
    render(<VoiceCallPage initialConversationId="42" autoStart={true} />);

    await waitFor(() => {
      expect(mockRecognitionInstances.length).toBe(1);
    });
    const recognition = mockRecognitionInstances[0];

    // Now switch to fake timers for speech timing validation
    vi.useFakeTimers();

    // Part 1: First 7 words spoken
    act(() => {
      recognition.onresult({
        resultIndex: 0,
        results: [
          Object.assign(
            [{ transcript: "Hello I need help checking the status" }],
            { isFinal: false }
          ),
        ],
      });
    });

    // Advance 400ms (pause mid-sentence) — timer is 1000ms so it must NOT fire yet
    act(() => {
      vi.advanceTimersByTime(400);
    });

    const callsDuringPause = mockApiPost.mock.calls.filter(
      (c) => c[0] === "/audio/livekit/utterance"
    );
    expect(callsDuringPause.length).toBe(0);

    // Part 2: Next 8 words spoken
    act(() => {
      recognition.onresult({
        resultIndex: 0,
        results: [
          Object.assign(
            [{ transcript: "Hello I need help checking the status of my recent order that was placed yesterday" }],
            { isFinal: true }
          ),
        ],
      });
    });

    // Advance 500ms (still within 1000ms silence window)
    act(() => {
      vi.advanceTimersByTime(500);
    });
    expect(
      mockApiPost.mock.calls.filter((c) => c[0] === "/audio/livekit/utterance").length
    ).toBe(0);

    // Advance remaining 500ms (total 1000ms silence elapsed)
    act(() => {
      vi.advanceTimersByTime(500);
    });

    // Silence timer should now fire and send ALL 15 words in one turn
    const utteranceCalls = mockApiPost.mock.calls.filter(
      (c) => c[0] === "/audio/livekit/utterance"
    );
    expect(utteranceCalls.length).toBe(1);
    expect(utteranceCalls[0][1].transcript).toBe(
      "Hello I need help checking the status of my recent order that was placed yesterday"
    );
  });

  it("2. barge-in with a long sentence: stops audio immediately, does NOT dispatch early, sends full sentence after silence", async () => {
    render(<VoiceCallPage initialConversationId="42" autoStart={true} />);

    await waitFor(() => {
      expect(mockRecognitionInstances.length).toBe(1);
    });
    const recognition = mockRecognitionInstances[0];

    vi.useFakeTimers();

    // Simulate agent speaking initial welcome
    // The component speaks on connect; window.speechSynthesis.cancel will be called on barge-in
    expect(window.speechSynthesis.cancel).toBeDefined();

    // User interrupts (barges in) with the first 3 words
    act(() => {
      recognition.onresult({
        resultIndex: 0,
        results: [
          Object.assign([{ transcript: "Wait stop actually" }], { isFinal: false }),
        ],
      });
    });

    // Verification: agent audio was cancelled
    expect(window.speechSynthesis.cancel).toHaveBeenCalled();

    // Verification: transcript was NOT prematurely sent to server on barge-in
    expect(
      mockApiPost.mock.calls.filter((c) => c[0] === "/audio/livekit/utterance").length
    ).toBe(0);

    // User continues speaking the rest of the long sentence
    act(() => {
      vi.advanceTimersByTime(300);
      recognition.onresult({
        resultIndex: 0,
        results: [
          Object.assign(
            [{ transcript: "Wait stop actually I want to change my delivery address to Mumbai" }],
            { isFinal: true }
          ),
        ],
      });
    });

    // Advance 500ms (silence timer still counting down)
    act(() => {
      vi.advanceTimersByTime(500);
    });
    expect(
      mockApiPost.mock.calls.filter((c) => c[0] === "/audio/livekit/utterance").length
    ).toBe(0);

    // Advance to 1000ms silence completion
    act(() => {
      vi.advanceTimersByTime(500);
    });

    // Now the full barged-in sentence is dispatched cleanly in one turn
    const calls = mockApiPost.mock.calls.filter(
      (c) => c[0] === "/audio/livekit/utterance"
    );
    expect(calls.length).toBe(1);
    expect(calls[0][1].transcript).toBe(
      "Wait stop actually I want to change my delivery address to Mumbai"
    );
  });

  it("3. recognition restart: preserves uncommitted speech buffer across onend and sends complete utterance", async () => {
    render(<VoiceCallPage initialConversationId="42" autoStart={true} />);

    await waitFor(() => {
      expect(mockRecognitionInstances.length).toBe(1);
    });
    const recognition = mockRecognitionInstances[0];

    vi.useFakeTimers();

    // User speaks first part before browser SpeechRecognition stops
    act(() => {
      recognition.onresult({
        resultIndex: 0,
        results: [
          Object.assign([{ transcript: "Please cancel my" }], { isFinal: true }),
        ],
      });
    });

    // Recognition session ends unexpectedly (e.g. browser speech engine restart)
    act(() => {
      if (recognition.onend) recognition.onend();
    });

    // SpeechRecognition restarted; user speaks second part
    act(() => {
      recognition.onresult({
        resultIndex: 0,
        results: [
          Object.assign([{ transcript: "subscription right now" }], { isFinal: true }),
        ],
      });
    });

    // Advance 1000ms silence timer
    act(() => {
      vi.advanceTimersByTime(1000);
    });

    // Verification: Both chunks were joined into one single utterance
    const calls = mockApiPost.mock.calls.filter(
      (c) => c[0] === "/audio/livekit/utterance"
    );
    expect(calls.length).toBe(1);
    expect(calls[0][1].transcript).toBe("Please cancel my subscription right now");
  });
});
