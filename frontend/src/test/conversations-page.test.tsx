import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ConversationsPage } from "@/components/resolve/customer";

const mockConversations = [
  {
    id: 101,
    subject: "Voice Call with ResolveAI",
    status: "resolved",
    channel: "voice",
    created_at: "2026-10-18T10:00:00Z",
    updated_at: "2026-10-18T10:15:00Z",
  },
  {
    id: 102,
    subject: "Return package for Order #9021",
    status: "open",
    channel: "text",
    created_at: "2026-10-19T09:00:00Z",
    updated_at: "2026-10-19T09:30:00Z",
  },
  {
    id: 103,
    subject: "Voice Call - Billing inquiry",
    status: "open",
    channel: "voice",
    created_at: "2026-10-19T11:00:00Z",
    updated_at: "2026-10-19T11:20:00Z",
  },
];

vi.mock("@/lib/auth", () => ({
  useAuth: () => ({
    user: { id: 1, role: "customer", email: "cust@example.com" },
    isLoading: false,
    logout: vi.fn(),
  }),
}));

vi.mock("@/lib/ws", () => ({
  useWebSocket: () => ({
    isConnected: true,
  }),
}));

vi.mock("@/lib/api", () => ({
  api: {
    get: vi.fn().mockImplementation((url: string) => {
      if (url === "/conversations") {
        return Promise.resolve({ data: mockConversations });
      }
      return Promise.resolve({ data: [] });
    }),
  },
}));

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => vi.fn(),
  Link: ({ children, to, ...props }: any) => (
    <a href={to} {...props}>
      {children}
    </a>
  ),
}));

describe("ConversationsPage Voice Call & Channel Filtering", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("1. renders conversations list with channel badges and filter segments", async () => {
    render(<ConversationsPage />);

    await waitFor(() => {
      expect(screen.getByText(/Voice Call with ResolveAI/i)).toBeInTheDocument();
      expect(screen.getByText(/Return package for Order #9021/i)).toBeInTheDocument();
    });

    // Check that Voice Calls and Chat segments exist
    expect(screen.getByRole("button", { name: "Voice Calls" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Chat" })).toBeInTheDocument();

    // Check channel badges in table
    const voiceBadges = screen.getAllByText("Voice Call");
    expect(voiceBadges.length).toBeGreaterThanOrEqual(2);
    const chatElements = screen.getAllByText("Chat");
    expect(chatElements.length).toBeGreaterThanOrEqual(2);
  });

  it("2. clicking 'Voice Calls' filters list to only voice conversations", async () => {
    render(<ConversationsPage />);

    await waitFor(() => {
      expect(screen.getByText(/Voice Call with ResolveAI/i)).toBeInTheDocument();
    });

    // Click 'Voice Calls' filter
    const voiceFilterBtn = screen.getByRole("button", { name: "Voice Calls" });
    fireEvent.click(voiceFilterBtn);

    // Voice calls should remain visible
    expect(screen.getByText(/Voice Call with ResolveAI/i)).toBeInTheDocument();
    expect(screen.getByText(/Voice Call - Billing inquiry/i)).toBeInTheDocument();

    // Text chat should be filtered out
    expect(screen.queryByText(/Return package for Order #9021/i)).not.toBeInTheDocument();
  });

  it("3. clicking 'Chat' filters list to only text conversations", async () => {
    render(<ConversationsPage />);

    await waitFor(() => {
      expect(screen.getByText(/Return package for Order #9021/i)).toBeInTheDocument();
    });

    // Click 'Chat' filter
    const chatFilterBtn = screen.getByRole("button", { name: "Chat" });
    fireEvent.click(chatFilterBtn);

    // Text chat should remain visible
    expect(screen.getByText(/Return package for Order #9021/i)).toBeInTheDocument();

    // Voice calls should be filtered out
    expect(screen.queryByText(/Voice Call with ResolveAI/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Voice Call - Billing inquiry/i)).not.toBeInTheDocument();
  });

  it("4. can combine Voice Call filter with status filter", async () => {
    render(<ConversationsPage />);

    await waitFor(() => {
      expect(screen.getByText(/Voice Call with ResolveAI/i)).toBeInTheDocument();
    });

    // Filter to Voice Calls
    fireEvent.click(screen.getByRole("button", { name: "Voice Calls" }));
    // Filter to Resolved
    fireEvent.click(screen.getByRole("button", { name: "Resolved" }));

    // Resolved voice call should remain
    expect(screen.getByText(/Voice Call with ResolveAI/i)).toBeInTheDocument();

    // Open voice call should be filtered out
    expect(screen.queryByText(/Voice Call - Billing inquiry/i)).not.toBeInTheDocument();
  });
});
