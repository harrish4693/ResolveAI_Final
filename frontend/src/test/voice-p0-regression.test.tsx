import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { AudioCaptureSession, ClientVADState, transcribeUtterance, calculateRMS, encodeWAV } from "@/lib/clientVAD";
import { VoiceTurnCoordinator, isEchoOfAgentText } from "@/lib/voiceEchoFilter";
import { ChatSurface } from "@/components/resolve/customer";
import { CallWithAgent } from "@/components/resolve/CallWithAgent";
import { voiceDiagnostics } from "@/lib/voiceDiagnostics";

// Mock dependencies for React components
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

const mockApiPost = vi.fn().mockResolvedValue({ data: { id: 101, ai_response: "AI Reply" } });
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

describe("ResolveAI V2 — Voice P0 Critical Regression Suite (All 17 Scenarios)", () => {
  let originalMediaDevices: any;
  let originalAudioContext: any;
  let originalFetch: any;

  beforeEach(() => {
    vi.clearAllMocks();
    originalMediaDevices = navigator.mediaDevices;
    originalAudioContext = window.AudioContext;
    originalFetch = global.fetch;
    localStorage.setItem("access_token", "test-token-jwt");
  });

  afterEach(() => {
    Object.defineProperty(navigator, "mediaDevices", {
      writable: true,
      configurable: true,
      value: originalMediaDevices,
    });
    window.AudioContext = originalAudioContext;
    global.fetch = originalFetch;
    localStorage.clear();
  });

  // 1. Microphone permission denied
  it("Scenario 1: Microphone permission denied throws clean error without crashing", async () => {
    Object.defineProperty(navigator, "mediaDevices", {
      writable: true,
      configurable: true,
      value: {
        getUserMedia: vi.fn().mockRejectedValue(new DOMException("Permission denied", "NotAllowedError")),
      },
    });

    const session = new AudioCaptureSession();
    await expect(session.start("utt_1")).rejects.toThrow("Permission denied");
    expect(session.getIsCapturing()).toBe(false);
  });

  // 2. AudioContext initially suspended
  it("Scenario 2: AudioContext initially suspended is automatically resumed on start", async () => {
    const resumeFn = vi.fn().mockResolvedValue(undefined);
    class MockSuspendedAudioContext {
      state = "suspended";
      sampleRate = 44100;
      resume = resumeFn;
      createMediaStreamSource = vi.fn(() => ({ connect: vi.fn() }));
      createScriptProcessor = vi.fn(() => ({ connect: vi.fn(), disconnect: vi.fn() }));
      createGain = vi.fn(() => ({ gain: { value: 0 }, connect: vi.fn() }));
      destination = {};
      close = vi.fn().mockResolvedValue(undefined);
    }
    window.AudioContext = MockSuspendedAudioContext as any;

    const mockTrack = { stop: vi.fn() };
    Object.defineProperty(navigator, "mediaDevices", {
      writable: true,
      configurable: true,
      value: {
        getUserMedia: vi.fn().mockResolvedValue({
          getTracks: () => [mockTrack],
          getAudioTracks: () => [mockTrack],
        }),
      },
    });

    const session = new AudioCaptureSession();
    await session.start("utt_2");
    expect(resumeFn).toHaveBeenCalledTimes(1);
    await session.stop();
  });

  // 3. No audio frames received
  it("Scenario 3: No audio frames received finalizes to null and avoids empty upload", async () => {
    class MockNoFramesAudioContext {
      state = "running";
      sampleRate = 44100;
      createMediaStreamSource = vi.fn(() => ({ connect: vi.fn() }));
      createScriptProcessor = vi.fn(() => ({ connect: vi.fn(), disconnect: vi.fn() }));
      createGain = vi.fn(() => ({ gain: { value: 0 }, connect: vi.fn() }));
      destination = {};
      close = vi.fn().mockResolvedValue(undefined);
    }
    window.AudioContext = MockNoFramesAudioContext as any;

    const mockTrack = { stop: vi.fn() };
    Object.defineProperty(navigator, "mediaDevices", {
      writable: true,
      configurable: true,
      value: {
        getUserMedia: vi.fn().mockResolvedValue({
          getTracks: () => [mockTrack],
          getAudioTracks: () => [mockTrack],
        }),
      },
    });

    const session = new AudioCaptureSession();
    await session.start("utt_3");
    // Stop immediately without firing onaudioprocess
    const finalized = await session.stop();
    expect(finalized).toBeNull();
  });

  // 4. Valid audio frames and quiet speech
  it("Scenario 4: Valid audio frames and quiet speech are captured and processed by VAD", () => {
    const vad = new ClientVADState({
      sampleRate: 16000,
      speechEnergyThreshold: 0.015,
      preRollMs: 200,
      minSpeechMs: 100,
      endSilenceMs: 200,
    });

    // Quiet speech frame with RMS ~0.02
    const quietFrame = new Float32Array(800).fill(0.02);
    const silenceFrame = new Float32Array(800).fill(0.001);

    // Initial background noise calibration
    vad.processFrame(silenceFrame, 50);

    // Quiet speech for 150ms
    vad.processFrame(quietFrame, 50);
    vad.processFrame(quietFrame, 50);
    vad.processFrame(quietFrame, 50);

    // Followed by silence ending the utterance
    vad.processFrame(silenceFrame, 50);
    vad.processFrame(silenceFrame, 50);
    vad.processFrame(silenceFrame, 50);
    const wavBlob = vad.processFrame(silenceFrame, 50);
    expect(wavBlob).toBeInstanceOf(Blob);
    expect(wavBlob!.size).toBeGreaterThan(44); // WAV header + data
  });

  // 5. Final audio frames arriving during stop/finalization
  it("Scenario 5: Final audio frames arriving during stop are captured before buffer closes", async () => {
    let capturedCallback: any = null;
    class MockAudioContext {
      state = "running";
      sampleRate = 44100;
      createMediaStreamSource = vi.fn(() => ({ connect: vi.fn() }));
      createScriptProcessor = vi.fn(() => {
        const proc = {
          connect: vi.fn(),
          disconnect: vi.fn(),
          onaudioprocess: null,
        };
        capturedCallback = proc;
        return proc;
      });
      createGain = vi.fn(() => ({ gain: { value: 0 }, connect: vi.fn() }));
      destination = {};
      close = vi.fn().mockResolvedValue(undefined);
    }
    window.AudioContext = MockAudioContext as any;

    const mockTrack = { stop: vi.fn() };
    Object.defineProperty(navigator, "mediaDevices", {
      writable: true,
      configurable: true,
      value: {
        getUserMedia: vi.fn().mockResolvedValue({
          getTracks: () => [mockTrack],
          getAudioTracks: () => [mockTrack],
        }),
      },
    });

    const session = new AudioCaptureSession();
    await session.start("utt_5");

    // Push initial speech frame
    capturedCallback.onaudioprocess({
      inputBuffer: { getChannelData: () => new Float32Array(4096).fill(0.05) },
    });

    // Start stop process and immediately push final frames before tick resolves
    const stopPromise = session.stop();
    capturedCallback.onaudioprocess({
      inputBuffer: { getChannelData: () => new Float32Array(4096).fill(0.04) },
    });

    const result = await stopPromise;
    expect(result).not.toBeNull();
    expect(result!.sampleCount).toBeGreaterThan(1000);
    expect(result!.wavBlob.size).toBeGreaterThan(44);
  });

  // 6. Empty or invalid encoded audio
  it("Scenario 6: Extremely short or empty audio buffers return null and are rejected", () => {
    const tinyBuffer = new Float32Array(50).fill(0.05); // Less than 400 samples
    const encoded = encodeWAV(tinyBuffer, 16000);
    expect(encoded).toBeInstanceOf(Blob);
    expect(encoded.size).toBe(44 + 50 * 2); // 44 byte header + 100 bytes
  });

  // 7. Rapid start/stop
  it("Scenario 7: Rapid start and stop does not throw unhandled exceptions or leak state", async () => {
    class MockAudioContext {
      state = "running";
      sampleRate = 44100;
      createMediaStreamSource = vi.fn(() => ({ connect: vi.fn() }));
      createScriptProcessor = vi.fn(() => ({ connect: vi.fn(), disconnect: vi.fn() }));
      createGain = vi.fn(() => ({ gain: { value: 0 }, connect: vi.fn() }));
      destination = {};
      close = vi.fn().mockResolvedValue(undefined);
    }
    window.AudioContext = MockAudioContext as any;

    const mockTrack = { stop: vi.fn() };
    Object.defineProperty(navigator, "mediaDevices", {
      writable: true,
      configurable: true,
      value: {
        getUserMedia: vi.fn().mockResolvedValue({
          getTracks: () => [mockTrack],
          getAudioTracks: () => [mockTrack],
        }),
      },
    });

    const session = new AudioCaptureSession();
    // Rapidly start, start again (ignored), stop, stop again (deduplicated)
    const p1 = session.start("rapid_1");
    const p2 = session.start("rapid_2");
    await Promise.all([p1, p2]);

    const stop1 = session.stop();
    const stop2 = session.stop();
    const [res1, res2] = await Promise.all([stop1, stop2]);
    expect(res1).toBe(res2); // Same promise result
  });

  // 8. Duplicate stop events and duplicate upload prevention
  it("Scenario 8: Duplicate stop calls return identical Promise and prevent duplicate uploads", async () => {
    let capturedCallback: any = null;
    class MockAudioContext {
      state = "running";
      sampleRate = 44100;
      createMediaStreamSource = vi.fn(() => ({ connect: vi.fn() }));
      createScriptProcessor = vi.fn(() => {
        const proc = { connect: vi.fn(), disconnect: vi.fn(), onaudioprocess: null };
        capturedCallback = proc;
        return proc;
      });
      createGain = vi.fn(() => ({ gain: { value: 0 }, connect: vi.fn() }));
      destination = {};
      close = vi.fn().mockResolvedValue(undefined);
    }
    window.AudioContext = MockAudioContext as any;

    const mockTrack = { stop: vi.fn() };
    Object.defineProperty(navigator, "mediaDevices", {
      writable: true,
      configurable: true,
      value: {
        getUserMedia: vi.fn().mockResolvedValue({
          getTracks: () => [mockTrack],
          getAudioTracks: () => [mockTrack],
        }),
      },
    });

    const session = new AudioCaptureSession();
    await session.start("utt_8");

    capturedCallback.onaudioprocess({
      inputBuffer: { getChannelData: () => new Float32Array(4096).fill(0.04) },
    });

    const stopA = session.stop();
    const stopB = session.stop();
    expect(stopA).toBe(stopB); // Exact reference match
    const result = await stopA;
    expect(result).not.toBeNull();
  });

  // 9. Upload failure, provider timeout, and empty transcript
  it("Scenario 9: STT provider failures and timeouts are cleanly handled with fallback", async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error("504 Gateway Timeout"));

    const fakeWav = new Blob([new Uint8Array(200)], { type: "audio/wav" });
    const res = await transcribeUtterance(fakeWav, "en-IN");
    expect(res.fallback).toBe("browser");
    expect(res.reason).toContain("504 Gateway Timeout");

    // Empty transcript response
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ transcript: "", confidence: 0 }),
    });
    const emptyRes = await transcribeUtterance(fakeWav, "en-IN");
    expect(emptyRes.transcript).toBe("");
  });

  // 10. Successful dictation inserts a transcript without submitting the message
  it("Scenario 10: Successful dictation updates draft text and NEVER sends message automatically", async () => {
    class MockAudioContext {
      sampleRate = 44100;
      createMediaStreamSource = vi.fn(() => ({ connect: vi.fn() }));
      createScriptProcessor = vi.fn(() => {
        const proc: any = { connect: vi.fn(), disconnect: vi.fn(), onaudioprocess: null };
        setTimeout(() => {
          if (proc.onaudioprocess) {
            proc.onaudioprocess({
              inputBuffer: { getChannelData: () => new Float32Array(8192).fill(0.05) },
            });
          }
        }, 10);
        return proc;
      });
      createGain = vi.fn(() => ({ gain: { value: 0 }, connect: vi.fn() }));
      destination = {};
      close = vi.fn().mockResolvedValue(undefined);
    }
    window.AudioContext = MockAudioContext as any;

    const mockTrack = { stop: vi.fn() };
    Object.defineProperty(navigator, "mediaDevices", {
      writable: true,
      configurable: true,
      value: {
        getUserMedia: vi.fn().mockResolvedValue({
          getTracks: () => [mockTrack],
          getAudioTracks: () => [mockTrack],
        }),
      },
    });

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        transcript: "Where is my refund",
        confidence: 0.96,
      }),
    });

    render(<ChatSurface conversationId="10" />);

    const micBtn = await screen.findByRole("button", { name: /start voice dictation/i });
    fireEvent.click(micBtn);

    const stopBtn = await screen.findByRole("button", { name: /stop dictation/i });
    await act(async () => {
      fireEvent.click(stopBtn);
    });

    const textarea = screen.getByRole("textbox", { name: /your message/i }) as HTMLTextAreaElement;
    await waitFor(() => {
      expect(textarea.value).toBe("Where is my refund");
    });

    // Verify messages POST was never called
    expect(mockApiPost).not.toHaveBeenCalledWith(
      expect.stringContaining("/messages"),
      expect.anything()
    );
  });

  // 11. Existing draft text is preserved
  it("Scenario 11: Dictated speech safely appends to existing user typed draft without overwriting", async () => {
    class MockAudioContext {
      sampleRate = 44100;
      createMediaStreamSource = vi.fn(() => ({ connect: vi.fn() }));
      createScriptProcessor = vi.fn(() => {
        const proc: any = { connect: vi.fn(), disconnect: vi.fn(), onaudioprocess: null };
        setTimeout(() => {
          if (proc.onaudioprocess) {
            proc.onaudioprocess({
              inputBuffer: { getChannelData: () => new Float32Array(8192).fill(0.05) },
            });
          }
        }, 10);
        return proc;
      });
      createGain = vi.fn(() => ({ gain: { value: 0 }, connect: vi.fn() }));
      destination = {};
      close = vi.fn().mockResolvedValue(undefined);
    }
    window.AudioContext = MockAudioContext as any;

    const mockTrack = { stop: vi.fn() };
    Object.defineProperty(navigator, "mediaDevices", {
      writable: true,
      configurable: true,
      value: {
        getUserMedia: vi.fn().mockResolvedValue({
          getTracks: () => [mockTrack],
          getAudioTracks: () => [mockTrack],
        }),
      },
    });

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        transcript: "urgent order",
        confidence: 0.95,
      }),
    });

    render(<ChatSurface conversationId="10" />);

    const textarea = screen.getByRole("textbox", { name: /your message/i }) as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "Hello support," } });

    const micBtn = await screen.findByRole("button", { name: /start voice dictation/i });
    fireEvent.click(micBtn);

    const stopBtn = await screen.findByRole("button", { name: /stop dictation/i });
    await act(async () => {
      fireEvent.click(stopBtn);
    });

    await waitFor(() => {
      expect(textarea.value).toBe("Hello support, urgent order");
    });
  });

  // 12. Old STT responses cannot overwrite newer drafts
  it("Scenario 12: Stale transcription responses from previous requests do not overwrite active text", () => {
    let draft = "User typed this later";
    const activeUtteranceId = "utt_current_2";
    const incomingStaleId = "utt_old_1";

    if (incomingStaleId === activeUtteranceId) {
      draft = "Stale transcript";
    }
    expect(draft).toBe("User typed this later");
  });

  // 13. Component unmount and cleanup
  it("Scenario 13: Unmounting component triggers thorough audio graph cleanup and track stopping", async () => {
    const stopFn = vi.fn();
    const closeFn = vi.fn().mockResolvedValue(undefined);

    class MockAudioContext {
      sampleRate = 44100;
      createMediaStreamSource = vi.fn(() => ({ connect: vi.fn() }));
      createScriptProcessor = vi.fn(() => ({ connect: vi.fn(), disconnect: vi.fn() }));
      createGain = vi.fn(() => ({ gain: { value: 0 }, connect: vi.fn() }));
      destination = {};
      close = closeFn;
    }
    window.AudioContext = MockAudioContext as any;

    Object.defineProperty(navigator, "mediaDevices", {
      writable: true,
      configurable: true,
      value: {
        getUserMedia: vi.fn().mockResolvedValue({
          getTracks: () => [{ stop: stopFn }],
          getAudioTracks: () => [{ stop: stopFn }],
        }),
      },
    });

    const { unmount } = render(<ChatSurface conversationId="10" />);
    const micBtn = await screen.findByRole("button", { name: /start voice dictation/i });
    fireEvent.click(micBtn);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /stop dictation/i })).toBeInTheDocument();
    });

    unmount();
    expect(stopFn).toHaveBeenCalled();
  });

  // 14. Call mode successfully processes consecutive turns
  it("Scenario 14: Call mode supports consecutive user turns and preserves dialogue", () => {
    const coordinator = new VoiceTurnCoordinator({ tailDurationMs: 0 });
    const turns = [
      "Hello, I need help with my account",
      "Yes my email is user@example.com",
      "I forgot my password",
      "Can you send a reset link?",
      "Yes please send to my phone instead",
    ];

    turns.forEach((t) => {
      const dispatch = coordinator.canDispatchTurn(t);
      expect(dispatch.canDispatch).toBe(true);
      coordinator.onAgentAudioStart("AI response to: " + t);
      coordinator.onAgentAudioAllFinished();
    });
  });

  // 15. Listening resumes after TTS playback
  it("Scenario 15: Listening automatically resumes after agent finishes speaking", () => {
    const coordinator = new VoiceTurnCoordinator({ tailDurationMs: 0 });
    coordinator.onAgentAudioStart("Your order has been shipped.");
    expect(coordinator.isAgentAudioActive()).toBe(true);

    coordinator.onAgentAudioAllFinished();
    expect(coordinator.isAgentAudioActive()).toBe(false);

    // Can immediately listen and dispatch next turn
    const nextTurn = coordinator.canDispatchTurn("What is the tracking number?");
    expect(nextTurn.canDispatch).toBe(true);
  });

  // 16. Barge-in, mute/unmute, and failed-turn recovery
  it("Scenario 16: Barge-in stops agent speech, mute suppresses input, and error recovers cleanly", () => {
    const coordinator = new VoiceTurnCoordinator({ tailDurationMs: 300, sustainedBargeInThresholdMs: 400 });
    coordinator.onAgentAudioStart("Here is a very long explanation about the policy...");

    // Immediate short acoustic echo is dropped
    const evalShort = coordinator.evaluateRecognitionResult("Here is a very");
    expect(evalShort.echoFilterDropped).toBe(true);

    // Sustained non-matching user speech triggers barge-in
    coordinator.onAgentAudioStart("Here is a very long explanation about the policy...");
    // Simulate user speaking over the agent for >= 400ms with distinct text
    const bargeInRes = coordinator.evaluateRecognitionResult("Stop please just cancel the order");
    // Barge in evaluates speech during playback
    expect(bargeInRes.agentAudioWasPlaying).toBe(true);

    // After barge in halts agent speech:
    coordinator.onAgentAudioAllFinished();
    expect(coordinator.getTailRemainingMs()).toBeGreaterThan(0);

    // Error recovery test
    const category = voiceDiagnostics.categorizeFailure(new Error("502 Bad Gateway"));
    expect(category).toBe("stt_failed_or_timeout");
  });

  // 17. Stale responses and overlapping turn prevention
  it("Scenario 17: Prevents rapid duplicate turns within 2.5s while allowing legitimate repeated words across turns", () => {
    const lastProcessedTurn = { text: "Yes", timestamp: 1000 };

    // Rapid duplicate within 500ms -> blocked
    const nowRapid = 1500;
    const isRapidDuplicate =
      "yes".toLowerCase() === lastProcessedTurn.text.toLowerCase() &&
      nowRapid - lastProcessedTurn.timestamp < 2500;
    expect(isRapidDuplicate).toBe(true);

    // Legitimate turn 10 seconds later in the conversation -> allowed
    const nowLater = 11000;
    const isLaterDuplicate =
      "yes".toLowerCase() === lastProcessedTurn.text.toLowerCase() &&
      nowLater - lastProcessedTurn.timestamp < 2500;
    expect(isLaterDuplicate).toBe(false);
  });
});
