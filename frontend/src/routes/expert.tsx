import { createFileRoute, Outlet } from "@tanstack/react-router";
export const Route = createFileRoute("/expert")({ component: () => <Outlet /> });
