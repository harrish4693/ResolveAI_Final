import { createFileRoute } from "@tanstack/react-router";
import { SettingsPage } from "@/components/resolve/customer";
import { pageHead } from "@/lib/resolve-meta";
export const Route = createFileRoute("/admin/settings")({
  head: () => pageHead("Workspace Settings", "Manage your support workspace preferences."),
  component: Page,
});
function Page() {
  return <SettingsPage role="admin" />;
}
