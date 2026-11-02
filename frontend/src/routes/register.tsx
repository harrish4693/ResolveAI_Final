import { createFileRoute } from "@tanstack/react-router";
import { AuthPage } from "@/components/resolve/auth-pages";
import { pageHead } from "@/lib/resolve-meta";
export const Route = createFileRoute("/register")({
  head: () => pageHead("Create Your Account", "Create your ResolveAI customer account."),
  component: Page,
});
function Page() {
  return <AuthPage register />;
}
