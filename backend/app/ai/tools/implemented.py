"""
ResolveAIV2 — M12.3 Production Support Tools

Each tool:
  - has explicit registration, name, schema, authorization, risk level
  - receives (db, user, conversation_id) from the runtime — never from the AI
  - validates inputs, checks ownership, returns structured results
  - never exposes passwords, tokens, or secrets
"""

from typing import Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools.base import BaseTool, ToolParameter, ToolSecurityPolicy
from app.tickets.models import Ticket
from app.users.models import User
from app.shared.models import TicketStatus, Priority, UserRole
from app.commerce.models import Order, Transaction

import re
from sqlalchemy import select, or_, func

# ══════════════════════════════════════════════════════════════
# A. GET ORDER STATUS  (Low Risk)
# ══════════════════════════════════════════════════════════════

class GetOrderStatusTool(BaseTool):
    name = "get_order_status"
    description = "Check the shipping/delivery status of a customer order."
    use_when = "Customer has provided or confirmed an order ID to check tracking or delivery status."
    do_not_use_when = "No order ID is known or provided yet (ask user for order ID first)."
    parameters = [
        ToolParameter(name="order_id", type="string", description="The order ID to look up (e.g. ORD123).")
    ]
    security_policy = ToolSecurityPolicy(
        requires_confirmation=False,
        risk_level="low",
    )

    async def execute(self, *, db: AsyncSession, user: User, conversation_id: int, **kwargs) -> Dict[str, Any]:
        order_id = kwargs.get("order_id", "").strip()
        if not order_id:
            return {"success": False, "tool": self.name, "error_code": "MISSING_ORDER_ID",
                    "message": "Please provide an order ID."}

        clean_id = re.sub(r"[#\s]", "", order_id).strip()
        norm_order_id = re.sub(r"[-_\s#]", "", order_id).lower()
        candidates = {norm_order_id}
        if norm_order_id.isdigit():
            candidates.add(f"ord{norm_order_id}")
            candidates.add(f"ord-{norm_order_id}")
        elif norm_order_id.startswith("ord"):
            candidates.add(norm_order_id[3:])

        stmt = select(Order).where(
            or_(
                Order.order_number.ilike(order_id),
                Order.order_number.ilike(clean_id),
                *[func.replace(func.replace(Order.order_number, "-", ""), "_", "").ilike(c) for c in candidates]
            ),
            Order.tenant_id == user.tenant_id
        )
        order = await db.scalar(stmt)

        if not order:
            return {"success": False, "tool": self.name, "error_code": "ORDER_NOT_FOUND",
                    "message": "Order could not be found. Please verify the order ID."}

        # Strict multi-tenant and customer ownership check
        if order.tenant_id != user.tenant_id or order.customer_id != user.id:
            return {"success": False, "tool": self.name, "error_code": "ACCESS_DENIED",
                    "message": "You do not have permission to view this order."}

        return {
            "success": True,
            "tool": self.name,
            "data": {
                "order_id": order.order_number,
                "status": order.status,
                "expected_delivery": order.expected_delivery.isoformat() if order.expected_delivery else None,
                "tracking_number": order.tracking_number,
            },
        }

# ══════════════════════════════════════════════════════════════
# A2. CHECK TRANSACTION  (Low Risk)
# ══════════════════════════════════════════════════════════════

class CheckTransactionTool(BaseTool):
    name = "check_transaction"
    description = "Check the status and details of a customer transaction."
    use_when = "Customer has provided a transaction or payment reference ID to verify payment or refund status."
    do_not_use_when = "No transaction ID is provided (ask user first) or if querying general order delivery."
    parameters = [
        ToolParameter(name="transaction_id", type="string", description="The transaction ID to look up (e.g. TXN123).")
    ]
    security_policy = ToolSecurityPolicy(
        requires_confirmation=False,
        risk_level="low",
    )

    async def execute(self, *, db: AsyncSession, user: User, conversation_id: int, **kwargs) -> Dict[str, Any]:
        txn_id = kwargs.get("transaction_id", "").strip()
        if not txn_id:
            return {"success": False, "tool": self.name, "error_code": "MISSING_TRANSACTION_ID",
                    "message": "Please provide a transaction ID."}

        stmt = select(Transaction).where(
            Transaction.transaction_id == txn_id,
            Transaction.tenant_id == user.tenant_id,
            Transaction.customer_id == user.id
        )
        txn = await db.scalar(stmt)

        if not txn:
            return {"success": False, "tool": self.name, "error_code": "TRANSACTION_NOT_FOUND",
                    "message": "Transaction could not be found. Please verify the transaction ID."}

        # Defense in depth explicit check
        if txn.tenant_id != user.tenant_id or txn.customer_id != user.id:
            return {"success": False, "tool": self.name, "error_code": "ACCESS_DENIED",
                    "message": "You do not have permission to view this transaction."}

        return {
            "success": True,
            "tool": self.name,
            "data": {
                "transaction_id": txn.transaction_id,
                "status": txn.status,
                "amount": txn.amount,
                "currency": txn.currency,
            },
        }

# ══════════════════════════════════════════════════════════════
# B. GET TICKET / SUPPORT STATUS  (Low Risk)
# ══════════════════════════════════════════════════════════════

class GetTicketStatusTool(BaseTool):
    name = "get_ticket_status"
    description = "Look up the status of a support ticket."
    use_when = "Customer has provided an existing numeric ticket ID to check progress."
    do_not_use_when = "Customer has not provided a ticket ID or is reporting a new issue."
    parameters = [
        ToolParameter(name="ticket_id", type="integer", description="The numeric ticket ID.")
    ]
    security_policy = ToolSecurityPolicy(
        requires_confirmation=False,
        risk_level="low",
    )

    async def execute(self, *, db: AsyncSession, user: User, conversation_id: int, **kwargs) -> Dict[str, Any]:
        raw = kwargs.get("ticket_id")
        try:
            ticket_id = int(raw)
        except (TypeError, ValueError):
            return {"success": False, "tool": self.name, "error_code": "INVALID_TICKET_ID",
                    "message": "Ticket ID must be a number."}

        ticket = await db.get(Ticket, ticket_id)
        if not ticket:
            return {"success": False, "tool": self.name, "error_code": "TICKET_NOT_FOUND",
                    "message": "Ticket not found."}

        # Ownership check — customers can only see their own tickets
        if str(user.role) in (UserRole.CUSTOMER, UserRole.CUSTOMER.value):
            if ticket.customer_id != user.id:
                return {"success": False, "tool": self.name, "error_code": "ACCESS_DENIED",
                        "message": "You do not have permission to view this ticket."}

        data: Dict[str, Any] = {
            "ticket_id": ticket.id,
            "subject": ticket.subject,
            "status": ticket.status if isinstance(ticket.status, str) else ticket.status.value,
            "priority": ticket.priority if isinstance(ticket.priority, str) else ticket.priority.value,
            "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
        }

        # Experts/admins may see more
        if str(user.role) in (UserRole.EXPERT, UserRole.EXPERT.value, UserRole.ADMIN, UserRole.ADMIN.value):
            data["category"] = ticket.category
            data["resolved_at"] = ticket.resolved_at.isoformat() if ticket.resolved_at else None

        return {"success": True, "tool": self.name, "data": data}


# ══════════════════════════════════════════════════════════════
# C. GET CUSTOMER ACCOUNT INFORMATION  (Low Risk)
# ══════════════════════════════════════════════════════════════

class GetCustomerAccountInfoTool(BaseTool):
    name = "get_customer_account_info"
    description = "Retrieve the authenticated customer's safe account information."
    use_when = "Customer specifically asks about their registered profile, email, or account status."
    do_not_use_when = "Customer is inquiring about orders, refunds, or general policies."
    parameters = []  # No inputs — uses the authenticated user
    security_policy = ToolSecurityPolicy(
        requires_confirmation=False,
        risk_level="low",
    )

    async def execute(self, *, db: AsyncSession, user: User, conversation_id: int, **kwargs) -> Dict[str, Any]:
        return {
            "success": True,
            "tool": self.name,
            "data": {
                "user_id": user.id,
                "full_name": user.full_name,
                "email": user.email,
                "role": user.role if isinstance(user.role, str) else user.role.value,
                "is_active": user.is_active,
            },
        }


# ══════════════════════════════════════════════════════════════
# D. CREATE SUPPORT TICKET  (Medium Risk)
# ══════════════════════════════════════════════════════════════

class CreateSupportTicketTool(BaseTool):
    name = "create_support_ticket"
    description = "Create a new support ticket for the customer."
    use_when = "Customer asks to open or create a new support ticket and has provided the issue description."
    do_not_use_when = "Customer issue can be answered immediately with KB or tool, or supervisor escalation is needed."
    parameters = [
        ToolParameter(name="subject", type="string", description="Short summary of the issue."),
        ToolParameter(name="category", type="string", description="Issue category.", required=False),
        ToolParameter(name="priority", type="string", description="Priority: low, medium, high, critical.", required=False),
    ]
    security_policy = ToolSecurityPolicy(
        requires_confirmation=True,
        risk_level="medium",
    )

    async def execute(self, *, db: AsyncSession, user: User, conversation_id: int, **kwargs) -> Dict[str, Any]:
        subject = (kwargs.get("subject") or "").strip()
        if not subject:
            return {"success": False, "tool": self.name, "error_code": "MISSING_SUBJECT",
                    "message": "A subject/description is required to create a ticket."}

        priority_str = (kwargs.get("priority") or "medium").lower()
        valid_priorities = {p.value for p in Priority}
        if priority_str not in valid_priorities:
            priority_str = "medium"

        ticket = Ticket(
            customer_id=user.id,
            conversation_id=conversation_id,
            subject=subject[:500],
            status=TicketStatus.OPEN,
            priority=priority_str,
            category=kwargs.get("category"),
        )
        db.add(ticket)
        await db.flush()

        return {
            "success": True,
            "tool": self.name,
            "data": {
                "ticket_id": ticket.id,
                "subject": ticket.subject,
                "status": "open",
                "priority": priority_str,
            },
        }


# ══════════════════════════════════════════════════════════════
# E. UPDATE TICKET INFORMATION  (Medium Risk)
# ══════════════════════════════════════════════════════════════

class UpdateTicketInfoTool(BaseTool):
    name = "update_ticket_info"
    description = "Update the subject or category of an existing ticket."
    use_when = "Customer requests updating the subject or category of an existing ticket."
    do_not_use_when = "Customer has no ticket ID or is requesting a new ticket."
    parameters = [
        ToolParameter(name="ticket_id", type="integer", description="The ticket ID."),
        ToolParameter(name="new_subject", type="string", description="Updated subject.", required=False),
        ToolParameter(name="new_category", type="string", description="Updated category.", required=False),
    ]
    security_policy = ToolSecurityPolicy(
        requires_confirmation=True,
        risk_level="medium",
    )

    async def execute(self, *, db: AsyncSession, user: User, conversation_id: int, **kwargs) -> Dict[str, Any]:
        raw = kwargs.get("ticket_id")
        try:
            ticket_id = int(raw)
        except (TypeError, ValueError):
            return {"success": False, "tool": self.name, "error_code": "INVALID_TICKET_ID",
                    "message": "Ticket ID must be a number."}

        ticket = await db.get(Ticket, ticket_id)
        if not ticket:
            return {"success": False, "tool": self.name, "error_code": "TICKET_NOT_FOUND",
                    "message": "Ticket not found."}

        # Ownership
        if str(user.role) in (UserRole.CUSTOMER, UserRole.CUSTOMER.value):
            if ticket.customer_id != user.id:
                return {"success": False, "tool": self.name, "error_code": "ACCESS_DENIED",
                        "message": "You do not have permission to update this ticket."}

        # Cannot modify resolved tickets
        status_val = ticket.status if isinstance(ticket.status, str) else ticket.status.value
        if status_val == TicketStatus.RESOLVED.value:
            return {"success": False, "tool": self.name, "error_code": "TICKET_RESOLVED",
                    "message": "Cannot update a resolved ticket."}

        new_subject = kwargs.get("new_subject")
        new_category = kwargs.get("new_category")
        if not new_subject and not new_category:
            return {"success": False, "tool": self.name, "error_code": "NO_CHANGES",
                    "message": "No update fields provided."}

        if new_subject:
            ticket.subject = new_subject[:500]
        if new_category:
            ticket.category = new_category[:100]

        await db.flush()

        return {
            "success": True,
            "tool": self.name,
            "data": {
                "ticket_id": ticket.id,
                "subject": ticket.subject,
                "category": ticket.category,
            },
        }


# ══════════════════════════════════════════════════════════════
# F. REQUEST HUMAN SUPPORT  (Medium Risk) — uses M12.1 handoff
# ══════════════════════════════════════════════════════════════

class RequestHumanSupportTool(BaseTool):
    name = "request_human_support"
    description = "Escalate the conversation to a human support expert."
    use_when = "Customer demands a human supervisor, reports fraud/security, or asks for live agent."
    do_not_use_when = "Standard queries that can be answered by AI or verified via tool."
    parameters = [
        ToolParameter(name="reason", type="string", description="Why the customer needs human help.", required=False),
    ]
    security_policy = ToolSecurityPolicy(
        requires_confirmation=False,
        risk_level="medium",
    )

    async def execute(self, *, db: AsyncSession, user: User, conversation_id: int, **kwargs) -> Dict[str, Any]:
        reason = (kwargs.get("reason") or "Customer requested human support").strip()

        # Signal to the ConversationService to trigger ESCALATE
        # We don't create the Handoff here directly — the service layer handles that
        return {
            "success": True,
            "tool": self.name,
            "escalate": True,  # Signal for the service layer
            "data": {
                "reason": reason,
                "conversation_id": conversation_id,
            },
        }
