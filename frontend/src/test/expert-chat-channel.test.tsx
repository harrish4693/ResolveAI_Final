import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { ChatSurface } from "@/components/resolve/customer";
import { ExpertConsole } from "@/components/resolve/operations";

vi.mock("@/lib/auth", () => ({
  useAuth: () => ({
    user: { id: 2, role: "expert", full_name: "Expert Alice" },
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

let mockConversationData: any = {};
let mockHandoffData: any = {};
let mockContextData: any = {};

vi.mock("@/lib/api", () => ({
  api: {
    get: vi.fn((url: string) => {
      if (url.includes("/messages")) {
        return Promise.resolve({ data: [] });
      }
      if (url.includes("/context")) {
        return Promise.resolve({ data: mockContextData });
      }
      if (url.includes("/handoffs/conversation/")) {
        return Promise.resolve({ data: mockHandoffData });
      }
      if (url.includes("/conversations/")) {
        return Promise.resolve({ data: mockConversationData });
      }
      return Promise.resolve({ data: {} });
    }),
    post: vi.fn(() => Promise.resolve({ data: {} })),
  },
}));

describe("Expert Chat Call-Channel Indicator Regression Suite", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockConversationData = {
      id: 201,
      channel: "voice",
      subject: "Voice Call with ResolveAI",
      status: "in_progress",
      workflow_state: "with_expert",
      created_at: new Date().toISOString(),
    };
    mockHandoffData = {
      id: 55,
      conversation_id: 201,
      category: "Billing",
      priority: "high",
      channel: "voice",
      status: "assigned",
    };
    mockContextData = {
      customer: { id: 1, name: "John Doe", email: "john@example.com", account_status: "Active" },
      active_ticket: {
        id: 201,
        category: "Billing",
        priority: "high",
        reason: "Double billing dispute",
        channel: "voice",
      },
      ai_context: { intent: "Billing Dispute", sentiment: "Frustrated", summary: "Disputed charge" },
      ticket_history: [],
    };
  });

  it("1. ChatSurface renders a clear 'Voice Call' badge with phone icon for voice-originated calls", async () => {
    mockConversationData.channel = "voice";

    render(<ChatSurface expert conversationId="201" />);

    const badge = await screen.findByTestId("chat-header-channel-badge");
    expect(badge).toBeInTheDocument();
    expect(badge.textContent).toMatch(/voice call/i);

    const metricIcon = await screen.findByTestId("chat-header-metric-icon");
    expect(metricIcon).toHaveClass("text-emerald-600");
  });

  it("2. ChatSurface renders a 'Chat' badge with message icon for text-originated conversations", async () => {
    mockConversationData.channel = "text";
    mockConversationData.subject = "Order Status Inquiry";

    render(<ChatSurface expert conversationId="201" />);

    const badge = await screen.findByTestId("chat-header-channel-badge");
    expect(badge).toBeInTheDocument();
    expect(badge.textContent).toMatch(/chat/i);
    expect(badge.textContent).not.toMatch(/voice call/i);
  });

  it("3. ExpertConsole displays 'Voice Call' badges in both header and context sidebar for voice calls", async () => {
    mockConversationData.channel = "voice";
    mockHandoffData.channel = "voice";
    mockContextData.active_ticket.channel = "voice";

    render(<ExpertConsole id="201" />);

    // Header channel badge
    const headerBadge = await screen.findByTestId("expert-header-channel-badge");
    expect(headerBadge).toBeInTheDocument();
    expect(headerBadge.textContent).toMatch(/voice call/i);

    // Sidebar Ticket Information channel badge
    const sidebarBadge = await screen.findByTestId("expert-sidebar-channel-badge");
    expect(sidebarBadge).toBeInTheDocument();
    expect(sidebarBadge.textContent).toMatch(/voice call/i);

    // Live Voice Interface action button is present and highlighted
    const voiceLink = screen.getByTitle(/open full dedicated voice interface for this call/i);
    expect(voiceLink).toBeInTheDocument();
    expect(voiceLink.textContent).toMatch(/live voice interface/i);
  });

  it("4. ExpertConsole displays 'Chat' badges in header and sidebar for text-originated escalations", async () => {
    mockConversationData.channel = "text";
    mockConversationData.subject = "General Query";
    mockHandoffData.channel = "text";
    mockContextData.active_ticket.channel = "text";

    render(<ExpertConsole id="201" />);

    const headerBadge = await screen.findByTestId("expert-header-channel-badge");
    expect(headerBadge).toBeInTheDocument();
    expect(headerBadge.textContent).toMatch(/chat/i);
    expect(headerBadge.textContent).not.toMatch(/voice call/i);

    const sidebarBadge = await screen.findByTestId("expert-sidebar-channel-badge");
    expect(sidebarBadge).toBeInTheDocument();
    expect(sidebarBadge.textContent).toMatch(/chat/i);
  });

  it("5. Persists and displays 'Voice Call' channel correctly after reload/refresh using active ticket context", async () => {
    // Simulate initial conversation loading with channel missing, but context returning channel="voice"
    mockConversationData = {
      id: 201,
      status: "in_progress",
      workflow_state: "with_expert",
      created_at: new Date().toISOString(),
    };
    mockHandoffData = { id: 55, conversation_id: 201, channel: "voice" };
    mockContextData.active_ticket.channel = "voice";

    render(<ExpertConsole id="201" />);

    const headerBadge = await screen.findByTestId("expert-header-channel-badge");
    expect(headerBadge.textContent).toMatch(/voice call/i);

    const sidebarBadge = await screen.findByTestId("expert-sidebar-channel-badge");
    expect(sidebarBadge.textContent).toMatch(/voice call/i);
  });
});

