import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { ChatSurface } from "@/components/resolve/customer";

// Mock dependencies
vi.mock("@/lib/auth", () => ({
  useAuth: () => ({
    user: { id: 1, role: "customer", full_name: "Test Customer" },
    isLoading: false,
    logout: vi.fn(),
  }),
}));

vi.mock("@/lib/ws", () => ({
  useWebSocket: () => ({
    isConnected: true,
    subscribe: vi.fn(() => vi.fn()),
    sendTyping: vi.fn(),
    sendVoiceCommand: vi.fn(),
    sendVoiceChunk: vi.fn(),
  }),
}));

const mockApiPost = vi.fn().mockResolvedValue({ data: [] });
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

// Mock SpeechRecognition class
class MockSpeechRecognition {
  lang = "en-IN";
  continuous = true;
  interimResults = true;
  maxAlternatives = 1;
  onstart: (() => void) | null = null;
  onresult: ((event: any) => void) | null = null;
  onerror: ((event: any) => void) | null = null;
  onend: (() => void) | null = null;

  static instance: MockSpeechRecognition | null = null;

  constructor() {
    MockSpeechRecognition.instance = this;
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

  simulateResult(transcript: string, isFinal = true) {
    if (this.onresult) {
      act(() => {
        this.onresult?.({
          results: [
            Object.assign([{ transcript }], { isFinal })
          ],
          resultIndex: 0,
        });
      });
    }
  }

  simulateError(error: string) {
    if (this.onerror) {
      act(() => {
        this.onerror?.({ error });
      });
    }
  }
}

describe("Chat Mode Speech-to-Text Dictation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    MockSpeechRecognition.instance = null;
    (window as any).SpeechRecognition = MockSpeechRecognition;
    delete (window as any).webkitSpeechRecognition;
  });

  afterEach(() => {
    delete (window as any).SpeechRecognition;
    delete (window as any).webkitSpeechRecognition;
  });

  it("1. starts and stops recognition when microphone button is clicked", async () => {
    render(<ChatSurface conversationId="10" />);

    const micBtn = await screen.findByRole("button", { name: /start voice dictation/i });
    expect(micBtn).toBeInTheDocument();

    // Click to start dictation
    fireEvent.click(micBtn);

    expect(MockSpeechRecognition.instance).not.toBeNull();
    expect(MockSpeechRecognition.instance?.start).toHaveBeenCalled();

    // State changes to listening
    expect(screen.getByRole("button", { name: /stop dictation/i })).toBeInTheDocument();
    expect(screen.getByText(/listening/i)).toBeInTheDocument();

    // Click to stop dictation
    fireEvent.click(screen.getByRole("button", { name: /stop dictation/i }));
    expect(MockSpeechRecognition.instance?.stop).toHaveBeenCalled();
  });

  it("2. populates the existing editable draft textarea with recognized speech", async () => {
    render(<ChatSurface conversationId="10" />);

    const micBtn = await screen.findByRole("button", { name: /start voice dictation/i });
    fireEvent.click(micBtn);

    const textarea = screen.getByRole("textbox", { name: /your message/i }) as HTMLTextAreaElement;
    expect(textarea.value).toBe("");

    // Simulate recognized speech
    MockSpeechRecognition.instance?.simulateResult("My package has not arrived yet", true);

    await waitFor(() => {
      expect(textarea.value).toBe("My package has not arrived yet");
    });
  });

  it("3. preserves existing draft text and appends speech with appropriate spacing", async () => {
    render(<ChatSurface conversationId="10" />);

    const textarea = (await screen.findByRole("textbox", { name: /your message/i })) as HTMLTextAreaElement;
    
    // User already typed something manually
    fireEvent.change(textarea, { target: { value: "Hello support team," } });
    expect(textarea.value).toBe("Hello support team,");

    // Click microphone to dictate additional text
    const micBtn = screen.getByRole("button", { name: /start voice dictation/i });
    fireEvent.click(micBtn);

    MockSpeechRecognition.instance?.simulateResult("I need help with my recent payment", true);

    // Should append with space
    await waitFor(() => {
      expect(textarea.value).toBe("Hello support team, I need help with my recent payment");
    });
  });

  it("4. recognition completion does NOT send message automatically", async () => {
    render(<ChatSurface conversationId="10" />);

    const micBtn = await screen.findByRole("button", { name: /start voice dictation/i });
    fireEvent.click(micBtn);

    MockSpeechRecognition.instance?.simulateResult("En order delivery aagala", true);

    // Stop recognition
    fireEvent.click(screen.getByRole("button", { name: /stop dictation/i }));

    // Message should NOT have been sent automatically
    expect(mockApiPost).not.toHaveBeenCalled();

    // Draft remains populated and editable
    const textarea = screen.getByRole("textbox", { name: /your message/i }) as HTMLTextAreaElement;
    await waitFor(() => {
      expect(textarea.value).toBe("En order delivery aagala");
    });
  });

  it("5. customer can edit transcript before sending through existing Send action", async () => {
    render(<ChatSurface conversationId="10" />);

    const micBtn = await screen.findByRole("button", { name: /start voice dictation/i });
    fireEvent.click(micBtn);

    MockSpeechRecognition.instance?.simulateResult("Initial spoken thought", true);

    const textarea = screen.getByRole("textbox", { name: /your message/i }) as HTMLTextAreaElement;
    await waitFor(() => {
      expect(textarea.value).toBe("Initial spoken thought");
    });

    // Customer manually edits the text
    fireEvent.change(textarea, { target: { value: "Initial spoken thought - corrected details" } });

    // Customer sends the message
    const sendBtn = screen.getByRole("button", { name: /send message/i });
    fireEvent.click(sendBtn);

    await waitFor(() => {
      expect(mockApiPost).toHaveBeenCalledWith(
        "/conversations/10/messages",
        expect.objectContaining({ content: "Initial spoken thought - corrected details" })
      );
    });
  });

  it("6. permission-denied and no-speech errors display clear feedback", async () => {
    render(<ChatSurface conversationId="10" />);

    const micBtn = await screen.findByRole("button", { name: /start voice dictation/i });
    
    // Simulate permission denied
    fireEvent.click(micBtn);
    MockSpeechRecognition.instance?.simulateError("not-allowed");

    await waitFor(() => {
      expect(screen.getByText(/microphone permission denied/i)).toBeInTheDocument();
    });

    // Reset and simulate no speech
    fireEvent.click(micBtn);
    MockSpeechRecognition.instance?.simulateError("no-speech");

    await waitFor(() => {
      expect(screen.getByText(/no speech was detected/i)).toBeInTheDocument();
    });
  });

  it("7. unsupported browser displays useful message and keeps text typing available", async () => {
    // Remove SpeechRecognition to simulate unsupported browser
    delete (window as any).SpeechRecognition;
    delete (window as any).webkitSpeechRecognition;

    render(<ChatSurface conversationId="10" />);

    const micBtn = await screen.findByRole("button", { name: /start voice dictation/i });
    fireEvent.click(micBtn);

    await waitFor(() => {
      expect(screen.getByText(/speech recognition is not supported in this browser/i)).toBeInTheDocument();
    });

    // Typing still works normally
    const textarea = screen.getByRole("textbox", { name: /your message/i }) as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "Typing still works fine" } });
    expect(textarea.value).toBe("Typing still works fine");
  });

  it("8. cleans up speech recognition session on unmount", async () => {
    const { unmount } = render(<ChatSurface conversationId="10" />);

    const micBtn = await screen.findByRole("button", { name: /start voice dictation/i });
    fireEvent.click(micBtn);

    const instance = MockSpeechRecognition.instance;
    expect(instance?.start).toHaveBeenCalled();

    // Unmount component while listening
    unmount();

    expect(instance?.abort).toHaveBeenCalled();
  });

  it("9. language selection updates recognition language with default en-IN", async () => {
    render(<ChatSurface conversationId="10" />);

    const langSelect = await screen.findByLabelText(/recognition language/i) as HTMLSelectElement;
    expect(langSelect.value).toBe("en-IN");

    // Select Tamil
    fireEvent.change(langSelect, { target: { value: "ta-IN" } });
    expect(langSelect.value).toBe("ta-IN");

    // Start dictation
    const micBtn = screen.getByRole("button", { name: /start voice dictation/i });
    fireEvent.click(micBtn);

    expect(MockSpeechRecognition.instance?.lang).toBe("ta-IN");
  });

  it("10. normal typed chat works without invoking speech recognition", async () => {
    render(<ChatSurface conversationId="10" />);

    const textarea = (await screen.findByRole("textbox", { name: /your message/i })) as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "Purely typed message without mic" } });

    const sendBtn = screen.getByRole("button", { name: /send message/i });
    fireEvent.click(sendBtn);

    await waitFor(() => {
      expect(mockApiPost).toHaveBeenCalledWith(
        "/conversations/10/messages",
        expect.objectContaining({ content: "Purely typed message without mic" })
      );
    });

    expect(MockSpeechRecognition.instance).toBeNull();
  });

  describe("Server-Side Saaras v4 Real Audio Dictation", () => {
    let originalMediaDevices: any;
    let originalAudioContext: any;
    let originalFetch: any;

    beforeEach(() => {
      delete (window as any).SpeechRecognition;
      delete (window as any).webkitSpeechRecognition;

      originalMediaDevices = navigator.mediaDevices;
      originalAudioContext = window.AudioContext;
      originalFetch = global.fetch;

      const mockTrack = { stop: vi.fn() };
      const mockStream = {
        getTracks: vi.fn(() => [mockTrack]),
      };
      Object.defineProperty(navigator, "mediaDevices", {
        writable: true,
        configurable: true,
        value: {
          getUserMedia: vi.fn().mockResolvedValue(mockStream),
        },
      });

      class MockAudioContext {
        sampleRate = 44100;
        createMediaStreamSource = vi.fn(() => ({
          connect: vi.fn(),
        }));
        createScriptProcessor = vi.fn(() => {
          const proc: any = {
            connect: vi.fn(),
            disconnect: vi.fn(),
            onaudioprocess: null,
          };
          // Immediately simulate audio processing frames
          setTimeout(() => {
            if (proc.onaudioprocess) {
              const buffer = {
                getChannelData: () => new Float32Array(8192).fill(0.04),
              };
              proc.onaudioprocess({ inputBuffer: buffer });
            }
          }, 10);
          return proc;
        });
        close = vi.fn().mockResolvedValue(undefined);
      }
      (window as any).AudioContext = MockAudioContext;

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          transcript: "En order delivery eppo varum bro",
          language_code: "ta-IN",
          confidence: 0.94,
        }),
      });
    });

    afterEach(() => {
      Object.defineProperty(navigator, "mediaDevices", {
        writable: true,
        configurable: true,
        value: originalMediaDevices,
      });
      window.AudioContext = originalAudioContext;
      global.fetch = originalFetch;
    });

    it("11. captures real microphone audio and populates composer via server STT", async () => {
      render(<ChatSurface conversationId="10" />);

      const micBtn = await screen.findByRole("button", { name: /start voice dictation/i });
      fireEvent.click(micBtn);

      await waitFor(() => {
        expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledWith({
          audio: expect.objectContaining({ echoCancellation: true }),
        });
        expect(screen.getByRole("button", { name: /stop dictation/i })).toBeInTheDocument();
      });

      // Stop dictation
      const stopBtn = screen.getByRole("button", { name: /stop dictation/i });
      await act(async () => {
        fireEvent.click(stopBtn);
      });

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          "/api/audio/stt",
          expect.objectContaining({ method: "POST" })
        );
      });

      const textarea = screen.getByRole("textbox", { name: /your message/i }) as HTMLTextAreaElement;
      await waitFor(() => {
        expect(textarea.value).toBe("En order delivery eppo varum bro");
      });

      // Message is NOT sent automatically
      expect(mockApiPost).not.toHaveBeenCalled();
    });

    it("12. handles microphone permission denied error gracefully", async () => {
      Object.defineProperty(navigator, "mediaDevices", {
        writable: true,
        configurable: true,
        value: {
          getUserMedia: vi.fn().mockRejectedValue(new Error("Permission denied")),
        },
      });

      render(<ChatSurface conversationId="10" />);

      const micBtn = await screen.findByRole("button", { name: /start voice dictation/i });
      fireEvent.click(micBtn);

      await waitFor(() => {
        expect(screen.getByText(/microphone permission denied/i)).toBeInTheDocument();
      });
    });
  });
});
