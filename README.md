# ResolveAIV2

AI-First Customer Support Platform — workflow-driven support with intelligent automation and human expertise.

## Features

- **Text Support** — Real-time conversational AI support
- **Voice Support** — STT/TTS with provider abstraction
- **AI Understanding** — Intent, sentiment, entity, priority analysis
- **Knowledge/RAG** — Retrieval-augmented responses from curated knowledge base
- **Decision Engine** — Deterministic RESOLVE / ASK_USER / ESCALATE
- **Human Handoff** — Context-preserving escalation to human experts
- **Expert System** — Queue, routing, assignment, expert tooling
- **Ticket Management** — Full lifecycle tracking

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, TypeScript, Vite, Tailwind CSS |
| Backend | Python 3.11+, FastAPI, Pydantic v2 |
| Database | SQLite (dev) / PostgreSQL (prod) via SQLAlchemy 2.0 |
| AI | Abstracted provider (mock default) |
| RAG | TF-IDF (default) / FAISS (pluggable) |
| Auth | JWT + bcrypt |

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- npm 9+

### Setup

```bash
# Clone and enter project
cd D:\ResolveAIV2

# Backend
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
alembic upgrade head
python -m uvicorn app.main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
npm install
npm run dev
```

### Environment

```bash
cp .env.example .env
# Edit .env with your settings
```

## Database Migrations & Schema Safety

ResolveAIV2 uses **Alembic** to manage database schema evolution safely across development and production environments.

### Applying Migrations
To upgrade the active database to the latest schema:
```bash
cd backend
python -m alembic upgrade head
```

### Rolling Back
To rollback the most recent migration:
```bash
python -m alembic downgrade -1
```

### Adding New Model Fields & Generating Migrations
Whenever you add or modify a column or table in `app/*/models.py`:
```bash
cd backend
python -m alembic revision --autogenerate -m "add_column_name_to_table"
python -m alembic upgrade head
```

### Startup Migration Check
On application startup, FastAPI checks the database's current revision in `alembic_version` against Alembic's latest `head`. If the database is behind, a warning is logged in the console:
```
⚠️ DATABASE MIGRATION WARNING: Database revision (...) is behind Alembic head (...).
Run 'python -m alembic upgrade head' to apply pending migrations and avoid runtime column errors.
```

### Schema Parity Testing
Automated test [`tests/test_migration_schema_parity.py`](file:///D:/ResolveAIV2/backend/tests/test_migration_schema_parity.py) runs on every test run. It executes `alembic upgrade head` on an empty database and compares the generated schema against SQLAlchemy's `Base.metadata`, failing immediately if any model change lacks a migration.

## Documentation

- [Master Project Guide](docs/PROJECT_GUIDE.md) — Comprehensive architecture, setup, capabilities, and verification guide.
- [Knowledge Library](docs/KNOWLEDGE_LIBRARY.md) — Canonical knowledge source for RAG and policies.
- [ResolveMart Business Specification](docs/resolve_mart_business_spec.md) — Domain rules and SLAs.
- [Documentation Index](docs/README.md) — Complete documentation catalog.

## Project Structure

```
D:\ResolveAIV2\
├── backend/          # FastAPI application
├── frontend/         # React/TypeScript application
├── docs/             # Documentation
├── .env.example      # Environment template
└── README.md
```
