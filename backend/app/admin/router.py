"""
ResolveAIV2 — Admin API Router

Exposes endpoints for administrator controls, including Dynamic Autonomy Settings.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.deps import get_current_user
from app.users.models import User
from app.shared.models import UserRole
from app.ai.autonomy_service import AutonomyConfigService
from app.ai.intelligence.autonomy import THRESHOLD_BOUNDS, AutonomyMode
from app.admin.schemas import (
    AutonomyUpdateRequest,
    AutonomyConfigResponse,
    ModeDescription,
)

router = APIRouter(prefix="/api/admin", tags=["Admin"])

MODES_INFO = [
    ModeDescription(
        mode="conservative",
        title="Conservative",
        description="Requires higher confidence (85%+) and lower risk tolerance (0.15). Prefers clarification or early expert review when uncertainty is elevated.",
        safety_summary="Strict safeguards. Clarifies early, escalates after 2 unsuccessful attempts.",
    ),
    ModeDescription(
        mode="balanced",
        title="Balanced (Default)",
        description="Standard production policy (75% confidence). Proven balance between autonomous resolution and expert safety handoffs.",
        safety_summary="Baseline production policy. Auto-resolves grounded, high-confidence queries.",
    ),
    ModeDescription(
        mode="high_automation",
        title="High Automation",
        description="Permits more autonomous handling of eligible low-risk requests with relaxed confidence (65%+).",
        safety_summary="Higher throughput on routine inquiries. Preserves mandatory safety rules for security and restricted actions.",
    ),
]

SAFETY_INVARIANTS = [
    "Security-sensitive (SECURITY_ISSUE) and CRITICAL priority requests unconditionally escalate.",
    "Restricted tool actions (refunds, account changes) strictly require human confirmation.",
    "Observed tool failures and customer-reported solution failures force escalation.",
    "Low confidence (< 40%) will never silently authorize risky actions.",
    "Admin autonomy controls cannot override customer isolation or role permissions.",
]


@router.get("/autonomy", response_model=AutonomyConfigResponse)
async def get_autonomy_settings(
    tenant_id: Optional[str] = Query(None, description="Optional tenant ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get current autonomy configuration for the tenant.
    Requires ADMIN role.
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized. Admin access required.")

    user_tenant = getattr(current_user, "tenant_id", "default") or "default"
    if tenant_id and tenant_id != user_tenant and user_tenant != "default":
        raise HTTPException(status_code=403, detail="Cannot access settings for a different tenant.")
    effective_tenant = tenant_id if (tenant_id and user_tenant == "default") else user_tenant
    cfg = await AutonomyConfigService.get_effective_config(db, tenant_id=effective_tenant)
    audit = await AutonomyConfigService.get_audit_trail(db, tenant_id=effective_tenant)

    bounds_dict = {k: [float(v[0]), float(v[1])] for k, v in THRESHOLD_BOUNDS.items()}

    return AutonomyConfigResponse(
        mode=cfg.mode.value if hasattr(cfg.mode, "value") else str(cfg.mode),
        tenant_id=cfg.tenant_id,
        auto_resolve_min_confidence=cfg.thresholds.auto_resolve_min_confidence,
        auto_resolve_max_risk=cfg.thresholds.auto_resolve_max_risk,
        confirm_min_confidence=cfg.thresholds.confirm_min_confidence,
        confirm_max_risk=cfg.thresholds.confirm_max_risk,
        frustration_escalation_threshold=cfg.thresholds.frustration_escalation_threshold,
        max_attempts_before_escalate=cfg.thresholds.max_attempts_before_escalate,
        policy_overrides=cfg.policy_overrides,
        allowed_bounds=bounds_dict,
        modes_info=MODES_INFO,
        recent_audit_trail=audit[-10:],
        safety_invariants=SAFETY_INVARIANTS,
    )


@router.put("/autonomy", response_model=AutonomyConfigResponse)
async def update_autonomy_settings(
    request: AutonomyUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Update autonomy settings for the tenant with bound validation.
    Requires ADMIN role.
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized. Admin access required.")

    user_tenant = getattr(current_user, "tenant_id", "default") or "default"
    if request.tenant_id and request.tenant_id != user_tenant and user_tenant != "default":
        raise HTTPException(status_code=403, detail="Cannot modify settings for a different tenant.")
    effective_tenant = request.tenant_id if (request.tenant_id and user_tenant == "default") else user_tenant

    # Assemble custom threshold overrides
    overrides = dict(request.policy_overrides or {})
    if request.auto_resolve_min_confidence is not None:
        overrides["auto_resolve_min_confidence"] = request.auto_resolve_min_confidence
    if request.auto_resolve_max_risk is not None:
        overrides["auto_resolve_max_risk"] = request.auto_resolve_max_risk
    if request.confirm_min_confidence is not None:
        overrides["confirm_min_confidence"] = request.confirm_min_confidence
    if request.confirm_max_risk is not None:
        overrides["confirm_max_risk"] = request.confirm_max_risk
    if request.frustration_escalation_threshold is not None:
        overrides["frustration_escalation_threshold"] = request.frustration_escalation_threshold
    if request.max_attempts_before_escalate is not None:
        overrides["max_attempts_before_escalate"] = request.max_attempts_before_escalate

    try:
        updated_dto = await AutonomyConfigService.update_config(
            db=db,
            tenant_id=effective_tenant,
            mode=request.mode,
            user_id=current_user.id,
            user_email=current_user.email,
            custom_overrides=overrides,
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to persist autonomy settings: {str(e)}")

    audit = await AutonomyConfigService.get_audit_trail(db, tenant_id=effective_tenant)
    bounds_dict = {k: [float(v[0]), float(v[1])] for k, v in THRESHOLD_BOUNDS.items()}

    return AutonomyConfigResponse(
        mode=updated_dto.mode.value if hasattr(updated_dto.mode, "value") else str(updated_dto.mode),
        tenant_id=updated_dto.tenant_id,
        auto_resolve_min_confidence=updated_dto.thresholds.auto_resolve_min_confidence,
        auto_resolve_max_risk=updated_dto.thresholds.auto_resolve_max_risk,
        confirm_min_confidence=updated_dto.thresholds.confirm_min_confidence,
        confirm_max_risk=updated_dto.thresholds.confirm_max_risk,
        frustration_escalation_threshold=updated_dto.thresholds.frustration_escalation_threshold,
        max_attempts_before_escalate=updated_dto.thresholds.max_attempts_before_escalate,
        policy_overrides=updated_dto.policy_overrides,
        allowed_bounds=bounds_dict,
        modes_info=MODES_INFO,
        recent_audit_trail=audit[-10:],
        safety_invariants=SAFETY_INVARIANTS,
    )


@router.post("/autonomy/reset", response_model=AutonomyConfigResponse)
async def reset_autonomy_settings(
    tenant_id: Optional[str] = Query(None, description="Optional tenant ID to reset"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Reset autonomy settings to the Balanced default policy.
    Requires ADMIN role.
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized. Admin access required.")

    user_tenant = getattr(current_user, "tenant_id", "default") or "default"
    if tenant_id and tenant_id != user_tenant and user_tenant != "default":
        raise HTTPException(status_code=403, detail="Cannot reset settings for a different tenant.")
    effective_tenant = tenant_id if (tenant_id and user_tenant == "default") else user_tenant

    try:
        reset_dto = await AutonomyConfigService.reset_config(
            db=db,
            tenant_id=effective_tenant,
            user_id=current_user.id,
            user_email=current_user.email,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reset autonomy settings: {str(e)}")

    audit = await AutonomyConfigService.get_audit_trail(db, tenant_id=effective_tenant)
    bounds_dict = {k: [float(v[0]), float(v[1])] for k, v in THRESHOLD_BOUNDS.items()}

    return AutonomyConfigResponse(
        mode=reset_dto.mode.value if hasattr(reset_dto.mode, "value") else str(reset_dto.mode),
        tenant_id=reset_dto.tenant_id,
        auto_resolve_min_confidence=reset_dto.thresholds.auto_resolve_min_confidence,
        auto_resolve_max_risk=reset_dto.thresholds.auto_resolve_max_risk,
        confirm_min_confidence=reset_dto.thresholds.confirm_min_confidence,
        confirm_max_risk=reset_dto.thresholds.confirm_max_risk,
        frustration_escalation_threshold=reset_dto.thresholds.frustration_escalation_threshold,
        max_attempts_before_escalate=reset_dto.thresholds.max_attempts_before_escalate,
        policy_overrides=reset_dto.policy_overrides,
        allowed_bounds=bounds_dict,
        modes_info=MODES_INFO,
        recent_audit_trail=audit[-10:],
        safety_invariants=SAFETY_INVARIANTS,
    )
