# ResolveAI V2 — Master Project Guide & Architecture Manual

**Project:** ResolveAI V2 — AI-First Intelligent Customer Support & Resolution Platform  
**System Version:** 2.2 (Production-Ready)  
**Authoritative Documentation Master:** Consolidated from Architecture, Implementation Plans, and Capability Audits.  

---

## 1. Project Overview & Architecture

ResolveAI V2 is an enterprise-grade, multi-tenant customer support platform that blends autonomous conversational AI with human expert collaboration. It provides real-time omnichannel resolution across web chat, speech dictation, and low-latency two-way phone/voice calls.

### Core Architectural Philosophy
* **AI-First Autonomous Resolution:** Handles common customer inquiries (order tracking, cancellations, refunds, general policy questions, troubleshooting) using verified tool execution and multi-tenant RAG retrieval without human intervention.
* **Safe Contextual Human Handoff:** When user frustration, out-of-policy exceptions, high-value transactions, or safety hazards occur, the system immediately suspends autonomous execution and seamlessly transfers the full state (conversation history, entities, sentiment, diagnostics) to an assigned human expert.
* **Multi-Tenant Data Isolation:** Enforces cryptographic and SQL-level tenant isolation across all database queries, RAG chunk retrieval, and vector memory.
* **Pan-Indian Multilingual & Code-Mixed Intelligence:** Comprehends all 22 scheduled Indian languages plus Indian English, natively supporting Romanized code-mixing (Tanglish, Hinglish, Tenglish, Kanglish, Manglish, Benglish, Marathish, Gujlish, Punglish).
* **High-Speed Voice Streaming:** Sub-500ms conversational turn turnaround via client-side VAD, Sarvam Saaras v4 STT, Groq Llama 3.3 / Gemini 2.5 Flash reasoning, pre-cached opener audio, and Sarvam Bulbul v3 neural TTS.

```
                      ┌──────────────────────────────────────────────┐
                      │          Omnichannel User Interfaces         │
                      │  (Customer Web Chat, Voice Call, Expert UI)  │
                      └──────────────────────┬───────────────────────┘
                                             │ HTTP REST / WebSocket
                                             ▼
                      ┌──────────────────────────────────────────────┐
                      │              FastAPI Gateway                 │
                      │   - JWT Auth & RBAC (Customer/Expert/Admin)  │
                      │   - Multi-Tenant Middleware & Correlation ID │
                      │   - WebSocket Session & Event Multiplexer    │
                      └──────┬──────────────────┬─────────────────┬──┘
                             │                  │                 │
             ┌───────────────┴────┐   ┌─────────┴─────────┐   ┌───┴──────────────┐
             ▼                    ▼   ▼                   ▼   ▼                  ▼
    ┌─────────────────┐ ┌───────────────────┐ ┌───────────────────┐ ┌───────────────────┐
    │  Voice Pipeline │ │ Multilingual LLM  │ │   Hybrid RAG      │ │ Incident Engine   │
    │  - Sarvam STT   │ │ - M4 Rule Engine  │ │ - TF-IDF Sparse   │ │ - Cross-Ticket    │
    │  - Bulbul TTS   │ │ - Groq Llama 3.3  │ │ - FAISS Dense     │ │ - Pattern Miner   │
    │  - Client VAD   │ │ - Gemini 2.5      │ │ - Multi-Tenant    │ │ - Autonomy Gate   │
    └─────────────────┘ └───────────────────┘ └───────────────────┘ └───────────────────┘
             │                    │                     │                   │
             └────────────────────┼─────────────────────┼───────────────────┘
                                  ▼                     ▼
                      ┌──────────────────────────────────────────────┐
                      │         Persistence & Cache Layer            │
                      │  - SQLite / PostgreSQL Async (SQLAlchemy)    │
                      │  - Alembic Migration History (15 Revisions)  │
                      │  - File-Based Audio Conversation Storage     │
                      └──────────────────────────────────────────────┘
```

---

## 2. Technology Stack & Setup

### Technology Matrix

| Layer | Component | Technologies |
| :--- | :--- | :--- |
| **Backend Runtime** | API & App Server | Python 3.11+, FastAPI 0.115+, Uvicorn (ASGI), Pydantic v2 |
| **Database & ORM** | Relational Store | SQLAlchemy 2.0 (Async), `aiosqlite` (dev), `asyncpg` (prod/PostgreSQL), Alembic |
| **AI Intelligence** | Multi-Provider Engine | Groq (`llama-3.3-70b-versatile`), Google Gemini (`gemini-2.5-flash`), OpenAI (`gpt-4o-mini`), ResolveAI M4 Deterministic Engine |
| **Speech & Audio** | Neural STT / TTS | Sarvam AI (`saaras:v4` STT, `bulbul:v3` TTS), WebRTC / LiveKit API, W3C Web Speech fallback |
| **Information Retrieval**| Hybrid RAG | `scikit-learn` (TF-IDF keyword matching), `faiss-cpu` (dense semantic search), `tiktoken` |
| **Frontend Framework** | Web Client & SSR | React 19, TypeScript 5.8+, Vite 8, TanStack Start, Nitro SSR, TanStack Router, TanStack Query |
| **Styling & Components**| Design System | Tailwind CSS v4, Radix UI primitives, Lucide React, class-variance-authority, clsx |
| **Testing & Quality** | Quality Assurance | Pytest 8, pytest-asyncio, Vitest 4, Playwright |

### Environment Setup & Quickstart

#### 1. System Requirements
* Windows 10/11, macOS, or Linux.
* Python 3.11 or higher.
* Node.js 20+ and npm 10+.

#### 2. Backend Initialization
```powershell
# Navigate to backend directory
cd backend

# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # On Windows PowerShell
# source .venv/bin/activate    # On Unix/macOS

# Install backend dependencies
pip install -r requirements.txt

# Configure environment variables
# Copy template and fill API keys (Groq, Gemini, Sarvam, OpenAI)
Copy-Item ..\.env.example .\.env

# Run database migrations and seed baseline data
alembic upgrade head
python seed.py
python seed_knowledge.py
python seed_orders.py
python seed_day3.py
```

#### 3. Frontend Initialization
```powershell
# Navigate to frontend directory
cd frontend

# Install npm dependencies
npm install

# Run frontend development server
npm run dev
```

#### 4. Unified One-Command Development Launcher
From the repository root, execute the PowerShell launcher script:
```powershell
.\run.ps1
```
This concurrently starts:
* **Backend API:** `http://127.0.0.1:8000` (Swagger docs at `/docs`)
* **Frontend Web App:** `http://localhost:5173`

---

## 3. Backend & Frontend Structure

### Directory Layout

```
ResolveAIV2/
├── .env.example                               # Authoritative environment template
├── requirements.txt                           # Root python dependencies
├── run.ps1                                    # Dev server launcher
├── backend/
│   ├── alembic/                               # Migration scripts & env
│   │   └── versions/                          # 15 schema migration versions
│   ├── alembic.ini                            # Migration configuration
│   ├── resolveai.db                           # Local SQLite database (seeded)
│   ├── app/
│   │   ├── main.py                            # FastAPI app instantiation & route registration
│   │   ├── config.py                          # Pydantic Settings & environment validation
│   │   ├── database.py                        # Async database engine & session dependency
│   │   ├── admin/                             # Admin metrics, audit logs, system toggles
│   │   ├── ai/                                # AI intelligence cascade, M4, providers, tools
│   │   ├── analytics/                         # Executive dashboards & CSAT aggregation
│   │   ├── auth/                              # JWT tokens, password hashing, OAuth, deps
│   │   ├── commerce/                          # Products, orders, transactions models
│   │   ├── conversations/                     # Multi-turn conversation state & services
│   │   ├── core/                              # Structured JSON logging & tracing
│   │   ├── experts/                           # Expert queue, profiles, capacity controls
│   │   ├── feedback/                          # Customer resolution & CSAT ratings
│   │   ├── handoff/                           # Escalation policies & assignment workflows
│   │   ├── memory/                            # Redis/DB entity & context persistence
│   │   ├── notifications/                     # Email, WebSocket, and in-app alerts
│   │   ├── rag/                               # Hybrid TF-IDF & FAISS knowledge retrieval
│   │   ├── shared/                            # Base models, exceptions, pagination, middleware
│   │   ├── tickets/                           # Ticket lifecycle & priority states
│   │   ├── users/                             # Customer, Expert, Admin user entities
│   │   ├── voice/                             # Sarvam STT/TTS, VAD, noise filter, openers
│   │   └── websockets/                        # Voice session state machine & event router
│   ├── data/audio/conversations/              # Local uploaded/synthesized audio cache
│   ├── scripts/                               # Operational CLI tools & evaluation suites
│   └── tests/                                 # 865 unit, integration, & regression tests
├── docs/                                      # Master documentation directory
│   ├── PROJECT_GUIDE.md                       # This master document
│   ├── README.md                              # Documentation directory index
│   ├── KNOWLEDGE_LIBRARY.md                   # Canonical RAG source knowledge
│   ├── all_knowledge_articles.json            # Structured dataset of 69 articles
│   └── resolve_mart_business_spec.md          # Business domain rules & SLAs
└── frontend/
    ├── package.json                           # Frontend dependencies & scripts
    ├── vite.config.ts                         # Vite + TanStack Start configuration
    ├── public/                                # Public assets, icons, voice audio
    └── src/
        ├── router.tsx                         # Router instantiation
        ├── routeTree.gen.ts                   # TanStack type-safe route tree
        ├── styles.css                         # Tailwind CSS v4 styling rules
        ├── assets/                            # Brand artwork and hero imagery
        ├── components/
        │   ├── ai-elements/                   # Generative UI cards, citations, status pills
        │   ├── resolve/                       # CallWithAgent, VoiceCallPage, customer, operations
        │   └── ui/                            # Shadcn UI primitives (dialog, button, dropdown, etc.)
        ├── hooks/                             # useNeuralTTS, use-mobile
        ├── lib/                               # Axios API client, auth context, client VAD, WS context
        ├── routes/                            # File-based routes (Customer, Expert, Admin, Auth)
        └── test/                              # Vitest component & voice test suites (156 tests)
```

---

## 4. Customer, Expert, and Admin Functionality

### 1. Customer Workspace (`/`, `/chat/:id`, `/call/:id`)
* **Conversational AI Chat:** Real-time streaming chat with instant typing indicators, structured tool execution results (Order status cards, Tracking timelines), and inline citations from verified knowledge articles.
* **Voice Call Agent (`/call`):** WebRTC two-way spoken conversation supporting interruptible barge-in, client-side VAD, noise suppression, and continuous multi-turn dialogue.
* **Order Tracking & Actions:** Self-service lookup for orders, shipment status, return initiation, and cancellation within policy windows.
* **Audio Dictation:** Speech-to-text dictation into the chat composer supporting mixed-language input.
* **Resolution Feedback:** Post-resolution CSAT ratings, feedback tags, and one-click reopening.

### 2. Expert Workspace (`/expert`, `/expert/queue`, `/expert/chat/:id`)
* **Real-Time Triage Queue:** Filtered list of tickets assigned to or awaiting human experts, sorted by SLA countdown, urgency, and language.
* **Live Escalation Handoff:** Displays full conversation context, extracted entities (order IDs, tracking numbers), customer emotional sentiment, and AI failure reasons so the customer never needs to repeat themselves.
* **Internal Collaboration Notes:** Threaded private internal notes visible only to experts and supervisors.
* **Ticket Reassignment & Status Transitions:** Handled via clean state machine (`ASSIGNED` $\to$ `HUMAN_HANDLING` $\to$ `RESOLVED`).

### 3. Admin Workspace (`/admin`, `/admin/analytics`, `/admin/knowledge`, `/admin/users`)
* **Operational Analytics Dashboard:** Live tracking of AI resolution rates, first-contact resolution (FCR), average handle time (AHT), escalation percentages, and sentiment shifts.
* **Knowledge Base Manager:** Interactive CRUD for knowledge articles, multi-tenant partition filters, live indexing, and cache invalidation.
* **User & Role Management:** Account activation, password resets, role assignment (`CUSTOMER`, `EXPERT`, `ADMIN`), and tenant assignment.
* **Dynamic Autonomy Controls:** Master overrides for autonomous action thresholds, financial concession limits, and automated refund caps.

---

## 5. Authentication, Authorization, and Tenant Isolation

### Authentication & Token Flow
* **Standard Credential Auth:** Password authentication with Argon2 / bcrypt hashing via `passlib[bcrypt]`.
* **OAuth 2.0 Integration:** Google OAuth login with automated user provisioning and state verification (`/api/auth/oauth/google`).
* **JWT Access & Refresh Strategy:**
  * Access Tokens: Short-lived (15 minutes), signed with `HS256`, carrying `sub` (user ID), `tenant_id`, `role`, and `email`.
  * Refresh Tokens: Long-lived (7 days), persisted in database with token revocation on password change or logout.

### Role-Based Access Control (RBAC)
FastAPI dependency injection enforces authorization:
* `get_current_active_user`: Validates token signature, expiration, and active status.
* `require_role(["EXPERT", "ADMIN"])`: Restricts expert queues and internal ticket actions.
* `require_role(["ADMIN"])`: Protects system analytics, tenant configurations, and knowledge management.

### Multi-Tenant Data Isolation
Every data-bearing model (`User`, `Conversation`, `Ticket`, `KnowledgeArticle`, `Order`, `Transaction`) enforces a mandatory `tenant_id` column.
* **Tenant Scoping:** All SQLAlchemy ORM queries and raw expressions execute with explicit tenant scoping:
  ```python
  stmt = select(Ticket).where(Ticket.tenant_id == current_user.tenant_id, Ticket.id == ticket_id)
  ```
* **RAG Partitioning:** The vector retriever strictly partitions search queries using `filter={"tenant_id": current_tenant}`. Cross-tenant leakage is strictly blocked and verified by automated regression tests.

---

## 6. RAG & Knowledge-Base Architecture

### Hybrid Retrieval Pipeline
ResolveAI V2 combines sparse lexical matching with dense semantic embeddings to balance ultra-fast local retrieval with contextual understanding.

```
Customer Query ──> [Query Normalizer & Entity Extractor]
                          │
         ┌────────────────┴────────────────┐
         ▼                                 ▼
   [TF-IDF Sparse Matcher]       [FAISS Dense Semantic Index]
   - Keyword overlap             - Sentence-Transformer embeddings
   - Exact entity match (POL-xxx)- Paraphrase & intent similarity
   - Zero-latency (<2ms)         - Sub-15ms vector cosine distance
         │                                 │
         └────────────────┬────────────────┘
                          ▼
            [Score Normalizer & Ranker]
                          │
                          ▼
           [Tenant Filter: WHERE tenant_id]
                          │
                          ▼
             [Top-K Formatted Passages] ──> Injected into LLM Prompt
```

### Knowledge Base Standards
* **Authoritative Policy Set:** Defined in [`KNOWLEDGE_LIBRARY.md`](KNOWLEDGE_LIBRARY.md) and seeded via `backend/seed_knowledge.py`.
* **Inviolable Core Rules (`[CORE]`):**
  * Support Currency: United States Dollar (**USD / $**).
  * Operating Window: AI is available **24/7/365**; Human experts: **Mon–Fri 9:00 AM – 6:00 PM EST**.
  * Return Policy Window: **30 calendar days** from verified delivery date.
  * Delivery Delay Escalation: Actionable only after **48 hours past expected delivery date**.
  * Lost Package Declaration: **5 days** with no carrier movement after expected date.
  * AI Identity: The AI assistant **must never pretend to be human** and must honor human escalation requests immediately without argument.

---

## 7. Multilingual & Code-Mixed Intelligence

The platform features deep comprehension of pan-Indian languages, recognizing that Indian users rarely communicate in formal academic scripts during voice or chat interactions.

### Code-Mixed Phrasing & Romanized Dialects
The system natively understands:
* **Tanglish:** Tamil spoken in Roman English characters (*"En order innum deliver aagala, eppo varum?"*)
* **Hinglish:** Hindi spoken in Roman English characters (*"Mera order ORD-101 abhi tak nahi aaya, refund chahiye."*)
* **Tenglish:** Telugu in Roman characters (*"Naa order tracking status ento cheppandi."*)
* **Kanglish, Manglish, Benglish, Marathish, Gujlish, Punglish.**

### Entity Preservation Guarantee
Critical alphanumeric identifiers (Order IDs like `ORD-101`, Ticket numbers `TKT-502`, tracking numbers, monetary amounts, phone numbers) are protected by regex boundary anchors. The system never alters, translates, or phonetically mutates an entity during cross-language reasoning.

---

## 8. Voice Pipeline, STT, TTS, VAD, and Call Agent

The ResolveAI Call Agent operates as a high-performance, real-time voice loop designed to maintain natural human-like pacing.

```
[User Spoken Input]
        │
        ▼
[Client-Side VAD (16kHz)] ──> Detects speech start & 800ms silence endpoint
        │
        ▼ (Audio WebSocket / REST)
[Sarvam Saaras v4 STT] ──> Streaming transcription / Romanized translit (45ms)
        │
        ▼
[Opener / Filler Cache] ──> Sub-1ms in-memory filler playback ("Checking that now...")
        │
        ▼
[LLM Reasoning (Groq)] ──> Tool execution + concise conversational phrasing (280ms TTFT)
        │
        ▼
[Sarvam Bulbul v3 TTS] ──> Streaming neural audio synthesis (120ms first chunk)
        │
        ▼
[Client Audio Output] ──> Web Audio Context with interruptible barge-in
```

### Voice Infrastructure Details
* **Voice Activity Detection (VAD):** Web Audio Worklet running client-side with energy thresholding, speech accumulation, and trailing silence timers (800ms–1000ms) to prevent premature cutoffs mid-sentence.
* **Barge-In Handling:** When user speech is detected while the agent is speaking, the client immediately pauses local playback and dispatches a `USER_INTERRUPT` event over the WebSocket to cancel active TTS streaming tasks on the backend.
* **Zero-Latency Opener Cache:** Pre-synthesized greetings and conversational fillers stored in memory across all 22 Indian languages ([`backend/app/voice/opener_cache.py`](file:///d:/ResolveAIV2/backend/app/voice/opener_cache.py)).
* **TTS Language Support:**
  * **Tier 1 (Neural Voice):** 11 languages (`en-IN`, `hi-IN`, `ta-IN`, `te-IN`, `kn-IN`, `ml-IN`, `bn-IN`, `mr-IN`, `gu-IN`, `pa-IN`, `od-IN`) synthesized via Sarvam Bulbul v3.
  * **Tier 2 (Browser Hybrid):** Urdu (`ur-IN`) and Assamese (`as-IN`) use client-side W3C Web Speech synthesis.

---

## 9. Human Handoff & Adaptive Autonomy

### Autonomous Tool Boundaries
The AI executes tools autonomously within safe policy boundaries:
* `get_order_status`: Read-only, autonomous.
* `get_tracking_details`: Read-only, autonomous.
* `cancel_order`: Autonomous only if order is in `CREATED` or `PROCESSING` state before warehouse dispatch.
* `process_refund`: Autonomous only if return has been approved and received by the warehouse.
* **Zero AI Discretion:** The AI has **zero authority to grant policy exceptions, financial concessions, or goodwill credits**.

### Escalation Protocol
A handoff event creates an `IncidentRecord`, transitions the ticket to `ESCALATED`, and assigns it to an available expert:
1. **Explicit Request:** User asks for an agent or supervisor (*"human please"*, *"agent taanga"*).
2. **Sentiment / Frustration:** Sentiment analysis detects severe customer agitation.
3. **Safety / Fraud:** Battery swelling, smoke, unauthorized charges, or account takeover.
4. **Policy Exception:** Demands for returns past the 30-day window are forwarded to supervisors.

---

## 10. Cross-Ticket Incident Detection & Persistence

ResolveAI V2 includes an asynchronous pattern-mining engine that clusters customer tickets to detect emerging product or operational incidents in real-time.

```
New Incoming Tickets ──> [Feature Extractor (Product, Issue Type, Region)]
                                   │
                                   ▼
                    [Time-Window Clustering (1h / 24h)]
                                   │
              ┌────────────────────┴────────────────────┐
              ▼                                         ▼
   [Threshold Exceeded? (>3 tickets)]        [Known Root Cause?]
              │                                         │
              ▼                                         ▼
    [Create IncidentRecord]                   [Update Existing Incident]
    - Status: INVESTIGATING                   - Increment ticket count
    - Severity: HIGH / CRITICAL               - Link related ticket IDs
    - Broadcast INCIDENT_ALERT via WS         - Trigger Proactive Notifications
```

### Persistence Models
* `IncidentRecord`: Stores incident title, description, category, affected product IDs, tenant scoping, severity, and root cause analysis.
* `Ticket`: Linked to `incident_id` foreign key for relational traceability.

---

## 11. Database Models & Migration Conventions

### Core Relational Models

| Table | Model Class | Purpose |
| :--- | :--- | :--- |
| `users` | `User` | Customer, Expert, and Admin profiles, passwords, and roles. |
| `conversations` | `Conversation` | Multi-turn interaction sessions, channels, and languages. |
| `conversation_messages` | `ConversationMessage` | Individual messages, sender roles, tokens, and audio URLs. |
| `tickets` | `Ticket` | Customer support tickets, priorities, statuses, and SLAs. |
| `handoffs` | `Handoff` | Expert escalation records, assignees, and timestamps. |
| `orders` | `Order` | E-commerce orders, items, shipping addresses, and statuses. |
| `transactions` | `Transaction` | Payment transactions, gateways, amounts, and states. |
| `knowledge_articles`| `KnowledgeArticle` | RAG policies, playbooks, categories, and search tags. |
| `incident_records` | `IncidentRecord` | Cross-ticket clusters and platform incidents. |
| `autonomy_configs` | `AutonomyConfig` | Tenant-level AI capability thresholds and boundaries. |

### Migration Conventions
* **Alembic Revisions:** All database changes must be executed through versioned Alembic scripts in `backend/alembic/versions/`.
* **Async Engine Compatibility:** Migrations must run cleanly in both SQLite (`aiosqlite`) and PostgreSQL (`asyncpg`).
* **Foreign Key Constraints:** Always define `ondelete="CASCADE"` or `ondelete="SET NULL"` explicitly.

---

## 12. Testing, Verification, & Troubleshooting

### Test Execution Commands

```powershell
# 1. Run Complete Backend Pytest Suite (865 tests)
cd backend
.venv\Scripts\python.exe -m pytest tests/ -q

# 2. Run Voice Multilingual Test Suite
.venv\Scripts\python.exe -m pytest tests/test_call_agent_multilingual_all_languages.py -q

# 3. Run Frontend Vitest Suite (18 test files, 156 tests)
cd frontend
npm test

# 4. Run Frontend Production Build Check
cd frontend
npm run build
```

### Common Troubleshooting Scenarios

| Issue / Error | Cause | Resolution |
| :--- | :--- | :--- |
| `ModuleNotFoundError: No module named 'app'` | Running pytest from repository root without PYTHONPATH | Run pytest from the `backend/` directory or prefix with `$env:PYTHONPATH='backend'`. |
| `SarvamTTSError: Language not supported by Bulbul v3` | Requesting Urdu, Assamese, or unverified dialect via neural TTS | Catch error and allow the frontend to fall back to browser Web Speech API synthesis. |
| `401 Unauthorized` on API requests | Expired access token or missing bearer header | Log in to obtain a fresh token or use the refresh endpoint `/api/auth/refresh`. |
| Audio recording not saving | Missing `data/audio/conversations/` directory | Directory is created automatically by `VoiceService`, ensure process has write permissions. |

---

## 13. Completed Milestones & Remaining Work

### Completed Milestones
* **M1–M5:** Core FastAPI architecture, JWT auth, database models, initial RAG, and basic handoff.
* **M6–M8:** Real-time WebSockets, LiveKit voice transport, analytics dashboard, and RAG cache invalidation.
* **M9–M11:** Agentic tool validation, Groq/Gemini multi-provider cascade, premium landing page, and bug hardening.
* **M12–M14:** Adaptive autonomy engine, cross-ticket incident detection, full multi-tenant isolation, and proactive escalation.
* **M15 / Call Agent Universal Upgrade:** End-to-end pan-Indian multilingual voice architecture (11 neural languages, 2 hybrid languages, 22-language understanding, sub-500ms latency, 100% entity preservation).
* **Safe Repository Cleanup:** Elimination of 23,500+ unneeded backup and scratch files, recovering 400 MB of disk bloat with zero feature regressions.

### Remaining Work & Future Roadmap
1. **LiveKit Cloud Production Cluster Deployment:** Connect the validated LiveKit transport to a distributed cloud room cluster for carrier-grade SIP telephony bridging.
2. **Additional Neural Voices:** Integrate newly emerging open-source or commercial neural acoustic models for the remaining 11 Indic languages as provider APIs mature.
3. **Automated Incident Auto-Remediation:** Expand the incident engine to automatically dispatch proactive bulk customer emails during major carrier shipment delays.

