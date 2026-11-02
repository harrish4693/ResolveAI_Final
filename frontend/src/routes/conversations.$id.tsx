import { createFileRoute } from "@tanstack/react-router";
import { ConversationDetails } from "@/components/resolve/customer";
import { pageHead } from "@/lib/resolve-meta";
export const Route = createFileRoute("/conversations/$id")({
  head: () =>
    pageHead(
      "Conversation Details",
      "View conversation history, ticket status, and resolution information.",
    ),
  component: Page,
});
function Page() {
  return <ConversationDetails id={Route.useParams().id} />;
}
