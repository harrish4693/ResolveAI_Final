import { createFileRoute } from "@tanstack/react-router";
import { QueuePage } from "@/components/resolve/operations";
import { pageHead } from "@/lib/resolve-meta";
export const Route = createFileRoute("/expert/assigned")({
  head: () => pageHead("My Assigned Cases", "Track support cases assigned to you."),
  component: Page,
});
function Page() {
  return <QueuePage kind="assigned" />;
}
