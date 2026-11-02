import asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy import select

from app.database import engine, async_session_factory, Base
import app.main  # This imports all models so relationships can resolve
from app.users.models import User
from app.commerce.models import Order, Transaction
from app.tickets.models import Ticket
from app.conversations.models import Conversation
from app.shared.models import TicketStatus, Priority
from app.rag.models import KnowledgeArticle

from app.auth.password import get_password_hash

async def seed_day3():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    async with async_session_factory() as session:
        # 1. Seed Customers
        customers_data = [
            {"email": "customer_normal@resolveai.com", "full_name": "Normal Customer", "is_active": True, "tenant_id": "default"},
            {"email": "customer_locked@resolveai.com", "full_name": "Locked Customer", "is_active": False, "tenant_id": "default"},
            {"email": "customer_tenant_b@resolveai.com", "full_name": "Tenant B Customer", "is_active": True, "tenant_id": "tenant_b"},
        ]
        
        user_ids = {}
        for cdata in customers_data:
            stmt = select(User).where(User.email == cdata["email"])
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            if not user:
                user = User(
                    email=cdata["email"],
                    password_hash=get_password_hash("password123"),
                    full_name=cdata["full_name"],
                    is_active=cdata["is_active"],
                    tenant_id=cdata["tenant_id"],
                    role="customer"
                )
                session.add(user)
                await session.flush()
            user_ids[cdata["email"]] = user.id
            
        c_normal_id = user_ids["customer_normal@resolveai.com"]
        
        # 2. Seed Orders
        now = datetime.now(timezone.utc)
        past_date = now - timedelta(days=10)
        orders_data = [
            {"order_number": "ORD-101", "status": "PROCESSING", "expected_delivery": now + timedelta(days=3), "tracking_number": None},
            {"order_number": "ORD-102", "status": "SHIPPED", "expected_delivery": now + timedelta(days=2), "tracking_number": "TRK102"},
            {"order_number": "ORD-103", "status": "DELIVERED", "expected_delivery": now - timedelta(days=1), "tracking_number": "TRK103"},
            {"order_number": "ORD-104", "status": "CANCELLED", "expected_delivery": None, "tracking_number": None},
            {"order_number": "ORD-105", "status": "PROCESSING", "expected_delivery": past_date, "tracking_number": None}, # Delayed
            {"order_number": "ORD-106", "status": "RETURN_REQUESTED", "expected_delivery": now - timedelta(days=5), "tracking_number": "TRK106"},
        ]
        
        for odata in orders_data:
            stmt = select(Order).where(Order.order_number == odata["order_number"])
            result = await session.execute(stmt)
            order = result.scalar_one_or_none()
            if not order:
                order = Order(
                    customer_id=c_normal_id,
                    tenant_id="default",
                    order_number=odata["order_number"],
                    status=odata["status"],
                    expected_delivery=odata["expected_delivery"],
                    tracking_number=odata["tracking_number"]
                )
                session.add(order)
            else:
                order.status = odata["status"]
                order.expected_delivery = odata["expected_delivery"]
                order.tracking_number = odata["tracking_number"]
                
        # 3. Seed Transactions
        txns_data = [
            {"transaction_id": "TXN-201", "status": "SUCCESS", "amount": 150.0},
            {"transaction_id": "TXN-202", "status": "PENDING", "amount": 250.0},
            {"transaction_id": "TXN-203", "status": "FAILED", "amount": 100.0},
            {"transaction_id": "TXN-204a", "status": "SUCCESS", "amount": 50.0},
            {"transaction_id": "TXN-204b", "status": "SUCCESS", "amount": 50.0},
        ]
        
        for tdata in txns_data:
            stmt = select(Transaction).where(Transaction.transaction_id == tdata["transaction_id"])
            result = await session.execute(stmt)
            txn = result.scalar_one_or_none()
            if not txn:
                txn = Transaction(
                    customer_id=c_normal_id,
                    tenant_id="default",
                    transaction_id=tdata["transaction_id"],
                    amount=tdata["amount"],
                    currency="USD",
                    status=tdata["status"]
                )
                session.add(txn)
            else:
                txn.status = tdata["status"]

        await session.flush()
        
        # 4. Seed Tickets (requires conversations)
        tickets_data = [
            {"subject": "TKT-301", "status": TicketStatus.OPEN, "priority": Priority.MEDIUM},
            {"subject": "TKT-302", "status": TicketStatus.ESCALATED, "priority": Priority.CRITICAL},
            {"subject": "TKT-303", "status": TicketStatus.RESOLVED, "priority": Priority.MEDIUM},
        ]
        
        for tdata in tickets_data:
            stmt = select(Ticket).where(Ticket.subject == tdata["subject"])
            result = await session.execute(stmt)
            tkt = result.scalar_one_or_none()
            if not tkt:
                # Create conversation first
                conv = Conversation(customer_id=c_normal_id, status="active", workflow_state="idle")
                session.add(conv)
                await session.flush()
                
                tkt = Ticket(
                    customer_id=c_normal_id,
                    conversation_id=conv.id,
                    subject=tdata["subject"],
                    status=tdata["status"],
                    priority=tdata["priority"]
                )
                session.add(tkt)
            else:
                tkt.status = tdata["status"]
                tkt.priority = tdata["priority"]
                
        # 5. KB Articles
        # Deactivate old generic articles in default tenant
        stmt = select(KnowledgeArticle).where(KnowledgeArticle.tenant_id == "default")
        result = await session.execute(stmt)
        old_articles = result.scalars().all()
        for art in old_articles:
            if not art.title.startswith("[ResolveMart]"):
                art.is_active = False
                
        resolvemart_kb = [
            {
                "title": "[ResolveMart] Order Lifecycle & General Policy",
                "content": "Orders pass through CREATED, PROCESSING, SHIPPED, and DELIVERED. Customers can cancel in CREATED or PROCESSING. SHIPPED orders cannot be cancelled or modified.",
                "category": "ORDERS",
                "tags": ["order", "lifecycle"]
            },
            {
                "title": "[ResolveMart] Delivery Policy",
                "content": "Standard delivery takes 3-5 business days. Delays >48h or lost packages (>5 days) must be escalated to human support. Delivered but not received also requires escalation.",
                "category": "DELIVERY",
                "tags": ["delivery", "shipping", "delay", "lost"]
            },
            {
                "title": "[ResolveMart] Cancellation Policy",
                "content": "Cancellations are allowed only in CREATED or PROCESSING state. We currently have no automated tool for this, so please escalate to a human. SHIPPED orders cannot be cancelled.",
                "category": "CANCELLATION",
                "tags": ["cancel", "cancellation"]
            },
            {
                "title": "[ResolveMart] Return Policy",
                "content": "Returns are allowed within 30 days of DELIVERED status in original condition.",
                "category": "RETURNS",
                "tags": ["return", "returns"]
            },
            {
                "title": "[ResolveMart] Refund Policy",
                "content": "Refunds are processed within 24 hours internally. Bank reflection takes 3-5 business days. Refund is made to the original payment method. The refund lifecycle has stages: Initiated, Processing, Completed.",
                "category": "REFUNDS",
                "tags": ["refund", "refunds", "money"]
            },
            {
                "title": "[ResolveMart] Payment Policy",
                "content": "Pending payments may take up to 15 minutes. Failed payments are reversed in 24-48 hours. If duplicate SUCCESS payments occur for the same order, escalate to a human.",
                "category": "PAYMENT",
                "tags": ["payment", "duplicate", "failed"]
            },
            {
                "title": "[ResolveMart] Shipping Address Change",
                "content": "Address can only be changed before SHIPPED. We have no automated tool for this, so escalate to a human. Never falsely claim the address was updated.",
                "category": "ADDRESS",
                "tags": ["address", "change", "update"]
            },
            {
                "title": "[ResolveMart] Product Issues (Damaged/Wrong/Missing)",
                "content": "If a product is damaged, wrong, or missing, immediately escalate to human support for review and photographic proof. Do not attempt to process the replacement directly.",
                "category": "ISSUES",
                "tags": ["damaged", "wrong", "missing"]
            },
            {
                "title": "[ResolveMart] Password Recovery",
                "content": "Customers can reset their password via the 'Forgot Password' link that sends an email with a secure reset link. AI cannot reset passwords.",
                "category": "ACCOUNT",
                "tags": ["password", "reset", "login"]
            },
            {
                "title": "[ResolveMart] Security & Locked Accounts",
                "content": "Accounts lock automatically after 5 failed attempts for 30 minutes. Unauthorized access or fraud reports must be escalated as CRITICAL priority immediately.",
                "category": "SECURITY",
                "tags": ["locked", "security", "fraud", "hacked"]
            },
            {
                "title": "[ResolveMart] Human Support & Escalations",
                "content": "Human support is available Mon-Fri 9 AM-6 PM. Escalate whenever there is a security issue, missing product, tool failure, or explicit customer demand.",
                "category": "SUPPORT",
                "tags": ["human", "support", "escalate"]
            },
            {
                "title": "[ResolveMart] Safe Assistance & Out-of-Domain",
                "content": "Decline respectfully if a request is out of domain. Never hallucinate policies or pretend to take actions that are not supported.",
                "category": "BOUNDARIES",
                "tags": ["out-of-domain", "safe"]
            },
        ]
        
        for kb in resolvemart_kb:
            stmt = select(KnowledgeArticle).where(
                KnowledgeArticle.title == kb["title"],
                KnowledgeArticle.tenant_id == "default"
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            if not existing:
                art = KnowledgeArticle(
                    title=kb["title"],
                    content=kb["content"],
                    category=kb["category"],
                    tags=kb["tags"],
                    is_active=True,
                    tenant_id="default"
                )
                session.add(art)
            else:
                existing.content = kb["content"]
                existing.is_active = True
                
        # Seed tenant_b specific article
        stmt = select(KnowledgeArticle).where(
            KnowledgeArticle.title == "[TenantB] Special Policy",
            KnowledgeArticle.tenant_id == "tenant_b"
        )
        result = await session.execute(stmt)
        existing_tb = result.scalar_one_or_none()
        if not existing_tb:
            tb_art = KnowledgeArticle(
                title="[TenantB] Special Policy",
                content="This is a top secret policy only for Tenant B.",
                category="TENANT_B",
                tags=["secret"],
                is_active=True,
                tenant_id="tenant_b"
            )
            session.add(tb_art)

        await session.commit()
        
    print("Day 3 seeding complete.")

if __name__ == "__main__":
    asyncio.run(seed_day3())
