import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { ChatSurface } from "@/components/resolve/customer";
import { CallWithAgent } from "@/components/resolve/CallWithAgent";
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

// Mock WebSocket
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

let mockConversationData: any = {
  id: 10,
  status: "in_progress",
  workflow_state: "asking_user",
  subject: "Test Ticket",
  preferred_language: "tanglish",
};

const mockApiGet = vi.fn().mockImplementation((url: string) => {
  if (url.includes("/messages")) {
    return Promise.resolve({ data: [] });
  }
  return Promise.resolve({ data: mockConversationData });
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

// Mock SpeechRecognition tracking all instances created
class MockSpeechRecognition {
  static instances: MockSpeechRecognition[] = [];
  static latestInstance: MockSpeechRecognition | null = null;
  static failNextStarts: number = 0;

  lang = "en-IN";
  continuous = true;
  interimResults = true;
  maxAlternatives = 1;
  onstart: (() => void) | null = null;
  onresult: ((event: any) => void) | null = null;
  onerror: ((event: any) => void) | null = null;
  onend: (() => void) | null = null;

  started = false;
  aborted = false;

  constructor() {
    MockSpeechRecognition.instances.push(this);
    MockSpeechRecognition.latestInstance = this;
  }

  start = vi.fn(() => {
    if (MockSpeechRecognition.failNextStarts > 0) {
      MockSpeechRecognition.failNextStarts--;
      throw new DOMException(
        "Failed to execute 'start' on 'SpeechRecognition': recognition has already started.",
        "InvalidStateError"
      );
    }
    this.started = true;
    if (this.onstart) {
      act(() => {
        this.onstart?.();
      });
    }
  });

  stop = vi.fn(() => {
    this.started = false;
    if (this.onend) {
      act(() => {
        this.onend?.();
      });
    }
  });

  abort = vi.fn(() => {
    this.started = false;
    this.aborted = true;
    if (this.onend) {
      act(() => {
        this.onend?.();
      });
    }
  });

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

  simulateEnd() {
    if (this.onend) {
      act(() => {
        this.onend?.();
      });
    }
  }
}

describe("Voice Transcription Regression Suite (Tanglish, Continuous Speech, Language Sync)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockWsHandlers = {};
    mockCurrentUser = { id: 1, role: "customer", full_name: "Test Customer" };
    mockConversationData = {
      id: 10,
      status: "in_progress",
      workflow_state: "asking_user",
      subject: "Test Ticket",
      preferred_language: "tanglish",
    };
    MockSpeechRecognition.instances = [];
    MockSpeechRecognition.latestInstance = null;
    MockSpeechRecognition.failNextStarts = 0;
    (window as any).SpeechRecognition = MockSpeechRecognition;
    (window as any).webkitSpeechRecognition = MockSpeechRecognition;

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
  });

  it("1. Automatically synchronizes recognition locale to ta-IN for Tanglish and preserves Tanglish phrases without English distortion", async () => {
    mockConversationData.preferred_language = "tanglish";
    render(<ChatSurface conversationId="10" />);

    // Wait for conversation load to set dictationLang
    await waitFor(() => {
      expect(mockApiGet).toHaveBeenCalled();
    });

    const micBtn = await screen.findByRole("button", { name: /start voice dictation/i });
    fireEvent.click(micBtn);

    const activeRecognizer = MockSpeechRecognition.latestInstance;
    expect(activeRecognizer).not.toBeNull();
    // Tanglish must automatically resolve to ta-IN locale for Tamil phonetic recognition
    expect(activeRecognizer?.lang).toBe("ta-IN");

    const textarea = screen.getByRole("textbox", { name: /your message/i }) as HTMLTextAreaElement;

    // Customer speaks Tanglish phrase: "Puriyala, simple ah sollu"
    activeRecognizer?.simulateSpeechEvent([
      { transcript: "Puriyala, simple ah sollu", isFinal: true },
    ]);

    await waitFor(() => {
      expect(textarea.value).toBe("Puriyala, simple ah sollu");
    });

    // Customer stops dictation cleanly
    fireEvent.click(screen.getByRole("button", { name: /stop dictation/i }));
    expect(textarea.value).toBe("Puriyala, simple ah sollu");
  });

  it("2. Accurately preserves Pure Tamil script in Chat dictation", async () => {
    mockConversationData.preferred_language = "tamil";
    render(<ChatSurface conversationId="10" />);

    await waitFor(() => {
      expect(mockApiGet).toHaveBeenCalled();
    });

    const micBtn = await screen.findByRole("button", { name: /start voice dictation/i });
    fireEvent.click(micBtn);

    const activeRecognizer = MockSpeechRecognition.latestInstance;
    expect(activeRecognizer?.lang).toBe("ta-IN");

    const textarea = screen.getByRole("textbox", { name: /your message/i }) as HTMLTextAreaElement;

    // Customer speaks pure Tamil
    activeRecognizer?.simulateSpeechEvent([
      { transcript: "என் ஆர்டர் இன்னும் வரவில்லை", isFinal: true },
    ]);

    await waitFor(() => {
      expect(textarea.value).toBe("என் ஆர்டர் இன்னும் வரவில்லை");
    });
  });

  it("3. Preserves Pure English speech and alphanumeric Order IDs exactly", async () => {
    mockConversationData.preferred_language = "english";
    render(<ChatSurface conversationId="10" />);

    await waitFor(() => {
      expect(mockApiGet).toHaveBeenCalled();
    });

    const micBtn = await screen.findByRole("button", { name: /start voice dictation/i });
    fireEvent.click(micBtn);

    const activeRecognizer = MockSpeechRecognition.latestInstance;
    expect(activeRecognizer?.lang).toBe("en-IN");

    const textarea = screen.getByRole("textbox", { name: /your message/i }) as HTMLTextAreaElement;

    // Customer dictates an Order ID in English
    activeRecognizer?.simulateSpeechEvent([
      { transcript: "Where is my package for order OD982345", isFinal: true },
    ]);

    await waitFor(() => {
      expect(textarea.value).toBe("Where is my package for order OD982345");
    });
  });

  it("4. Supports continuous speech across natural pauses without premature termination", async () => {
    render(<ChatSurface conversationId="10" />);

    const micBtn = await screen.findByRole("button", { name: /start voice dictation/i });
    fireEvent.click(micBtn);

    const firstRecognizer = MockSpeechRecognition.latestInstance!;
    expect(firstRecognizer).not.toBeNull();

    const textarea = screen.getByRole("textbox", { name: /your message/i }) as HTMLTextAreaElement;

    // Utterance 1
    firstRecognizer.simulateSpeechEvent([
      { transcript: "En order innum deliver aagala", isFinal: true },
    ]);

    await waitFor(() => {
      expect(textarea.value).toBe("En order innum deliver aagala");
    });

    // Browser Web Speech API times out / pauses and fires onend
    firstRecognizer.simulateEnd();

    // Fast-forward the 120ms restart timer
    await waitFor(() => {
      // A NEW fresh instance of SpeechRecognition must be created
      expect(MockSpeechRecognition.instances.length).toBeGreaterThan(1);
    });

    const secondRecognizer = MockSpeechRecognition.latestInstance!;
    expect(secondRecognizer).not.toBe(firstRecognizer);

    // Utterance 2 spoken in the restarted session
    secondRecognizer.simulateSpeechEvent([
      { transcript: "konjam check panni sollunga", isFinal: true },
    ]);

    // Both utterances must be seamlessly combined without dropping the first
    await waitFor(() => {
      expect(textarea.value).toBe("En order innum deliver aagala konjam check panni sollunga");
    });

    // Stop dictation
    fireEvent.click(screen.getByRole("button", { name: /stop dictation/i }));
    expect(textarea.value).toBe("En order innum deliver aagala konjam check panni sollunga");
  });

  it("5. Clean shutdown when user clicks stop dictation prevents subsequent automatic restarts", async () => {
    render(<ChatSurface conversationId="10" />);

    const micBtn = await screen.findByRole("button", { name: /start voice dictation/i });
    fireEvent.click(micBtn);

    const recognizer = MockSpeechRecognition.latestInstance!;
    recognizer.simulateSpeechEvent([
      { transcript: "Testing clean stop", isFinal: true },
    ]);

    const stopBtn = screen.getByRole("button", { name: /stop dictation/i });
    fireEvent.click(stopBtn);

    const countAfterStop = MockSpeechRecognition.instances.length;

    // Simulate recognition onend after stop
    recognizer.simulateEnd();

    // Wait past restart debounce period
    await new Promise((resolve) => setTimeout(resolve, 200));

    // No new recognizer should have been spawned
    expect(MockSpeechRecognition.instances.length).toBe(countAfterStop);
    expect(screen.getByRole("button", { name: /start voice dictation/i })).toBeInTheDocument();
  });

  it("6. Language switching mid-dictation cleanly restarts with new language while preserving draft", async () => {
    mockConversationData.preferred_language = "tanglish";
    render(<ChatSurface conversationId="10" />);

    await waitFor(() => {
      expect(mockApiGet).toHaveBeenCalled();
    });

    const micBtn = await screen.findByRole("button", { name: /start voice dictation/i });
    fireEvent.click(micBtn);

    const firstRecognizer = MockSpeechRecognition.latestInstance!;
    expect(firstRecognizer.lang).toBe("ta-IN");

    firstRecognizer.simulateSpeechEvent([
      { transcript: "Idhu mudinja apram", isFinal: true },
    ]);

    const textarea = screen.getByRole("textbox", { name: /your message/i }) as HTMLTextAreaElement;
    await waitFor(() => {
      expect(textarea.value).toBe("Idhu mudinja apram");
    });

    // User switches language dropdown to English mid-session
    const langSelect = screen.getByLabelText(/recognition language/i);
    fireEvent.change(langSelect, { target: { value: "en-IN" } });

    await waitFor(() => {
      const newRecognizer = MockSpeechRecognition.latestInstance!;
      expect(newRecognizer.lang).toBe("en-IN");
    });

    // Speak in English
    const newRecognizer = MockSpeechRecognition.latestInstance!;
    newRecognizer.simulateSpeechEvent([
      { transcript: "please confirm my refund", isFinal: true },
    ]);

    await waitFor(() => {
      expect(textarea.value).toBe("Idhu mudinja apram please confirm my refund");
    });
  });

  it("7. Call with Agent UI exposes language switcher and synchronizes initial call language", async () => {
    render(
      <CallWithAgent
        conversationId="10"
        onClose={vi.fn()}
        initialLanguage="ta-IN"
        preferredLanguage="tanglish"
      />
    );

    // Verify language selector is present with Tamil (ta-IN) selected
    const langSelect = await screen.findByRole("combobox", { name: /call recognition language/i });
    expect((langSelect as HTMLSelectElement).value).toBe("ta-IN");

    // Recognizer initialized with ta-IN
    await waitFor(() => {
      expect(MockSpeechRecognition.latestInstance?.lang).toBe("ta-IN");
    });

    // Switch language to Hindi
    fireEvent.change(langSelect, { target: { value: "hi-IN" } });
    expect((langSelect as HTMLSelectElement).value).toBe("hi-IN");

    // Recognizer restarted with hi-IN
    await waitFor(() => {
      expect(MockSpeechRecognition.latestInstance?.lang).toBe("hi-IN");
    });
  });

  it("8. Silence pauses (no-speech) do not terminate listening session in Chat Mode when speech was spoken", async () => {
    render(<ChatSurface conversationId="10" />);

    const micBtn = await screen.findByRole("button", { name: /start voice dictation/i });
    fireEvent.click(micBtn);

    const recognizer = MockSpeechRecognition.latestInstance!;
    recognizer.simulateSpeechEvent([
      { transcript: "En order", isFinal: true },
    ]);

    // Speech recognition triggers a no-speech event (recoverable silence)
    act(() => {
      recognizer.onerror?.({ error: "no-speech" });
    });

    // The interface should remain in the listening state
    expect(screen.getByRole("button", { name: /stop dictation/i })).toBeInTheDocument();
  });

  it("9. Preserves uncommitted interim words when Chrome triggers onend during natural pauses", async () => {
    mockConversationData.preferred_language = "tanglish";
    render(<ChatSurface conversationId="10" />);

    const micBtn = await screen.findByRole("button", { name: /start voice dictation/i });
    fireEvent.click(micBtn);

    const firstRecognizer = MockSpeechRecognition.latestInstance!;
    const textarea = screen.getByRole("textbox", { name: /your message/i }) as HTMLTextAreaElement;

    // Customer speaks: "Puriyala" is finalized, followed immediately by interim "simple ah sollu"
    firstRecognizer.simulateSpeechEvent([
      { transcript: "Puriyala", isFinal: true },
      { transcript: "simple ah sollu", isFinal: false },
    ]);

    expect(textarea.value).toBe("Puriyala simple ah sollu");

    // Chrome Web Speech API ends the session due to a pause before "simple ah sollu" became isFinal
    firstRecognizer.simulateEnd();

    // The uncommitted interim "simple ah sollu" MUST be preserved and folded into the draft!
    expect(textarea.value).toBe("Puriyala simple ah sollu");

    // Wait for the restart
    await waitFor(() => {
      expect(MockSpeechRecognition.instances.length).toBeGreaterThan(1);
    });

    const secondRecognizer = MockSpeechRecognition.latestInstance!;
    expect(secondRecognizer).not.toBe(firstRecognizer);

    // Customer continues speaking in the restarted session: "En order innum varala"
    secondRecognizer.simulateSpeechEvent([
      { transcript: "En order innum varala", isFinal: true },
    ]);

    // All clauses must be preserved seamlessly without dropping either "Puriyala" or "simple ah sollu"
    await waitFor(() => {
      expect(textarea.value).toBe("Puriyala simple ah sollu En order innum varala");
    });
  });

  it("10. Safe retry with backoff when SpeechRecognition.start() encounters transient audio device contention", async () => {
    render(<ChatSurface conversationId="10" />);

    const micBtn = await screen.findByRole("button", { name: /start voice dictation/i });
    fireEvent.click(micBtn);

    const firstRecognizer = MockSpeechRecognition.latestInstance!;
    firstRecognizer.simulateSpeechEvent([
      { transcript: "Testing audio retry", isFinal: true },
    ]);

    // Make the next start() attempt throw InvalidStateError (Chrome mic hardware still busy)
    MockSpeechRecognition.failNextStarts = 1;

    // Chrome fires onend
    firstRecognizer.simulateEnd();

    // After backoff retry, the recognizer must recover and successfully start a new session
    await waitFor(
      () => {
        const instances = MockSpeechRecognition.instances;
        expect(instances.length).toBeGreaterThan(1);
        const latest = MockSpeechRecognition.latestInstance;
        expect(latest?.started).toBe(true);
      },
      { timeout: 2500 }
    );

    // Stop dictation cleanly
    fireEvent.click(screen.getByRole("button", { name: /stop dictation/i }));
  });

  it("11. Full multi-clause continuous utterance survives multiple onend pause cycles", async () => {
    mockConversationData.preferred_language = "tanglish";
    render(<ChatSurface conversationId="10" />);

    const micBtn = await screen.findByRole("button", { name: /start voice dictation/i });
    fireEvent.click(micBtn);

    const textarea = screen.getByRole("textbox", { name: /your message/i }) as HTMLTextAreaElement;

    // Stage A: First word "Puriyala"
    let currentRec = MockSpeechRecognition.latestInstance!;
    currentRec.simulateSpeechEvent([{ transcript: "Puriyala,", isFinal: true }]);
    expect(textarea.value).toBe("Puriyala,");

    // Stage B: Natural pause, interim "simple ah sollu"
    currentRec.simulateSpeechEvent([
      { transcript: "Puriyala,", isFinal: true },
      { transcript: "simple ah sollu.", isFinal: false },
    ]);
    expect(textarea.value).toBe("Puriyala, simple ah sollu.");

    // Pause causes Chrome onend
    currentRec.simulateEnd();
    expect(textarea.value).toBe("Puriyala, simple ah sollu.");

    // Stage C: Recognizer auto-restarts for next clause
    await waitFor(() => {
      expect(MockSpeechRecognition.instances.length).toBeGreaterThan(1);
    });

    currentRec = MockSpeechRecognition.latestInstance!;
    currentRec.simulateSpeechEvent([{ transcript: "En order innum varala.", isFinal: true }]);

    await waitFor(() => {
      expect(textarea.value).toBe("Puriyala, simple ah sollu. En order innum varala.");
    });

    // Pause causes another onend
    currentRec.simulateEnd();
    expect(textarea.value).toBe("Puriyala, simple ah sollu. En order innum varala.");

    // Stage D: Recognizer auto-restarts for final clause
    await waitFor(() => {
      expect(MockSpeechRecognition.instances.length).toBeGreaterThan(2);
    });

    currentRec = MockSpeechRecognition.latestInstance!;
    currentRec.simulateSpeechEvent([
      { transcript: "Tracking status check panni sollunga", isFinal: true },
    ]);

    await waitFor(() => {
      expect(textarea.value).toBe(
        "Puriyala, simple ah sollu. En order innum varala. Tracking status check panni sollunga"
      );
    });

    // User finishes and clicks stop dictation
    const stopBtn = screen.getByRole("button", { name: /stop dictation/i });
    fireEvent.click(stopBtn);

    expect(textarea.value).toBe(
      "Puriyala, simple ah sollu. En order innum varala. Tracking status check panni sollunga"
    );
  });
});
