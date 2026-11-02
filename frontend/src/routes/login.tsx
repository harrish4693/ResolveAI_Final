import { createFileRoute } from "@tanstack/react-router";
import { AuthPage } from "@/components/resolve/auth-pages";
import { pageHead } from "@/lib/resolve-meta";
export const Route = createFileRoute("/login")({
  head: () => pageHead("Sign In", "Sign in to your ResolveAI customer support workspace."),
  component: Page,
});
function Page() {
  return <AuthPage />;
}
