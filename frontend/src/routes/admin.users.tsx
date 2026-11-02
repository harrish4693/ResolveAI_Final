import { createFileRoute } from "@tanstack/react-router";
import { UsersPage } from "@/components/resolve/operations";
import { pageHead } from "@/lib/resolve-meta";
export const Route = createFileRoute("/admin/users")({
  head: () =>
    pageHead("Users and Roles", "Review authorized user accounts and support team roles."),
  component: Page,
});
function Page() {
  return <UsersPage />;
}
