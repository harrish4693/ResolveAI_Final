import { createFileRoute } from "@tanstack/react-router";
import { VoiceCallPage } from "@/components/resolve/VoiceCallPage";
import { pageHead } from "@/lib/resolve-meta";

export const Route = createFileRoute("/call/$id")({
  head: () =>
    pageHead("Voice Call", "Live natural voice conversation with ResolveAI."),
  component: Page,
});

function Page() {
  const { id } = Route.useParams();
  return <VoiceCallPage initialConversationId={id} autoStart={true} />;
}
