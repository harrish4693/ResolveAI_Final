import { createFileRoute } from "@tanstack/react-router";
import { ConversationsPage } from "@/components/resolve/customer";
import { pageHead } from "@/lib/resolve-meta";
export const Route = createFileRoute("/conversations/")({
  head: () =>
    pageHead("My Conversations", "Search your conversation history and follow ticket updates."),
  component: Page,
});
function Page() {
  return <ConversationsPage />;
}
