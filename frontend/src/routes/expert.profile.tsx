import { createFileRoute } from "@tanstack/react-router";
import { SettingsPage } from "@/components/resolve/customer";
import { pageHead } from "@/lib/resolve-meta";
export const Route = createFileRoute("/expert/profile")({
  head: () => pageHead("Expert Profile", "Manage your expert support profile and preferences."),
  component: Page,
});
function Page() {
  return <SettingsPage role="expert" />;
}
