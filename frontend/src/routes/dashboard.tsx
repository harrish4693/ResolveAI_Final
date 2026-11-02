import { createFileRoute } from "@tanstack/react-router";
import { CustomerDashboard } from "@/components/resolve/customer";
import { pageHead } from "@/lib/resolve-meta";
export const Route = createFileRoute("/dashboard")({
  head: () =>
    pageHead(
      "Customer Dashboard",
      "Keep track of your support conversations and get help in your language.",
    ),
  component: Page,
});
function Page() {
  return <CustomerDashboard />;
}
