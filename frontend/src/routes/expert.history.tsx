import { createFileRoute } from "@tanstack/react-router";
import { QueuePage } from "@/components/resolve/operations";
import { pageHead } from "@/lib/resolve-meta";
export const Route = createFileRoute("/expert/history")({
  head: () => pageHead("Expert Conversation History", "Review your support conversation history."),
  component: Page,
});
function Page() {
  return <QueuePage kind="history" />;
}
