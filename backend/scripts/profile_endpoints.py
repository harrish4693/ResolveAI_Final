"""
Profiling and benchmark script for ResolveAI V2.
Measures:
1. GET /api/handoffs/{id}/context breakdown (SQL vs compute vs incident detection vs serialization)
2. GET /api/analytics/incidents breakdown (SQL vs clustering vs reconciliation vs serialization)
3. Auth / Login (DB lookup vs bcrypt.checkpw vs token creation)
4. Dashboard Queue & Stats
"""

import asyncio
import time
import sys
import os

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import all models to configure mapper registry
import app.main  # noqa: F401

from sqlalchemy import select, func, text
from app.database import async_session_factory
from app.handoff.models import Handoff
from app.tickets.models import Ticket
from app.users.models import User
from app.experts.models import Expert
from app.conversations.models import Conversation, ConversationMessage
from app.shared.models import UserRole, HandoffStatus, SenderType
from app.handoff.router import get_handoff_context, get_queue, get_stats
from app.analytics.router import get_incident_analytics
from app.auth.schemas import LoginRequest
from app.auth.router import login
from app.auth import password as pwd_utils


async def profile_all():
    print("=" * 60)
    print("RESOLVEAI V2 PERFORMANCE AUDIT & PROFILING")
    print("=" * 60)

    async with async_session_factory() as db:
        # Check available test entities
        admin_user = (await db.execute(
            select(User).where(User.role == UserRole.ADMIN).limit(1)
        )).scalar_one_or_none()
        
        expert_user = (await db.execute(
            select(User).where(User.role == UserRole.EXPERT).limit(1)
        )).scalar_one_or_none()

        test_handoff = (await db.execute(
            select(Handoff).order_by(Handoff.id.desc()).limit(1)
        )).scalar_one_or_none()

        if not admin_user:
            print("ERROR: No admin user found in database.")
            return

        print(f"Admin User: {admin_user.email} (ID: {admin_user.id})")
        if expert_user:
            print(f"Expert User: {expert_user.email} (ID: {expert_user.id})")
        if test_handoff:
            print(f"Test Handoff ID: {test_handoff.id} (Status: {test_handoff.status})")
        else:
            print("No handoff found in DB!")
            return

        test_handoff_id = test_handoff.id
        acting_user = admin_user

        print("\n" + "-" * 50)
        print("1. PROFILING GET /api/handoffs/{id}/context (CURRENT UNOPTIMIZED)")
        print("-" * 50)

        # Measure individual parts inside context:
        t0 = time.perf_counter()
        h = await db.scalar(select(Handoff).where(Handoff.id == test_handoff_id))
        t1 = time.perf_counter()
        print(f"  [DB] Fetch Handoff: {(t1 - t0)*1000:.2f} ms")

        conv = await db.scalar(select(Conversation).where(Conversation.id == h.conversation_id))
        t2 = time.perf_counter()
        print(f"  [DB] Fetch Conversation: {(t2 - t1)*1000:.2f} ms")

        cust = await db.scalar(select(User).where(User.id == conv.customer_id))
        t3 = time.perf_counter()
        print(f"  [DB] Fetch Customer: {(t3 - t2)*1000:.2f} ms")

        history_res = await db.execute(
            select(Conversation)
            .where(Conversation.customer_id == cust.id)
            .where(Conversation.id != conv.id)
            .order_by(Conversation.created_at.desc())
            .limit(5)
        )
        history = history_res.scalars().all()
        t4 = time.perf_counter()
        print(f"  [DB] Fetch Conversation History (5): {(t4 - t3)*1000:.2f} ms")

        ai_msgs_res = await db.execute(
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conv.id)
            .where(ConversationMessage.sender_type == SenderType.AI)
            .order_by(ConversationMessage.created_at.asc())
        )
        ai_msgs = ai_msgs_res.scalars().all()
        t5 = time.perf_counter()
        print(f"  [DB] Fetch AI Messages: {(t5 - t4)*1000:.2f} ms")

        cust_msg = await db.scalar(
            select(ConversationMessage.content)
            .where(ConversationMessage.conversation_id == conv.id)
            .where(ConversationMessage.sender_type == SenderType.CUSTOMER)
            .order_by(ConversationMessage.created_at.desc())
        )
        t6 = time.perf_counter()
        print(f"  [DB] Fetch Latest Customer Message: {(t6 - t5)*1000:.2f} ms")

        # Now measure incident computation currently inside get_handoff_context
        t_inc_start = time.perf_counter()
        from app.tickets.models import Ticket
        from app.ai.intelligence.incidents import IncidentDetector, TicketSnapshot
        from app.ai.incident_service import IncidentPersistenceService

        recent_tickets_res = await db.execute(
            select(Ticket).order_by(Ticket.created_at.desc()).limit(100)
        )
        recent_tickets = recent_tickets_res.scalars().all()
        t_db_tickets = time.perf_counter()
        print(f"  [DB] Fetch 100 Recent Tickets for Incident Clustering: {(t_db_tickets - t_inc_start)*1000:.2f} ms")

        curr_ticket = await db.scalar(select(Ticket).where(Ticket.conversation_id == conv.id))
        t_db_currticket = time.perf_counter()
        print(f"  [DB] Fetch Current Ticket: {(t_db_currticket - t_db_tickets)*1000:.2f} ms")

        t_detect_start = time.perf_counter()
        snapshots = [
            TicketSnapshot(
                ticket_id=t.id,
                subject=t.subject or "",
                category=t.category or "General",
                intent="",
                normalized_text="",
                created_at=t.created_at,
                customer_id=t.customer_id,
                tenant_id="default",
                status=str(t.status.value if hasattr(t.status, "value") else t.status),
            )
            for t in recent_tickets
        ]
        detector = IncidentDetector()
        detected_incidents = detector.detect_incidents(snapshots, tenant_id="default")
        t_detect_end = time.perf_counter()
        print(f"  [AI COMPUTE] IncidentDetector.detect_incidents (100 tickets): {(t_detect_end - t_detect_start)*1000:.2f} ms")

        t_recon_start = time.perf_counter()
        detected_incidents = await IncidentPersistenceService.reconcile_hypotheses(db, detected_incidents, tenant_id="default")
        t_recon_end = time.perf_counter()
        print(f"  [DB/AI] IncidentPersistenceService.reconcile_hypotheses: {(t_recon_end - t_recon_start)*1000:.2f} ms")

        # Measure total get_handoff_context function call (cold)
        t_ctx_start = time.perf_counter()
        ctx = await get_handoff_context(handoff_id=test_handoff_id, db=db, current_user=acting_user)
        t_ctx_end = time.perf_counter()
        print(f"  >>> TOTAL get_handoff_context() runtime (COLD): {(t_ctx_end - t_ctx_start)*1000:.2f} ms")

        # Measure warm call
        t_ctx_warm_start = time.perf_counter()
        ctx_warm = await get_handoff_context(handoff_id=test_handoff_id, db=db, current_user=acting_user)
        t_ctx_warm_end = time.perf_counter()
        print(f"  >>> TOTAL get_handoff_context() runtime (WARM): {(t_ctx_warm_end - t_ctx_warm_start)*1000:.2f} ms")

        print("\n" + "-" * 50)
        print("2. PROFILING GET /api/analytics/incidents")
        print("-" * 50)
        t_ana_start = time.perf_counter()
        ana_res = await get_incident_analytics(tenant_id=None, db=db, current_user=admin_user)
        t_ana_end = time.perf_counter()
        print(f"  >>> TOTAL get_incident_analytics() runtime (COLD): {(t_ana_end - t_ana_start)*1000:.2f} ms")

        t_ana_warm_start = time.perf_counter()
        ana_res_warm = await get_incident_analytics(tenant_id=None, db=db, current_user=admin_user)
        t_ana_warm_end = time.perf_counter()
        print(f"  >>> TOTAL get_incident_analytics() runtime (WARM): {(t_ana_warm_end - t_ana_warm_start)*1000:.2f} ms")
        print(f"      Candidates: {len(ana_res.candidates)}, Confirmed: {len(ana_res.confirmed)}, Total Incidents: {ana_res.total_incidents}")

        print("\n" + "-" * 50)
        print("3. PROFILING DASHBOARD (Queue + Stats)")
        print("-" * 50)
        t_q_start = time.perf_counter()
        queue_res = await get_queue(limit=5, db=db, current_user=acting_user)
        t_q_end = time.perf_counter()
        print(f"  GET /queue?limit=5: {(t_q_end - t_q_start)*1000:.2f} ms (count: {len(queue_res)})")

        t_s_start = time.perf_counter()
        stats_res = await get_stats(db=db, current_user=acting_user)
        t_s_end = time.perf_counter()
        print(f"  GET /stats: {(t_s_end - t_s_start)*1000:.2f} ms (queue_size: {stats_res.queue_size})")

        print("\n" + "-" * 50)
        print("4. PROFILING AUTH & PASSWORD VERIFICATION")
        print("-" * 50)
        # Test password hashing & verification
        test_pwd = "TestPassword123!"
        h_pwd = pwd_utils.get_password_hash(test_pwd)
        t_pw_start = time.perf_counter()
        valid = pwd_utils.verify_password(test_pwd, h_pwd)
        t_pw_end = time.perf_counter()
        print(f"  bcrypt.checkpw() CPU time: {(t_pw_end - t_pw_start)*1000:.2f} ms (valid={valid})")

        print("\n" + "-" * 50)
        print("5. VERIFYING DATABASE INDEXES")
        print("-" * 50)
        res = await db.execute(text("""
            SELECT tablename, indexname, indexdef 
            FROM pg_indexes 
            WHERE schemaname = 'public' 
              AND tablename IN ('handoffs', 'tickets', 'incident_records', 'conversations', 'conversation_messages', 'users')
            ORDER BY tablename, indexname;
        """))
        for row in res.fetchall():
            print(f"  {row[0]} | {row[1]} | {row[2]}")


if __name__ == "__main__":
    asyncio.run(profile_all())
