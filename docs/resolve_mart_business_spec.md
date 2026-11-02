# ResolveMart Business Specification

> **Disclaimer**: ResolveMart is a fictional academic/demo e-commerce company created exclusively for demonstrating ResolveAI V2. Its policies and data are completely fictional and are not real-world company policies. This document serves as the authoritative business specification for tests, knowledge base (KB) articles, demo data, and AI/RAG behavior.

---

## 1. Company Profile

* **Company Name**: ResolveMart
* **Purpose**: Fictional e-commerce company acting as the sole reference environment for the ResolveAI V2 demonstration.
* **Fictional/Academic Status**: 100% fictional. Used for academic demonstration of AI capabilities.
* **Business Type**: E-commerce retail (Electronics and Accessories).
* **Supported Customer Channels**: Text chat (primary), Voice (secondary).
* **Support Scope**: Account management, Order tracking, Deliveries, Payments, Returns, Refunds, Security, and general inquiries.
* **Supported Regions/Countries**: United States.
* **Supported Currency**: USD.
* **Business Hours**: Human expert support is available Monday to Friday, 9 AM to 6 PM.
* **Support Availability**: Automated AI support is available 24/7.
* **Human Escalation Availability**: Yes, the AI can escalate to human experts via a support ticketing and handoff system.
* **Contact/Support Concept**: Customers interact first with the AI agent. If the AI cannot resolve the issue or if the policy mandates it (e.g., security, damaged items), the AI creates a ticket and escalates the conversation to a human.
* **Tenant Identity**: The demo primarily operates under the `default` tenant ID for the standard customer-facing demo. A separate isolated secondary tenant (`tenant_b`) is used strictly for security and tenant-isolation testing, and is not part of the normal demo flow.

---

## 2. Product Catalog

The following fictional product catalog is used to simulate customer orders. All items are priced in USD and have virtual/infinite stock for demo purposes.

| Product ID/SKU | Product Name | Category | Price (USD) | Returnable | Short Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| RM-001 | Wireless Headphones | Audio | $150.00 | Yes | Over-ear noise-canceling wireless headphones. |
| RM-002 | Smartwatch | Wearables | $250.00 | Yes | Fitness and health tracking smartwatch. |
| RM-003 | Mechanical Keyboard | Accessories | $100.00 | Yes | RGB mechanical keyboard with tactile switches. |
| RM-004 | Wireless Mouse | Accessories | $50.00 | Yes | Ergonomic wireless optical mouse. |
| RM-005 | 4K Monitor | Displays | $350.00 | Yes | 27-inch 4K UHD IPS monitor. |
| RM-006 | Laptop Stand | Accessories | $30.00 | Yes | Adjustable aluminum laptop stand. |
| RM-007 | USB-C Hub | Accessories | $45.00 | Yes | 7-in-1 USB-C multiport adapter. |
| RM-008 | Phone Case | Accessories | $20.00 | Yes | Shockproof silicone phone case. |
| RM-009 | Bluetooth Speaker | Audio | $80.00 | Yes | Portable waterproof Bluetooth speaker. |
| RM-010 | Power Bank | Accessories | $40.00 | Yes | 20000mAh portable charger. |

*Note: All products are eligible for standard return within 30 days of delivery. No special handling rules apply.*

---

## 3. Customer / Account Model

### Customer Identity
Customers are represented in the system using their email address, full name, and an encrypted password. They are assigned a role of `customer`.

### Account States
* **Active**: Normal operating state (`is_active = True`).
* **Locked**: Accounts are temporarily locked after 5 consecutive failed login attempts. The lock automatically expires after 30 minutes.

### Authentication & Recovery
* **Password Recovery**: Customers can reset their password via a "Forgot Password" link that sends an email with a secure reset link.
* **Account Security**: Passwords must be at least 8 characters long (alphanumeric with symbols). OTPs and passwords must never be shared.

### Privacy & Data Access Boundaries
* **Allowed**: The AI and support agents can reveal the authenticated customer's *own* account information, order status, transaction status, and ticket status.
* **Not Allowed**: The AI must **never** reveal another customer's personal data, order info, or transaction info. It must **never** expose sensitive authentication information, passwords, secrets, or raw payment credentials.

---

## 4. Order Lifecycle

The system models orders with a string-based `status`. The following states are authoritative:

* **CREATED**: Order placed, awaiting payment confirmation.
  * *Allowed*: Cancellation, address change.
* **PROCESSING**: Payment confirmed, preparing for shipment.
  * *Allowed*: Cancellation, address change.
* **SHIPPED**: Package handed over to carrier. A `tracking_number` is generated.
  * *Allowed*: Tracking.
  * *Forbidden*: Cancellation, address change.
* **DELIVERED**: Package successfully delivered to the customer.
  * *Allowed*: Initiating a return.
* **CANCELLED**: Order cancelled before shipment.
  * *Actions*: Automatically initiates a refund for deducted amounts.
* **RETURN_REQUESTED**: Customer initiated a return after delivery.
* **RETURNED**: Item received back at the warehouse and inspected.
  * *Actions*: Triggers a refund.
* **REFUNDED**: Refund processing is completed.
* **FAILED**: Order failed due to unsuccessful payment.

*Note: AI must fetch the live status from the database via tools. It must not guess or invent a status.*

---

## 5. Delivery Policy

* **Standard Delivery Estimate**: 3-5 business days from the date of shipment.
* **Shipment Tracking**: Tracking is available once the order status is `SHIPPED`.
* **Delayed Delivery**: If a delivery is past the expected date by more than 48 hours, the AI should provide the tracking status.
* **Lost Package**: If the package is not delivered 5 days past the expected date, the AI must escalate to human support.
* **Delivered-but-not-received**: If the status is `DELIVERED` but the customer claims they did not receive it, the AI must escalate to a human to check proof of delivery.
* **Failed Delivery**: Packages returned to the sender due to an invalid address will automatically trigger a refund.

---

## 6. Cancellation Policy

* **Allowed**: Cancellations are permitted **only** if the order status is `CREATED` or `PROCESSING`. Because there is no automated tool to cancel an order, the AI must explicitly **ESCALATE** these valid requests to human support for execution.
* **Not Allowed**: Cancellations are strictly forbidden once the order status is `SHIPPED` or later. 
* **Normal Shipped-Order Request**: The AI should explain that cancellation is not allowed after shipment and provide the supported return path. This is a safe policy response (`RESOLVE`), not an attempted cancellation.
* **Exception Requests**: If the customer explicitly demands an exception for a shipped order, the AI must **ESCALATE** to human support because it is a policy exception.
* **Confirmation**: Once a human agent cancels the order, the status changes to `CANCELLED` and initiates the refund process.

---

## 7. Return Policy

* **Eligibility Period**: Returns must be requested within 30 days of the order reaching `DELIVERED` status.
* **Eligible Order Statuses**: Only `DELIVERED` orders can be returned.
* **Eligible Product Conditions**: Products must be in original packaging and condition.
* **Return Request Process**: The customer requests a return; the status updates to `RETURN_REQUESTED`. The customer ships the item back. Once received, the status becomes `RETURNED`.
* **Inspection**: Returned items are inspected before the refund is finalized to `REFUNDED`.
* **Human Review**: Returns involving damaged or wrong products require human review (see Section 12).

---

## 8. Refund Policy

* **Initiation**: A refund is initiated automatically when an order is `CANCELLED`, `RETURNED`, or if a payment `FAILED` after funds were deducted.
* **Refund Lifecycle Semantics**: The refund state is primarily represented on the `Transaction` record (e.g., as `REFUNDED`). It involves three distinct stages:
  1. **Refund Initiated**: ResolveMart has requested/started the refund. (An order status of `CANCELLED` or `RETURNED` triggers this, but does NOT mean the customer has received the money yet.)
  2. **Refund Processing**: The refund is being processed internally by ResolveMart (takes up to 24 hours) and is still pending with the bank.
  3. **Refund Completed**: The original payment method has received the refund (reflects in the bank after 3-5 business days).
* **Payment Method**: Refunds are strictly sent back to the original payment method. No exceptions.
* **Failed Refund**: If a refund fails, the AI must escalate the issue to human support.

---

## 9. Payment Policy

* **Successful Payment**: Status `SUCCESS`. Order moves to `PROCESSING`.
* **Failed Payment**: Status `FAILED`. Usually reversed by banks within 24-48 hours. If deducted but order failed, refunded in 3-5 days.
* **Pending Payment**: Status `PENDING`. Occurs when the bank is confirming the transaction. Takes up to 15 minutes. Customers should not attempt to pay again while pending.
* **Duplicate Payment**: If multiple `SUCCESS` transactions exist for a single order, the AI must escalate to human support for a partial refund.
* **Information Exposure**: The AI may only confirm the transaction status and amount. It must not expose full credit card numbers or backend transaction secrets.

---

## 10. Address Change Policy

* **Before Shipment**: Shipping address changes are permitted if the order is `CREATED` or `PROCESSING`. However, because there is no automated address-update tool, the AI **must** safely escalate to human support to perform the actual update. The AI must never falsely claim the address was changed.
* **After Shipment**: The shipping address **cannot** be changed once the order is `SHIPPED`. The AI should safely decline and explain this policy.
* **Customer Responsibility**: The customer is responsible for providing the correct address. Failed deliveries due to incorrect addresses will be returned to sender and refunded.
* **Escalation**: Valid change requests (before shipment) and explicit customer demands for exceptions (after shipment) must both be escalated to a human.

---

## 11. Damaged / Wrong / Missing Product Policy

These flows cannot be fully resolved by the AI and require human escalation.

* **Damaged Product**: Requires photographic proof. Escalate to human support for replacement or refund.
* **Wrong Product**: Requires photographic proof. Escalate to human support to arrange a return and dispatch the correct product.
* **Missing Item**: Human support must verify the parcel weight with the carrier. Escalate to human.
* **Missing Package (Delivered but not found)**: Escalate to human to coordinate with the delivery carrier.

---

## 12. Account & Security Policy

* **Password Reset**: Self-service via the "Forgot Password" link. AI cannot reset passwords directly.
* **Locked Account**: Unlocks automatically after 30 minutes following 5 failed login attempts. AI can inform the customer but cannot bypass the lock.
* **Security Incident / Unauthorized Access**: If a customer reports unauthorized access, suspicious transactions, or account compromise, this is a **CRITICAL** priority. The AI must immediately escalate to a human support expert who will review logs and potentially freeze the account.
* **Boundaries**: AI must never output passwords, authentication tokens, or payment credentials.

---

## 13. Support Ticket Policy

Tickets are created when a human expert is needed.

* **Creation**: Tickets are created automatically by the AI using the `create_support_ticket` tool when escalating.
* **Ticket Statuses**: `OPEN`, `AI_PROCESSING`, `WAITING_FOR_USER`, `ESCALATED`, `ASSIGNED`, `HUMAN_HANDLING`, `RESOLVED`.
* **Priority Levels**: `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`.
* **Updates**: AI can update the subject or category of an active ticket using `update_ticket_info`.
* **Closure**: Once a ticket is `RESOLVED`, it cannot be modified by the AI.

---

## 14. Human Escalation Policy

The AI must deterministically follow these resolution pathways:

* **RESOLVE**: The AI resolves the query using KB articles (policy questions) or DB tools (order/transaction status lookups) without human help.
* **ASK_USER**: The AI asks the user for missing required information (e.g., asking for an Order Number or Transaction ID).
* **ESCALATE**: The AI creates a ticket and hands off to a human expert.

**Mandatory Escalation Conditions:**
1. Security incidents, fraud, or account compromise.
2. Unresolved payment issues (e.g., duplicate payments).
3. Repeated failure to automatically resolve an issue.
4. Unsupported business requests or policy exceptions (e.g., cancelling a shipped order).
5. Severe delivery issues (lost packages, delivered-but-missing).
6. Customer explicitly demands human support.
7. Tool failure when safe resolution is impossible.

---

## 15. AI/RAG Source-of-Truth Rules

To ensure strict consistency during the demo, the AI must adhere to the following architecture:

* **Business Policy**: General policies and timelines come strictly from the **Knowledge Base (RAG)**.
* **Live Customer State**: The actual status of a specific order, transaction, or ticket comes strictly from the **Database Tools**.
* **Combinatory Resolution**: The AI interprets the request, uses tools to fetch live state, references the KB for policy meaning, and formulates a secure response.
* **Strict Prohibitions**:
  * The AI must **NOT** invent company policies.
  * The AI must **NOT** invent order or transaction statuses.
  * The AI must **NOT** expose another customer's information (tenant/customer isolation must be respected).
  * The AI must **NOT** fabricate tool results or claim a tool action succeeded if it failed.

---

## 16. Demo Data Plan (Day 3 Readiness)

The following precise demo data profile is required for Day 3 seeding:

### Customers
* `customer_normal`: Active, standard user.
* `customer_locked`: Active, but currently in a 30-minute locked state.
* `customer_tenant_b`: A customer residing in a separate tenant ID to test isolation.

### Orders
* `ORD-101`: `PROCESSING`
* `ORD-102`: `SHIPPED` (with tracking number)
* `ORD-103`: `DELIVERED`
* `ORD-104`: `CANCELLED`
* `ORD-105`: `PROCESSING` (but `expected_delivery` is in the past, to simulate delay)
* `ORD-106`: `RETURN_REQUESTED`

### Transactions
* `TXN-201`: `SUCCESS` (maps to an order)
* `TXN-202`: `PENDING`
* `TXN-203`: `FAILED`
* `TXN-204a` & `TXN-204b`: Both `SUCCESS` for the same order (duplicate scenario).

### Tickets
* `TKT-301`: `OPEN` (Medium priority)
* `TKT-302`: `ESCALATED` (Critical priority - Security)
* `TKT-303`: `RESOLVED` (Cannot be updated)

---

## 17. Test Scenario Matrix

| # | Scenario | Expected Source | AI Action | Human Escalation |
| :--- | :--- | :--- | :--- | :--- |
| 1 | Order tracking (Valid ID, Shipped) | Tool + KB | RESOLVE | No |
| 2 | Order ID clarification | Conversation | ASK_USER | No |
| 3 | Cancellation before shipment | Tool + KB | RESOLVE / ESCALATE (if tool missing) | No (ideally) |
| 4 | Cancellation after shipment | Tool + KB | RESOLVE (Refuse cancellation) | No |
| 5 | Refund pending timeframe query | KB | RESOLVE | No |
| 6 | Refund completed status check | Tool | RESOLVE | No |
| 7 | Payment failed explanation | Tool + KB | RESOLVE | No |
| 8 | Payment pending status | Tool + KB | RESOLVE | No |
| 9 | Duplicate payment reported | Tool | ESCALATE | Yes |
| 10 | Address change before shipment | Tool | ESCALATE (No tool exists) | Yes |
| 11 | Address change after shipment | Tool + KB | RESOLVE (Refuse) / ESCALATE if demanded | No/Yes |
| 12 | Damaged product received | KB | ESCALATE | Yes |
| 13 | Wrong product received | KB | ESCALATE | Yes |
| 14 | Missing product in package | KB | ESCALATE | Yes |
| 15 | Password recovery inquiry | KB | RESOLVE | No |
| 16 | Locked account inquiry | KB | RESOLVE | No |
| 17 | Unauthorized account access | KB | ESCALATE (Critical) | Yes |
| 18 | Fraud/security incident | KB | ESCALATE (Critical) | Yes |
| 19 | Customer explicitly requests human | Conversation | ESCALATE | Yes |
| 20 | Unknown/out-of-domain request | - | RESOLVE (Safely decline; do not hallucinate policy) | No |
| 21 | Cross-customer access attempt | Tool (Auth check) | RESOLVE (Deny access) | No |
| 22 | Cross-tenant KB access attempt | RAG (Isolation) | RESOLVE (Not found) | No |
| 23 | Tool failure (DB down) | Tool Error | ESCALATE | Yes |
| 24 | Missing required info (e.g., no ID) | Conversation | ASK_USER | No |
| 25 | Multi-turn intent change | Conversation | RESOLVE / ASK_USER | No |

---

## 18. Conflict Audit

Existing academic/demo policies and the actual backend implementation were reviewed and incorporated into the authoritative ResolveMart specification.

**Status**: `NO REMAINING BUSINESS-RULE CONFLICTS`

**Details:**
* The current `backend/seed_orders.py` defines `ORD-123` (`SHIPPED`) and `ORD-999` (`DELIVERED`), which strictly aligns with the defined Order Lifecycle.
* The current `backend/seed_knowledge.py` rules (delivery times, password locks, payment handling) were integrated directly into this specification.
* Existing tool arguments (`transaction_id`, `order_number`, `ticket_id`) exactly match the expected parameters defined here.
* Crucially, the specification was updated to reflect that there are **no automated tools** for address change or order cancellation, resolving a previous contradiction. Both actions now safely mandate a human escalation.
* Database models (`Order.status`, `Transaction.status`, `TicketStatus` enums) perfectly accommodate the fictional policies described, with refund lifecycle correctly mapped to `Transaction`.
