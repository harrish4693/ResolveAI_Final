import { createFileRoute } from "@tanstack/react-router";
import { HelpPage } from "@/components/resolve/customer";
import { pageHead } from "@/lib/resolve-meta";
export const Route = createFileRoute("/help")({
  validateSearch: (search: Record<string, unknown>): { category?: string | undefined } => ({
    category: typeof search["category"] === "string" ? search["category"] : undefined,
  }),
  head: () =>
    pageHead("Help & Support", "Get instant 24/7 AI-powered support via voice or chat, or manage your tickets."),
  component: Page,
});
function Page() {
  return <HelpPage initialCategory={Route.useSearch().category ?? "All topics"} />;
}
