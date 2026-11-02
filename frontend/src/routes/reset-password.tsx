import { createFileRoute } from "@tanstack/react-router";
import { ResetPasswordPage } from "@/components/resolve/auth-pages";
import { pageHead } from "@/lib/resolve-meta";

export const Route = createFileRoute("/reset-password")({
  validateSearch: (search: Record<string, unknown>) => ({
    token: typeof search.token === "string" ? search.token : "",
  }),
  head: () => pageHead("Reset Password", "Set a new password for your ResolveAI account."),
  component: Page,
});

function Page() {
  const search = Route.useSearch();
  return <ResetPasswordPage initialToken={search?.token} />;
}

