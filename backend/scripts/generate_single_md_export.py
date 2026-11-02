import os
import json
from datetime import datetime, timezone

def generate_single_md():
    export_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "audit", "rag_dataset_export"))
    
    with open(os.path.join(export_dir, "policies.json"), "r", encoding="utf-8") as f:
        policies = json.load(f)
    with open(os.path.join(export_dir, "orders.json"), "r", encoding="utf-8") as f:
        orders = json.load(f)
    with open(os.path.join(export_dir, "transactions.json"), "r", encoding="utf-8") as f:
        transactions = json.load(f)
    with open(os.path.join(export_dir, "tickets.json"), "r", encoding="utf-8") as f:
        tickets = json.load(f)
    with open(os.path.join(export_dir, "handoffs.json"), "r", encoding="utf-8") as f:
        handoffs = json.load(f)
    with open(os.path.join(export_dir, "tool_executions.json"), "r", encoding="utf-8") as f:
        tool_executions = json.load(f)
    with open(os.path.join(export_dir, "rag_chunks.json"), "r", encoding="utf-8") as f:
        rag_chunks = json.load(f)

    md = []
    md.append("# ResolveAI V2 — Complete RAG Dataset, Policies, Commercial Orders & Status History")
    md.append("")
    md.append(f"> **Generated:** {datetime.now(timezone.utc).isoformat()}")
    md.append("> **Audit Type:** Complete Single-File Read-Only Data Export")
    md.append(f"> **Database Sources:** PostgreSQL (Active Application DB) & Local Replica `resolveai.db`")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## Table of Contents")
    md.append("1. [Executive Summary & Record Counts](#1-executive-summary--record-counts)")
    md.append("2. [Core Business Rules & Inviolable Parameters (`[CORE]`)](#2-core-business-rules--inviolable-parameters-core)")
    md.append("3. [Commercial Orders (All 7 Orders)](#3-commercial-orders-all-7-orders)")
    md.append("4. [Payment Transactions (All 5 Transactions)](#4-payment-transactions-all-5-transactions)")
    md.append("5. [Support Tickets & Lifecycle Status Events (All 175 Tickets)](#5-support-tickets--lifecycle-status-events-all-175-tickets)")
    md.append("6. [Supervisor Escalations & Handoffs (All 44 Records)](#6-supervisor-escalations--handoffs-all-44-records)")
    md.append("7. [Autonomous Tool Execution Audit Trail (All 45 Records)](#7-autonomous-tool-execution-audit-trail-all-45-records)")
    md.append("8. [Complete Company Knowledge Base & Policies (All 69 Articles Full Text)](#8-complete-company-knowledge-base--policies-all-69-articles-full-text)")
    md.append("9. [RAG Ingestion Tokenized Chunks (All 69 Chunks)](#9-rag-ingestion-tokenized-chunks-all-69-chunks)")
    md.append("10. [Storage Schema Realities & Ingestion Architecture](#10-storage-schema-realities--ingestion-architecture)")
    md.append("")
    md.append("---")
    md.append("")

    # Section 1: Executive Summary
    md.append("## 1. Executive Summary & Record Counts")
    md.append("")
    md.append("| Dataset Entity | Storage Table | Total Records | Active / Status Summary |")
    md.append("| :--- | :--- | :---: | :--- |")
    md.append(f"| **Knowledge Articles / Policies** | `knowledge_articles` | **{len(policies)}** | 61 Active, 8 Inactive (66 `default`, 3 `tenant_b`) |")
    md.append(f"| **Commercial Orders** | `orders` | **{len(orders)}** | 2 SHIPPED, 2 PROCESSING, 1 DELIVERED, 1 CANCELLED, 1 RETURN_REQUESTED |")
    md.append(f"| **Financial Transactions** | `transactions` | **{len(transactions)}** | 3 SUCCESS, 1 PENDING, 1 FAILED (Total: $600.00 USD) |")
    md.append(f"| **Support Tickets** | `tickets` | **{len(tickets)}** | 91 OPEN, 41 RESOLVED, 35 ESCALATED, 8 WAITING_FOR_USER |")
    md.append(f"| **Supervisor Handoffs** | `handoffs` | **{len(handoffs)}** | 38 WAITING, 4 ASSIGNED, 2 RESOLVED |")
    md.append(f"| **Tool Audit Executions** | `tool_executions` | **{len(tool_executions)}** | 45 tool executions with idempotency hashes and results |")
    md.append(f"| **RAG Tokenized Chunks** | In-Memory FAISS/TF-IDF | **{len(rag_chunks)}** | 69 distinct 500-token chunks indexed by `tiktoken` |")
    md.append("")
    md.append("---")
    md.append("")

    # Section 2: Core Rules
    md.append("## 2. Core Business Rules & Inviolable Parameters (`[CORE]`)")
    md.append("")
    md.append("| Domain | Core Rule / Parameter | Inviolable Policy Value |")
    md.append("| :--- | :--- | :--- |")
    md.append("| **Operating Region & Currency** | Geographical market and billing | United States (US), charged exclusively in **USD ($)** |")
    md.append("| **Support Hours** | AI vs. Human Support Availability | **AI Support:** 24/7/365 availability<br>**Human Experts:** Monday–Friday, 9:00 AM – 6:00 PM EST |")
    md.append("| **Shipping & Delivery** | Standard transit window | **3–5 business days** from shipment dispatch |")
    md.append("| **Delivery Delay Escalation** | Actionable delay threshold | Investigated and escalated only after **48 hours past expected delivery date** |")
    md.append("| **Lost Package Threshold** | Official declared lost status | Package marked lost after **5 days** past expected delivery with no carrier scan |")
    md.append("| **Return Policy Window** | Return eligibility duration | **30 calendar days** from confirmed delivery date in original condition |")
    md.append("| **Refund Processing Time** | Internal system execution | Processed within **24 hours** of cancellation/return approval |")
    md.append("| **Bank Reflection Time** | Financial institution processing | **3–5 business days** depending on customer's banking institution |")
    md.append("| **Pending Payment Window** | Payment gateway clearance buffer | Wait up to **15 minutes** before retrying or escalating |")
    md.append("| **Failed Payment Reversal** | Deducted amount reversal | Auto-reversed within **24–48 hours** by the merchant bank |")
    md.append("| **Deducted Without Order** | Payment taken without order creation | Auto-refunded within **3–5 business days** |")
    md.append("| **Account Lockout Policy** | Brute-force credential protection | Temporarily locked for **30 minutes** after **5 consecutive failed attempts** |")
    md.append("| **Password Requirement** | Security standard | Minimum **8 characters**, alphanumeric |")
    md.append("| **Ticket Priority Levels** | SLA severity classifications | `LOW`, `MEDIUM`, `HIGH`, `CRITICAL` (Fraud/Unauthorized access is always `CRITICAL`) |")
    md.append("| **Ticket Lifecycle Statuses** | Workflow state machine | `OPEN`, `AI_PROCESSING`, `WAITING_FOR_USER`, `ESCALATED`, `ASSIGNED`, `HUMAN_HANDLING`, `RESOLVED` |")
    md.append("")
    md.append("---")
    md.append("")

    # Section 3: Orders
    md.append("## 3. Commercial Orders (All 7 Orders)")
    md.append("")
    md.append("All existing order records retrieved directly from the `orders` database table:")
    md.append("")
    md.append("| ID | Order Number | Customer ID | Tenant | Status | Tracking Number | Expected Delivery | Created Timestamp | Updated Timestamp |")
    md.append("| :---: | :--- | :---: | :---: | :--- | :---: | :--- | :--- | :--- |")
    for o in orders:
        exp = o['expected_delivery'] or "None / N/A"
        trk = f"`{o['tracking_number']}`" if o['tracking_number'] else "*None*"
        md.append(f"| {o['id']} | **`{o['order_number']}`** | {o['customer_id']} | `{o['tenant_id']}` | **`{o['status']}`** | {trk} | {exp} | {o['created_at']} | {o['updated_at']} |")
    md.append("")
    md.append("---")
    md.append("")

    # Section 4: Transactions
    md.append("## 4. Payment Transactions (All 5 Transactions)")
    md.append("")
    md.append("All existing transaction records retrieved directly from the `transactions` database table:")
    md.append("")
    md.append("| ID | Transaction ID | Customer ID | Tenant | Amount | Currency | Status | Created Timestamp | Updated Timestamp |")
    md.append("| :---: | :--- | :---: | :---: | :---: | :---: | :--- | :--- | :--- |")
    for t in transactions:
        md.append(f"| {t['id']} | **`{t['transaction_id']}`** | {t['customer_id']} | `{t['tenant_id']}` | ${t['amount']:.2f} | {t['currency']} | **`{t['status']}`** | {t['created_at']} | {t['updated_at']} |")
    md.append("")
    md.append("---")
    md.append("")

    # Section 5: Tickets
    md.append("## 5. Support Tickets & Lifecycle Status Events (All 175 Tickets)")
    md.append("")
    md.append("Complete audit of support tickets representing customer lifecycle events and resolution states from `tickets` table:")
    md.append("")
    md.append("| ID | Subject | Customer | Conv ID | Category | Status | Priority | Resolved At | Created At |")
    md.append("| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |")
    for t in tickets:
        subj = t['subject'].replace("|", "-")
        cat = t['category'] or "—"
        res = t['resolved_at'] or "—"
        md.append(f"| {t['id']} | {subj} | {t['customer_id']} | {t['conversation_id']} | {cat} | `{t['status']}` | `{t['priority']}` | {res} | {t['created_at']} |")
    md.append("")
    md.append("---")
    md.append("")

    # Section 6: Handoffs
    md.append("## 6. Supervisor Escalations & Handoffs (All 44 Records)")
    md.append("")
    md.append("AI-to-human escalation bridges capturing reasons, priorities, and assigned experts from `handoffs` table:")
    md.append("")
    md.append("| ID | Ticket ID | Conv ID | Customer | Reason / Trigger | Priority | Category | Status | Assigned Expert | Created At |")
    md.append("| :---: | :---: | :---: | :---: | :--- | :---: | :---: | :---: | :---: | :--- |")
    for h in handoffs:
        reason = h['escalation_reason'].replace("\n", " ").replace("|", "-")[:80]
        expert = h['assigned_expert_id'] or "Unassigned"
        md.append(f"| {h['id']} | {h['ticket_id']} | {h['conversation_id']} | {h['customer_id']} | {reason} | `{h['priority']}` | `{h['category']}` | `{h['status']}` | {expert} | {h['created_at']} |")
    md.append("")
    md.append("---")
    md.append("")

    # Section 7: Tool Executions
    md.append("## 7. Autonomous Tool Execution Audit Trail (All 45 Records)")
    md.append("")
    md.append("Complete record of autonomous tools invoked during customer interactions from `tool_executions` table:")
    md.append("")
    md.append("| ID | Conv ID | Customer | Tool Name | Status | Arguments | Result Summary | Started At |")
    md.append("| :---: | :---: | :---: | :--- | :---: | :--- | :--- | :--- |")
    for te in tool_executions:
        args = str(te['tool_args']).replace("\n", " ").replace("|", "-")[:45]
        res = str(te['result_summary'] or te['error_code'] or "None").replace("\n", " ").replace("|", "-")[:50]
        md.append(f"| {te['id']} | {te['conversation_id']} | {te['customer_id']} | **`{te['tool_name']}`** | `{te['status']}` | `{args}` | {res} | {te['started_at']} |")
    md.append("")
    md.append("---")
    md.append("")

    # Section 8: Policies Full Text
    md.append("## 8. Complete Company Knowledge Base & Policies (All 69 Articles Full Text)")
    md.append("")
    md.append("Verbatim content for all 69 knowledge base articles indexed in PostgreSQL:")
    md.append("")
    for p in policies:
        status_label = "Active" if p['is_active'] else "Inactive"
        tags_str = ", ".join([f"`{t}`" for t in p['tags']]) if p['tags'] else "None"
        md.append(f"### [Article {p['id']}] {p['title']}")
        md.append(f"- **Category:** `{p['category']}` | **Tenant ID:** `{p['tenant_id']}` | **Active Status:** `{status_label}`")
        md.append(f"- **Tags:** {tags_str}")
        md.append(f"- **Created:** `{p['created_at']}` | **Updated:** `{p['updated_at']}`")
        md.append("")
        md.append(p['content'].strip())
        md.append("")
        md.append("---")
        md.append("")

    # Section 9: RAG Chunks
    md.append("## 9. RAG Ingestion Tokenized Chunks (All 69 Chunks)")
    md.append("")
    md.append("Exact chunking produced by `tiktoken` (`cl100k_base`, 500 max tokens) consumed by FAISS and TF-IDF:")
    md.append("")
    md.append("| Chunk ID | Article ID | Tenant | Category | Article Title | Chunk Index | Text Length |")
    md.append("| :---: | :---: | :---: | :--- | :--- | :---: | :---: |")
    for c in rag_chunks:
        md.append(f"| {c['chunk_id']} | {c['article_id']} | `{c['tenant_id']}` | `{c['category']}` | {c['title']} | {c['chunk_index']} / {c['total_chunks_for_article']} | {len(c['chunk_text'])} chars |")
    md.append("")
    md.append("---")
    md.append("")

    # Section 10: Storage Schema Realities & Ingestion Architecture
    md.append("## 10. Storage Schema Realities & Ingestion Architecture")
    md.append("")
    md.append("### A. Database Storage Realities")
    md.append("1. **Order Schema:** The physical `orders` table tracks lifecycle events with `(id, customer_id, tenant_id, order_number, status, expected_delivery, tracking_number, created_at, updated_at)`. There is no separate item array or line-item cost column in the database table.")
    md.append("2. **Transaction Schema:** The physical `transactions` table tracks payment events with `(id, customer_id, tenant_id, transaction_id, amount, currency, status, created_at, updated_at)`. Transactions link to customers; there is no direct SQL foreign key to `orders.id`.")
    md.append("3. **Vector Indices:** FAISS indices are generated dynamically in-memory (`IndexFlatL2`, 1536 dimensions) using OpenAI embeddings and cached per tenant, rather than saved to disk as binary `.faiss` files.")
    md.append("")
    md.append("### B. Hybrid RAG Pipeline")
    md.append("- **Sparse Keyword Search:** `TFIDFRetriever` creates an in-memory TF-IDF matrix over article titles, tags, and content per tenant.")
    md.append("- **Dense Vector Search:** `FAISSRetriever` embeds chunked documents.")
    md.append("- **Pan-Indian Semantic Canonicalization:** When a customer asks a question in Tamil, Tanglish, Telugu, Kannada, Malayalam, Hindi, Hinglish, Bengali, Marathi, Gujarati, or Punjabi, the `UniversalMeaningEngine` extracts canonical English concepts (e.g. `['delivery_delay', 'shipping', 'order']`) to retrieve the English policy without query translation data loss.")
    md.append("- **Multi-Tenant Scoping:** All database and RAG searches strictly enforce `WHERE tenant_id = :tenant_id`.")
    md.append("")

    content = "\n".join(md)
    
    # Save to export directory and root
    target_export = os.path.join(export_dir, "COMPLETE_DATASET.md")
    target_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "COMPLETE_DATASET.md"))
    
    with open(target_export, "w", encoding="utf-8") as f:
        f.write(content)
    with open(target_root, "w", encoding="utf-8") as f:
        f.write(content)
        
    print(f"Generated {target_export} and {target_root}")
    print(f"Total lines: {len(md)}, Total characters: {len(content)}")

if __name__ == "__main__":
    generate_single_md()

