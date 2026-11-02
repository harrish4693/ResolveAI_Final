import { createFileRoute } from "@tanstack/react-router";
import { ExpertDashboard } from "@/components/resolve/operations";
import { pageHead } from "@/lib/resolve-meta";
export const Route = createFileRoute("/expert/")({
  head: () =>
    pageHead("Expert Dashboard", "Review your assigned support cases and customer escalations."),
  component: Page,
});
function Page() {
  return <ExpertDashboard />;
}
