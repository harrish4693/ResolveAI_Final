import { createFileRoute } from "@tanstack/react-router";
import { ExpertConsole } from "@/components/resolve/operations";
import { pageHead } from "@/lib/resolve-meta";
export const Route = createFileRoute("/expert/chat/$id")({
  head: () =>
    pageHead(
      "Expert Conversation Console",
      "Customer conversations, internal notes, and AI handoff context.",
    ),
  component: Page,
});
function Page() {
  return <ExpertConsole id={Route.useParams().id} />;
}
