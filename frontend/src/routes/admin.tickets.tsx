import { createFileRoute } from "@tanstack/react-router";
import { QueuePage } from "@/components/resolve/operations";
import { pageHead } from "@/lib/resolve-meta";
export const Route = createFileRoute("/admin/tickets")({
  head: () =>
    pageHead("Ticket Monitoring", "Monitor organization-wide tickets and expert assignments."),
  component: Page,
});
function Page() {
  return <QueuePage kind="admin" />;
}
