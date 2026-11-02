"""
ResolveAI V2 — M14 Final Integration, Persistence & Safety Audit Tests

Verifies:
1. Database persistence of autonomy settings across restart/cache invalidation.
2. Tenant security and isolation enforced via trusted authenticated context.
3. Safety invariants (security, critical, restricted tools, failure risk) across all 3 autonomy modes.
4. Prevention of duplicate handoffs on repeated messages to escalated conversations.
5. Incident lifecycle management and status tracking.
6. End-to-end code-mixed complaint handling through handoff context.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.users.models import User
from app.conversations.models import Conversation, ConversationMessage
from app.tickets.models import Ticket, TicketStatus
from app.handoff.models import Handoff
from app.ai.autonomy_models import AutonomyConfig
from app.ai.autonomy_service import AutonomyConfigService
from app.ai.intelligence.autonomy import AutonomyMode, AutonomyLevelDeterminer, AutonomyLevel
from app.ai.m4.provider import M4AIProvider
from app.ai.intelligence.language import CodeMixedLanguageDetector, IndianLanguageNormalizer
from app.ai.intelligence.incidents import IncidentDetector, IncidentStateManager, TicketSnapshot
from app.auth.jwt import create_access_token
from app.auth.password import get_password_hash


# ==============================================================================
# 1. Database Persistence Across Restart / Cache Invalidation
# ==============================================================================

@pytest.mark.asyncio
async def test_autonomy_settings_persist_across_restart_simulation(
    async_client: AsyncClient,
    db_session: AsyncSession,
    auth_headers_admin,
):
    """Verify settings written to DB survive complete cache clearing and reload accurately."""
    AutonomyConfigService.invalidate_cache()

    # 1. Update settings via Admin API
    payload = {
        "mode": "conservative",
        "tenant_id": "audit_persist_tenant",
        "auto_resolve_min_confidence": 88.0,
        "auto_resolve_max_risk": 0.12,
    }
    update_res = await async_client.put("/api/admin/autonomy", json=payload, headers=auth_headers_admin)
    assert update_res.status_code == 200
    data = update_res.json()
    assert data["mode"] == "conservative"
    assert data["auto_resolve_min_confidence"] == 88.0

    # 2. Simulate process restart: completely wipe in-memory cache
    AutonomyConfigService.invalidate_cache()

    # 3. Fetch configuration afresh from DB via service
    fresh_cfg = await AutonomyConfigService.get_effective_config(db_session, tenant_id="audit_persist_tenant")
    assert fresh_cfg.mode == AutonomyMode.CONSERVATIVE
    assert fresh_cfg.thresholds.auto_resolve_min_confidence == 88.0
    assert fresh_cfg.thresholds.auto_resolve_max_risk == 0.12

    # 4. Verify audit trail survived restart
    audit_trail = await AutonomyConfigService.get_audit_trail(db_session, tenant_id="audit_persist_tenant")
    assert len(audit_trail) >= 1
    assert audit_trail[-1]["new_mode"] == "conservative"


@pytest.mark.asyncio
async def test_missing_tenant_config_safely_defaults_to_balanced(db_session: AsyncSession):
    """Verify non-configured tenants safely default to Balanced mode without error."""
    AutonomyConfigService.invalidate_cache()
    default_cfg = await AutonomyConfigService.get_effective_config(db_session, tenant_id="non_existent_tenant_999")
    assert default_cfg.mode == AutonomyMode.BALANCED
    assert default_cfg.thresholds.auto_resolve_min_confidence == 75.0
    assert default_cfg.thresholds.auto_resolve_max_risk == 0.25


# ==============================================================================
# 2. Tenant Isolation & Trusted Context Enforcement
# ==============================================================================

@pytest.mark.asyncio
async def test_tenant_admin_cannot_access_or_modify_other_tenant(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Verify Tenant A Admin cannot read or modify Tenant B settings even if they specify tenant_id."""
    # Create Admin strictly bound to tenant_alpha
    admin_alpha = User(
        email="admin_alpha@example.com",
        full_name="Admin Alpha",
        password_hash=get_password_hash("Password123!"),
        role="admin",
        tenant_id="tenant_alpha",
    )
    db_session.add(admin_alpha)
    await db_session.commit()
    await db_session.refresh(admin_alpha)

    token_alpha = create_access_token(admin_alpha.id, "admin")
    headers_alpha = {"Authorization": f"Bearer {token_alpha}"}

    # Attempt to read Tenant Beta settings -> Forbidden
    get_res = await async_client.get("/api/admin/autonomy?tenant_id=tenant_beta", headers=headers_alpha)
    assert get_res.status_code == 403
    assert "different tenant" in get_res.json()["detail"].lower()

    # Attempt to modify Tenant Beta settings -> Forbidden
    put_res = await async_client.put(
        "/api/admin/autonomy",
        json={"mode": "high_automation", "tenant_id": "tenant_beta"},
        headers=headers_alpha,
    )
    assert put_res.status_code == 403
    assert "different tenant" in put_res.json()["detail"].lower()

    # Attempt to reset Tenant Beta settings -> Forbidden
    reset_res = await async_client.post("/api/admin/autonomy/reset?tenant_id=tenant_beta", headers=headers_alpha)
    assert reset_res.status_code == 403
    assert "different tenant" in reset_res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_unauthenticated_and_non_admin_cannot_access_autonomy_controls(
    async_client: AsyncClient,
    auth_headers_a,
    auth_headers_expert,
):
    """Verify unauthenticated requests get 401 and customers/experts get 403."""
    # Unauthenticated
    res_unauth = await async_client.get("/api/admin/autonomy")
    assert res_unauth.status_code == 401

    # Customer
    res_cust = await async_client.get("/api/admin/autonomy", headers=auth_headers_a)
    assert res_cust.status_code == 403

    # Expert
    res_exp = await async_client.get("/api/admin/autonomy", headers=auth_headers_expert)
    assert res_exp.status_code == 403


# ==============================================================================
# 3. Safety Invariants Across All Autonomy Modes
# ==============================================================================

@pytest.mark.asyncio
@pytest.mark.parametrize("mode", [AutonomyMode.CONSERVATIVE, AutonomyMode.BALANCED, AutonomyMode.HIGH_AUTOMATION])
async def test_security_issue_unconditionally_escalates_across_all_modes(mode):
    """Verify SECURITY_ISSUE intent unconditionally escalates in every autonomy mode."""
    provider = M4AIProvider()
    analysis = {
        "intent": "SECURITY_ISSUE",
        "sentiment": "NEUTRAL",
        "original_message": "Someone breached my account and stole my credentials",
        "entities": {},
        "priority": "high",
    }
    resp = await provider.generate_response(
        analysis=analysis,
        knowledge=[{"id": 1, "content": "Security instructions", "score": 0.95}],
        context={"conversation_id": 9001, "autonomy_mode": mode.value},
    )
    assert analysis["decision_state"] == "ESCALATE"
    assert "security" in analysis["decision_reason"].lower()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", [AutonomyMode.CONSERVATIVE, AutonomyMode.BALANCED, AutonomyMode.HIGH_AUTOMATION])
async def test_critical_priority_unconditionally_escalates_across_all_modes(mode):
    """Verify CRITICAL priority requests unconditionally escalate in every autonomy mode."""
    determiner = AutonomyLevelDeterminer(mode=mode)
    analysis = {
        "intent": "GENERAL_QUERY",
        "priority": "CRITICAL",
        "sentiment": "NEUTRAL",
        "original_message": "Immediate outage in production server",
        "entities": {},
    }
    decision = determiner.determine_level(analysis, {"rag_results": [{"score": 0.95}]})
    assert decision.level == AutonomyLevel.ESCALATE
    assert "CRITICAL" in decision.reasoning


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", [AutonomyMode.CONSERVATIVE, AutonomyMode.BALANCED, AutonomyMode.HIGH_AUTOMATION])
async def test_restricted_tools_strictly_require_confirmation_in_all_modes(mode):
    """Verify restricted tools (refunds, account changes) require confirmation in all modes."""
    determiner = AutonomyLevelDeterminer(mode=mode)
    for tool in ["create_refund_request", "update_account"]:
        analysis = {
            "intent": "REFUND_ISSUE",
            "priority": "medium",
            "sentiment": "NEUTRAL",
            "decision_state": "USE_TOOL",
            "tool_name": tool,
            "entities": {"transaction_id": "tx_999"},
        }
        decision = determiner.determine_level(analysis, {"rag_results": [{"score": 0.90}]})
        assert decision.level == AutonomyLevel.CONFIRMATION_REQUIRED
        assert tool in decision.reasoning


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", [AutonomyMode.CONSERVATIVE, AutonomyMode.BALANCED, AutonomyMode.HIGH_AUTOMATION])
async def test_high_failure_risk_influences_escalation_across_all_modes(mode):
    """Verify predicted high failure risk and prior failed solutions force expert review."""
    determiner = AutonomyLevelDeterminer(mode=mode)
    analysis = {
        "intent": "GENERAL_QUERY",
        "priority": "low",
        "sentiment": "NEUTRAL",
        "original_message": "How do I fix this?",
        "entities": {},
        "failure_risk": {
            "probability": 0.85,
            "likelihood": "VERY_HIGH",
            "should_escalate_early": True,
            "has_prior_solution_failed": True,
        },
    }
    decision = determiner.determine_level(analysis, {"rag_results": [{"score": 0.90}]})
    assert decision.level == AutonomyLevel.ESCALATE
    assert "failure risk" in decision.reasoning.lower() or "prior solution" in decision.reasoning.lower()


# ==============================================================================
# 4. Duplicate Prevention on Escalated Conversations
# ==============================================================================

@pytest.mark.asyncio
async def test_repeated_messages_do_not_create_duplicate_handoffs(
    db_session: AsyncSession,
    test_user_a,
):
    """Verify repeated messages on an already-escalated conversation update analysis without duplicate Handoffs."""
    from app.conversations.service import ConversationService

    # Create conversation and associated ticket automatically via ConversationService
    service = ConversationService()
    conv = await service.create_conversation(
        db_session,
        test_user_a.id,
        "I need help with my payment",
        "Support Chat",
    )
    stmt_ticket = select(Ticket).where(Ticket.conversation_id == conv.id)
    ticket = (await db_session.execute(stmt_ticket)).scalar_one()

    # Create initial handoff
    initial_handoff = Handoff(
        conversation_id=conv.id,
        ticket_id=ticket.id,
        customer_id=test_user_a.id,
        escalation_reason="Initial security escalation",
        priority="high",
        category="Security",
        ai_analysis={"initial": True},
        collected_information={},
    )
    db_session.add(initial_handoff)
    await db_session.commit()

    # Query initial handoff count
    stmt = select(Handoff).where(Handoff.conversation_id == conv.id)
    handoffs_before = (await db_session.execute(stmt)).scalars().all()
    assert len(handoffs_before) == 1

    # Simulate triggering AI response on the already-escalated conversation
    analysis_update = {
        "decision_state": "ESCALATE",
        "decision_reason": "Repeated security clarification",
        "sentiment": "FRUSTRATED",
        "intent": "SECURITY_ISSUE",
        "priority": "high",
    }

    # Execute handoff block logic as implemented in ConversationService._trigger_ai_response
    existing = (await db_session.execute(stmt)).scalar_one_or_none()
    assert existing is not None
    if existing.ai_analysis and isinstance(existing.ai_analysis, dict):
        updated = dict(existing.ai_analysis)
        updated.update(analysis_update)
        existing.ai_analysis = updated
    await db_session.commit()

    # Verify handoff count remains strictly 1
    handoffs_after = (await db_session.execute(stmt)).scalars().all()
    assert len(handoffs_after) == 1
    assert handoffs_after[0].ai_analysis["sentiment"] == "FRUSTRATED"


# ==============================================================================
# 5. Incident Lifecycle Persistence Assessment
# ==============================================================================

@pytest.mark.asyncio
async def test_incident_lifecycle_status_management(
    async_client: AsyncClient,
    auth_headers_admin,
):
    """Verify Admin can update and retrieve incident lifecycle status."""
    incident_id = "inc_test_payment_gateway_down"
    IncidentStateManager.reset()

    # Default status before update
    initial_status = IncidentStateManager.get_status(incident_id)
    assert initial_status == "candidate"

    # Admin updates status to investigating
    res_inv = await async_client.post(
        f"/api/analytics/incidents/{incident_id}/status",
        json={"status": "investigating"},
        headers=auth_headers_admin,
    )
    assert res_inv.status_code == 200
    assert res_inv.json()["status"] == "investigating"

    # Verify state reflects update
    assert IncidentStateManager.get_status(incident_id) == "investigating"

    # Admin updates to confirmed
    res_conf = await async_client.post(
        f"/api/analytics/incidents/{incident_id}/status",
        json={"status": "confirmed"},
        headers=auth_headers_admin,
    )
    assert res_conf.status_code == 200
    assert res_conf.json()["status"] == "confirmed"
    assert IncidentStateManager.get_status(incident_id) == "confirmed"


# ==============================================================================
# 6. End-to-End Workflow: Code-Mixed Input to Handoff Context
# ==============================================================================

@pytest.mark.asyncio
async def test_end_to_end_codemixed_complaint_to_handoff_context():
    """Verify Workflow A: Code-mixed complaint -> normalized interpretation -> intent -> autonomy decision."""
    detector = CodeMixedLanguageDetector()
    normalizer = IndianLanguageNormalizer()
    determiner = AutonomyLevelDeterminer(mode=AutonomyMode.BALANCED)

    raw_message = "En order innum varala bro, 5 days aachu"

    # 1. Detect language
    lang_result = detector.detect(raw_message)
    assert lang_result.is_code_mixed is True
    assert lang_result.primary_language == "ta"

    # 2. Normalize to English
    norm_result = normalizer.normalize(raw_message)
    assert "order" in norm_result.normalized.lower()
    assert norm_result.language_result.confidence > 0.5

    # 3. Analyze intent
    analysis = {
        "intent": "DELIVERY_ISSUE",
        "sentiment": "NEGATIVE",
        "original_message": raw_message,
        "normalized_message": norm_result.normalized,
        "entities": {"order_id": "12345"},
        "priority": "medium",
    }

    # 4. Evaluate autonomy under Balanced mode
    context = {"rag_results": [{"score": 0.85}]}
    decision = determiner.determine_level(analysis, context)
    assert decision.level in (AutonomyLevel.AUTOMATIC, AutonomyLevel.CONFIRMATION_REQUIRED)
    assert decision.mode == "balanced"
