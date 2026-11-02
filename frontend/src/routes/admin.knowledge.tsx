import { createFileRoute } from "@tanstack/react-router";
import { KnowledgePage } from "@/components/resolve/operations";
import { pageHead } from "@/lib/resolve-meta";
export const Route = createFileRoute("/admin/knowledge")({
  head: () =>
    pageHead(
      "Knowledge Base Management",
      "Manage your support knowledge documents and indexing status.",
    ),
  component: Page,
});
function Page() {
  return <KnowledgePage />;
}
