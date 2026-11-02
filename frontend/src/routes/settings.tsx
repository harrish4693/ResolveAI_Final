import { createFileRoute } from "@tanstack/react-router";
import { SettingsPage } from "@/components/resolve/customer";
import { pageHead } from "@/lib/resolve-meta";
export const Route = createFileRoute("/settings")({
  head: () =>
    pageHead("Account Settings", "Manage your ResolveAI account and notification preferences."),
  component: Page,
});
function Page() {
  return <SettingsPage />;
}
