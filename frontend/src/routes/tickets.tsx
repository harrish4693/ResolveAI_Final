import { createFileRoute } from "@tanstack/react-router";
import { ConversationsPage } from "@/components/resolve/customer";
import { pageHead } from "@/lib/resolve-meta";

export const Route = createFileRoute("/tickets")({
  head: () =>
    pageHead("My Tickets", "View your support tickets, categories, and status."),
  component: Page,
});

function Page() {
  return <ConversationsPage />;
}
