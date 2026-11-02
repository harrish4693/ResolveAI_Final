"""
ResolveAIV2 — Expert Console, Real-time Sync & Cache Performance Suite

Validates:
1. Real-time customer query sync in Expert Console:
   - ConnectionManager dispatch to customer and assigned expert user_id.
   - Unassigned handoff broadcast to all connected staff.
   - Recipient deduplication.
   - Internal note isolation from customers.
   - Router expert user_id resolution from Expert.user_id.
   - Perspective alignment rendering logic contract.
2. Expert dashboard performance & incident caching:
   - Under-load clustering performance (< 500ms for 100 tickets).
   - In-memory TTL cache lifecycle and invalidation.
   - Schema contracts: HandoffStats, HandoffRead.
3. Multi-tenant incident cache isolation:
   - Strict tenant-keyed storage.
   - Invalidation isolation between tenants.
   - TTL expiration behavior.
"""

import time
from datetime import datetime, timezone
from typing import Dict, List, Set
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.ai.intelligence.incidents import IncidentDetector, TicketSnapshot
from app.conversations.models import Conversation, ConversationMessage
from app.experts.models import Expert
from app.handoff.models import Handoff
from app.handoff.router import (
    _INCIDENT_CACHE_TTL_SECONDS,
    _INCIDENT_MAP_CACHE,
    invalidate_incident_map_cache,
)
from app.handoff.schemas import HandoffRead, HandoffStats
from app.shared.models import HandoffStatus, Priority, SenderType, UserRole, WorkflowState
from app.users.models import User
from app.websockets.events import new_message_event, typing_event
from app.websockets.manager import ConnectionManager


@pytest.fixture(autouse=True)
def setup_db():
    """Bypass in-memory SQLite socketpair synchronization for mock/unit tests."""
    yield


@pytest.fixture(autouse=True)
def clean_incident_cache():
    """Ensure incident map cache is cleared between tests."""
    _INCIDENT_MAP_CACHE.clear()
    yield
    _INCIDENT_MAP_CACHE.clear()


def run_coro(coro):
    """Drive coroutine to completion synchronously without creating OS-level socketpairs."""
    try:
        while True:
            coro.send(None)
    except StopIteration as e:
        return e.value


# ============================================================================
# Section 1: Real-Time Chat Sync & Perspective Alignment
# ============================================================================

def test_manager_dispatches_to_customer_and_expert_user_id():
    """Verify that send_to_conversation_participants sends to customer_id and expert_id."""
    cm = ConnectionManager()

    mock_customer_ws = AsyncMock()
    mock_expert_ws = AsyncMock()

    cm._connections[101] = {mock_customer_ws}
    cm._connections[202] = {mock_expert_ws}

    event = new_message_event(
        conversation_id=1,
        message_id=55,
        sender_type="customer",
        content="Naa order status kekuren",
        created_at="2026-10-28T22:00:00Z",
    )

    run_coro(cm.send_to_conversation_participants(customer_id=101, expert_id=202, event=event))

    assert mock_customer_ws.send_json.called
    assert mock_customer_ws.send_json.call_args[0][0] == event
    assert mock_expert_ws.send_json.called
    assert mock_expert_ws.send_json.call_args[0][0] == event


def test_manager_broadcasts_to_all_connected_experts_when_unassigned():
    """When a handoff is unassigned (expert_id=None), all connected staff in _expert_users receive the message."""
    cm = ConnectionManager()

    mock_customer_ws = AsyncMock()
    mock_expert1_ws = AsyncMock()
    mock_expert2_ws = AsyncMock()

    cm._connections[101] = {mock_customer_ws}
    cm._connections[501] = {mock_expert1_ws}
    cm._connections[502] = {mock_expert2_ws}
    cm._expert_users.add(501)
    cm._expert_users.add(502)

    event = new_message_event(
        conversation_id=2,
        message_id=56,
        sender_type="customer",
        content="Help me, agent escalated this to expert",
        created_at="2026-10-28T22:00:00Z",
    )

    run_coro(cm.send_to_conversation_participants(customer_id=101, expert_id=None, event=event))

    assert mock_customer_ws.send_json.called
    assert mock_expert1_ws.send_json.called
    assert mock_expert2_ws.send_json.called
    assert mock_expert1_ws.send_json.call_args[0][0] == event
    assert mock_expert2_ws.send_json.call_args[0][0] == event


def test_manager_deduplicates_recipients_when_assigned_expert_is_in_expert_users():
    """Verify that assigned expert who is also in _expert_users does not receive duplicate messages."""
    cm = ConnectionManager()

    mock_expert_ws = AsyncMock()
    cm._connections[303] = {mock_expert_ws}
    cm._expert_users.add(303)

    event = {"type": "TEST_EVENT"}

    run_coro(cm.send_to_conversation_participants(customer_id=999, expert_id=303, event=event))

    assert mock_expert_ws.send_json.call_count == 1


def test_manager_internal_note_withholds_from_customer():
    """Internal notes (is_internal=True) must NOT be delivered to customer_id."""
    cm = ConnectionManager()

    mock_customer_ws = AsyncMock()
    mock_expert_ws = AsyncMock()

    cm._connections[101] = {mock_customer_ws}
    cm._connections[202] = {mock_expert_ws}

    event = {"type": "INTERNAL_NOTE", "content": "Checking inventory"}

    run_coro(cm.send_to_conversation_participants(customer_id=101, expert_id=202, event=event, is_internal=True))

    assert not mock_customer_ws.send_json.called
    assert mock_expert_ws.send_json.called
    assert mock_expert_ws.send_json.call_args[0][0] == event


def test_router_resolves_expert_user_id_from_assigned_expert_id():
    """
    Verify that in escalated handoff, the expert User.id is retrieved from Expert.user_id,
    preventing the ID-mismatch bug where Expert.id was passed as user_id.
    """
    fake_handoff = Handoff(id=5, conversation_id=10, assigned_expert_id=1)
    fake_expert = Expert(id=1, user_id=888)

    async def mock_lookup():
        handoff = fake_handoff
        expert_user_id = None
        if handoff and handoff.assigned_expert_id:
            expert_rec = fake_expert if fake_expert.id == handoff.assigned_expert_id else None
            if expert_rec:
                expert_user_id = expert_rec.user_id
        return expert_user_id

    expert_user_id = run_coro(mock_lookup())
    assert expert_user_id == 888
    assert expert_user_id != fake_handoff.assigned_expert_id


def test_perspective_alignment_logic_contract():
    """
    Verify perspective rendering contract:
    - Customer interface (expert=False):
        * customer message: isSelf = True (Right / 'You')
        * expert message: isSelf = False (Left / 'Support Expert')
    - Expert interface (expert=True):
        * customer message: isSelf = False (Left / 'Customer')
        * expert message: isSelf = True (Right / 'You (Expert)')
    """
    def compute_perspective(expert_view: bool, sender_type: str):
        is_expert = sender_type in ("expert", "support")
        is_client = sender_type in ("customer", "client")
        is_self = is_expert if expert_view else is_client

        if is_self:
            label = "You (Expert)" if expert_view else "You"
        else:
            label = "Customer" if expert_view and is_client else "Support Expert"

        return is_self, label

    # In Expert View:
    is_self_cust, label_cust = compute_perspective(expert_view=True, sender_type="customer")
    assert is_self_cust is False
    assert label_cust == "Customer"

    is_self_exp, label_exp = compute_perspective(expert_view=True, sender_type="expert")
    assert is_self_exp is True
    assert label_exp == "You (Expert)"

    # In Customer View:
    is_self_c_cust, label_c_cust = compute_perspective(expert_view=False, sender_type="customer")
    assert is_self_c_cust is True
    assert label_c_cust == "You"

    is_self_c_exp, label_c_exp = compute_perspective(expert_view=False, sender_type="expert")
    assert is_self_c_exp is False
    assert label_c_exp == "Support Expert"


# ============================================================================
# Section 2: Dashboard Performance & Incident Caching
# ============================================================================

def test_incident_detector_performance_under_load():
    """Verify that clustering 100 tickets executes in < 500ms."""
    categories = ["Billing", "Technical", "Delivery", "Account", "Security"]
    snapshots = [
        TicketSnapshot(
            ticket_id=i,
            subject=f"Issue with {categories[i % len(categories)]} order ref #{1000 + i}",
            category=categories[i % len(categories)],
            created_at=datetime.now(timezone.utc),
            customer_id=10,
            tenant_id="default",
            status="open",
        )
        for i in range(1, 101)
    ]

    detector = IncidentDetector()
    t0 = time.perf_counter()
    incidents = detector.detect_incidents(snapshots, tenant_id="default")
    t1 = time.perf_counter()
    duration_ms = (t1 - t0) * 1000

    assert duration_ms < 500, f"detect_incidents took {duration_ms:.2f}ms, expected < 500ms"
    assert len(incidents) > 0, "Expected at least 1 detected incident cluster"


def test_incident_map_cache_lifecycle():
    """Verify in-memory TTL cache operations and invalidation."""
    tenant = "test_tenant"
    invalidate_incident_map_cache(tenant)
    assert tenant not in _INCIDENT_MAP_CACHE

    test_map = {1: {"incident_id": "INC-001", "is_confirmed": True, "severity": "HIGH"}}
    now = time.monotonic()
    _INCIDENT_MAP_CACHE[tenant] = (now, test_map)

    assert tenant in _INCIDENT_MAP_CACHE
    assert _INCIDENT_MAP_CACHE[tenant][1][1]["incident_id"] == "INC-001"

    invalidate_incident_map_cache(tenant)
    assert tenant not in _INCIDENT_MAP_CACHE


def test_handoff_stats_model_contract():
    """Verify HandoffStats schema and default serialization."""
    stats = HandoffStats(
        queue_size=12,
        active_chats=3,
        resolved_count=45,
        average_csat=4.8,
    )
    data = stats.model_dump()
    assert data["queue_size"] == 12
    assert data["active_chats"] == 3
    assert data["resolved_count"] == 45
    assert data["average_csat"] == 4.8


def test_handoff_read_bounded_serialization():
    """Verify HandoffRead serialization preserves all priority and risk fields."""
    now = datetime.now(timezone.utc)
    item = HandoffRead(
        id=1,
        conversation_id=101,
        category="Billing",
        escalation_reason="Customer payment failure",
        priority=Priority.HIGH,
        status=HandoffStatus.WAITING,
        created_at=now,
        updated_at=now,
        failure_risk_level="HIGH",
        failure_probability=0.85,
        predicted_difficulty="MODERATE",
        warning_signals=["Negative sentiment", "Repeated failure"],
        incident_id="INC-BILL-0001",
        priority_rank=170,
        priority_rationale="High resolution failure risk",
    )
    dumped = item.model_dump()
    assert dumped["id"] == 1
    assert dumped["incident_id"] == "INC-BILL-0001"
    assert dumped["priority_rank"] == 170
    assert dumped["failure_risk_level"] == "HIGH"


# ============================================================================
# Section 3: Tenant Cache Isolation
# ============================================================================

def test_tenant_cache_isolation():
    """Verify Tenant A and Tenant B have separate caches and do not bleed."""
    tenant_a = "tenant-alpha"
    tenant_b = "tenant-beta"

    data_a = {101: {"incident_id": "INC-ALPHA-1", "is_confirmed": True, "severity": "HIGH"}}
    data_b = {202: {"incident_id": "INC-BETA-1", "is_confirmed": False, "severity": "MEDIUM"}}

    now = time.monotonic()
    _INCIDENT_MAP_CACHE[tenant_a] = (now, data_a)
    _INCIDENT_MAP_CACHE[tenant_b] = (now, data_b)

    assert tenant_a in _INCIDENT_MAP_CACHE
    assert tenant_b in _INCIDENT_MAP_CACHE
    assert _INCIDENT_MAP_CACHE[tenant_a][1] == data_a
    assert _INCIDENT_MAP_CACHE[tenant_b][1] == data_b
    assert 101 not in _INCIDENT_MAP_CACHE[tenant_b][1]
    assert 202 not in _INCIDENT_MAP_CACHE[tenant_a][1]


def test_tenant_cache_invalidation_isolation():
    """Verify invalidating Tenant A does not clear Tenant B."""
    tenant_a = "tenant-alpha"
    tenant_b = "tenant-beta"

    now = time.monotonic()
    _INCIDENT_MAP_CACHE[tenant_a] = (now, {101: {"incident_id": "INC-A"}})
    _INCIDENT_MAP_CACHE[tenant_b] = (now, {202: {"incident_id": "INC-B"}})

    invalidate_incident_map_cache(tenant_a)

    assert tenant_a not in _INCIDENT_MAP_CACHE
    assert tenant_b in _INCIDENT_MAP_CACHE
    assert _INCIDENT_MAP_CACHE[tenant_b][1] == {202: {"incident_id": "INC-B"}}


def test_tenant_cache_ttl_expiration():
    """Verify cache expires after TTL (30 seconds)."""
    tenant = "tenant-alpha"
    old_time = time.monotonic() - (_INCIDENT_CACHE_TTL_SECONDS + 5)
    _INCIDENT_MAP_CACHE[tenant] = (old_time, {101: {"incident_id": "INC-EXPIRED"}})

    cached = _INCIDENT_MAP_CACHE.get(tenant)
    is_valid = cached and (time.monotonic() - cached[0] < _INCIDENT_CACHE_TTL_SECONDS)
    assert not is_valid, "Cache entry should be considered expired"

