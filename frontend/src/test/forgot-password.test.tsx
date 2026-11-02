import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { AuthPage, ForgotPasswordPage, ResetPasswordPage } from "@/components/resolve/auth-pages";

const mockApiPost = vi.fn();
const mockNavigate = vi.fn();
const mockLogin = vi.fn().mockResolvedValue({ id: 1, role: "customer", email: "test@resolveai.com" });

vi.mock("@/lib/api", () => ({
  api: {
    post: (url: string, data: any) => mockApiPost(url, data),
    get: vi.fn(),
  },
}));

vi.mock("@/lib/auth", () => ({
  useAuth: () => ({
    user: null,
    isLoading: false,
    login: mockLogin,
    loginWithGoogle: vi.fn(),
  }),
}));

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => mockNavigate,
  Link: ({ children, to, ...props }: any) => (
    <a href={to} {...props}>
      {children}
    </a>
  ),
}));

describe("Forgot Password Confirmation Mail Suite", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it("1. displays 'Forgot password?' link on sign in page", () => {
    render(<AuthPage register={false} />);
    const forgotLink = screen.getByRole("link", { name: /forgot password\?/i });
    expect(forgotLink).toBeInTheDocument();
    expect(forgotLink).toHaveAttribute("href", "/forgot-password");

    const backHomeLinks = screen.getAllByRole("link", { name: /back to home/i });
    expect(backHomeLinks.length).toBeGreaterThan(0);
    expect(backHomeLinks[0]).toHaveAttribute("href", "/");
  });

  it("2. renders ForgotPasswordPage confirming account email and submits to API", async () => {
    mockApiPost.mockResolvedValueOnce({
      data: {
        message: "Password reset confirmation email generated",
        dev_reset_url: "http://localhost:5173/reset-password?token=mock_jwt_token",
        dev_reset_token: "mock_jwt_token",
      },
    });

    render(<ForgotPasswordPage />);

    expect(screen.getByRole("heading", { name: /confirm account email/i })).toBeInTheDocument();
    expect(screen.getByText("customer@resolveai.com")).toBeInTheDocument();
    const confirmBtn = screen.getByRole("button", { name: /confirm & send reset link/i });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(mockApiPost).toHaveBeenCalledWith("/auth/forgot-password", {
        email: "customer@resolveai.com",
      });
    });

    // Check confirmation screen
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /check your email/i })).toBeInTheDocument();
      expect(screen.getByText("customer@resolveai.com")).toBeInTheDocument();
      expect(screen.getByText(/15 minutes/i)).toBeInTheDocument();
      expect(screen.getByRole("link", { name: /open reset password page/i })).toBeInTheDocument();
    });
  });

  it("3. handles API error gracefully on forgot password submission", async () => {
    mockApiPost.mockRejectedValueOnce({
      response: {
        data: {
          detail: "Unable to process password reset request at this time.",
        },
      },
    });

    render(<ForgotPasswordPage />);
    const confirmBtn = screen.getByRole("button", { name: /confirm & send reset link/i });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(
        screen.getByText(/unable to process password reset request at this time/i)
      ).toBeInTheDocument();
    });
  });

  it("4. ResetPasswordPage validates matching passwords and submits reset", async () => {
    // Set window.location.search to have token
    delete (window as any).location;
    window.location = { search: "?token=valid_test_token" } as any;

    mockApiPost.mockResolvedValueOnce({
      data: { message: "Password has been reset successfully" },
    });

    render(<ResetPasswordPage />);

    expect(screen.getByRole("heading", { name: /set new password/i })).toBeInTheDocument();

    const newPassInput = screen.getByPlaceholderText(/at least 8 characters/i);
    const confirmInput = screen.getByPlaceholderText(/re-enter your new password/i);
    const submitBtn = screen.getByRole("button", { name: /confirm & reset password/i });

    // Test mismatched passwords
    fireEvent.change(newPassInput, { target: { value: "StrongPass1" } });
    fireEvent.change(confirmInput, { target: { value: "DifferentPass2" } });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText(/passwords do not match/i)).toBeInTheDocument();
    });

    // Test matched passwords
    fireEvent.change(confirmInput, { target: { value: "StrongPass1" } });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockApiPost).toHaveBeenCalledWith("/auth/reset-password", {
        token: "valid_test_token",
        new_password: "StrongPass1",
      });
    });

    // Check success state
    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: /password reset successfully!/i })
      ).toBeInTheDocument();
      expect(screen.getByRole("link", { name: /sign in to your account/i })).toBeInTheDocument();
    });
  });

  it("5. confirms already provided account creation email while allowing user to edit it", async () => {
    localStorage.setItem("resolve_account_created_email", "existing_created_user@resolveai.com");

    mockApiPost.mockResolvedValueOnce({
      data: {
        message: "Password reset confirmation email generated",
        dev_reset_url: "http://localhost:5173/reset-password?token=mock_jwt_token",
      },
    });

    render(<ForgotPasswordPage />);

    // Must show Confirm Account Email heading and the pre-existing email
    expect(screen.getByRole("heading", { name: /confirm account email/i })).toBeInTheDocument();
    expect(screen.getByText("existing_created_user@resolveai.com")).toBeInTheDocument();
    expect(screen.getByDisplayValue("existing_created_user@resolveai.com")).toBeInTheDocument();

    // One-click confirmation button
    const confirmBtn = screen.getByRole("button", { name: /confirm & send reset link/i });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(mockApiPost).toHaveBeenCalledWith("/auth/forgot-password", {
        email: "existing_created_user@resolveai.com",
      });
    });

    // Successfully displays confirmation screen
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /check your email/i })).toBeInTheDocument();
      expect(screen.getByText("existing_created_user@resolveai.com")).toBeInTheDocument();
    });
  });

  it("6. allows user to enter email for password reset and submit", async () => {
    mockApiPost.mockResolvedValueOnce({
      data: {
        message: "Password reset confirmation email generated",
        dev_reset_url: "http://localhost:5173/reset-password?token=mock_jwt_token",
        dev_reset_token: "mock_jwt_token",
      },
    });

    render(<ForgotPasswordPage />);
    const emailInput = screen.getByPlaceholderText(/you@example.com/i);
    expect(emailInput).toBeInTheDocument();

    fireEvent.change(emailInput, { target: { value: "user_from_login@resolveai.com" } });
    expect(emailInput).toHaveValue("user_from_login@resolveai.com");

    const confirmBtn = screen.getByRole("button", { name: /confirm & send reset link/i });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(mockApiPost).toHaveBeenCalledWith("/auth/forgot-password", {
        email: "user_from_login@resolveai.com",
      });
    });

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /check your email/i })).toBeInTheDocument();
      expect(screen.getByText("user_from_login@resolveai.com")).toBeInTheDocument();
    });
  });

  it("7. shows email confirmation screen when account creation is completed", async () => {
    mockApiPost.mockResolvedValueOnce({
      data: {
        access_token: "mock_acc_token",
        refresh_token: "mock_ref_token",
      },
    });

    render(<AuthPage register={true} />);

    fireEvent.change(screen.getByPlaceholderText(/your full name/i), {
      target: { value: "New Customer" },
    });
    fireEvent.change(screen.getByPlaceholderText(/you@example.com/i), {
      target: { value: "new_created@resolveai.com" },
    });
    fireEvent.change(screen.getByPlaceholderText(/at least 8 characters/i), {
      target: { value: "StrongPass123" },
    });
    fireEvent.change(screen.getByPlaceholderText(/re-enter your password/i), {
      target: { value: "StrongPass123" },
    });

    const submitBtn = screen.getByRole("button", { name: /create customer account/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockApiPost).toHaveBeenCalledWith("/auth/register", {
        email: "new_created@resolveai.com",
        password: "StrongPass123",
        full_name: "New Customer",
      });
    });

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: /account created successfully!/i })
      ).toBeInTheDocument();
      expect(screen.getByText("new_created@resolveai.com")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /continue to workspace/i })).toBeInTheDocument();
    });

    // Clicking continue to workspace navigates to dashboard
    fireEvent.click(screen.getByRole("button", { name: /continue to workspace/i }));
    expect(mockNavigate).toHaveBeenCalledWith({ to: "/dashboard" });
  });

  it("8. allows user to enter email while at login page and trigger reset link directly", async () => {
    mockApiPost.mockResolvedValueOnce({
      data: {
        message: "Password reset confirmation email generated",
        dev_reset_url: "http://localhost:5173/reset-password?token=mock_jwt_token",
      },
    });

    render(<AuthPage register={false} />);
    const emailInput = screen.getByPlaceholderText(/you@example.com/i);
    fireEvent.change(emailInput, { target: { value: "login_user@resolveai.com" } });

    const sendLinkBtn = screen.getByRole("button", { name: /send link to this email/i });
    expect(sendLinkBtn).toBeInTheDocument();
    fireEvent.click(sendLinkBtn);

    await waitFor(() => {
      expect(mockApiPost).toHaveBeenCalledWith("/auth/forgot-password", {
        email: "login_user@resolveai.com",
      });
    });

    await waitFor(() => {
      expect(screen.getByText(/reset link sent! check your mail/i)).toBeInTheDocument();
      expect(screen.getByText("login_user@resolveai.com")).toBeInTheDocument();
    });
  });
});



