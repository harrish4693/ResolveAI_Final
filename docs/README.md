# ResolveAI V2 — Documentation Directory

This directory contains the consolidated, production-ready documentation and knowledge assets for ResolveAI V2.

---

## Documentation Index

| File | Description | Purpose |
| :--- | :--- | :--- |
| **[`PROJECT_GUIDE.md`](PROJECT_GUIDE.md)** | **Master Project Documentation:** Comprehensive guide covering system architecture, technology stack, setup, backend/frontend layout, multi-tenant isolation, RAG, multilingual intelligence, voice pipeline (STT/TTS/VAD), human handoff, incident detection, database models, testing, and troubleshooting. | Primary technical manual for developers & operators. |
| **[`KNOWLEDGE_LIBRARY.md`](KNOWLEDGE_LIBRARY.md)** | **Canonical RAG Knowledge Base:** Authoritative human-authored operational policies (POL-001–018) and troubleshooting playbooks (TS-001–060). | Source knowledge parsed directly by `backend/seed_knowledge.py` to seed database tables. |
| **[`all_knowledge_articles.json`](all_knowledge_articles.json)** | **Structured Knowledge Base Dataset:** Raw JSON dataset containing all 69 indexed articles across active tenants (`default` and `tenant_b`), including tags, categories, and activation status. | Required data file for knowledge base evaluation and catalog generation scripts. |
| **[`resolve_mart_business_spec.md`](resolve_mart_business_spec.md)** | **ResolveMart Business Specification:** Authoritative business domain rules, company profile, order state machines, return/refund windows, and customer service SLAs. | Referenced by backend test fixtures and compliance suites. |

---

*Note: Large generated catalogs (such as `KNOWLEDGE_BASE_DETAILS.md`) can be regenerated on demand from `all_knowledge_articles.json` by running `python backend/scripts/generate_knowledge_doc.py`.*
