import { useState, useEffect, type FormEvent } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import {
  Eye,
  EyeOff,
  ArrowRight,
  Globe2,
  Loader2,
  Mail,
  CheckCircle2,
  KeyRound,
  ArrowLeft,
  ShieldCheck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Logo } from "./workspace";
import art from "@/assets/conversation-art.jpg";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export function AuthPage({ register = false }: { register?: boolean }) {
  const [visible, setVisible] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);
  const [registeredSuccess, setRegisteredSuccess] = useState(false);
  const [registeredEmail, setRegisteredEmail] = useState("");
  const [registeredRole, setRegisteredRole] = useState<string>("customer");
  const [loginResetSent, setLoginResetSent] = useState(false);
  const [loginResetEmail, setLoginResetEmail] = useState("");
  const [loginResetLoading, setLoginResetLoading] = useState(false);
  const [loginResetDevUrl, setLoginResetDevUrl] = useState<string | null>(null);

  async function handleSendResetFromLogin() {
    const emailToSend = emailInput.trim();
    if (!emailToSend) {
      setError("Please enter your email address above to receive a password reset link.");
      return;
    }
    setError("");
    setLoginResetLoading(true);
    try {
      const res = await api.post("/auth/forgot-password", { email: emailToSend });
      setLoginResetSent(true);
      setLoginResetEmail(emailToSend);
      if (res.data?.dev_reset_url) {
        setLoginResetDevUrl(res.data.dev_reset_url);
      }
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Failed to send reset link.");
    } finally {
      setLoginResetLoading(false);
    }
  }
  const [emailInput, setEmailInput] = useState(() => {
    if (typeof window !== "undefined" && !register) {
      return (
        localStorage.getItem("resolve_account_created_email") ||
        localStorage.getItem("resolve_account_email") ||
        "customer@resolveai.com"
      );
    }
    return "";
  });
  const [passwordInput, setPasswordInput] = useState("");
  const { user, login, loginWithGoogle, isLoading } = useAuth();
  const navigate = useNavigate();

  // If already authenticated, redirect to role dashboard (unless viewing registration confirmation)
  useEffect(() => {
    if (!isLoading && user && !registeredSuccess) {
      if (user.role === "expert") {
        navigate({ to: "/expert", replace: true });
      } else if (user.role === "admin") {
        navigate({ to: "/admin", replace: true });
      } else {
        navigate({ to: "/dashboard", replace: true });
      }
    }
  }, [user, isLoading, navigate, registeredSuccess]);

  // Handle Google OAuth query params
  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    const token = params.get("access_token");
    const refresh = params.get("refresh_token");
    const oauthError = params.get("error");

    if (oauthError) {
      setError(decodeURIComponent(oauthError.replace(/\+/g, " ")));
      window.history.replaceState({}, document.title, window.location.pathname);
    } else if (token && refresh) {
      setLoading(true);
      login(token, refresh)
        .then((user) => {
          window.history.replaceState({}, document.title, window.location.pathname);
          if (user?.role === "expert") {
            navigate({ to: "/expert" });
          } else if (user?.role === "admin") {
            navigate({ to: "/admin" });
          } else {
            navigate({ to: "/dashboard" });
          }
        })
        .catch(() => setError("Failed to complete Google Sign-In"))
        .finally(() => setLoading(false));
    }
  }, [login, navigate]);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    setLoading(true);

    const data = new FormData(e.currentTarget);
    const email = (emailInput || String(data.get("email"))).trim();
    const password = passwordInput || String(data.get("password"));

    if (register) {
      const confirm = String(data.get("confirm"));
      const name = String(data.get("name")).trim();
      if (password !== confirm) {
        setError("Passwords don’t match. Please try again.");
        setLoading(false);
        return;
      }

      try {
        const res = await api.post("/auth/register", {
          email,
          password,
          full_name: name,
        });
        if (typeof window !== "undefined") {
          localStorage.setItem("resolve_account_created_email", email);
          localStorage.setItem("resolve_account_email", email);
        }
        const { access_token, refresh_token } = res.data;
        const loggedInUser = await login(access_token, refresh_token);
        if (!loggedInUser) {
          setError("Failed to load user profile. Please try logging in again.");
          return;
        }
        setRegisteredEmail(email);
        setRegisteredRole(loggedInUser.role);
        setRegisteredSuccess(true);
      } catch (err: any) {
        const detail = err.response?.data?.detail;
        if (!err.response) {
          setError("Cannot reach backend server. Please make sure the backend is running.");
        } else {
          setError(typeof detail === "string" ? detail : "Registration failed. Please try again.");
        }
      } finally {
        setLoading(false);
      }
    } else {
      try {
        const res = await api.post("/auth/login", {
          email,
          password,
        });
        if (typeof window !== "undefined") {
          localStorage.setItem("resolve_account_email", email);
        }
        const { access_token, refresh_token } = res.data;
        const loggedInUser = await login(access_token, refresh_token);
        if (!loggedInUser) {
          setError("Failed to load user profile. Please try logging in again.");
          return;
        }
        if (loggedInUser.role === "expert") {
          navigate({ to: "/expert" });
        } else if (loggedInUser.role === "admin") {
          navigate({ to: "/admin" });
        } else {
          navigate({ to: "/dashboard" });
        }
      } catch (err: any) {
        const detail = err.response?.data?.detail;
        if (!err.response) {
          setError("Cannot reach backend server. Please make sure the backend is running.");
        } else {
          setError(typeof detail === "string" ? detail : "Invalid email or password.");
        }
      } finally {
        setLoading(false);
      }
    }
  }

  const handleGoogleAuth = async () => {
    try {
      setGoogleLoading(true);
      setError("");
      await loginWithGoogle();
    } catch {
      setError("Unable to connect to Google authentication.");
      setGoogleLoading(false);
    }
  };

  return (
    <main className="auth-page">
      <section className="auth-branding">
        <Link to="/">
          <Logo />
        </Link>
        <div>
          <span className="eyebrow">Agentic Multilingual Customer Support</span>
          <h1 className="mt-5">Customer support that understands every conversation.</h1>
          <p>
            From the first question to the final resolution. Helpful answers, intelligent support,
            and a human touch when it matters.
          </p>
        </div>
        <img
          src={art}
          alt="ResolveAI conversation illustration"
          className="auth-art"
          width={1024}
          height={1024}
        />
        <p className="text-xs flex items-center gap-2">
          <Globe2 className="size-4" />
          English · Tanglish · Hinglish
        </p>
      </section>
      <section className="auth-form-side">
        <div className="auth-form">
          <div className="mb-4">
            <Link
              to="/"
              className="inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors py-1 px-2 rounded-lg hover:bg-muted/40 -ml-2"
            >
              <ArrowLeft className="size-3.5" />
              Back to home
            </Link>
          </div>
          {registeredSuccess ? (
            <div className="space-y-6 text-center animate-in fade-in slide-in-from-bottom-2">
              <div className="mx-auto size-14 rounded-full bg-primary/10 border border-primary/20 flex items-center justify-center text-primary shadow-xs">
                <CheckCircle2 className="size-7" />
              </div>
              <div>
                <h2 className="text-2xl font-bold tracking-tight">Account Created Successfully!</h2>
                <p className="text-xs text-muted-foreground mt-2 leading-relaxed">
                  We've sent an account confirmation email to:
                  <br />
                  <strong className="text-foreground">{registeredEmail}</strong>
                </p>
              </div>

              <div className="p-4 rounded-xl bg-muted/60 border border-border text-xs text-muted-foreground text-left space-y-2">
                <div className="flex items-start gap-2">
                  <ShieldCheck className="size-4 text-primary shrink-0 mt-0.5" />
                  <p>
                    Your ResolveAI customer account is active. A welcome confirmation email has been dispatched with your details.
                  </p>
                </div>
                <p className="text-[11px] text-muted-foreground/80 pl-6">
                  Check your inbox to verify your registration details and access your 24/7 support channels.
                </p>
              </div>

              <div className="pt-2 space-y-2">
                <Button
                  className="w-full h-11 font-medium gap-2"
                  onClick={() => {
                    if (registeredRole === "expert") {
                      navigate({ to: "/expert" });
                    } else if (registeredRole === "admin") {
                      navigate({ to: "/admin" });
                    } else {
                      navigate({ to: "/dashboard" });
                    }
                  }}
                >
                  Continue to Workspace
                  <ArrowRight className="size-4" />
                </Button>

                <Link to="/login" className="w-full block">
                  <Button variant="ghost" className="w-full h-10 text-xs text-muted-foreground font-medium">
                    Sign in with another account
                  </Button>
                </Link>
              </div>
            </div>
          ) : (
            <form onSubmit={submit}>
              <h2>{register ? "A better support experience." : "Welcome back."}</h2>
              <p className="mb-6 text-muted-foreground">
                {register
                  ? "Create your customer account to get started."
                  : "Sign in to pick up where you left off."}
              </p>

            <Button
              type="button"
              variant="outline"
              className="w-full h-11 flex items-center justify-center gap-2 mb-4 font-medium"
              onClick={handleGoogleAuth}
              disabled={googleLoading || loading}
            >
              {googleLoading ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <svg className="size-4" viewBox="0 0 24 24">
                  <path
                    fill="#4285F4"
                    d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                  />
                  <path
                    fill="#34A853"
                    d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                  />
                  <path
                    fill="#FBBC05"
                    d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
                  />
                  <path
                    fill="#EA4335"
                    d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
                  />
                </svg>
              )}
              Continue with Google
            </Button>

            <div className="relative flex items-center justify-center mb-6">
              <span className="w-full border-t border-border" />
              <span className="bg-card px-3 text-[11px] text-muted-foreground uppercase absolute">
                or with email
              </span>
            </div>

            {register && (
              <label className="field">
                Full name
                <Input name="name" required placeholder="Your full name" autoComplete="name" />
              </label>
            )}
            <label className="field">
              Email address
              <Input
                name="email"
                type="email"
                required
                value={emailInput}
                onChange={(e) => setEmailInput(e.target.value)}
                placeholder="you@example.com"
                autoComplete="email"
              />
            </label>
            <div className="field">
              <div className="flex items-center justify-between">
                <span>Password</span>
                {!register && (
                  <div className="flex items-center gap-2">
                    <Link
                      to="/forgot-password"
                      search={emailInput.trim() ? { email: emailInput.trim() } : undefined}
                      className="text-xs text-primary font-medium hover:underline"
                    >
                      Forgot password?
                    </Link>
                    {emailInput.trim() && !loginResetSent && (
                      <button
                        type="button"
                        aria-label="Send link to this email"
                        onClick={handleSendResetFromLogin}
                        disabled={loginResetLoading}
                        className="text-[11px] text-muted-foreground hover:text-primary transition-colors cursor-pointer bg-transparent border-none p-0 underline"
                      >
                        {loginResetLoading ? (
                          <span className="inline-flex items-center gap-1">
                            <Loader2 className="size-3 animate-spin inline" />
                            Sending...
                          </span>
                        ) : (
                          "Send link to this email"
                        )}
                      </button>
                    )}
                  </div>
                )}
              </div>
              <div className="password-field">
                <Input
                  name="password"
                  required
                  minLength={register ? 8 : 1}
                  value={passwordInput}
                  onChange={(e) => setPasswordInput(e.target.value)}
                  type={visible ? "text" : "password"}
                  placeholder={register ? "At least 8 characters" : "Enter your password"}
                  autoComplete={register ? "new-password" : "current-password"}
                />
                <Button
                  aria-label={visible ? "Hide password" : "Show password"}
                  variant="ghost"
                  size="icon"
                  type="button"
                  onClick={() => setVisible(!visible)}
                >
                  {visible ? <EyeOff /> : <Eye />}
                </Button>
              </div>
            </div>
            {loginResetSent && (
              <div className="p-3.5 rounded-xl bg-primary/10 border border-primary/20 text-left space-y-1.5 my-3 animate-in fade-in">
                <div className="flex items-center gap-2 text-primary font-semibold text-xs">
                  <Mail className="size-4" />
                  <span>Reset link sent! Check your mail</span>
                </div>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  We've sent a password reset confirmation email to <strong className="text-foreground">{loginResetEmail}</strong>.
                  Please check your mail and use the link to reset your password.
                </p>
                {loginResetDevUrl && (
                  <Link
                    to="/reset-password"
                    search={{ token: loginResetDevUrl.includes("token=") ? loginResetDevUrl.split("token=")[1] : "" }}
                    className="text-xs font-semibold text-primary hover:underline inline-flex items-center gap-1 pt-1"
                  >
                    Open Reset Password Page &rarr;
                  </Link>
                )}
              </div>
            )}
            {register && (
              <label className="field">
                Confirm password
                <Input
                  name="confirm"
                  required
                  minLength={8}
                  type={visible ? "text" : "password"}
                  placeholder="Re-enter your password"
                  autoComplete="new-password"
                />
              </label>
            )}
            {error && (
              <p className="text-destructive text-xs leading-relaxed mb-5" role="alert">
                {error}
              </p>
            )}
            <Button className="w-full h-11" type="submit" disabled={loading || googleLoading}>
              {loading ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <>
                  {register ? "Create customer account" : "Sign in"}
                  <ArrowRight />
                </>
              )}
            </Button>
            <div className="text-center text-xs text-muted-foreground mt-6">
              <span>
                {register ? "Already have an account?" : "New to ResolveAI?"}{" "}
                <Link to={register ? "/login" : "/register"} className="text-primary font-semibold hover:underline">
                  {register ? "Sign in" : "Create an account"}
                </Link>
              </span>
            </div>
          </form>
          )}
      </div>
    </section>
  </main>
  );
}

const DEFAULT_ACCOUNT_EMAIL = "customer@resolveai.com";

export function ForgotPasswordPage({ initialEmail }: { initialEmail?: string } = {}) {
  const { user } = useAuth();
  const [accountEmail, setAccountEmail] = useState<string>(() => {
    if (initialEmail) return initialEmail;
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      const queryEmail = params.get("email");
      const storedAccount = localStorage.getItem("resolve_account_email");
      const storedCreated = localStorage.getItem("resolve_account_created_email");
      return (
        queryEmail ||
        storedAccount ||
        storedCreated ||
        user?.email ||
        DEFAULT_ACCOUNT_EMAIL
      );
    }
    return DEFAULT_ACCOUNT_EMAIL;
  });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [submittedEmail, setSubmittedEmail] = useState("");
  const [devResetUrl, setDevResetUrl] = useState<string | null>(null);
  const [devResetToken, setDevResetToken] = useState<string | null>(null);

  useEffect(() => {
    if (initialEmail) {
      setAccountEmail(initialEmail);
    } else if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      const queryEmail = params.get("email");
      const storedAccount = localStorage.getItem("resolve_account_email");
      const storedCreated = localStorage.getItem("resolve_account_created_email");
      const candidate =
        queryEmail ||
        storedAccount ||
        storedCreated ||
        user?.email;
      if (candidate) {
        setAccountEmail(candidate);
      }
    }
  }, [user, initialEmail]);

  async function handleSendReset() {
    const emailToSend = (accountEmail || DEFAULT_ACCOUNT_EMAIL).trim();
    if (!emailToSend) {
      setError("Please enter your account email address.");
      return;
    }
    setError("");
    setLoading(true);

    try {
      const res = await api.post("/auth/forgot-password", { email: emailToSend });
      setSubmitted(true);
      setSubmittedEmail(emailToSend);
      if (res.data?.dev_reset_url) {
        setDevResetUrl(res.data.dev_reset_url);
      }
      if (res.data?.dev_reset_token) {
        setDevResetToken(res.data.dev_reset_token);
      }
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      setError(
        typeof detail === "string"
          ? detail
          : "Failed to process password reset. Please try again."
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-branding">
        <Link to="/">
          <Logo />
        </Link>
        <div>
          <span className="eyebrow">Account Security &amp; Recovery</span>
          <h1 className="mt-5">Reset your password quickly and securely.</h1>
          <p>
            Verify your account email. We'll send you a confirmation link with secure instructions to
            reset your password.
          </p>
        </div>
        <img
          src={art}
          alt="ResolveAI conversation illustration"
          className="auth-art"
          width={1024}
          height={1024}
        />
        <p className="text-xs flex items-center gap-2">
          <Globe2 className="size-4" />
          English · Tanglish · Hinglish
        </p>
      </section>
      <section className="auth-form-side">
        <div className="auth-form">
          {submitted ? (
            <div className="space-y-6 text-center animate-in fade-in slide-in-from-bottom-2">
              <div className="mx-auto size-14 rounded-full bg-primary/10 border border-primary/20 flex items-center justify-center text-primary shadow-xs">
                <Mail className="size-7" />
              </div>
              <div>
                <h2 className="text-2xl font-bold tracking-tight">Check your email</h2>
                <p className="text-xs text-muted-foreground mt-2 leading-relaxed">
                  We've sent a password reset confirmation email to:
                  <br />
                  <strong className="text-foreground">{submittedEmail}</strong>
                </p>
              </div>

              <div className="p-4 rounded-xl bg-muted/60 border border-border text-xs text-muted-foreground text-left space-y-2">
                <div className="flex items-start gap-2">
                  <ShieldCheck className="size-4 text-primary shrink-0 mt-0.5" />
                  <p>
                    Click the confirmation link inside the email to choose a new password. The link
                    expires in <strong>15 minutes</strong>.
                  </p>
                </div>
                <p className="text-[11px] text-muted-foreground/80 pl-6">
                  If you don't see the email, check your spam or junk folder.
                </p>
              </div>

              {devResetUrl && (
                <div className="p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/20 text-left space-y-1.5">
                  <span className="text-[10px] font-semibold uppercase tracking-wider text-amber-600 block">
                    Developer Mode Preview
                  </span>
                  <p className="text-xs text-muted-foreground">
                    Direct password reset link generated:
                  </p>
                  <a
                    href={devResetUrl}
                    className="inline-flex items-center gap-1.5 text-xs font-semibold text-primary hover:underline break-all"
                  >
                    Open Reset Password Page &rarr;
                  </a>
                </div>
              )}

              <div className="pt-2">
                <Link to="/login" className="w-full block">
                  <Button variant="outline" className="w-full h-11 font-medium gap-2">
                    <ArrowLeft className="size-4" />
                    Back to sign in
                  </Button>
                </Link>
              </div>
            </div>
          ) : (
            <form onSubmit={(e) => { e.preventDefault(); handleSendReset(); }} className="space-y-5 animate-in fade-in slide-in-from-bottom-2">
              <div className="size-11 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary mb-2 shadow-xs">
                <ShieldCheck className="size-5" />
              </div>
              <div>
                <h2 className="text-2xl font-bold tracking-tight">Confirm Account Email</h2>
                <p className="text-xs text-muted-foreground mt-1">
                  Enter your account email below. We'll send secure password reset instructions to your inbox:
                </p>
              </div>

              {error && (
                <p className="text-destructive text-xs leading-relaxed" role="alert">
                  {error}
                </p>
              )}

              {/* Editable Account Email Field with current confirmation badge */}
              <label className="field block">
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-xs font-medium text-foreground">Email address</span>
                  {accountEmail && (
                    <span className="text-[10px] bg-primary/10 text-primary border border-primary/20 px-2.5 py-0.5 rounded-full font-medium truncate max-w-[200px]">
                      {accountEmail}
                    </span>
                  )}
                </div>
                <Input
                  name="email"
                  type="email"
                  required
                  value={accountEmail}
                  onChange={(e) => setAccountEmail(e.target.value)}
                  placeholder="you@example.com"
                  autoComplete="email"
                  autoFocus
                />
              </label>

              <Button
                type="submit"
                className="w-full h-11 font-medium gap-2"
                disabled={loading}
              >
                {loading ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <>
                    Confirm &amp; Send Reset Link
                    <ArrowRight className="size-4" />
                  </>
                )}
              </Button>

              <div className="flex items-center justify-between pt-2 text-xs">
                <Link
                  to="/"
                  className="inline-flex items-center gap-1.5 text-muted-foreground hover:text-foreground transition-colors font-medium"
                >
                  <ArrowLeft className="size-3.5" />
                  Back to home
                </Link>
                <Link
                  to="/login"
                  className="inline-flex items-center gap-1.5 text-muted-foreground hover:text-primary transition-colors font-medium"
                >
                  Back to sign in
                </Link>
              </div>
            </form>
          )}
        </div>
      </section>
    </main>
  );
}

export function ResetPasswordPage({ initialToken }: { initialToken?: string } = {}) {
  const [token, setToken] = useState(() => {
    if (initialToken) return initialToken;
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      return params.get("token") || "";
    }
    return "";
  });
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [visible, setVisible] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    if (initialToken) {
      setToken(initialToken);
    } else if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      const urlToken = params.get("token");
      if (urlToken) {
        setToken(urlToken);
      }
    }
  }, [initialToken]);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");

    if (!token.trim()) {
      setError("Password reset token is missing. Please request a new confirmation email.");
      return;
    }

    if (newPassword !== confirmPassword) {
      setError("Passwords do not match. Please re-enter.");
      return;
    }

    if (newPassword.length < 8) {
      setError("Password must be at least 8 characters long.");
      return;
    }

    setLoading(true);

    try {
      await api.post("/auth/reset-password", {
        token: token.trim(),
        new_password: newPassword,
      });
      setSuccess(true);
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      setError(
        typeof detail === "string"
          ? detail
          : "Invalid or expired reset token. Please request a new confirmation link."
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-branding">
        <Link to="/">
          <Logo />
        </Link>
        <div>
          <span className="eyebrow">Account Security</span>
          <h1 className="mt-5">Create your new secure password.</h1>
          <p>
            Choose a strong password containing letters and numbers to protect your account.
          </p>
        </div>
        <img
          src={art}
          alt="ResolveAI conversation illustration"
          className="auth-art"
          width={1024}
          height={1024}
        />
        <p className="text-xs flex items-center gap-2">
          <Globe2 className="size-4" />
          English · Tanglish · Hinglish
        </p>
      </section>
      <section className="auth-form-side">
        <div className="auth-form">
          {success ? (
            <div className="space-y-6 text-center animate-in fade-in slide-in-from-bottom-2">
              <div className="mx-auto size-14 rounded-full bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-600 shadow-xs">
                <CheckCircle2 className="size-7" />
              </div>
              <div>
                <h2 className="text-2xl font-bold tracking-tight">Password reset successfully!</h2>
                <p className="text-xs text-muted-foreground mt-2 leading-relaxed">
                  Your ResolveAI account password has been updated and a confirmation email has been
                  sent. You can now sign in with your new credentials.
                </p>
              </div>

              <div className="pt-2">
                <Link to="/login" className="w-full block">
                  <Button className="w-full h-11 font-medium gap-2">
                    Sign in to your account
                    <ArrowRight className="size-4" />
                  </Button>
                </Link>
              </div>
            </div>
          ) : (
            <form onSubmit={submit} className="space-y-4">
              <div className="size-11 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary mb-2 shadow-xs">
                <KeyRound className="size-5" />
              </div>
              <div>
                <h2 className="text-2xl font-bold tracking-tight">Set new password</h2>
                <p className="text-xs text-muted-foreground mt-1">
                  Enter your new password below.
                </p>
              </div>

              {error && (
                <div className="p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-xs leading-relaxed">
                  {error}
                </div>
              )}

              {token ? (
                <div className="p-3 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-between gap-3 text-xs text-primary font-medium animate-in fade-in">
                  <div className="flex items-center gap-2 min-w-0">
                    <ShieldCheck className="size-4 shrink-0 text-primary" />
                    <span className="truncate">Reset confirmation link verified</span>
                  </div>
                  <span className="text-[10px] bg-primary/20 text-primary px-2 py-0.5 rounded-full font-semibold shrink-0">
                    Active
                  </span>
                </div>
              ) : (
                <label className="field block">
                  Reset Token
                  <Input
                    name="token"
                    required
                    value={token}
                    onChange={(e) => setToken(e.target.value)}
                    placeholder="Paste your reset token"
                  />
                </label>
              )}

              <label className="field block">
                New password
                <div className="password-field">
                  <Input
                    name="newPassword"
                    required
                    minLength={8}
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    type={visible ? "text" : "password"}
                    placeholder="At least 8 characters"
                    autoComplete="new-password"
                    autoFocus
                  />
                  <Button
                    aria-label={visible ? "Hide password" : "Show password"}
                    variant="ghost"
                    size="icon"
                    type="button"
                    onClick={() => setVisible(!visible)}
                  >
                    {visible ? <EyeOff /> : <Eye />}
                  </Button>
                </div>
              </label>

              <label className="field block">
                Confirm new password
                <Input
                  name="confirmPassword"
                  required
                  minLength={8}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  type={visible ? "text" : "password"}
                  placeholder="Re-enter your new password"
                  autoComplete="new-password"
                />
              </label>

              <p className="text-[11px] text-muted-foreground">
                Password must be at least 8 characters long and contain uppercase, lowercase, and numbers.
              </p>

              <Button className="w-full h-11" type="submit" disabled={loading}>
                {loading ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <>
                    Confirm &amp; Reset Password
                    <ArrowRight className="size-4" />
                  </>
                )}
              </Button>

              <div className="text-center pt-2">
                <Link
                  to="/login"
                  className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-primary transition-colors font-medium"
                >
                  <ArrowLeft className="size-3.5" />
                  Back to sign in
                </Link>
              </div>
            </form>
          )}
        </div>
      </section>
    </main>
  );
}
