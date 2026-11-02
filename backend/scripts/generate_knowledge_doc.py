import json
import os

def generate_doc():
    json_path = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "all_knowledge_articles.json")
    with open(json_path, "r", encoding="utf-8") as f:
        articles = json.load(f)

    out_lines = []
    out_lines.append("# ResolveAI V2 — Complete Knowledge Base Details & Reference Guide")
    out_lines.append("")
    out_lines.append("> **Active Knowledge Base Repository:** PostgreSQL `knowledge_articles` table & ResolveMart Knowledge Library.")
    out_lines.append(f"> **Total Articles Indexed:** {len(articles)} across all active tenants (`default` and `tenant_b`).")
    out_lines.append("> **Retrieval Pipelines:** Real-time Hybrid RAG (TF-IDF keyword matching + FAISS dense semantic embeddings) with multi-tenant filtering and pan-Indian semantic query expansion.")
    out_lines.append("")
    out_lines.append("---")
    out_lines.append("")
    out_lines.append("## Table of Contents")
    out_lines.append("1. [Executive Summary & Core Business Rules](#1-executive-summary--core-business-rules)")
    out_lines.append("2. [Complete Knowledge Article Catalog (All 69 Items)](#2-complete-knowledge-article-catalog-all-69-items)")
    out_lines.append("3. [Part 1 — Core Operational FAQs (Articles 1–20)](#3-part-1--core-operational-faqs-articles-120)")
    out_lines.append("4. [Part 2 — Core Knowledge Engine Architecture & Standards (Articles 22–29)](#4-part-2--core-knowledge-engine-architecture--standards-articles-2229)")
    out_lines.append("5. [Part 3 — Authoritative Business Policies (POL-001 to POL-018, Articles 30–47)](#5-part-3--authoritative-business-policies-pol-001-to-pol-018-articles-3047)")
    out_lines.append("6. [Part 4 — General Troubleshooting Playbooks (TS-001 to TS-031, Articles 48–55)](#6-part-4--general-troubleshooting-playbooks-ts-001-to-ts-031-articles-4855)")
    out_lines.append("7. [Part 5 — Hardware Product Diagnostic Playbooks (TS-040 to TS-049, Articles 56–65)](#7-part-5--hardware-product-diagnostic-playbooks-ts-040-to-ts-049-articles-5665)")
    out_lines.append("8. [Part 6 — Critical Safety & Platform Hazards (TS-050 & TS-060, Articles 66–67)](#8-part-6--critical-safety--platform-hazards-ts-050--ts-060-articles-6667)")
    out_lines.append("9. [Part 7 — Multi-Tenant Isolation Articles (Tenant B Overrides, Articles 21, 68, 69)](#9-part-7--multi-tenant-isolation-articles-tenant-b-overrides-articles-21-68-69)")
    out_lines.append("10. [Part 8 — AI Agent Decisioning, Tools & Escalation Architecture](#10-part-8--ai-agent-decisioning-tools--escalation-architecture)")
    out_lines.append("")
    out_lines.append("---")
    out_lines.append("")

    # Section 1: Executive Summary & Core Rules
    out_lines.append("## 1. Executive Summary & Core Business Rules")
    out_lines.append("")
    out_lines.append("The ResolveAI V2 knowledge base is the central source of truth for the autonomous customer support agent, human experts, and triage systems. It is partitioned by `tenant_id` to guarantee absolute multi-tenant data isolation.")
    out_lines.append("")
    out_lines.append("### Inviolable Core Facts (`[CORE]`)")
    out_lines.append("| Domain | Core Rule / Parameter | Inviolable Policy Value |")
    out_lines.append("| :--- | :--- | :--- |")
    out_lines.append("| **Operating Region & Currency** | Geographical market and billing | United States (US), charged exclusively in **USD ($)** |")
    out_lines.append("| **Support Hours** | AI vs. Human Support Availability | **AI Support:** 24/7/365 availability<br>**Human Experts:** Monday–Friday, 9:00 AM – 6:00 PM EST |")
    out_lines.append("| **Shipping & Delivery** | Standard transit window | **3–5 business days** from shipment dispatch |")
    out_lines.append("| **Delivery Delay Escalation** | Actionable delay threshold | Investigated and escalated only after **48 hours past expected delivery date** |")
    out_lines.append("| **Lost Package Threshold** | Official declared lost status | Package marked lost after **5 days** past expected delivery with no carrier scan |")
    out_lines.append("| **Return Policy Window** | Return eligibility duration | **30 calendar days** from confirmed delivery date in original condition |")
    out_lines.append("| **Refund Processing Time** | Internal system execution | Processed within **24 hours** of cancellation/return approval |")
    out_lines.append("| **Bank Reflection Time** | Financial institution processing | **3–5 business days** depending on customer's banking institution |")
    out_lines.append("| **Pending Payment Window** | Payment gateway clearance buffer | Wait up to **15 minutes** before retrying or escalating |")
    out_lines.append("| **Failed Payment Reversal** | Deducted amount reversal | Auto-reversed within **24–48 hours** by the merchant bank |")
    out_lines.append("| **Deducted Without Order** | Payment taken without order creation | Auto-refunded within **3–5 business days** |")
    out_lines.append("| **Account Lockout Policy** | Brute-force credential protection | Temporarily locked for **30 minutes** after **5 consecutive failed attempts** |")
    out_lines.append("| **Password Requirement** | Security standard | Minimum **8 characters**, alphanumeric |")
    out_lines.append("| **Ticket Priority Levels** | SLA severity classifications | `LOW`, `MEDIUM`, `HIGH`, `CRITICAL` (Fraud/Unauthorized access is always `CRITICAL`) |")
    out_lines.append("| **Ticket Lifecycle Statuses** | Workflow state machine | `OPEN`, `AI_PROCESSING`, `WAITING_FOR_USER`, `ESCALATED`, `ASSIGNED`, `HUMAN_HANDLING`, `RESOLVED` |")
    out_lines.append("")
    out_lines.append("---")
    out_lines.append("")

    # Section 2: Index Table
    out_lines.append("## 2. Complete Knowledge Article Catalog (All 69 Items)")
    out_lines.append("")
    out_lines.append("| ID | Tenant | Category | Article Title | Primary Tags | Status |")
    out_lines.append("| :---: | :---: | :--- | :--- | :--- | :---: |")
    for a in articles:
        title_str = a['title'].strip() if a['title'] else "Untitled Article"
        tags_str = ", ".join(a['tags']) if a['tags'] else "—"
        status_str = "Active" if a['is_active'] else "Inactive"
        out_lines.append(f"| {a['id']} | `{a['tenant_id']}` | **{a['category']}** | {title_str} | `{tags_str}` | {status_str} |")
    out_lines.append("")
    out_lines.append("---")
    out_lines.append("")

    articles_by_id = {a['id']: a for a in articles}

    # Helper function to print an article
    def render_article(a, as_code=False):
        title_str = a['title'].strip() if a['title'] else "Untitled Article"
        lines = []
        lines.append(f"### [ID: {a['id']}] {title_str}")
        lines.append(f"- **Category:** `{a['category']}` | **Tenant ID:** `{a['tenant_id']}` | **Status:** `{'Active' if a['is_active'] else 'Inactive'}`")
        tags_display = ', '.join([f'`{t}`' for t in a['tags']]) if a['tags'] else 'None'
        lines.append(f"- **Search Tags:** {tags_display}")
        lines.append("")
        if as_code:
            lines.append("```text")
            lines.append(a['content'].strip())
            lines.append("```")
        else:
            lines.append(a['content'].strip())
        lines.append("")
        lines.append("---")
        lines.append("")
        return lines

    # Part 1: Articles 1 to 20
    out_lines.append("## 3. Part 1 — Core Operational FAQs (Articles 1–20)")
    out_lines.append("")
    out_lines.append("Rapid reference answers for common customer inquiries regarding account recovery, payment troubleshooting, order lifecycle, cancellations, and escalations.")
    out_lines.append("")
    for aid in range(1, 21):
        if aid in articles_by_id:
            out_lines.extend(render_article(articles_by_id[aid], as_code=False))

    # Part 2: Articles 22 to 29
    out_lines.append("## 4. Part 2 — Core Knowledge Engine Architecture & Standards (Articles 22–29)")
    out_lines.append("")
    out_lines.append("Governing rules dictating how AI assistants ingest knowledge, fetch live database facts, classify rules (`[CORE]` vs `[EXT]`), format handoff notes, and maintain professional conversational tone.")
    out_lines.append("")
    for aid in range(22, 30):
        if aid in articles_by_id:
            out_lines.extend(render_article(articles_by_id[aid], as_code=False))

    # Part 3: Articles 30 to 47 (POL-001 to POL-018)
    out_lines.append("## 5. Part 3 — Authoritative Business Policies (POL-001 to POL-018, Articles 30–47)")
    out_lines.append("")
    out_lines.append("Comprehensive operational and legal policies governing ResolveMart customer service.")
    out_lines.append("")
    for aid in range(30, 48):
        if aid in articles_by_id:
            out_lines.extend(render_article(articles_by_id[aid], as_code=False))

    # Part 4: Articles 48 to 55 (TS-001 to TS-031)
    out_lines.append("## 6. Part 4 — General Troubleshooting Playbooks (TS-001 to TS-031, Articles 48–55)")
    out_lines.append("")
    out_lines.append("Diagnostic playbooks and decision trees for tracking, delayed delivery, marked delivered not received, payment errors, refund delays, account lockouts, and unauthorized access.")
    out_lines.append("")
    for aid in range(48, 56):
        if aid in articles_by_id:
            out_lines.extend(render_article(articles_by_id[aid], as_code=False))

    # Part 5: Articles 56 to 65 (TS-040 to TS-049)
    out_lines.append("## 7. Part 5 — Hardware Product Diagnostic Playbooks (TS-040 to TS-049, Articles 56–65)")
    out_lines.append("")
    out_lines.append("Device-level hardware troubleshooting playbooks for all 10 ResolveMart products (RM-001 through RM-010).")
    out_lines.append("")
    for aid in range(56, 66):
        if aid in articles_by_id:
            out_lines.extend(render_article(articles_by_id[aid], as_code=False))

    # Part 6: Articles 66 & 67 (TS-050 & TS-060)
    out_lines.append("## 8. Part 6 — Critical Safety & Platform Hazards (TS-050 & TS-060, Articles 66–67)")
    out_lines.append("")
    out_lines.append("Immediate stop-use emergency procedures for hazardous batteries/smoke (TS-050) and web checkout/platform diagnostic procedures (TS-060).")
    out_lines.append("")
    for aid in [66, 67]:
        if aid in articles_by_id:
            out_lines.extend(render_article(articles_by_id[aid], as_code=False))

    # Part 7: Articles 21, 68, 69 (Tenant B)
    out_lines.append("## 9. Part 7 — Multi-Tenant Isolation Articles (Tenant B Overrides, Articles 21, 68, 69)")
    out_lines.append("")
    out_lines.append("Tenant-isolated articles proving that Tenant B has separate policies (e.g. 90-day return window) that are invisible and inaccessible to Tenant Default.")
    out_lines.append("")
    for aid in [21, 68, 69]:
        if aid in articles_by_id:
            out_lines.extend(render_article(articles_by_id[aid], as_code=False))

    # Part 8: AI Agent Architecture
    out_lines.append("## 10. Part 8 — AI Agent Decisioning, Tools & Escalation Architecture")
    out_lines.append("")
    out_lines.append("### A. Knowledge vs. Live State Division")
    out_lines.append("- **Knowledge Base (RAG):** General rules, policies, time windows, return criteria, troubleshooting steps, and warranty conditions.")
    out_lines.append("- **Live Tool Execution:** Order tracking status, current balance, payment gateway state, ticket queue status. AI never assumes or fabricates live states from the knowledge base.")
    out_lines.append("")
    out_lines.append("### B. Hybrid RAG Architecture")
    out_lines.append("1. **TF-IDF Sparse Ingestion:** Inverted token index across article title, category, tags, and body.")
    out_lines.append("2. **FAISS Dense Semantic Retrieval:** Vector index mapping conversational queries to relevant policy paragraphs.")
    out_lines.append("3. **Pan-Indian Query Enrichment:** Multilingual queries in native scripts (Tamil, Telugu, Kannada, Malayalam, Hindi, Bengali, Marathi, Gujarati, Punjabi) or Romanized transliterations (Tanglish, Hinglish) are canonically mapped to English search concepts by the `UniversalMeaningEngine`, yielding high-confidence recall without translating the user's conversation.")
    out_lines.append("4. **Tenant Isolation:** All retrieval passes strict `WHERE tenant_id = :tenant_id` clauses to prevent cross-tenant data leakage.")
    out_lines.append("")
    out_lines.append("### C. Autonomous Escalation Triggers")
    out_lines.append("The AI assistant automatically transfers the ticket to a human expert when:")
    out_lines.append("1. **Security/Fraud Alert:** Suspected account takeover, unauthorized charges, or credential breaches (`CRITICAL` priority).")
    out_lines.append("2. **Delivery Delay Exceeding Threshold:** Package delayed > 48 hours past delivery estimate, or declared lost after 5 days.")
    out_lines.append("3. **Delivered but Not Received:** Suspected misdelivery or courier theft.")
    out_lines.append("4. **Hardware Safety Risk:** Battery swelling, overheating, smoke, or burning smell (`CRITICAL` priority).")
    out_lines.append("5. **Missing/Damaged Goods:** Physical product defects or incomplete shipments requiring human inspection.")
    out_lines.append("6. **Customer Demand:** Direct user request to speak with a human support representative.")
    out_lines.append("")

    # Write to docs/KNOWLEDGE_BASE_DETAILS.md and root KNOWLEDGE_BASE_DETAILS.md
    docs_path = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "KNOWLEDGE_BASE_DETAILS.md")
    root_path = os.path.join(os.path.dirname(__file__), "..", "..", "KNOWLEDGE_BASE_DETAILS.md")
    
    content = "\n".join(out_lines)
    with open(docs_path, "w", encoding="utf-8") as f:
        f.write(content)
    with open(root_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Generated {docs_path} and {root_path} ({len(out_lines)} lines, {len(content)} characters)")

if __name__ == "__main__":
    generate_doc()
