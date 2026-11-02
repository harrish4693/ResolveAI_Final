import { createFileRoute } from "@tanstack/react-router";
import { AdminDashboard } from "@/components/resolve/operations";
import { pageHead } from "@/lib/resolve-meta";
export const Route = createFileRoute("/admin/")({
  head: () =>
    pageHead("Admin Overview", "Monitor your support operation and conversation outcomes."),
  component: Page,
});
function Page() {
  return <AdminDashboard />;
}
