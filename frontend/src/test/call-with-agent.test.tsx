import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ChatSurface } from "@/components/resolve/customer";

// Mock dependencies
vi.mock("@/lib/auth", () => ({
  useAuth: () => ({
    user: { id: 1, role: "customer", full_name: "Jane Doe" },
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

const mockApiPost = vi.fn();
const mockApiGet = vi.fn().mockImplementation((url: string) => {
  if (url.includes("/messages")) {
    return Promise.resolve({ data: [] });
  }
  return Promise.resolve({
    data: { id: 10, status: "in_progress", workflow_state: "asking_user", subject: "Order Help" },
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

// Mock livekit-client
vi.mock("livekit-client", () => {
  class MockRoom {
    on = vi.fn();
    connect = vi.fn().mockResolvedValue(undefined);
    disconnect = vi.fn();
    localParticipant = {
      setMicrophoneEnabled: vi.fn().mockResolvedValue(undefined),
    };
  }
  return {
    Room: MockRoom,
    RoomEvent: {
      TrackSubscribed: "trackSubscribed",
      TrackUnsubscribed: "trackUnsubscribed",
      ActiveSpeakersChanged: "activeSpeakersChanged",
      Disconnected: "disconnected",
    },
    Track: {
      Kind: {
        Audio: "audio",
      },
    },
  };
});

describe("Call with Agent Mode Integration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("1. renders Call with Agent button in chat header for active conversation", async () => {
    render(<ChatSurface conversationId="10" />);

    const callBtn = await screen.findByRole("button", { name: /call with agent/i });
    expect(callBtn).toBeInTheDocument();
  });

  it("2. clicking Call with Agent toggles call mode and fetches LiveKit token", async () => {
    mockApiPost.mockResolvedValueOnce({
      data: {
        server_url: "wss://test.livekit.cloud",
        token: "mock-livekit-jwt-token",
        room_name: "resolveai-convo-10",
      },
    });

    render(<ChatSurface conversationId="10" />);

    const callBtn = await screen.findByRole("button", { name: /call with agent/i });
    fireEvent.click(callBtn);

    // Call surface should appear
    await waitFor(() => {
      expect(mockApiPost).toHaveBeenCalledWith("/audio/livekit/token", {
        conversation_id: 10,
      });
    });

    expect(screen.getByText(/resolveai voice assistant/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /end call/i })).toBeInTheDocument();
  });

  it("3. displays graceful feedback when LiveKit voice service is not configured (503)", async () => {
    mockApiPost.mockRejectedValueOnce({
      response: {
        status: 503,
        data: {
          detail: "LiveKit real-time voice service is not configured.",
        },
      },
    });

    render(<ChatSurface conversationId="10" />);

    const callBtn = await screen.findByRole("button", { name: /call with agent/i });
    fireEvent.click(callBtn);

    await waitFor(() => {
      expect(screen.getByText(/livekit real-time voice service is not configured/i)).toBeInTheDocument();
    });

    // Close call button should be present
    const closeBtn = screen.getByRole("button", { name: /close call/i });
    expect(closeBtn).toBeInTheDocument();
    fireEvent.click(closeBtn);

    // Exits call mode back to chat
    await waitFor(() => {
      expect(screen.queryByText(/resolveai voice assistant/i)).not.toBeInTheDocument();
    });
  });

  it("4. ending call returns back to normal chat mode", async () => {
    mockApiPost.mockResolvedValueOnce({
      data: {
        server_url: "wss://test.livekit.cloud",
        token: "mock-livekit-jwt-token",
        room_name: "resolveai-convo-10",
      },
    });

    render(<ChatSurface conversationId="10" />);

    const callBtn = await screen.findByRole("button", { name: /call with agent/i });
    fireEvent.click(callBtn);

    const endCallBtn = await screen.findByRole("button", { name: /end call/i });
    fireEvent.click(endCallBtn);

    await waitFor(() => {
      expect(screen.queryByText(/resolveai voice assistant/i)).not.toBeInTheDocument();
    });

    // Chat mode remains operational
    expect(screen.getByRole("textbox", { name: /your message/i })).toBeInTheDocument();
  });

  it("5. initializes real microphone audio capture with AudioContext and Client VAD", async () => {
    mockApiPost.mockResolvedValueOnce({
      data: {
        server_url: "wss://test.livekit.cloud",
        token: "mock-livekit-jwt-token",
        room_name: "resolveai-convo-10",
      },
    });

    const mockTrack = { stop: vi.fn(), enabled: true };
    const mockStream = {
      getTracks: vi.fn(() => [mockTrack]),
      getAudioTracks: vi.fn(() => [mockTrack]),
    };
    const getUserMediaMock = vi.fn().mockResolvedValue(mockStream);
    Object.defineProperty(navigator, "mediaDevices", {
      writable: true,
      configurable: true,
      value: { getUserMedia: getUserMediaMock },
    });

    const originalAudioContext = window.AudioContext;
    class MockAudioContext {
      sampleRate = 44100;
      createMediaStreamSource = vi.fn(() => ({ connect: vi.fn() }));
      createScriptProcessor = vi.fn(() => ({
        connect: vi.fn(),
        disconnect: vi.fn(),
        onaudioprocess: null,
      }));
      close = vi.fn().mockResolvedValue(undefined);
    }
    (window as any).AudioContext = MockAudioContext;

    try {
      render(<ChatSurface conversationId="10" />);

      const callBtn = await screen.findByRole("button", { name: /call with agent/i });
      fireEvent.click(callBtn);

      await waitFor(() => {
        expect(getUserMediaMock).toHaveBeenCalledWith(
          expect.objectContaining({
            audio: expect.objectContaining({ echoCancellation: true }),
          })
        );
      });
    } finally {
      window.AudioContext = originalAudioContext;
    }
  });
});
