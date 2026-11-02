
import { createFileRoute } from "@tanstack/react-router";
import { pageHead } from "@/lib/resolve-meta";
import { LandingPage } from "@/components/resolve/LandingPage";

export const Route = createFileRoute("/")({
  head: () =>
    pageHead(
      "ResolveAI — Autonomous Voice & Omnichannel Customer Support",
      "Human-like voice AI agents, real-time tool execution, and sub-second multi-turn customer support conversations that actually resolve.",
    ),
  component: LandingPage,
});





