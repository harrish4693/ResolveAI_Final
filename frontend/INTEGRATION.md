# ResolveAI frontend integration

## Current state

This repository supplied a TanStack Start frontend template, not the FastAPI application mentioned in the brief. No existing API clients, JWT implementation, endpoint schemas, WebSocket events, authenticated users, support records, or knowledge documents were available. No backend was replaced or added.

All pages are explicitly a frontend preview. Workspace navigation previews screens only and never grants authorization. Metrics use unavailable values, data tables use empty states, and sending a message, signing in, registering, saving settings, or uploading documents never simulates success. No private customer data or secrets are present. Login/register submit handlers perform local validation only; they do not create authentication sessions.

## Required integration inputs

Supply the existing backend source or OpenAPI specification and frontend API client, plus the following existing contracts. Actual endpoint paths and schemas must be inspected, not invented:

- Authentication: customer registration, email/password login, token refresh, logout, verified current-user identity and role, token storage and expiry behavior, password recovery if supported.
- Customers: dashboard counts, paginated conversation list and filters, conversation history and ticket detail, message creation, eligible feedback, profile and notification settings.
- Real time: WebSocket URL and auth handshake, event schemas, message IDs and timestamps, sender metadata, reconnect behavior, delivery and error events, handoff/resolve/ask-user events.
- Experts: queue and assignment filtering, claim operation with ownership conflict responses, private internal note contract, original conversation context, AI handoff summary, escalation reason, intent, sentiment, history, resolve and escalation authorization.
- Admins: date-filtered analytics, ticket access, document ingestion and indexing status, knowledge retrieval, authorized user management and workspace preferences.

## Security boundary

Before connecting live data, wire verified backend identity into router context and protected layout guards. Enforce permissions in FastAPI, including private notes and role changes. Authenticate WebSockets using the existing protocol. Do not infer permission from URL, preview navigation, or editable browser state. Backend-provided roles determine post-login navigation. Public registration creates customers only.

## Route map

Customer: `/`, `/dashboard`, `/chat/:id`, `/conversations`, `/conversations/:id`, `/help`, `/settings`.
Expert: `/expert`, `/expert/queue`, `/expert/assigned`, `/expert/history`, `/expert/chat/:id`, `/expert/profile`.
Admin: `/admin`, `/admin/analytics`, `/admin/knowledge`, `/admin/tickets`, `/admin/users`, `/admin/settings`.
Public forms: `/login`, `/register`. Password reset is intentionally omitted without a supported backend flow.

## UI foundations

Shared light design, role-specific sidebar, search dialog, notifications, account menu, metric unavailable states, table filters, form validation, customer chat suggestions, internal note mode, and knowledge upload-unavailable dialog. Conversation and composer use AI Elements; no model calls are introduced.
