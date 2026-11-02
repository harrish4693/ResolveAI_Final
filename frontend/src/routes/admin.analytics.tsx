import { createFileRoute } from "@tanstack/react-router";
import { AdminDashboard } from "@/components/resolve/operations";
import { pageHead } from "@/lib/resolve-meta";
export const Route = createFileRoute("/admin/analytics")({
  head: () =>
    pageHead(
      "Support Analytics",
      "Track verified customer support trends and resolution analytics.",
    ),
  component: Page,
});
function Page() {
  return <AdminDashboard analytics />;
}
