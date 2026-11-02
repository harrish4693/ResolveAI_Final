import { createFileRoute } from "@tanstack/react-router";
import { QueuePage } from "@/components/resolve/operations";
import { pageHead } from "@/lib/resolve-meta";
export const Route = createFileRoute("/expert/queue")({
  head: () => pageHead("Expert Case Queue", "Search and review escalated customer support cases."),
  component: Page,
});
function Page() {
  return <QueuePage />;
}
