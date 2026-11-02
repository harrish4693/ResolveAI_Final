import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { VoiceCallPage } from "@/components/resolve/VoiceCallPage";
import { Workspace } from "@/components/resolve/workspace";
import { CustomerDashboard } from "@/components/resolve/customer";

// Mock dependencies
let mockCurrentUser: any = { id: 1, role: "customer", full_name: "Jane Doe", email: "jane@example.com" };
vi.mock("@/lib/auth", () => ({
  useAuth: () => ({
    user: mockCurrentUser,
    isLoading: false,
    logout: vi.fn(),
  }),
}));

let mockWsHandlers: Record<string, (event: any) => void> = {};
const mockSubscribe = vi.fn((event: string, cb: any) => {
  mockWsHandlers[event] = cb;
  return vi.fn();
});

const mockUseWebSocket = vi.fn(() => ({
  isConnected: true,
  subscribe: mockSubscribe,
  sendTyping: vi.fn(),
  sendVoiceCommand: vi.fn(),
  sendVoiceChunk: vi.fn(),
}));

vi.mock("@/lib/ws", () => ({
  useWebSocket: () => mockUseWebSocket(),
}));

const mockApiPost = vi.fn();
const mockApiGet = vi.fn().mockImplementation((url: string) => {
  if (url === "/tickets/summary") {
    return Promise.resolve({ data: { open: 2, resolved: 5, waiting_for_user: 1 } });
  }
  if (url === "/conversations") {
    return Promise.resolve({
      data: [
        { id: 10, status: "active", subject: "Refund for Order #1042" },
        { id: 11, status: "waiting", subject: "Billing Issue" },
      ],
    });
  }
  return Promise.resolve({ data: {} });
});

vi.mock("@/lib/api", () => ({
  api: {
    get: (url: string) => mockApiGet(url),
    post: (url: string, data: any) => mockApiPost(url, data),
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
    Track: {
      Kind: {
        Audio: "audio",
      },
    },
  };
});

describe("Dedicated Standalone Voice Call Interface", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockCurrentUser = { id: 1, role: "customer", full_name: "Jane Doe", email: "jane@example.com" };
  });

  it("1. renders standalone voice call hub without requiring chat interaction", async () => {
    render(<VoiceCallPage />);

    expect(screen.getByText(/voice call with resolveai/i)).toBeInTheDocument();
    expect(screen.getByText(/talk directly with resolveai/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /start voice call now/i })).toBeInTheDocument();

    // Verify recent open tickets are displayed for one-click voice continuation
    await waitFor(() => {
      expect(screen.getByText(/refund for order #1042/i)).toBeInTheDocument();
    });
  });

  it("2. clicking 'Start Voice Call Now' creates conversation and connects LiveKit room", async () => {
    mockApiPost.mockImplementation((url: string) => {
      if (url === "/conversations") {
        return Promise.resolve({ data: { id: 99, status: "active" } });
      }
      if (url === "/audio/livekit/token") {
        return Promise.resolve({
          data: {
            server_url: "wss://test.livekit.cloud",
            token: "mock-livekit-token-99",
            room_name: "resolveai-convo-99",
          },
        });
      }
      return Promise.resolve({ data: {} });
    });

    render(<VoiceCallPage />);

    const startBtn = screen.getByRole("button", { name: /start voice call now/i });
    fireEvent.click(startBtn);

    await waitFor(() => {
      expect(mockApiPost).toHaveBeenCalledWith("/conversations", expect.objectContaining({
        channel: "voice",
      }));
      expect(mockApiPost).not.toHaveBeenCalledWith("/conversations", expect.objectContaining({
        initial_message: "Customer initiated live voice call",
      }));
      expect(mockApiPost).toHaveBeenCalledWith("/audio/livekit/token", {
        conversation_id: 99,
      });
    });

    // In-call controls and visualizer should now be active
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /end call/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /mute microphone/i })).toBeInTheDocument();
    });
  });

  it("3. auto-connects to specified conversation when initialConversationId is provided", async () => {
    mockApiPost.mockResolvedValueOnce({
      data: {
        server_url: "wss://test.livekit.cloud",
        token: "mock-livekit-token-10",
        room_name: "resolveai-convo-10",
      },
    });

    render(<VoiceCallPage initialConversationId="10" autoStart={true} />);

    await waitFor(() => {
      expect(mockApiPost).toHaveBeenCalledWith("/audio/livekit/token", {
        conversation_id: 10,
      });
    });

    expect(await screen.findByRole("button", { name: /end call/i })).toBeInTheDocument();
  });

  it("4. toggles mute and speaker states during active call", async () => {
    mockApiPost.mockResolvedValueOnce({
      data: {
        server_url: "wss://test.livekit.cloud",
        token: "mock-token",
        room_name: "room-10",
      },
    });

    render(<VoiceCallPage initialConversationId="10" autoStart={true} />);

    const muteBtn = await screen.findByRole("button", { name: /mute microphone/i });
    fireEvent.click(muteBtn);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /unmute microphone/i })).toBeInTheDocument();
    });

    const speakerBtn = screen.getByRole("button", { name: /mute agent voice/i });
    fireEvent.click(speakerBtn);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /unmute agent voice/i })).toBeInTheDocument();
    });
  });

  it("5. toggles live transcript drawer during active call", async () => {
    mockApiPost.mockResolvedValueOnce({
      data: {
        server_url: "wss://test.livekit.cloud",
        token: "mock-token",
        room_name: "room-10",
      },
    });

    render(<VoiceCallPage initialConversationId="10" autoStart={true} />);

    const transcriptToggle = await screen.findByRole("button", { name: /toggle live transcript/i });
    fireEvent.click(transcriptToggle);

    await waitFor(() => {
      expect(screen.getByText(/live call transcript/i)).toBeInTheDocument();
    });
  });

  it("6. ending call shows completed call summary with ticket info", async () => {
    mockApiPost.mockResolvedValueOnce({
      data: {
        server_url: "wss://test.livekit.cloud",
        token: "mock-token",
        room_name: "room-10",
      },
    });

    render(<VoiceCallPage initialConversationId="10" autoStart={true} />);

    const endCallBtn = await screen.findByRole("button", { name: /end call/i });
    fireEvent.click(endCallBtn);

    await waitFor(() => {
      expect(screen.getByText(/voice call completed/i)).toBeInTheDocument();
      expect(screen.getByText(/ticket #10/i)).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /start new call/i })).toBeInTheDocument();
    });
  });

  it("7. handles LiveKit 503 error gracefully with retry option", async () => {
    mockApiPost.mockRejectedValueOnce({
      response: {
        status: 503,
        data: {
          detail: "LiveKit real-time voice service is not configured.",
        },
      },
    });

    render(<VoiceCallPage initialConversationId="10" autoStart={true} />);

    await waitFor(() => {
      expect(screen.getByText(/voice connection error/i)).toBeInTheDocument();
      expect(screen.getByText(/livekit real-time voice service is not configured/i)).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /retry call/i })).toBeInTheDocument();
    });
  });

  it("8. workspace navigation and dashboard contain direct Voice Call entry points", async () => {
    render(
      <Workspace title="Dashboard" active="Dashboard">
        <CustomerDashboard />
      </Workspace>
    );

    // Sidebar navigation has Voice Call
    const navItems = screen.getAllByRole("link", { name: /voice call/i });
    expect(navItems.length).toBeGreaterThan(0);

    // Dashboard hero has Start Voice Call
    const dashboardVoiceBtn = screen.getAllByRole("link", { name: /start voice call/i });
    expect(dashboardVoiceBtn.length).toBeGreaterThan(0);
  });

  it("9. receives tool confirmation request via websocket and displays authorization modal", async () => {
    mockApiPost.mockResolvedValueOnce({
      data: {
        server_url: "wss://test.livekit.cloud",
        token: "mock-token",
        room_name: "room-10",
      },
    });

    render(<VoiceCallPage initialConversationId="10" autoStart={true} />);

    await waitFor(() => {
      expect(mockWsHandlers["TOOL_CONFIRMATION_REQUIRED"]).toBeDefined();
    });

    // Simulate backend requesting confirmation for create_refund_request tool
    mockWsHandlers["TOOL_CONFIRMATION_REQUIRED"]({
      conversation_id: 10,
      data: {
        execution_id: "exec_12345",
        tool_name: "create_refund_request",
      },
    });

    // ConfirmationModal should appear
    expect(await screen.findByText(/action authorization required/i)).toBeInTheDocument();
    expect(screen.getAllByText(/process refund request/i).length).toBeGreaterThanOrEqual(1);

    // Confirm button click
    mockApiPost.mockResolvedValueOnce({ data: { status: "success" } });
    const acceptBtn = screen.getByRole("button", { name: /authorize action/i });
    fireEvent.click(acceptBtn);

    await waitFor(() => {
      expect(mockApiPost).toHaveBeenCalledWith("/conversations/10/tools/exec_12345/confirm", {
        action: "accept",
      });
    });
  });

  it("10. submits customer satisfaction feedback rating after call completion", async () => {
    mockApiPost.mockResolvedValueOnce({
      data: {
        server_url: "wss://test.livekit.cloud",
        token: "mock-token",
        room_name: "room-10",
      },
    });

    render(<VoiceCallPage initialConversationId="10" autoStart={true} />);

    const endCallBtn = await screen.findByRole("button", { name: /end call/i });
    fireEvent.click(endCallBtn);

    await waitFor(() => {
      expect(screen.getByText(/how was your call experience\?/i)).toBeInTheDocument();
    });

    // Click 5th star
    const starButtons = screen.getAllByRole("button").filter((b) => b.querySelector("svg.lucide-star"));
    expect(starButtons.length).toBe(5);
    fireEvent.click(starButtons[4]);

    // Submit feedback
    mockApiPost.mockResolvedValueOnce({ data: { id: 1, rating: 5 } });
    const submitBtn = screen.getByRole("button", { name: /submit feedback/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockApiPost).toHaveBeenCalledWith("/conversations/10/feedback", {
        rating: 5,
        comment: "",
      });
      expect(screen.getByText(/feedback submitted\. thank you/i)).toBeInTheDocument();
    });
  });

  it("11. expert message flagged internal is never passed to speech function or displayed", async () => {
    mockApiPost.mockResolvedValueOnce({
      data: {
        server_url: "wss://test.livekit.cloud",
        token: "mock-token",
        room_name: "room-10",
      },
    });

    render(<VoiceCallPage initialConversationId="10" autoStart={true} />);

    await waitFor(() => {
      expect(mockWsHandlers["NEW_MESSAGE"]).toBeDefined();
    });

    // Simulate backend sending an internal note event
    mockWsHandlers["NEW_MESSAGE"]({
      conversation_id: "10",
      data: {
        id: 999,
        sender_type: "expert",
        content: "SECRET INTERNAL NOTE: Suspected fraudster.",
        is_internal: true,
      },
    });

    // Verify it is NOT in the document or transcript
    expect(screen.queryByText(/suspected fraudster/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/secret internal note/i)).not.toBeInTheDocument();
  });

  it("12. ends call mutually when VOICE_CALL_ENDED WebSocket event is received", async () => {
    mockApiPost.mockResolvedValueOnce({
      data: {
        server_url: "wss://test.livekit.cloud",
        token: "mock-token",
        room_name: "room-10",
      },
    });

    render(<VoiceCallPage initialConversationId="10" autoStart={true} />);

    await waitFor(() => {
      expect(mockWsHandlers["VOICE_CALL_ENDED"]).toBeDefined();
    });

    // Simulate remote party ending call
    mockWsHandlers["VOICE_CALL_ENDED"]({
      conversation_id: 10,
      data: { ended_by: "expert" },
    });

    // Should transition to ended state
    await waitFor(() => {
      expect(screen.getByText(/voice call completed/i)).toBeInTheDocument();
    });
  });

  it("13. routes expert to expert console post-call and hides customer CSAT form", async () => {
    mockCurrentUser = { id: 5, role: "expert", full_name: "Expert John", email: "john@example.com" };

    mockApiPost.mockResolvedValueOnce({
      data: {
        server_url: "wss://test.livekit.cloud",
        token: "mock-expert-token",
        room_name: "room-10",
      },
    });

    render(<VoiceCallPage initialConversationId="10" autoStart={true} />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /end call/i })).toBeInTheDocument();
    });

    // Expert clicks "End Call"
    mockApiPost.mockResolvedValueOnce({ data: { status: "call_ended" } });
    fireEvent.click(screen.getByRole("button", { name: /end call/i }));

    await waitFor(() => {
      expect(screen.getByText(/voice call completed/i)).toBeInTheDocument();
    });

    // Verify customer CSAT rating form is NOT shown for expert
    expect(screen.queryByText(/how was your call experience\?/i)).not.toBeInTheDocument();

    // Verify expert navigation: links to /expert/chat/$id, NOT /chat/$id
    const expertLink = screen.getByRole("link", { name: /return to expert console/i });
    expect(expertLink).toBeInTheDocument();
    expect(expertLink.getAttribute("href")).toBe("/expert/chat/$id");
    expect(screen.queryByRole("link", { name: /view in chat/i })).not.toBeInTheDocument();

    // Verify Back to Queue link
    const queueLink = screen.getByRole("link", { name: /back to queue/i });
    expect(queueLink).toBeInTheDocument();
    expect(queueLink.getAttribute("href")).toBe("/expert/queue");
  });
});

