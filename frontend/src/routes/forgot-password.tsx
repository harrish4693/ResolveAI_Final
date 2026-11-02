import { createFileRoute } from "@tanstack/react-router";
import { ForgotPasswordPage } from "@/components/resolve/auth-pages";
import { pageHead } from "@/lib/resolve-meta";

export const Route = createFileRoute("/forgot-password")({
  validateSearch: (search: Record<string, unknown>) => ({
    email: typeof search.email === "string" ? search.email : undefined,
  }),
  head: () => pageHead("Forgot Password", "Reset your ResolveAI account password."),
  component: Page,
});

function Page() {
  const search = Route.useSearch();
  return <ForgotPasswordPage initialEmail={search?.email} />;
}
