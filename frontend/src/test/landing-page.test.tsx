import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { LandingPage } from "@/components/resolve/LandingPage";

vi.mock("@/lib/auth", () => ({
  useAuth: () => ({
    user: null,
    isLoading: false,
  }),
}));

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => vi.fn(),
  Link: ({ children, to, ...props }: any) => (
    <a href={to} {...props}>
      {children}
    </a>
  ),
}));

describe("ResolveAI Simple Professional Landing Page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("1. renders hero title and clear description about the project", () => {
    render(<LandingPage />);

    expect(
      screen.getByRole("heading", {
        name: /intelligent customer support,\s*powered by voice ai/i,
      })
    ).toBeInTheDocument();

    expect(
      screen.getByText(/talk or chat with an intelligent ai support agent/i)
    ).toBeInTheDocument();
  });

  it("2. renders primary call-to-action buttons for voice call and support chat", () => {
    render(<LandingPage />);

    const voiceBtns = screen.getAllByRole("link", { name: /start voice call/i });
    expect(voiceBtns.length).toBeGreaterThan(0);
    expect(voiceBtns[0]).toHaveAttribute("href", "/call");

    const chatBtn = screen.getByRole("link", { name: /open support chat/i });
    expect(chatBtn).toBeInTheDocument();
  });

  it("3. displays the 3 simple project highlights", () => {
    render(<LandingPage />);

    expect(screen.getByRole("heading", { name: /natural voice calls/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /ai support chat/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /human expert handoff/i })).toBeInTheDocument();
  });

  it("4. displays 3-step 'How It Works' section", () => {
    render(<LandingPage />);

    expect(screen.getByRole("heading", { name: /how it works/i })).toBeInTheDocument();
    expect(screen.getByText(/connect via voice or chat/i)).toBeInTheDocument();
    expect(screen.getByText(/get instant resolution/i)).toBeInTheDocument();
    expect(screen.getByText(/track & stay updated/i)).toBeInTheDocument();
  });

  it("5. displays clean footer with quick links", () => {
    render(<LandingPage />);

    const footerCallLinks = screen.getAllByRole("link", { name: /voice call/i });
    expect(footerCallLinks.length).toBeGreaterThan(0);
    const helpLinks = screen.getAllByRole("link", { name: /help/i });
    expect(helpLinks.length).toBeGreaterThan(0);
  });
});
