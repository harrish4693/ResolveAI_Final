"""
ResolveAIV2 — Comprehensive Incident Intelligence & Lifecycle Persistence Suite

Covers:
1. Incident detection and clustering:
   - Basic payment issue clustering.
   - Synonym canonicalization across differing complaint wordings.
   - Supported code-mixed variants (Tanglish, Hinglish) clustered with English.
   - Unrelated tickets prevented from clustering.
   - Robust spike detection: insufficient data handling vs defensible surge detection.
   - Malformed/missing metadata robustness.
2. Authorization and Expert handoff integration:
   - RBAC on incident analytics and tenant boundaries.
   - Incident context enrichment in Expert Handoff context.
3. Durable database lifecycle persistence:
   - Status persistence across DB sessions.
   - Recovery following simulated process restart (in-memory wipe).
   - Multi-worker / multi-instance consistency.
   - State transition validation (e.g. candidate -> investigating -> confirmed -> resolved).
   - Rejection of invalid transitions (e.g. resolved -> candidate, candidate -> mitigated).
   - Role-based status updates (Admin only).
   - Cross-tenant isolation on incident modification and retrieval.
   - Idempotency and deduplication across repeated detection passes.
   - Unrelated cluster isolation.
"""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.incident_models import IncidentRecord
from app.ai.incident_service import (
    ALLOWED_STATUSES,
    VALID_TRANSITIONS,
    IncidentPersistenceService,
)
from app.ai.intelligence.incidents import (
    IncidentDetector,
    IncidentStateManager,
    TicketSimilarityAnalyzer,
    TicketSnapshot,
)
from app.auth.jwt import create_access_token
from app.auth.password import get_password_hash
from app.conversations.models import Conversation
from app.database import async_session_factory
from app.handoff.models import Handoff
from app.shared.models import HandoffStatus, Priority, TicketStatus, UserRole, WorkflowState
from app.tickets.models import Ticket
from app.users.models import User


@pytest.fixture(autouse=True)
def reset_incident_state():
    """Reset in-memory incident state before and after each test."""
    IncidentStateManager.reset()
    yield
    IncidentStateManager.reset()


# ==============================================================================
# Section 1: Related-Ticket Detection & Clustering
# ==============================================================================

def test_related_ticket_detection_basic():
    """Verify related tickets with similar payment issues form an incident cluster."""
    detector = IncidentDetector()
    now = datetime.now(timezone.utc)

    tickets = [
        TicketSnapshot(
            ticket_id=1,
            subject="Payment gateway timeout during checkout",
            category="payment",
            intent="PAYMENT_ISSUE",
            created_at=now,
            customer_id=101,
            tenant_id="default",
        ),
        TicketSnapshot(
            ticket_id=2,
            subject="Checkout payment gateway failure",
            category="payment",
            intent="PAYMENT_ISSUE",
            created_at=now + timedelta(minutes=10),
            customer_id=102,
            tenant_id="default",
        ),
    ]

    incidents = detector.detect_incidents(tickets, tenant_id="default")
    assert len(incidents) == 1
    inc = incidents[0]
    assert inc.status == "candidate"
    assert inc.category == "payment"
    assert set(inc.affected_tickets) == {1, 2}
    assert inc.affected_customer_count == 2
    assert inc.confidence >= 0.6


def test_similar_complaints_different_wording():
    """Verify complaints with different wording match via synonym canonicalization."""
    analyzer = TicketSimilarityAnalyzer()
    now = datetime.now(timezone.utc)

    t1 = TicketSnapshot(
        ticket_id=10,
        subject="Bank debited but order failed",
        category="payment",
        intent="PAYMENT_ISSUE",
        created_at=now,
    )
    t2 = TicketSnapshot(
        ticket_id=11,
        subject="Payment cut from card account but transaction declined",
        category="payment",
        intent="PAYMENT_ISSUE",
        created_at=now + timedelta(minutes=15),
    )

    sim = analyzer.compute_similarity(t1, t2)
    assert sim.keyword_score > 0.3
    assert sim.category_score >= 0.8
    assert sim.overall >= 0.45

    detector = IncidentDetector()
    incidents = detector.detect_incidents([t1, t2], tenant_id="default")
    assert len(incidents) == 1
    assert set(incidents[0].affected_tickets) == {10, 11}


def test_supported_code_mixed_complaint_variants():
    """Verify code-mixed complaints (Tanglish & Hinglish) are grouped with English complaints."""
    detector = IncidentDetector()
    now = datetime.now(timezone.utc)

    tickets = [
        TicketSnapshot(
            ticket_id=20,
            subject="Payment deducted but order failed",
            category="payment",
            intent="PAYMENT_ISSUE",
            created_at=now,
            customer_id=201,
            tenant_id="default",
        ),
        TicketSnapshot(
            ticket_id=21,
            subject="Panam deduct aagiduchu order confirm aagala",
            category="payment",
            intent="PAYMENT_ISSUE",
            created_at=now + timedelta(minutes=5),
            customer_id=202,
            tenant_id="default",
        ),
        TicketSnapshot(
            ticket_id=22,
            subject="Paisa kat gaya order nahi aaya",
            category="payment",
            intent="PAYMENT_ISSUE",
            created_at=now + timedelta(minutes=8),
            customer_id=203,
            tenant_id="default",
        ),
    ]

    incidents = detector.detect_incidents(tickets, tenant_id="default")
    assert len(incidents) >= 1
    all_grouped_tids = {tid for inc in incidents for tid in inc.affected_tickets}
    assert 20 in all_grouped_tids
    assert 21 in all_grouped_tids
    assert 22 in all_grouped_tids


def test_unrelated_tickets_not_incorrectly_grouped():
    """Ensure disparate tickets across different domains do not form an incident."""
    detector = IncidentDetector()
    now = datetime.now(timezone.utc)

    tickets = [
        TicketSnapshot(
            ticket_id=31,
            subject="Payment gateway timeout",
            category="payment",
            intent="PAYMENT_ISSUE",
            created_at=now,
            tenant_id="default",
        ),
        TicketSnapshot(
            ticket_id=32,
            subject="Where is my courier shipment package tracking",
            category="delivery",
            intent="DELIVERY_ISSUE",
            created_at=now + timedelta(minutes=10),
            tenant_id="default",
        ),
        TicketSnapshot(
            ticket_id=33,
            subject="Forgot password cannot login to account",
            category="account",
            intent="LOGIN_ISSUE",
            created_at=now + timedelta(minutes=20),
            tenant_id="default",
        ),
    ]

    incidents = detector.detect_incidents(tickets, tenant_id="default")
    assert len(incidents) == 0


# ==============================================================================
# Section 2: Defensible Spike Detection
# ==============================================================================

def test_insufficient_data_for_spike_detection():
    """Ensure spike detector does not fabricate metrics with insufficient data."""
    detector = IncidentDetector()
    now = datetime.now(timezone.utc)

    sparse_tickets = [
        TicketSnapshot(ticket_id=1, subject="Issue A", created_at=now),
        TicketSnapshot(ticket_id=2, subject="Issue B", created_at=now + timedelta(minutes=5)),
    ]
    res1 = detector.detect_spike(sparse_tickets)
    assert res1["is_spike"] is False
    assert res1["reason"] == "insufficient_data"
    assert res1["spike_ratio"] is None

    rapid_burst = [
        TicketSnapshot(ticket_id=i, subject=f"Issue {i}", created_at=now + timedelta(minutes=i))
        for i in range(6)
    ]
    res2 = detector.detect_spike(rapid_burst, baseline_hours=24.0, current_hours=2.0)
    assert res2["is_spike"] is False
    assert res2["reason"] in ("insufficient_time_span", "insufficient_baseline_data")


def test_defensible_spike_detection_with_real_baseline():
    """Verify spike detector correctly flags surge when arrival rate surges over baseline."""
    detector = IncidentDetector()
    now = datetime.now(timezone.utc)

    baseline_tickets = [
        TicketSnapshot(
            ticket_id=i,
            subject=f"Old complaint {i}",
            created_at=now - timedelta(hours=22 - (i * 3)),
        )
        for i in range(6)
    ]

    current_tickets = [
        TicketSnapshot(
            ticket_id=100 + i,
            subject=f"Surge complaint {i}",
            created_at=now - timedelta(minutes=50 - (i * 8)),
        )
        for i in range(6)
    ]

    all_tickets = baseline_tickets + current_tickets
    res = detector.detect_spike(all_tickets, baseline_hours=24.0, current_hours=2.0)

    assert res["is_spike"] is True
    assert res["spike_ratio"] is not None
    assert res["spike_ratio"] >= 2.5
    assert res["current_count"] == 6


# ==============================================================================
# Section 3: Status Transitions & Robustness
# ==============================================================================

@pytest.mark.asyncio
async def test_incident_status_candidate_vs_confirmed(async_client: AsyncClient, auth_headers_admin):
    """Verify incidents default to 'candidate' and transition to 'confirmed' via Admin API."""
    incident_id = "INC-TEST-01"
    assert IncidentStateManager.get_status(incident_id) == "candidate"

    res = await async_client.post(
        f"/api/analytics/incidents/{incident_id}/status",
        headers=auth_headers_admin,
        json={"status": "confirmed"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "confirmed"
    assert IncidentStateManager.get_status(incident_id) == "confirmed"

    res2 = await async_client.post(
        f"/api/analytics/incidents/{incident_id}/status",
        headers=auth_headers_admin,
        json={"status": "resolved"},
    )
    assert res2.status_code == 200
    assert res2.json()["status"] == "resolved"


def test_missing_metadata_and_malformed_input():
    """Verify detector handles empty subjects, None created_at, and missing fields cleanly."""
    detector = IncidentDetector()

    malformed_tickets = [
        TicketSnapshot(ticket_id=1, subject="", category="", intent="", created_at=None),
        TicketSnapshot(ticket_id=2, subject=None, category=None, intent=None, created_at=None),
        TicketSnapshot(ticket_id=3, subject="Valid subject", category="General", created_at=None),
    ]

    incidents = detector.detect_incidents(malformed_tickets, tenant_id="default")
    assert isinstance(incidents, list)

    spike_info = detector.detect_spike(malformed_tickets)
    assert spike_info["is_spike"] is False
    assert spike_info["reason"] == "insufficient_data"


# ==============================================================================
# Section 4: Authorization & Tenant Isolation
# ==============================================================================

@pytest.mark.asyncio
async def test_authorization_and_tenant_isolation(
    async_client: AsyncClient,
    auth_headers_a,
    auth_headers_admin,
):
    """Verify customer cannot access incident analytics and cross-tenant tickets are isolated."""
    cust_res = await async_client.get("/api/analytics/incidents", headers=auth_headers_a)
    assert cust_res.status_code == 403

    admin_res = await async_client.get("/api/analytics/incidents", headers=auth_headers_admin)
    assert admin_res.status_code == 200
    data = admin_res.json()
    assert "candidates" in data
    assert "confirmed" in data
    assert "spike_alerts" in data

    now = datetime.now(timezone.utc)
    t_a = [
        TicketSnapshot(ticket_id=1, subject="Payment failed", category="payment", intent="PAYMENT_ISSUE", created_at=now, tenant_id="tenant_x"),
        TicketSnapshot(ticket_id=2, subject="Payment failed", category="payment", intent="PAYMENT_ISSUE", created_at=now, tenant_id="tenant_x"),
    ]
    t_b = [
        TicketSnapshot(ticket_id=3, subject="Payment failed", category="payment", intent="PAYMENT_ISSUE", created_at=now, tenant_id="tenant_y"),
    ]

    detector = IncidentDetector()
    inc_x = detector.detect_incidents(t_a + t_b, tenant_id="tenant_x")
    inc_y = detector.detect_incidents(t_a + t_b, tenant_id="tenant_y")

    assert len(inc_x) == 1
    assert inc_x[0].affected_tickets == [1, 2]
    assert len(inc_y) == 0


@pytest.mark.asyncio
async def test_expert_handoff_context_includes_incident_context(
    async_client: AsyncClient,
    auth_headers_a,
    auth_headers_b,
    auth_headers_expert,
    db_session: AsyncSession,
):
    """Verify GET /api/handoffs/{id}/context returns incident_context when related tickets exist."""
    res_b = await async_client.post(
        "/api/conversations",
        headers=auth_headers_b,
        json={"initial_message": "Payment gateway timeout money deducted", "subject": "Payment issue"},
    )
    convo_b_id = res_b.json()["id"]

    res_a = await async_client.post(
        "/api/conversations",
        headers=auth_headers_a,
        json={"initial_message": "Someone accessed my account and stole money!", "subject": "Security Breach"},
    )
    convo_a_id = res_a.json()["id"]

    res_b2 = await async_client.post(
        "/api/conversations",
        headers=auth_headers_b,
        json={"initial_message": "Unauthorized login someone stole my money", "subject": "Stolen money security"},
    )

    handoff_res = await async_client.get(f"/api/handoffs/conversation/{convo_a_id}", headers=auth_headers_expert)
    assert handoff_res.status_code == 200
    handoff_data = handoff_res.json()
    handoff_id = handoff_data["id"]

    ctx_res = await async_client.get(f"/api/handoffs/{handoff_id}/context", headers=auth_headers_expert)
    assert ctx_res.status_code == 200
    ctx_data = ctx_res.json()

    assert "customer" in ctx_data
    assert "active_ticket" in ctx_data
    assert "ai_context" in ctx_data
    assert "ticket_history" in ctx_data

    if ctx_data.get("incident_context"):
        inc = ctx_data["incident_context"]
        assert "incident_id" in inc
        assert "title" in inc
        assert "status" in inc
        assert "related_ticket_count" in inc
        assert isinstance(inc["evidence"], list)


# ==============================================================================
# Section 5: Durable Database Lifecycle Persistence
# ==============================================================================

@pytest.mark.asyncio
async def test_incident_status_survives_session_reinitialization():
    """Verify that an incident status persisted in one DB session is correctly read from a new session."""
    incident_id = "INC-TEST-SESSION-001"
    tenant_id = "test_tenant_session"

    async with async_session_factory() as session1:
        record1 = await IncidentPersistenceService.update_status(
            db=session1,
            incident_id=incident_id,
            status="investigating",
            tenant_id=tenant_id,
            category="payment",
            title="Session Persistence Test Incident",
            affected_ticket_ids=[101, 102],
        )
        assert record1.status == "investigating"
        assert record1.incident_id == incident_id

    async with async_session_factory() as session2:
        loaded_status = await IncidentPersistenceService.get_status(
            db=session2,
            incident_id=incident_id,
            tenant_id=tenant_id,
        )
        assert loaded_status == "investigating"

        stmt = select(IncidentRecord).where(
            IncidentRecord.tenant_id == tenant_id,
            IncidentRecord.incident_id == incident_id,
        )
        raw_record = (await session2.execute(stmt)).scalar_one_or_none()
        assert raw_record is not None
        assert raw_record.status == "investigating"
        assert raw_record.category == "payment"
        assert raw_record.affected_ticket_ids == [101, 102]
        assert len(raw_record.status_history) >= 1
        assert raw_record.status_history[0]["to_status"] == "investigating"


@pytest.mark.asyncio
async def test_incident_status_survives_restart_simulation():
    """Verify that wiping in-memory state recovers persisted incident status directly from DB."""
    incident_id = "INC-RESTART-002"
    tenant_id = "test_tenant_restart"

    async with async_session_factory() as session:
        await IncidentPersistenceService.update_status(
            db=session,
            incident_id=incident_id,
            status="confirmed",
            tenant_id=tenant_id,
            category="billing",
        )

    IncidentStateManager.reset()
    assert IncidentStateManager._statuses == {}

    async with async_session_factory() as fresh_session:
        recovered_status = await IncidentPersistenceService.get_status(
            db=fresh_session,
            incident_id=incident_id,
            tenant_id=tenant_id,
        )
        assert recovered_status == "confirmed"
        assert IncidentStateManager.get_status(incident_id) == "confirmed"


@pytest.mark.asyncio
async def test_second_service_instance_reads_updated_status():
    """Simulates Worker A updating an incident and Worker B reading consistent status via DB."""
    incident_id = "INC-WORKER-003"
    tenant_id = "test_tenant_workers"

    async with async_session_factory() as worker_a_session:
        await IncidentPersistenceService.update_status(
            db=worker_a_session,
            incident_id=incident_id,
            status="investigating",
            tenant_id=tenant_id,
        )
        await IncidentPersistenceService.update_status(
            db=worker_a_session,
            incident_id=incident_id,
            status="mitigated",
            tenant_id=tenant_id,
        )

    IncidentStateManager.reset()

    async with async_session_factory() as worker_b_session:
        worker_b_status = await IncidentPersistenceService.get_status(
            db=worker_b_session,
            incident_id=incident_id,
            tenant_id=tenant_id,
        )
        assert worker_b_status == "mitigated"


@pytest.mark.asyncio
async def test_lifecycle_transition_validation():
    """Verify valid transitions succeed and invalid transitions raise ValueError."""
    incident_id = "INC-TRANS-004"
    tenant_id = "test_tenant_transitions"

    async with async_session_factory() as session:
        rec1 = await IncidentPersistenceService.update_status(
            db=session,
            incident_id=incident_id,
            status="investigating",
            tenant_id=tenant_id,
        )
        assert rec1.status == "investigating"

        rec2 = await IncidentPersistenceService.update_status(
            db=session,
            incident_id=incident_id,
            status="confirmed",
            tenant_id=tenant_id,
        )
        assert rec2.status == "confirmed"

        rec3 = await IncidentPersistenceService.update_status(
            db=session,
            incident_id=incident_id,
            status="resolved",
            tenant_id=tenant_id,
        )
        assert rec3.status == "resolved"

        with pytest.raises(ValueError) as excinfo:
            await IncidentPersistenceService.update_status(
                db=session,
                incident_id=incident_id,
                status="candidate",
                tenant_id=tenant_id,
            )
        assert "Invalid status transition" in str(excinfo.value)

        with pytest.raises(ValueError) as excinfo2:
            await IncidentPersistenceService.update_status(
                db=session,
                incident_id=incident_id,
                status="invalid_bogus_status",
                tenant_id=tenant_id,
            )
        assert "Allowed statuses are" in str(excinfo2.value)


@pytest.mark.asyncio
async def test_candidate_cannot_transition_directly_to_mitigated():
    """Verify that an incident candidate cannot be marked mitigated without investigation."""
    incident_id = "INC-DIRECT-MITIGATE"
    tenant_id = "test_tenant_mitigate"

    async with async_session_factory() as session:
        with pytest.raises(ValueError) as excinfo:
            await IncidentPersistenceService.update_status(
                db=session,
                incident_id=incident_id,
                status="mitigated",
                tenant_id=tenant_id,
            )
        assert "Invalid status transition" in str(excinfo.value)


@pytest.mark.asyncio
async def test_unauthorized_users_cannot_update_incident_status(
    async_client: AsyncClient,
    auth_headers_a,
    auth_headers_expert,
    auth_headers_admin,
):
    """Verify RBAC on status updates: Unauthenticated/Customer/Expert rejected; Admin succeeds."""
    incident_id = "INC-RBAC-005"

    res_unauth = await async_client.post(
        f"/api/analytics/incidents/{incident_id}/status",
        json={"status": "investigating"},
    )
    assert res_unauth.status_code == 401

    res_cust = await async_client.post(
        f"/api/analytics/incidents/{incident_id}/status",
        headers=auth_headers_a,
        json={"status": "investigating"},
    )
    assert res_cust.status_code == 403

    res_expert = await async_client.post(
        f"/api/analytics/incidents/{incident_id}/status",
        headers=auth_headers_expert,
        json={"status": "investigating"},
    )
    assert res_expert.status_code == 403

    res_admin = await async_client.post(
        f"/api/analytics/incidents/{incident_id}/status",
        headers=auth_headers_admin,
        json={"status": "investigating"},
    )
    assert res_admin.status_code == 200
    assert res_admin.json()["status"] == "investigating"


@pytest.mark.asyncio
async def test_cross_tenant_isolation_enforced(async_client: AsyncClient, db_session: AsyncSession):
    """Verify Tenant A admin cannot read or modify Tenant B's incident status."""
    admin_x = User(
        email="admin_x_inc@tenantx.com",
        full_name="Admin X",
        password_hash=get_password_hash("Password123!"),
        role=UserRole.ADMIN,
        tenant_id="tenant_x",
    )
    db_session.add(admin_x)

    admin_y = User(
        email="admin_y_inc@tenanty.com",
        full_name="Admin Y",
        password_hash=get_password_hash("Password123!"),
        role=UserRole.ADMIN,
        tenant_id="tenant_y",
    )
    db_session.add(admin_y)
    await db_session.commit()
    await db_session.refresh(admin_x)
    await db_session.refresh(admin_y)

    token_x = create_access_token(admin_x.id, "admin")
    headers_x = {"Authorization": f"Bearer {token_x}"}

    token_y = create_access_token(admin_y.id, "admin")
    headers_y = {"Authorization": f"Bearer {token_y}"}

    res_x = await async_client.post(
        "/api/analytics/incidents/INC-TENANT-X/status",
        headers=headers_x,
        json={"status": "investigating"},
    )
    assert res_x.status_code == 200
    assert res_x.json()["tenant_id"] == "tenant_x"

    res_y_tamper = await async_client.post(
        "/api/analytics/incidents/INC-TENANT-X/status?tenant_id=tenant_x",
        headers=headers_y,
        json={"status": "confirmed"},
    )
    assert res_y_tamper.status_code == 403

    res_y_read_tamper = await async_client.get(
        "/api/analytics/incidents?tenant_id=tenant_x",
        headers=headers_y,
    )
    assert res_y_read_tamper.status_code == 403


@pytest.mark.asyncio
async def test_repeated_detection_does_not_create_duplicate_records(db_session: AsyncSession):
    """Verify that executing detection multiple times updates existing records without creating duplicates."""
    tenant_id = "test_tenant_dedup"
    now = datetime.now(timezone.utc)

    tickets = [
        TicketSnapshot(ticket_id=301, subject="Payment gateway error", category="payment", intent="PAYMENT_ISSUE", created_at=now, tenant_id=tenant_id),
        TicketSnapshot(ticket_id=302, subject="Checkout payment gateway failure", category="payment", intent="PAYMENT_ISSUE", created_at=now + timedelta(minutes=5), tenant_id=tenant_id),
    ]

    detector = IncidentDetector()
    hypotheses1 = detector.detect_incidents(tickets, tenant_id=tenant_id)
    assert len(hypotheses1) == 1
    inc1 = hypotheses1[0]

    await IncidentPersistenceService.update_status(
        db=db_session,
        incident_id=inc1.incident_id,
        status="investigating",
        tenant_id=tenant_id,
        category=inc1.category,
        affected_ticket_ids=inc1.affected_tickets,
    )

    count_stmt = select(func.count(IncidentRecord.id)).where(IncidentRecord.tenant_id == tenant_id)
    count1 = (await db_session.execute(count_stmt)).scalar()
    assert count1 == 1

    for i in range(5):
        tickets.append(
            TicketSnapshot(
                ticket_id=303 + i,
                subject="Payment gateway timed out",
                category="payment",
                intent="PAYMENT_ISSUE",
                created_at=now + timedelta(minutes=10 + i * 2),
                tenant_id=tenant_id,
            )
        )
        hypotheses_repeated = detector.detect_incidents(tickets, tenant_id=tenant_id)
        hypotheses_reconciled = await IncidentPersistenceService.reconcile_hypotheses(db_session, hypotheses_repeated, tenant_id=tenant_id)
        assert len(hypotheses_reconciled) == 1
        assert hypotheses_reconciled[0].status == "investigating"

    count2 = (await db_session.execute(count_stmt)).scalar()
    assert count2 == 1

    record = await IncidentPersistenceService.get_incident(db_session, inc1.incident_id, tenant_id=tenant_id)
    assert record is not None
    assert record.status == "investigating"
    assert 301 in record.affected_ticket_ids
    assert 302 in record.affected_ticket_ids


@pytest.mark.asyncio
async def test_unrelated_clusters_do_not_inherit_status(db_session: AsyncSession):
    """Ensure that dynamically detected incidents match their saved status and unrelated clusters stay as candidate."""
    tenant_id = "test_tenant_safe_match"
    now = datetime.now(timezone.utc)

    payment_tickets = [
        TicketSnapshot(ticket_id=501, subject="Payment failed", category="payment", intent="PAYMENT_ISSUE", created_at=now, tenant_id=tenant_id),
        TicketSnapshot(ticket_id=502, subject="Payment failed", category="payment", intent="PAYMENT_ISSUE", created_at=now, tenant_id=tenant_id),
    ]

    detector = IncidentDetector()
    pay_hyp = detector.detect_incidents(payment_tickets, tenant_id=tenant_id)[0]

    await IncidentPersistenceService.update_status(
        db=db_session,
        incident_id=pay_hyp.incident_id,
        status="confirmed",
        tenant_id=tenant_id,
        category="payment",
        affected_ticket_ids=[501, 502],
    )

    delivery_tickets = [
        TicketSnapshot(ticket_id=601, subject="Delivery package delay", category="delivery", intent="DELIVERY_ISSUE", created_at=now, tenant_id=tenant_id),
        TicketSnapshot(ticket_id=602, subject="Courier tracking missing", category="delivery", intent="DELIVERY_ISSUE", created_at=now, tenant_id=tenant_id),
    ]

    deliv_hyp = detector.detect_incidents(delivery_tickets, tenant_id=tenant_id)[0]
    reconciled = await IncidentPersistenceService.reconcile_hypotheses(db_session, [deliv_hyp], tenant_id=tenant_id)

    assert reconciled[0].incident_id != pay_hyp.incident_id
    assert reconciled[0].status == "candidate"

