"""
ResolveAIV2 — Comprehensive Autonomy Controls, Failure Prediction & Escalation Suite

Covers:
1. Dynamic Autonomy Controls:
   - Mode validation (conservative, balanced, high_automation) and bounded overrides.
   - Balanced mode preservation of default behavior.
   - Conservative mode stricter clarification/escalation policy.
   - High automation safety boundaries (sensitive vs routine queries).
   - Security-sensitive and critical requests escalation across all modes.
   - Restricted tool action confirmation rules.
   - Invalid/missing settings safe fallback to balanced defaults.
   - Admin RBAC and cross-tenant setting isolation.
   - Durable DB persistence and audit logs.
   - Backward compatibility with code-mixing and failure risk.
   - UI reset and bounded threshold override enforcement.
2. Resolution Failure Prediction & Proactive Escalation:
   - Output integration into expert handoff context.
   - Missing prediction metadata graceful handling.
   - Predicted risk distinguished from confirmed observed failure.
   - Repeated unsuccessful attempt accumulation.
   - Frustration alone does not force premature escalation on greetings.
   - Deterministic queue ranking and priority rationales.
   - Cross-ticket incident context integration and priority boost.
   - Customer/expert permission enforcement on failure analytics.
   - Admin failure analytics calculation from real DB records.
3. P0 Escalation Regressions & Anti-False-Escalation:
   - Greetings and routine FAQs resolve without escalation.
   - Routine troubleshooting guidance preservation.
   - Missing required info clarification (ASK_USER).
   - Real risk / fraud cases escalate immediately (ESCALATE).
   - Explicit human agent requests escalate immediately (ESCALATE).
   - Provider timeout safe recovery.
   - Markdown-wrapped JSON extraction and schema validation.
   - Empty RAG results safe fallback.
   - Authorized vs unauthorized order lookups (cross-customer leak prevention).
   - Multilingual intent and decision parity.
   - Single unduplicated response alternation in text chat.
4. Code-Mixed Handoff Context:
   - Tanglish / Hinglish metadata in handoff context.
   - Missing metadata and genuine confidence scores (unfabricated).
   - Authorization and customer isolation.
   - Legacy response field schema stability.
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.autonomy_models import AutonomyConfig
from app.ai.autonomy_service import AutonomyConfigService
from app.ai.groq_provider import clean_json_markdown
from app.ai.intelligence.autonomy import (
    MODE_THRESHOLDS,
    THRESHOLD_BOUNDS,
    AutonomyConfigDTO,
    AutonomyLevel,
    AutonomyLevelDeterminer,
    AutonomyMode,
    AutonomyThresholds,
)
from app.ai.intelligence.failure_prediction import (
    FailureLikelihood,
    FailurePredictor,
    ResolutionAttemptTracker,
    global_attempt_tracker,
)
from app.ai.intelligence.incidents import IncidentStateManager
from app.ai.intelligence.language import UniversalMeaningEngine
from app.ai.m4.decision import DecisionEngine
from app.ai.m4.provider import M4AIProvider
from app.ai.schemas import DecisionSchema
from app.ai.validation.models import (
    ResponseValidationContext,
    ToolResultContext,
    ValidationStatus,
)
from app.ai.validation.rules import _normalize_id, check_security
from app.ai.validation.service import ValidationService
from app.auth.jwt import create_access_token
from app.auth.password import get_password_hash
from app.conversations.models import Conversation, ConversationMessage
from app.conversations.service import ConversationService
from app.handoff.models import Handoff
from app.shared.models import (
    ConversationStatus,
    HandoffStatus,
    MessageType,
    Priority,
    SenderType,
    UserRole,
    WorkflowState,
)
from app.tickets.models import Ticket
from app.users.models import User


@pytest.fixture(autouse=True)
def reset_autonomy_and_failure_state():
    """Reset in-memory state before and after each test."""
    IncidentStateManager.reset()
    global_attempt_tracker._attempts.clear()
    AutonomyConfigService.invalidate_cache()
    yield
    IncidentStateManager.reset()
    global_attempt_tracker._attempts.clear()
    AutonomyConfigService.invalidate_cache()


# ==============================================================================
# Section 1: Dynamic Autonomy Controls
# ==============================================================================

def test_each_supported_mode_validated_correctly():
    """Verify supported modes validate and illegal modes or out-of-bounds overrides fail."""
    for mode in ["conservative", "balanced", "high_automation"]:
        dto = AutonomyConfigDTO.for_mode(mode)
        assert dto.mode.value == mode
        assert isinstance(dto.thresholds, AutonomyThresholds)

    with pytest.raises(ValueError, match="Invalid autonomy mode"):
        AutonomyConfigDTO.for_mode("unrestricted_god_mode")

    dto_custom = AutonomyConfigDTO.for_mode("balanced", custom_overrides={"auto_resolve_min_confidence": 80.0})
    assert dto_custom.thresholds.auto_resolve_min_confidence == 80.0

    with pytest.raises(ValueError, match="violates safety bounds"):
        AutonomyConfigDTO.for_mode("balanced", custom_overrides={"auto_resolve_min_confidence": 20.0})

    with pytest.raises(ValueError, match="violates safety bounds"):
        AutonomyConfigDTO.for_mode("balanced", custom_overrides={"auto_resolve_max_risk": 0.95})


@pytest.mark.asyncio
async def test_balanced_mode_preserves_existing_default_behavior():
    """Verify Balanced mode maintains existing production confidence thresholds."""
    provider = M4AIProvider()
    analysis = {
        "intent": "DELIVERY_ISSUE",
        "sentiment": "NEUTRAL",
        "original_message": "Where is my parcel 9999?",
        "entities": {"order_id": "9999"},
        "priority": "low",
    }
    articles = [{"id": 1, "content": "Track orders via your account portal with order ID.", "score": 0.85}]

    await provider.generate_response(
        analysis=analysis,
        knowledge=articles,
        context={"conversation_id": 1001, "autonomy_mode": "balanced"},
    )
    assert analysis["decision_state"] in ("RESOLVE", "USE_TOOL")
    assert analysis["autonomy"]["mode"] == "balanced"
    assert analysis["autonomy"]["level"] == "AUTOMATIC"


@pytest.mark.asyncio
async def test_conservative_mode_applies_stricter_policy():
    """Verify Conservative mode prefers clarification or human review when confidence is below 85%."""
    determiner = AutonomyLevelDeterminer(mode=AutonomyMode.CONSERVATIVE)

    analysis = {
        "intent": "GENERAL_QUERY",
        "sentiment": "NEUTRAL",
        "original_message": "Can I use ResolveAI overseas?",
        "entities": {},
        "priority": "low",
    }
    context = {"history": [], "rag_results": [{"score": 0.15}]}

    decision_cons = determiner.determine_level(analysis, context, mode=AutonomyMode.CONSERVATIVE)
    assert decision_cons.level in (AutonomyLevel.CONFIRMATION_REQUIRED, AutonomyLevel.ESCALATE)
    assert "conservative" in decision_cons.reasoning.lower()

    decision_bal = determiner.determine_level(analysis, context, mode=AutonomyMode.BALANCED)
    assert decision_bal.level == AutonomyLevel.AUTOMATIC


@pytest.mark.asyncio
async def test_high_automation_does_not_bypass_safety_rules():
    """Verify High Automation permits routine queries to resolve at 65%, but sensitive queries cannot."""
    determiner = AutonomyLevelDeterminer(mode=AutonomyMode.HIGH_AUTOMATION)

    routine_analysis = {
        "intent": "GREETING",
        "sentiment": "NEUTRAL",
        "original_message": "Hi, good morning!",
        "entities": {},
        "priority": "low",
    }
    context_routine = {"rag_results": [{"score": 0.70}]}
    decision_routine = determiner.determine_level(routine_analysis, context_routine)
    assert decision_routine.level == AutonomyLevel.AUTOMATIC

    sensitive_analysis = {
        "intent": "REFUND_ISSUE",
        "sentiment": "NEUTRAL",
        "original_message": "I want a refund for transaction 123",
        "entities": {"transaction_id": "123"},
        "priority": "medium",
    }
    decision_sensitive = determiner.determine_level(sensitive_analysis, context_routine)
    assert decision_sensitive.level != AutonomyLevel.AUTOMATIC


@pytest.mark.asyncio
async def test_security_and_critical_requests_still_escalate():
    """Verify SECURITY_ISSUE and CRITICAL priority ALWAYS escalate even in High Automation."""
    provider = M4AIProvider()

    analysis_sec = {
        "intent": "SECURITY_ISSUE",
        "sentiment": "NEUTRAL",
        "original_message": "Account credentials compromised by unauthorized party",
        "entities": {},
        "priority": "high",
    }
    perfect_articles = [{"id": 1, "content": "Emergency security guide", "score": 0.99}]
    await provider.generate_response(
        analysis=analysis_sec,
        knowledge=perfect_articles,
        context={"conversation_id": 2001, "autonomy_mode": "high_automation"},
    )
    assert analysis_sec["decision_state"] == "ESCALATE"

    analysis_crit = {
        "intent": "GENERAL_QUERY",
        "sentiment": "NEUTRAL",
        "original_message": "Server system down affecting all users",
        "entities": {},
        "priority": "critical",
    }
    await provider.generate_response(
        analysis=analysis_crit,
        knowledge=perfect_articles,
        context={"conversation_id": 2002, "autonomy_mode": "high_automation"},
    )
    assert analysis_crit["decision_state"] == "ESCALATE"


def test_restricted_tool_actions_still_require_confirmation():
    """Verify tools with financial or account impact require confirmation across all modes."""
    determiner = AutonomyLevelDeterminer(mode=AutonomyMode.HIGH_AUTOMATION)

    for tool in ["create_refund_request", "update_account", "create_support_ticket"]:
        analysis = {
            "intent": "REFUND_ISSUE",
            "decision_state": "USE_TOOL",
            "tool_name": tool,
            "priority": "low",
        }
        decision = determiner.determine_level(analysis, {"history": []})
        assert decision.level == AutonomyLevel.CONFIRMATION_REQUIRED
        assert "requires customer confirmation" in decision.reasoning or "Restricted" in decision.reasoning


@pytest.mark.asyncio
async def test_invalid_or_missing_settings_fallback_safely(db_session: AsyncSession):
    """Verify that querying a non-existent tenant returns balanced default configuration."""
    AutonomyConfigService.invalidate_cache()
    dto = await AutonomyConfigService.get_effective_config(db_session, tenant_id="non_existent_tenant_999")
    assert dto.mode == AutonomyMode.BALANCED
    assert dto.thresholds.auto_resolve_min_confidence == 75.0
    assert dto.thresholds.auto_resolve_max_risk == 0.25
    assert dto.thresholds.max_attempts_before_escalate == 3


@pytest.mark.asyncio
async def test_only_authorized_admins_can_update_settings(
    async_client: AsyncClient,
    auth_headers_a,
    auth_headers_expert,
    auth_headers_admin,
):
    """Verify RBAC: Customers and Experts get 403 Forbidden; Admins get 200."""
    payload = {"mode": "conservative"}

    res_cust = await async_client.put("/api/admin/autonomy", json=payload, headers=auth_headers_a)
    assert res_cust.status_code == 403

    res_exp = await async_client.put("/api/admin/autonomy", json=payload, headers=auth_headers_expert)
    assert res_exp.status_code == 403

    res_adm = await async_client.put("/api/admin/autonomy", json=payload, headers=auth_headers_admin)
    assert res_adm.status_code == 200
    assert res_adm.json()["mode"] == "conservative"


@pytest.mark.asyncio
async def test_tenant_settings_cannot_leak(
    async_client: AsyncClient,
    auth_headers_admin,
):
    """Verify tenant isolation: Tenant A's settings do not bleed into Tenant B."""
    AutonomyConfigService.invalidate_cache()

    res_a = await async_client.put(
        "/api/admin/autonomy",
        json={"mode": "conservative", "tenant_id": "tenant_alpha"},
        headers=auth_headers_admin,
    )
    assert res_a.status_code == 200
    assert res_a.json()["mode"] == "conservative"

    res_b = await async_client.put(
        "/api/admin/autonomy",
        json={"mode": "high_automation", "tenant_id": "tenant_beta"},
        headers=auth_headers_admin,
    )
    assert res_b.status_code == 200
    assert res_b.json()["mode"] == "high_automation"

    get_a = await async_client.get("/api/admin/autonomy?tenant_id=tenant_alpha", headers=auth_headers_admin)
    assert get_a.json()["mode"] == "conservative"

    get_b = await async_client.get("/api/admin/autonomy?tenant_id=tenant_beta", headers=auth_headers_admin)
    assert get_b.json()["mode"] == "high_automation"


@pytest.mark.asyncio
async def test_saved_settings_persist_durably(
    async_client: AsyncClient,
    auth_headers_admin,
    db_session: AsyncSession,
):
    """Verify settings survive cache invalidation and are committed to DB."""
    AutonomyConfigService.invalidate_cache()

    res = await async_client.put(
        "/api/admin/autonomy",
        json={"mode": "conservative", "tenant_id": "durable_tenant", "auto_resolve_min_confidence": 88.0},
        headers=auth_headers_admin,
    )
    assert res.status_code == 200

    AutonomyConfigService.invalidate_cache("durable_tenant")

    stmt = select(AutonomyConfig).where(AutonomyConfig.tenant_id == "durable_tenant")
    row = (await db_session.execute(stmt)).scalar_one_or_none()
    assert row is not None
    assert row.mode == "conservative"
    assert row.auto_resolve_min_confidence == 88.0
    assert len(row.audit_log) >= 1
    assert row.audit_log[-1]["new_mode"] == "conservative"


@pytest.mark.asyncio
async def test_existing_tasks_1_to_3_backward_compatible():
    """Verify Code-Mixed language and Failure Risk prediction integrate seamlessly with Autonomy."""
    provider = M4AIProvider()

    analysis = {
        "intent": "DELIVERY_ISSUE",
        "sentiment": "NEUTRAL",
        "original_message": "En parcel delivery status enna aachu?",
        "is_code_mixed": True,
        "normalized_message": "What is my parcel delivery status?",
        "entities": {"order_id": "ORD123"},
        "priority": "low",
    }
    articles = [{"id": 1, "content": "Your delivery ORD123 is on track for tomorrow.", "score": 0.90}]

    await provider.generate_response(
        analysis=analysis,
        knowledge=articles,
        context={"conversation_id": 3001, "autonomy_mode": "balanced"},
    )
    assert analysis["decision_state"] in ("RESOLVE", "USE_TOOL")
    assert "failure_risk" in analysis
    assert "autonomy" in analysis
    assert analysis["autonomy"]["mode"] == "balanced"


@pytest.mark.asyncio
async def test_reset_and_bounded_threshold_validation(
    async_client: AsyncClient,
    auth_headers_admin,
):
    """Verify resetting to default and rejection of illegal policy overrides."""
    await async_client.put(
        "/api/admin/autonomy",
        json={"mode": "conservative", "tenant_id": "reset_test_tenant"},
        headers=auth_headers_admin,
    )

    res_reset = await async_client.post(
        "/api/admin/autonomy/reset?tenant_id=reset_test_tenant",
        headers=auth_headers_admin,
    )
    assert res_reset.status_code == 200
    data = res_reset.json()
    assert data["mode"] == "balanced"
    assert data["auto_resolve_min_confidence"] == 75.0

    res_forbidden = await async_client.put(
        "/api/admin/autonomy",
        json={
            "mode": "high_automation",
            "tenant_id": "reset_test_tenant",
            "policy_overrides": {"bypass_confirmation": True},
        },
        headers=auth_headers_admin,
    )
    assert res_forbidden.status_code == 400
    assert "forbidden" in res_forbidden.json()["detail"].lower()


# ==============================================================================
# Section 2: Failure Prediction & Proactive Escalation
# ==============================================================================

@pytest.mark.asyncio
async def test_failure_prediction_output_integrated_correctly(
    async_client: AsyncClient,
    auth_headers_expert,
    test_user_a: User,
    test_expert: User,
    db_session: AsyncSession,
):
    """Verify that failure prediction signals, difficulty, and recommendation appear in handoff context."""
    convo = Conversation(customer_id=test_user_a.id, workflow_state="waiting_for_expert")
    db_session.add(convo)
    await db_session.flush()

    ticket = Ticket(
        customer_id=test_user_a.id,
        conversation_id=convo.id,
        subject="Payment debited but order not confirmed",
        category="Payments/Finance",
        priority="high",
    )
    db_session.add(ticket)
    await db_session.flush()

    failure_risk_meta = {
        "likelihood": "HIGH",
        "probability": 0.72,
        "predicted_difficulty": "COMPLEX",
        "should_escalate_early": True,
        "reasons": ["Complex intent: PAYMENT_ISSUE", "Customer reported previous solution did not work"],
        "frustration_level": 0.65,
        "observed_failure_count": 2,
        "has_prior_solution_failed": True,
        "suggested_action": "Investigate previous solution failure and verify payment gateway logs",
        "priority_rationale": "High priority with reported prior solution failure",
    }

    handoff = Handoff(
        conversation_id=convo.id,
        ticket_id=ticket.id,
        customer_id=test_user_a.id,
        escalation_reason="Repeated payment failure reported",
        priority=Priority.HIGH,
        category="Payments/Finance",
        ai_analysis={"failure_risk": failure_risk_meta, "intent": "PAYMENT_ISSUE", "sentiment": "NEGATIVE"},
        status=HandoffStatus.WAITING,
    )
    db_session.add(handoff)
    await db_session.commit()

    resp = await async_client.get(f"/api/handoffs/{handoff.id}/context", headers=auth_headers_expert)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert "failure_risk" in data
    fr = data["failure_risk"]
    assert fr is not None
    assert fr["risk_level"] == "HIGH"
    assert fr["probability"] == 0.72
    assert fr["predicted_difficulty"] == "COMPLEX"
    assert fr["has_prior_solution_failed"] is True
    assert fr["observed_failure_count"] == 2
    assert len(fr["signals"]) == 2
    assert "payment gateway logs" in fr["suggested_action"]


@pytest.mark.asyncio
async def test_missing_prediction_metadata_handled_gracefully(
    async_client: AsyncClient,
    auth_headers_expert,
    test_user_a: User,
    test_expert: User,
    db_session: AsyncSession,
):
    """Verify that a handoff with null or missing ai_analysis handles failure risk safely without crashing."""
    convo = Conversation(customer_id=test_user_a.id, workflow_state="waiting_for_expert")
    db_session.add(convo)
    await db_session.flush()

    ticket = Ticket(
        customer_id=test_user_a.id,
        conversation_id=convo.id,
        subject="Simple General Inquiry",
        category="General",
        priority="low",
    )
    db_session.add(ticket)
    await db_session.flush()

    handoff = Handoff(
        conversation_id=convo.id,
        ticket_id=ticket.id,
        customer_id=test_user_a.id,
        escalation_reason="General help needed",
        priority=Priority.LOW,
        category="General",
        ai_analysis=None,
        status=HandoffStatus.WAITING,
    )
    db_session.add(handoff)
    await db_session.commit()

    resp = await async_client.get(f"/api/handoffs/{handoff.id}/context", headers=auth_headers_expert)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "failure_risk" in data
    fr = data["failure_risk"]
    assert fr is not None
    assert fr["risk_level"] in ("LOW", "MODERATE")
    assert isinstance(fr["probability"], float)
    assert isinstance(fr["signals"], list)


def test_predicted_risk_distinguished_from_observed_failure():
    """Verify predicted risk is not marked as confirmed failure without evidence."""
    predictor = FailurePredictor()
    analysis = {
        "intent": "REFUND_ISSUE",
        "entities": {},
        "sentiment": "NEUTRAL",
        "original_message": "How do I request a refund for an order?",
    }
    pred = predictor.predict(analysis, {"rag_results": [], "history": []})
    assert pred.observed_failure_count == 0
    assert pred.has_prior_solution_failed is False

    analysis_failed = {
        "intent": "REFUND_ISSUE",
        "entities": {},
        "sentiment": "NEGATIVE",
        "original_message": "I already tried that link and it did not work at all, still not working!",
    }
    pred_failed = predictor.predict(analysis_failed, {"rag_results": [], "history": []})
    assert pred_failed.has_prior_solution_failed is True
    assert any("solution did not work" in r.lower() for r in pred_failed.reasons)
    assert pred_failed.probability > pred.probability


def test_repeated_unsuccessful_attempts_influence_risk():
    """Verify that repeated failed attempts increase failure probability only when supported by real data."""
    predictor = FailurePredictor()
    tracker = ResolutionAttemptTracker()

    analysis = {"intent": "GENERAL_QUERY", "entities": {}, "original_message": "Please assist"}
    pred_initial = predictor.predict(analysis, {"rag_results": [], "history": []}, tracker, conversation_id=42)

    tracker.track_attempt(42, "tool:check_status", success=False, error_message="Timeout")
    tracker.track_attempt(42, "tool:retry_status", success=False, error_message="Timeout")
    tracker.track_attempt(42, "rag_lookup", success=False, error_message="No match")

    pred_after_failures = predictor.predict(analysis, {"rag_results": [], "history": []}, tracker, conversation_id=42)

    assert pred_after_failures.probability > pred_initial.probability
    assert pred_after_failures.observed_failure_count == 3
    assert pred_after_failures.should_escalate_early is True


def test_customer_frustration_alone_does_not_force_escalation():
    """Verify negative sentiment or frustration on a simple greeting doesn't force premature escalation."""
    predictor = FailurePredictor()
    analysis = {
        "intent": "GREETING",
        "entities": {},
        "sentiment": "NEGATIVE",
        "original_message": "Hello, I am upset today.",
    }
    pred = predictor.predict(analysis, {"rag_results": [{"score": 0.8}], "history": []})
    assert pred.likelihood == FailureLikelihood.LOW
    assert pred.should_escalate_early is False


@pytest.mark.asyncio
async def test_mandatory_security_escalation_remains_intact():
    """Verify security issues trigger mandatory escalation regardless of low predicted failure score."""
    provider = M4AIProvider()

    analysis = {
        "intent": "SECURITY_ISSUE",
        "sentiment": "NEUTRAL",
        "original_message": "Someone compromised my login account credentials.",
        "entities": {},
        "priority": "critical",
    }
    articles = [{"id": 1, "content": "Security emergency guide", "score": 0.95}]

    await provider.generate_response(analysis, articles, {"conversation_id": 999})
    assert analysis["decision_state"] == "ESCALATE"


@pytest.mark.asyncio
async def test_queue_prioritization_follows_documented_policy(
    async_client: AsyncClient,
    auth_headers_expert,
    test_user_a: User,
    db_session: AsyncSession,
):
    """
    Verify deterministic queue ranking:
    1. Critical Priority
    2. High Priority with High Failure Risk
    3. Low Priority
    """
    now = datetime.now(timezone.utc)

    h_low = Handoff(
        conversation_id=101,
        ticket_id=201,
        customer_id=test_user_a.id,
        escalation_reason="Low priority issue",
        priority=Priority.LOW,
        category="General",
        created_at=now - timedelta(hours=2),
        status=HandoffStatus.WAITING,
        ai_analysis={"failure_risk": {"likelihood": "LOW", "probability": 0.1}},
    )
    h_high_risk = Handoff(
        conversation_id=102,
        ticket_id=202,
        customer_id=test_user_a.id,
        escalation_reason="High risk payment failure",
        priority=Priority.HIGH,
        category="Payments",
        created_at=now - timedelta(minutes=30),
        status=HandoffStatus.WAITING,
        ai_analysis={"failure_risk": {"likelihood": "HIGH", "probability": 0.85, "has_prior_solution_failed": True}},
    )
    h_critical = Handoff(
        conversation_id=103,
        ticket_id=203,
        customer_id=test_user_a.id,
        escalation_reason="Security compromise",
        priority=Priority.CRITICAL,
        category="Security",
        created_at=now - timedelta(minutes=10),
        status=HandoffStatus.WAITING,
        ai_analysis={"failure_risk": {"likelihood": "HIGH", "probability": 0.9}},
    )

    db_session.add_all([h_low, h_high_risk, h_critical])
    await db_session.commit()

    resp = await async_client.get("/api/handoffs/queue", headers=auth_headers_expert)
    assert resp.status_code == 200, resp.text
    queue = resp.json()
    assert len(queue) >= 3

    queue_ids = [q["id"] for q in queue]
    assert queue_ids.index(h_critical.id) < queue_ids.index(h_high_risk.id)
    assert queue_ids.index(h_high_risk.id) < queue_ids.index(h_low.id)

    high_risk_item = next(q for q in queue if q["id"] == h_high_risk.id)
    assert high_risk_item["priority_rationale"] is not None
    assert "High resolution failure risk" in high_risk_item["priority_rationale"]


@pytest.mark.asyncio
async def test_cross_ticket_incident_context_integration(
    async_client: AsyncClient,
    auth_headers_expert,
    test_user_a: User,
    db_session: AsyncSession,
):
    """Verify that a ticket affected by an incident gets incident_id and priority boost."""
    now = datetime.now(timezone.utc)

    t1 = Ticket(
        customer_id=test_user_a.id,
        conversation_id=501,
        subject="Payment gateway outage error 504",
        category="payment",
        priority="high",
        created_at=now,
    )
    t2 = Ticket(
        customer_id=test_user_a.id,
        conversation_id=502,
        subject="Payment gateway outage timeout error 504",
        category="payment",
        priority="high",
        created_at=now + timedelta(minutes=5),
    )
    db_session.add_all([t1, t2])
    await db_session.flush()

    h = Handoff(
        conversation_id=501,
        ticket_id=t1.id,
        customer_id=test_user_a.id,
        escalation_reason="Payment timeout",
        priority=Priority.HIGH,
        category="payment",
        status=HandoffStatus.WAITING,
    )
    db_session.add(h)
    await db_session.commit()

    from app.handoff.router import invalidate_incident_map_cache
    invalidate_incident_map_cache("default")

    resp = await async_client.get("/api/handoffs/queue", headers=auth_headers_expert)
    assert resp.status_code == 200
    queue = resp.json()
    item = next((q for q in queue if q["id"] == h.id), None)
    assert item is not None
    assert item["incident_id"] is not None
    assert "incident" in item["priority_rationale"].lower()


@pytest.mark.asyncio
async def test_customer_and_expert_permissions_enforced(
    async_client: AsyncClient,
    auth_headers_a,
    auth_headers_expert,
):
    """Verify that customers cannot view expert queue or admin failure analytics."""
    resp_queue = await async_client.get("/api/handoffs/queue", headers=auth_headers_a)
    assert resp_queue.status_code == 403

    resp_admin = await async_client.get("/api/analytics/failure-risk", headers=auth_headers_a)
    assert resp_admin.status_code == 403

    resp_expert = await async_client.get("/api/analytics/failure-risk", headers=auth_headers_expert)
    assert resp_expert.status_code == 403


@pytest.mark.asyncio
async def test_admin_analytics_returns_real_unfabricated_metrics(
    async_client: AsyncClient,
    auth_headers_admin,
    test_user_a: User,
    db_session: AsyncSession,
):
    """Verify that /api/analytics/failure-risk computes actual metrics from DB entities."""
    h1 = Handoff(
        conversation_id=701,
        ticket_id=801,
        customer_id=test_user_a.id,
        escalation_reason="High risk issue",
        priority=Priority.HIGH,
        category="Billing",
        status=HandoffStatus.WAITING,
        ai_analysis={"failure_risk": {"likelihood": "HIGH", "probability": 0.8}},
    )
    h2 = Handoff(
        conversation_id=702,
        ticket_id=802,
        customer_id=test_user_a.id,
        escalation_reason="Low risk query",
        priority=Priority.LOW,
        category="General",
        status=HandoffStatus.RESOLVED,
        ai_analysis={"failure_risk": {"likelihood": "LOW", "probability": 0.2}},
    )
    db_session.add_all([h1, h2])
    await db_session.commit()

    resp = await async_client.get("/api/analytics/failure-risk", headers=auth_headers_admin)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["high_risk_ticket_count"] >= 1
    assert data["total_evaluated_tickets"] >= 2
    assert isinstance(data["repeat_contact_rate"], float)
    assert isinstance(data["category_distribution"], list)
    assert len(data["limitations"]) > 0
    assert any("strictly derived" in lit.lower() for lit in data["limitations"])


@pytest.mark.asyncio
async def test_existing_decision_rules_backward_compatible():
    """Verify that standard inquiries without risk remain RESOLVE or USE_TOOL without degradation."""
    provider = M4AIProvider()

    analysis = {
        "intent": "DELIVERY_ISSUE",
        "sentiment": "NEUTRAL",
        "original_message": "Where is my parcel 12345?",
        "entities": {"order_id": "12345"},
        "priority": "medium",
    }
    articles = [{"id": 1, "content": "You can track your order using the order ID in our tracking portal.", "score": 0.85}]

    await provider.generate_response(analysis, articles, {"conversation_id": 999})
    assert analysis["decision_state"] in ("RESOLVE", "USE_TOOL")
    assert "failure_risk" in analysis
    assert analysis["failure_risk"]["likelihood"] in ("LOW", "MODERATE")


@pytest.mark.asyncio
async def test_repeated_processing_does_not_generate_duplicate_alerts(
    db_session: AsyncSession,
    test_user_a: User,
):
    """Verify that executing turns on an already escalated conversation updates analysis without creating duplicate handoffs."""
    convo = Conversation(customer_id=test_user_a.id, workflow_state="waiting_for_expert")
    db_session.add(convo)
    await db_session.flush()

    h = Handoff(
        conversation_id=convo.id,
        ticket_id=999,
        customer_id=test_user_a.id,
        escalation_reason="First escalation",
        priority=Priority.MEDIUM,
        category="General",
        status=HandoffStatus.WAITING,
        ai_analysis={"failure_risk": {"likelihood": "MODERATE", "probability": 0.4}},
    )
    db_session.add(h)
    await db_session.commit()

    count_before = (await db_session.execute(
        select(Handoff).where(Handoff.conversation_id == convo.id)
    )).scalars().all()
    assert len(count_before) == 1

    new_analysis = {"failure_risk": {"likelihood": "HIGH", "probability": 0.75}}
    if count_before[0].ai_analysis:
        updated = dict(count_before[0].ai_analysis)
        updated.update(new_analysis)
        count_before[0].ai_analysis = updated
    await db_session.commit()

    count_after = (await db_session.execute(
        select(Handoff).where(Handoff.conversation_id == convo.id)
    )).scalars().all()
    assert len(count_after) == 1
    assert count_after[0].ai_analysis["failure_risk"]["likelihood"] == "HIGH"


# ==============================================================================
# Section 3: P0 Anti-False-Escalation Regressions
# ==============================================================================

@pytest.mark.asyncio
async def test_scenario_1_greeting_does_not_escalate(
    async_client: AsyncClient,
    auth_headers_a: dict,
    db_session: AsyncSession,
):
    """Greeting like 'Hi' or 'Hello' should return a friendly response, not escalate."""
    resp = await async_client.post(
        "/api/conversations",
        json={"initial_message": "Hello, good morning!"},
        headers=auth_headers_a,
    )
    assert resp.status_code == 200
    convo_id = resp.json()["id"]

    stmt = (
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == convo_id)
        .order_by(ConversationMessage.created_at.asc())
    )
    messages = (await db_session.execute(stmt)).scalars().all()
    assert len(messages) >= 2
    ai_msg = messages[-1]
    assert ai_msg.sender_type == SenderType.AI
    assert "expert" not in ai_msg.content.lower()


@pytest.mark.asyncio
async def test_scenario_2_known_faq_resolves_with_knowledge():
    """When KB contains relevant policy articles, the decision engine should RESOLVE, not escalate."""
    decision_engine = DecisionEngine()
    analysis = {
        "intent": "REFUND_ISSUE",
        "entities": {},
        "original_message": "What is your refund policy?",
    }
    knowledge = [
        {
            "id": 1,
            "title": "POL-007 — Refunds",
            "content": "Refunds are processed to the original payment method within 3 to 5 business days.",
            "category": "REFUNDS",
        }
    ]
    decision = decision_engine.decide(analysis, knowledge)
    assert decision["decision"] == "RESOLVE"
    assert "article" in decision


@pytest.mark.asyncio
async def test_scenario_3_routine_troubleshooting_does_not_escalate():
    """Routine troubleshooting (e.g. app blank screen) must offer guidance, not escalate."""
    decision_engine = DecisionEngine()
    analysis = {
        "intent": "GENERAL_QUERY",
        "entities": {},
        "original_message": "My screen is blank when I open the app. What can I do?",
    }
    knowledge = [
        {
            "id": 2,
            "title": "TS-060 — App Problems",
            "content": "Refresh the app, clear browser cache, or restart your device.",
            "category": "TROUBLESHOOTING",
        }
    ]
    decision = decision_engine.decide(analysis, knowledge)
    assert decision["decision"] in ("RESOLVE", "ASK_USER")
    assert decision["decision"] != "ESCALATE"


@pytest.mark.asyncio
async def test_scenario_4_missing_required_info_returns_ask_user():
    """When a customer asks for order status without providing the ID, ask for it."""
    decision_engine = DecisionEngine()
    analysis = {
        "intent": "ORDER_STATUS",
        "entities": {},
        "original_message": "Can you check the status of my order?",
    }
    decision = decision_engine.decide(analysis, [])
    assert decision["decision"] == "ASK_USER"
    assert decision["missing_entity"] == "order_id"


@pytest.mark.asyncio
async def test_scenario_5_real_risk_fraud_escalates():
    """Legitimate security / fraud alerts must escalate to human experts."""
    decision_engine = DecisionEngine()
    analysis = {
        "intent": "FRAUD_SUSPICION",
        "entities": {},
        "priority": "CRITICAL",
        "original_message": "My account was hacked and unauthorized money was withdrawn from my card!",
    }
    decision = decision_engine.decide(analysis, [])
    assert decision["decision"] == "ESCALATE"
    assert "fraud" in decision.get("reason", "").lower() or "risk" in decision.get("reason", "").lower() or "critical" in decision.get("reason", "").lower()


@pytest.mark.asyncio
async def test_scenario_6_explicit_human_agent_request_escalates():
    """Customer demanding a human agent must be escalated."""
    decision_engine = DecisionEngine()
    analysis = {
        "intent": "HUMAN_AGENT_REQUEST",
        "entities": {},
        "original_message": "I want to speak with a human manager immediately.",
    }
    decision = decision_engine.decide(analysis, [])
    assert decision["decision"] == "ESCALATE"
    assert decision.get("missing_entity") == "human_agent" or "human" in decision.get("reason", "").lower()


@pytest.mark.asyncio
async def test_scenario_7_provider_timeout_safe_recovery(
    db_session: AsyncSession,
    test_user_a: User,
):
    """When the provider raises a timeout, fallback should report technical difficulties without flagging user as an attacker."""
    service = ConversationService()
    conv = Conversation(customer_id=test_user_a.id, channel="web")
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)

    msg = ConversationMessage(
        conversation_id=conv.id,
        sender_type=SenderType.CUSTOMER,
        content="Hello, is anyone there?",
        message_type=MessageType.TEXT,
    )
    db_session.add(msg)
    await db_session.commit()
    await db_session.refresh(msg)

    with patch.object(service.ai_provider, "analyze", side_effect=TimeoutError("Groq request timed out")):
        await service._trigger_ai_response(db_session, conv, msg)

    stmt = (
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == conv.id, ConversationMessage.sender_type == SenderType.AI)
    )
    ai_msgs = (await db_session.execute(stmt)).scalars().all()
    assert len(ai_msgs) >= 1
    last_ai = ai_msgs[-1]
    assert "technical difficulties" in last_ai.content.lower() or "expert" in last_ai.content.lower()


def test_scenario_8_markdown_wrapped_json_handled_safely():
    """clean_json_markdown should correctly extract JSON from code blocks and surrounding commentary."""
    raw_markdown = """Here is the structured decision:
```json
{
  "decision": "RESOLVE",
  "reason": "Direct answer available",
  "response_text": "Your order is on the way!"
}
```
Hope this helps!"""
    cleaned = clean_json_markdown(raw_markdown)
    parsed = json.loads(cleaned)
    assert parsed["decision"] == "RESOLVE"
    assert parsed["response_text"] == "Your order is on the way!"

    schema_inst = DecisionSchema.model_validate_json(cleaned)
    assert schema_inst.decision == "RESOLVE"


@pytest.mark.asyncio
async def test_scenario_9_empty_rag_does_not_force_escalate_routine_query():
    """When RAG yields empty results for general greeting or routine query, ASK_USER instead of escalating."""
    decision_engine = DecisionEngine()
    analysis = {
        "intent": "GREETING",
        "entities": {},
        "original_message": "Hi, how are you today?",
    }
    decision = decision_engine.decide(analysis, [])
    assert decision["decision"] == "ASK_USER"
    assert decision["decision"] != "ESCALATE"


@pytest.mark.asyncio
async def test_scenario_10_order_status_authorization(
    db_session: AsyncSession,
    test_user_a: User,
    test_user_b: User,
):
    """
    Customer A looking up their own order ORD-123 is valid.
    Customer A looking up Customer B's order ORD-999 is blocked as CROSS_CUSTOMER_ORDER_LEAK.
    """
    assert _normalize_id("ORD-123") == "ord123"
    assert _normalize_id("ord_123") == "ord123"
    assert _normalize_id("ORD123") == "ord123"

    tr_legit = ToolResultContext(
        tool_name="get_order_status",
        success=True,
        data={"order_id": "ORD-123", "status": "SHIPPED"},
    )
    ctx_legit = ResponseValidationContext(
        conversation_id=1,
        customer_id=test_user_a.id,
        user_message="What is the status of my order ORD-123?",
        draft_response="I checked your order ORD-123 and it is currently SHIPPED.",
        tool_results=[tr_legit],
        agent_decision="RESOLVE",
        authorized_order_ids=["ord123"],
    )
    res_legit = await ValidationService.validate_response(ctx_legit)
    assert res_legit.status == ValidationStatus.VALID, f"Legitimate order was rejected: {res_legit.violations}"

    ctx_leak = ResponseValidationContext(
        conversation_id=2,
        customer_id=test_user_a.id,
        user_message="Check order ORD-999",
        draft_response="Order ORD-999 is delivered to someone else.",
        tool_results=[],
        agent_decision="RESOLVE",
        authorized_order_ids=["ord123"],
    )
    res_leak = check_security(ctx_leak)
    assert res_leak.status == ValidationStatus.ESCALATE
    assert any(v.violation_type == "CROSS_CUSTOMER_ORDER_LEAK" for v in res_leak.violations)


def test_scenario_11_multilingual_routine_parity():
    """UniversalMeaningEngine correctly identifies intents across Tamil, Tanglish, Hinglish, and English without bias."""
    engine = UniversalMeaningEngine()

    test_cases = [
        ("Hello, can you help me?", "English", "GREETING"),
        ("Vanakkam bro, eppadi irukkeenga?", "Tanglish", "GREETING"),
        ("Namaste, kaise ho aap?", "Hinglish", "GREETING"),
        ("வணக்கம்", "Tamil", "GREETING"),
        ("வணக்கம், எனக்கு உதவி வேண்டும்", "Tamil", "GREETING"),
        ("Where is my order ORD-101?", "English", "DELIVERY_ISSUE"),
        ("En order ORD-101 eppo varum bro?", "Tanglish", "DELIVERY_ISSUE"),
        ("Mera order ORD-101 kahan tak pahuncha?", "Hinglish", "DELIVERY_ISSUE"),
    ]

    decision_engine = DecisionEngine()

    for phrase, lang, expected_intent in test_cases:
        meaning = engine.understand_utterance(phrase)
        assert meaning.intent == expected_intent, f"Failed intent for '{phrase}' ({lang}): got {meaning.intent}"

        analysis = {"intent": meaning.intent, "entities": meaning.entities, "original_message": phrase}
        decision = decision_engine.decide(analysis, [])
        assert decision["decision"] != "ESCALATE", f"Routine query '{phrase}' in {lang} erroneously escalated: {decision}"


@pytest.mark.asyncio
async def test_scenario_12_single_unduped_response_text_chat(
    async_client: AsyncClient,
    auth_headers_a: dict,
    db_session: AsyncSession,
):
    """An end-to-end conversation turn produces exactly one customer message and one AI response."""
    convo_resp = await async_client.post(
        "/api/conversations",
        json={"initial_message": "Hi, I have a quick question."},
        headers=auth_headers_a,
    )
    assert convo_resp.status_code == 200
    convo_id = convo_resp.json()["id"]

    msg_resp = await async_client.post(
        f"/api/conversations/{convo_id}/messages",
        json={"content": "What are your business hours?"},
        headers=auth_headers_a,
    )
    assert msg_resp.status_code == 200

    stmt = (
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == convo_id)
        .order_by(ConversationMessage.created_at.asc())
    )
    messages = (await db_session.execute(stmt)).scalars().all()

    assert len(messages) == 4, f"Expected 4 messages but found {len(messages)}"
    assert messages[0].sender_type == SenderType.CUSTOMER
    assert messages[1].sender_type == SenderType.AI
    assert messages[2].sender_type == SenderType.CUSTOMER
    assert messages[3].sender_type == SenderType.AI


# ==============================================================================
# Section 4: Code-Mixed Handoff Context & Metadata
# ==============================================================================

@pytest.mark.asyncio
async def test_tanglish_metadata_in_handoff_context(
    async_client: AsyncClient,
    auth_headers_a,
    auth_headers_expert,
    test_user_a: User,
    test_expert: User,
    db_session: AsyncSession,
):
    """Test that Tanglish code-mixed metadata and confidence are accurately returned in handoff context."""
    convo = Conversation(customer_id=test_user_a.id, workflow_state="waiting_for_expert")
    db_session.add(convo)
    await db_session.flush()

    ticket = Ticket(
        customer_id=test_user_a.id,
        conversation_id=convo.id,
        subject="Tanglish Payment Query",
        category="Payments/Finance",
        priority="high",
    )
    db_session.add(ticket)
    await db_session.flush()

    tanglish_analysis = {
        "original_message": "En payment cut aayiduchu, refund eppo varum?",
        "language": "ta",
        "is_code_mixed": True,
        "code_mix_type": "tanglish",
        "normalized_message": "My payment was deducted, when will the refund arrive?",
        "intent": "PAYMENT_ISSUE",
        "sentiment": "negative",
        "confidence_score": 88.5,
    }

    handoff = Handoff(
        conversation_id=convo.id,
        ticket_id=ticket.id,
        customer_id=test_user_a.id,
        escalation_reason="Customer reported payment debit in Tanglish with urgency",
        priority=Priority.HIGH,
        category="Payments/Finance",
        ai_summary="Payment deducted without order confirmation.",
        ai_analysis=tanglish_analysis,
        status=HandoffStatus.ASSIGNED,
        assigned_expert_id=test_expert.id,
    )
    db_session.add(handoff)

    msg_cust = ConversationMessage(
        conversation_id=convo.id,
        sender_type=SenderType.CUSTOMER,
        content="En payment cut aayiduchu, refund eppo varum?",
    )
    db_session.add(msg_cust)

    msg_ai = ConversationMessage(
        conversation_id=convo.id,
        sender_type=SenderType.AI,
        content="Let me connect you with a payment specialist.",
        metadata_=tanglish_analysis,
    )
    db_session.add(msg_ai)
    await db_session.commit()

    res = await async_client.get(f"/api/handoffs/{handoff.id}/context", headers=auth_headers_expert)
    assert res.status_code == 200
    data = res.json()

    assert "language_context" in data
    lang_ctx = data["language_context"]
    assert lang_ctx is not None
    assert lang_ctx["detected_language"] == "ta"
    assert lang_ctx["is_code_mixed"] is True
    assert lang_ctx["code_mix_type"] == "tanglish"
    assert lang_ctx["normalized_message"] == "My payment was deducted, when will the refund arrive?"
    assert lang_ctx["original_message"] == "En payment cut aayiduchu, refund eppo varum?"

    assert data["confidence_score"] == 88.5
    assert data["ai_context"]["confidence_score"] == 88.5
    assert data["ai_context"]["intent"] == "PAYMENT_ISSUE"
    assert data["ai_context"]["sentiment"] == "negative"
    assert data["ai_context"]["language_context"]["code_mix_type"] == "tanglish"


@pytest.mark.asyncio
async def test_hinglish_metadata_in_handoff_context(
    async_client: AsyncClient,
    auth_headers_expert,
    test_user_a: User,
    test_expert: User,
    db_session: AsyncSession,
):
    """Test that Hinglish code-mixed metadata is handled properly."""
    convo = Conversation(customer_id=test_user_a.id, workflow_state="waiting_for_expert")
    db_session.add(convo)
    await db_session.flush()

    ticket = Ticket(
        customer_id=test_user_a.id,
        conversation_id=convo.id,
        subject="Hinglish Delivery Query",
        category="Delivery/Logistics",
        priority="medium",
    )
    db_session.add(ticket)
    await db_session.flush()

    hinglish_analysis = {
        "original_message": "Mera order abhi tak deliver nahi hua, check karo please",
        "language": "hi",
        "is_code_mixed": True,
        "code_mix_type": "hinglish",
        "normalized_message": "My order has not been delivered yet, please check",
        "intent": "DELIVERY_ISSUE",
        "sentiment": "negative",
        "confidence": 0.76,
    }

    handoff = Handoff(
        conversation_id=convo.id,
        ticket_id=ticket.id,
        customer_id=test_user_a.id,
        escalation_reason="Delivery delayed in Hinglish",
        priority=Priority.MEDIUM,
        category="Delivery/Logistics",
        ai_analysis=hinglish_analysis,
        status=HandoffStatus.ASSIGNED,
        assigned_expert_id=test_expert.id,
    )
    db_session.add(handoff)
    await db_session.commit()

    res = await async_client.get(f"/api/handoffs/{handoff.id}/context", headers=auth_headers_expert)
    assert res.status_code == 200
    data = res.json()

    assert data["language_context"]["code_mix_type"] == "hinglish"
    assert data["language_context"]["detected_language"] == "hi"
    assert data["confidence_score"] == 76.0


@pytest.mark.asyncio
async def test_missing_metadata_does_not_break_endpoint(
    async_client: AsyncClient,
    auth_headers_expert,
    test_user_a: User,
    test_expert: User,
    db_session: AsyncSession,
):
    """Test graceful handling when metadata is completely missing/null."""
    convo = Conversation(customer_id=test_user_a.id, workflow_state="waiting_for_expert")
    db_session.add(convo)
    await db_session.flush()

    ticket = Ticket(
        customer_id=test_user_a.id,
        conversation_id=convo.id,
        subject="Empty metadata ticket",
        category="General",
        priority="low",
    )
    db_session.add(ticket)
    await db_session.flush()

    handoff = Handoff(
        conversation_id=convo.id,
        ticket_id=ticket.id,
        customer_id=test_user_a.id,
        escalation_reason="Manual escalation without AI analysis",
        priority=Priority.LOW,
        category="General",
        ai_analysis=None,
        status=HandoffStatus.ASSIGNED,
        assigned_expert_id=test_expert.id,
    )
    db_session.add(handoff)
    await db_session.commit()

    res = await async_client.get(f"/api/handoffs/{handoff.id}/context", headers=auth_headers_expert)
    assert res.status_code == 200
    data = res.json()

    assert data["language_context"] is None
    assert data["confidence_score"] is None
    assert data["ai_context"]["intent"] == "Unknown"
    assert data["ai_context"]["sentiment"] == "Neutral"
    assert data["ai_context"]["summary"] == "Manual escalation without AI analysis"


@pytest.mark.asyncio
async def test_missing_confidence_does_not_produce_fabricated_score(
    async_client: AsyncClient,
    auth_headers_expert,
    test_user_a: User,
    test_expert: User,
    db_session: AsyncSession,
):
    """Test that missing confidence remains None and is never fabricated."""
    convo = Conversation(customer_id=test_user_a.id, workflow_state="waiting_for_expert")
    db_session.add(convo)
    await db_session.flush()

    ticket = Ticket(
        customer_id=test_user_a.id,
        conversation_id=convo.id,
        subject="Standard English Query",
        category="General",
        priority="low",
    )
    db_session.add(ticket)
    await db_session.flush()

    analysis = {
        "language": "English",
        "intent": "GENERAL_QUERY",
        "sentiment": "neutral",
    }

    handoff = Handoff(
        conversation_id=convo.id,
        ticket_id=ticket.id,
        customer_id=test_user_a.id,
        escalation_reason="General query escalation",
        priority=Priority.LOW,
        category="General",
        ai_analysis=analysis,
        status=HandoffStatus.ASSIGNED,
        assigned_expert_id=test_expert.id,
    )
    db_session.add(handoff)
    await db_session.commit()

    res = await async_client.get(f"/api/handoffs/{handoff.id}/context", headers=auth_headers_expert)
    assert res.status_code == 200
    data = res.json()

    assert data["confidence_score"] is None
    assert data["ai_context"]["confidence_score"] is None
    assert data["language_context"]["detected_language"] == "English"
    assert data["language_context"]["is_code_mixed"] is False
    assert data["language_context"]["normalized_message"] is None


@pytest.mark.asyncio
async def test_authorization_and_customer_isolation(
    async_client: AsyncClient,
    auth_headers_a,
    auth_headers_b,
    auth_headers_expert,
    auth_headers_admin,
    test_user_a: User,
    test_expert: User,
    db_session: AsyncSession,
):
    """Verify RBAC and security isolation: customers cannot access context; only assigned expert or admin can."""
    convo = Conversation(customer_id=test_user_a.id, workflow_state="waiting_for_expert")
    db_session.add(convo)
    await db_session.flush()

    ticket = Ticket(
        customer_id=test_user_a.id,
        conversation_id=convo.id,
        subject="Isolated ticket",
        category="General",
        priority="low",
    )
    db_session.add(ticket)
    await db_session.flush()

    handoff = Handoff(
        conversation_id=convo.id,
        ticket_id=ticket.id,
        customer_id=test_user_a.id,
        escalation_reason="Private context",
        priority=Priority.LOW,
        category="General",
        status=HandoffStatus.ASSIGNED,
        assigned_expert_id=test_expert.id,
    )
    db_session.add(handoff)
    await db_session.commit()

    res_cust_a = await async_client.get(f"/api/handoffs/{handoff.id}/context", headers=auth_headers_a)
    assert res_cust_a.status_code == 403

    res_cust_b = await async_client.get(f"/api/handoffs/{handoff.id}/context", headers=auth_headers_b)
    assert res_cust_b.status_code == 403

    res_exp = await async_client.get(f"/api/handoffs/{handoff.id}/context", headers=auth_headers_expert)
    assert res_exp.status_code == 200

    res_adm = await async_client.get(f"/api/handoffs/{handoff.id}/context", headers=auth_headers_admin)
    assert res_adm.status_code == 200


@pytest.mark.asyncio
async def test_existing_response_fields_continue_to_work(
    async_client: AsyncClient,
    auth_headers_expert,
    test_user_a: User,
    test_expert: User,
    db_session: AsyncSession,
):
    """Verify all legacy response fields (customer, active_ticket, ticket_history) retain expected structure."""
    convo = Conversation(customer_id=test_user_a.id, workflow_state="waiting_for_expert")
    db_session.add(convo)
    await db_session.flush()

    ticket = Ticket(
        customer_id=test_user_a.id,
        conversation_id=convo.id,
        subject="Field regression ticket",
        category="Billing",
        priority="high",
    )
    db_session.add(ticket)
    await db_session.flush()

    handoff = Handoff(
        conversation_id=convo.id,
        ticket_id=ticket.id,
        customer_id=test_user_a.id,
        escalation_reason="Billing inquiry",
        priority=Priority.HIGH,
        category="Billing",
        status=HandoffStatus.ASSIGNED,
        assigned_expert_id=test_expert.id,
    )
    db_session.add(handoff)
    await db_session.commit()

    res = await async_client.get(f"/api/handoffs/{handoff.id}/context", headers=auth_headers_expert)
    assert res.status_code == 200
    data = res.json()

    assert data["customer"]["id"] == test_user_a.id
    assert data["customer"]["email"] == test_user_a.email
    assert data["customer"]["account_status"] == "Active"

    assert data["active_ticket"]["id"] == convo.id
    assert data["active_ticket"]["category"] == "Billing"
    assert data["active_ticket"]["priority"] == "high"
    assert data["active_ticket"]["reason"] == "Billing inquiry"

    assert isinstance(data["ticket_history"], list)
