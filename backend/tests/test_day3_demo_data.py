import pytest
from sqlalchemy import select, func

from app.users.models import User
from app.commerce.models import Order, Transaction
from app.tickets.models import Ticket
from app.rag.models import KnowledgeArticle
from seed_day3 import seed_day3

@pytest.mark.asyncio
async def test_day3_db_consistency(db_session):
    # Ensure seed is applied to test DB first
    await seed_day3()
    
    # 1. Customers
    stmt = select(User).where(User.email == "customer_normal@resolveai.com")
    normal_user = (await db_session.execute(stmt)).scalar_one_or_none()
    assert normal_user is not None
    assert normal_user.tenant_id == "default"
    assert normal_user.is_active is True
    
    stmt = select(User).where(User.email == "customer_locked@resolveai.com")
    locked_user = (await db_session.execute(stmt)).scalar_one_or_none()
    assert locked_user is not None
    assert locked_user.is_active is False
    
    stmt = select(User).where(User.email == "customer_tenant_b@resolveai.com")
    tenant_b_user = (await db_session.execute(stmt)).scalar_one_or_none()
    assert tenant_b_user is not None
    assert tenant_b_user.tenant_id == "tenant_b"
    
    # 2. Orders
    orders = ["ORD-101", "ORD-102", "ORD-103", "ORD-104", "ORD-105", "ORD-106"]
    for o in orders:
        stmt = select(Order).where(Order.order_number == o)
        order = (await db_session.execute(stmt)).scalar_one_or_none()
        assert order is not None
        assert order.customer_id == normal_user.id
        assert order.tenant_id == "default"
        
    # Check specific statuses
    o104 = (await db_session.execute(select(Order).where(Order.order_number == "ORD-104"))).scalar_one()
    assert o104.status == "CANCELLED"
    
    # 3. Transactions (duplicate success scenario)
    stmt = select(Transaction).where(Transaction.transaction_id == "TXN-204a")
    t204a = (await db_session.execute(stmt)).scalar_one()
    assert t204a.status == "SUCCESS"
    assert t204a.tenant_id == "default"
    
    stmt = select(Transaction).where(Transaction.transaction_id == "TXN-204b")
    t204b = (await db_session.execute(stmt)).scalar_one()
    assert t204b.status == "SUCCESS"
    
    # 4. Tickets
    stmt = select(Ticket).where(Ticket.subject == "TKT-302")
    tkt_critical = (await db_session.execute(stmt)).scalar_one()
    assert tkt_critical.status == "escalated"
    assert tkt_critical.priority == "critical"
    
@pytest.mark.asyncio
async def test_day3_kb_consistency(db_session):
    await seed_day3()
    
    # Ensure no old generic articles are active in default
    stmt = select(KnowledgeArticle).where(
        KnowledgeArticle.tenant_id == "default",
        KnowledgeArticle.is_active == True,
        ~KnowledgeArticle.title.startswith("[ResolveMart]")
    )
    old_active = (await db_session.execute(stmt)).scalars().all()
    assert len(old_active) == 0
    
    # Check authoritative articles exist
    stmt = select(KnowledgeArticle).where(KnowledgeArticle.title == "[ResolveMart] Cancellation Policy")
    art = (await db_session.execute(stmt)).scalar_one()
    assert art.tenant_id == "default"
    assert "no automated tool" in art.content
    
    # Check tenant_b specific isolation in DB
    stmt = select(KnowledgeArticle).where(KnowledgeArticle.tenant_id == "tenant_b")
    tb_arts = (await db_session.execute(stmt)).scalars().all()
    assert len(tb_arts) > 0
    assert all(a.title == "[TenantB] Special Policy" for a in tb_arts)

@pytest.mark.asyncio
async def test_day3_seed_idempotency(db_session):
    # Run once
    await seed_day3()
    # Count orders
    count_stmt = select(func.count(Order.id))
    initial_count = (await db_session.execute(count_stmt)).scalar()
    
    # Run twice
    await seed_day3()
    final_count = (await db_session.execute(count_stmt)).scalar()
    
    assert initial_count == final_count, "Seed is not idempotent for Orders"
    
    # Check transactions
    txn_count_stmt = select(func.count(Transaction.id))
    txn_count = (await db_session.execute(txn_count_stmt)).scalar()
    await seed_day3()
    txn_count_final = (await db_session.execute(txn_count_stmt)).scalar()
    assert txn_count == txn_count_final, "Seed is not idempotent for Transactions"
