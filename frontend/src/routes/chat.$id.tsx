import { createFileRoute } from "@tanstack/react-router";
import { CustomerChat } from "@/components/resolve/customer";
import { pageHead } from "@/lib/resolve-meta";
export const Route = createFileRoute("/chat/$id")({
  head: () => pageHead("AI Support Chat", "Talk to ResolveAI in English, Tanglish, or Hinglish."),
  component: Page,
});
function Page() {
  const { id } = Route.useParams();
  return <CustomerChat conversationId={id} />;
}
