import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { HelpPage } from "@/components/resolve/customer";

let mockUser: any = { id: 1, role: "customer", email: "cust@example.com" };

vi.mock("@/lib/auth", () => ({
  useAuth: () => ({
    user: mockUser,
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
    get: vi.fn().mockResolvedValue({
      data: [
        {
          id: 1,
          title: "POL-001 — Confidential Internal Service Charter",
          category: "SERVICE_STANDARDS",
          content: "Internal guidance only. Never pretend to be human. Live data to fetch.",
        },
      ],
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

describe("Customer Help Center vs Internal Knowledge Visibility", () => {
  beforeEach(() => {
    mockUser = { id: 1, role: "customer", email: "cust@example.com" };
    vi.clearAllMocks();
  });

  it("1. customer sees zero knowledge articles or FAQs", async () => {
    render(<HelpPage />);

    // Support Hub headings & actions are present
    expect(screen.getByText(/How can we help you today\?/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Instant Voice Call/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /AI Support Chat/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /My Support Tickets/i })).toBeInTheDocument();

    // Zero internal knowledge articles
    expect(
      screen.queryByText(/POL-001 — Confidential Internal Service Charter/i)
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/Never pretend to be human/i)).not.toBeInTheDocument();

    // Zero FAQ articles shown to customer
    expect(
      screen.queryByText(/Frequently Asked Questions/i)
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/How do I reset or change my account password\?/i)
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/What payment methods are supported\?/i)
    ).not.toBeInTheDocument();
  });

  it("2. customer has direct support action links (Call, Chat, Tickets)", async () => {
    render(<HelpPage />);

    expect(screen.getByRole("link", { name: /start voice call/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /start ai chat/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /view my tickets/i })).toBeInTheDocument();
  });

  it("3. staff user (admin) sees internal knowledge base articles", async () => {
    mockUser = { id: 99, role: "admin", email: "admin@example.com" };
    render(<HelpPage />);

    const article = await screen.findByText(
      /POL-001 — Confidential Internal Service Charter/i
    );
    expect(article).toBeInTheDocument();
    expect(
      screen.getByText(/Internal Knowledge Base & SOPs/i)
    ).toBeInTheDocument();
  });
});
