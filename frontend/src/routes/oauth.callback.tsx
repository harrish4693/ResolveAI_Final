import { useEffect, useState, useRef } from "react";
import { createFileRoute, useNavigate, Link } from "@tanstack/react-router";
import { Loader2, AlertCircle, ArrowLeft, CheckCircle2 } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Logo } from "@/components/resolve/workspace";
import { Button } from "@/components/ui/button";
import { pageHead } from "@/lib/resolve-meta";

type OAuthSearch = {
  code?: string;
  error?: string;
};

export const Route = createFileRoute("/oauth/callback")({
  validateSearch: (search: Record<string, unknown>): OAuthSearch => {
    return {
      code: typeof search.code === "string" ? search.code : undefined,
      error: typeof search.error === "string" ? search.error : undefined,
    };
  },
  head: () => pageHead("Authenticating", "Signing you into ResolveAI..."),
  component: OAuthCallbackPage,
});

function OAuthCallbackPage() {
  const search = Route.useSearch();
  const navigate = useNavigate();
  const { login } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<"processing" | "success" | "error">("processing");
  const processedRef = useRef(false);

  useEffect(() => {
    if (processedRef.current) return;

    let code = search.code;
    let oauthError = search.error;

    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      if (!code) code = params.get("code") || undefined;
      if (!oauthError) oauthError = params.get("error") || undefined;
    }

    if (oauthError) {
      processedRef.current = true;
      setStatus("error");
      setError(decodeURIComponent(oauthError.replace(/\+/g, " ")));
      return;
    }

    if (!code) {
      processedRef.current = true;
      setStatus("error");
      setError("No authorization code was provided by the authentication provider.");
      return;
    }

    processedRef.current = true;

    const exchange = async () => {
      try {
        const response = await api.post<{ access_token: string; refresh_token: string }>(
          "/auth/google/exchange",
          { code }
        );
        const { access_token, refresh_token } = response.data;
        const user = await login(access_token, refresh_token);
        setStatus("success");

        setTimeout(() => {
          if (user?.role === "expert") {
            navigate({ to: "/expert", replace: true });
          } else if (user?.role === "admin") {
            navigate({ to: "/admin", replace: true });
          } else {
            navigate({ to: "/dashboard", replace: true });
          }
        }, 500);
      } catch (err: any) {
        console.error("OAuth exchange failed:", err);
        setStatus("error");
        const detail = err.response?.data?.detail;
        setError(typeof detail === "string" ? detail : "Authentication failed. Please try signing in again.");
      }
    };

    exchange();
  }, [search, login, navigate]);

  return (
    <main className="min-h-screen flex items-center justify-center p-6 bg-background text-foreground relative overflow-hidden">
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        <div className="w-[500px] h-[500px] bg-primary/10 rounded-full blur-[120px]" />
      </div>

      <div className="relative z-10 w-full max-w-md p-8 rounded-2xl bg-card/80 backdrop-blur-xl border border-border shadow-2xl text-center space-y-6">
        <div className="flex justify-center">
          <Logo />
        </div>

        {status === "processing" && (
          <div className="space-y-4 py-4">
            <div className="size-14 mx-auto rounded-full bg-primary/10 flex items-center justify-center">
              <Loader2 className="size-7 text-primary animate-spin" />
            </div>
            <div>
              <h1 className="text-xl font-semibold">Completing Sign-In</h1>
              <p className="text-sm text-muted-foreground mt-1">
                Securely verifying your Google credentials...
              </p>
            </div>
          </div>
        )}

        {status === "success" && (
          <div className="space-y-4 py-4">
            <div className="size-14 mx-auto rounded-full bg-emerald-500/10 flex items-center justify-center">
              <CheckCircle2 className="size-7 text-emerald-500" />
            </div>
            <div>
              <h1 className="text-xl font-semibold">Authentication Successful</h1>
              <p className="text-sm text-muted-foreground mt-1">
                Redirecting you to your workspace...
              </p>
            </div>
          </div>
        )}

        {status === "error" && (
          <div className="space-y-5 py-2">
            <div className="size-14 mx-auto rounded-full bg-destructive/10 flex items-center justify-center">
              <AlertCircle className="size-7 text-destructive" />
            </div>
            <div>
              <h1 className="text-xl font-semibold">Authentication Failed</h1>
              <p className="text-sm text-destructive mt-2 text-center break-words bg-destructive/10 border border-destructive/20 rounded-lg p-3">
                {error}
              </p>
            </div>
            <Link to="/login" className="block pt-2">
              <Button variant="outline" className="w-full h-11 gap-2">
                <ArrowLeft className="size-4" />
                Return to Sign In
              </Button>
            </Link>
          </div>
        )}
      </div>
    </main>
  );
}
