"""
ResolveAIV2 — Autonomy Configuration Service

Manages persistence, caching, validation, and audit trails for
Admin-configurable dynamic autonomy controls.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.autonomy_models import AutonomyConfig
from app.ai.intelligence.autonomy import (
    AutonomyConfigDTO,
    AutonomyMode,
    MODE_THRESHOLDS,
    THRESHOLD_BOUNDS,
)

logger = logging.getLogger(__name__)


class AutonomyConfigService:
    """Service for retrieving, updating, and auditing autonomy controls per tenant."""

    # In-process cache: tenant_id -> (AutonomyConfigDTO, timestamp)
    _cache: Dict[str, AutonomyConfigDTO] = {}

    @classmethod
    def invalidate_cache(cls, tenant_id: Optional[str] = None):
        """Invalidate in-memory cache for a tenant or all tenants."""
        if tenant_id:
            cls._cache.pop(tenant_id, None)
        else:
            cls._cache.clear()

    @classmethod
    async def get_effective_config(
        cls,
        db: Optional[AsyncSession] = None,
        tenant_id: str = "default",
    ) -> AutonomyConfigDTO:
        """
        Retrieves the active autonomy configuration for the tenant.
        Falls back safely to the Balanced default if DB or record is unavailable.
        """
        # Check in-memory cache first
        if tenant_id in cls._cache:
            return cls._cache[tenant_id]

        if db is None:
            return AutonomyConfigDTO.default(tenant_id)

        try:
            stmt = select(AutonomyConfig).where(AutonomyConfig.tenant_id == tenant_id)
            row = (await db.execute(stmt)).scalar_one_or_none()
            if row is None:
                # Return and cache default DTO
                dto = AutonomyConfigDTO.default(tenant_id)
                cls._cache[tenant_id] = dto
                return dto

            dto = AutonomyConfigDTO.for_mode(
                mode=row.mode,
                tenant_id=row.tenant_id,
                custom_overrides={
                    "auto_resolve_min_confidence": row.auto_resolve_min_confidence,
                    "auto_resolve_max_risk": row.auto_resolve_max_risk,
                    "confirm_min_confidence": row.confirm_min_confidence,
                    "confirm_max_risk": row.confirm_max_risk,
                    "frustration_escalation_threshold": row.frustration_escalation_threshold,
                    "max_attempts_before_escalate": row.max_attempts_before_escalate,
                    **(row.policy_overrides or {}),
                },
            )
            cls._cache[tenant_id] = dto
            return dto
        except Exception as e:
            logger.warning("Error fetching autonomy config for tenant %s: %s. Using default.", tenant_id, e)
            return AutonomyConfigDTO.default(tenant_id)

    @classmethod
    async def update_config(
        cls,
        db: AsyncSession,
        tenant_id: str,
        mode: str,
        user_id: int,
        user_email: str = "",
        custom_overrides: Optional[Dict[str, Any]] = None,
    ) -> AutonomyConfigDTO:
        """
        Updates autonomy settings with strict validation and audit logging.
        """
        # 1. Validate mode
        try:
            mode_enum = AutonomyMode(mode.lower().strip())
        except ValueError:
            valid_modes = [m.value for m in AutonomyMode]
            raise ValueError(f"Invalid autonomy mode '{mode}'. Must be one of: {valid_modes}")

        # 2. Validate custom overrides against safety bounds
        overrides = dict(custom_overrides or {})
        for key, val in overrides.items():
            if key in THRESHOLD_BOUNDS:
                min_b, max_b = THRESHOLD_BOUNDS[key]
                try:
                    num_val = float(val)
                except (ValueError, TypeError):
                    raise ValueError(f"Override '{key}' must be a numeric value")
                if not (min_b <= num_val <= max_b):
                    raise ValueError(
                        f"Threshold override '{key}' ({val}) violates safety bounds [{min_b}, {max_b}]"
                    )
            elif key in ("bypass_security", "bypass_confirmation", "unrestricted_tools"):
                raise ValueError(f"Policy override '{key}' is forbidden by platform safety policy")

        # 3. Construct new DTO
        dto = AutonomyConfigDTO.for_mode(
            mode=mode_enum,
            tenant_id=tenant_id,
            custom_overrides=overrides,
        )

        # 4. Fetch or create DB record
        stmt = select(AutonomyConfig).where(AutonomyConfig.tenant_id == tenant_id)
        row = (await db.execute(stmt)).scalar_one_or_none()

        old_mode = row.mode if row else "balanced"
        now_iso = datetime.now(timezone.utc).isoformat()

        audit_entry = {
            "timestamp": now_iso,
            "user_id": user_id,
            "user_email": user_email,
            "previous_mode": old_mode,
            "new_mode": mode_enum.value,
            "overrides": overrides,
            "status": "success",
        }

        if row is None:
            row = AutonomyConfig(
                tenant_id=tenant_id,
                mode=mode_enum.value,
                auto_resolve_min_confidence=dto.thresholds.auto_resolve_min_confidence,
                auto_resolve_max_risk=dto.thresholds.auto_resolve_max_risk,
                confirm_min_confidence=dto.thresholds.confirm_min_confidence,
                confirm_max_risk=dto.thresholds.confirm_max_risk,
                frustration_escalation_threshold=dto.thresholds.frustration_escalation_threshold,
                max_attempts_before_escalate=dto.thresholds.max_attempts_before_escalate,
                policy_overrides=overrides,
                updated_by_user_id=user_id,
                audit_log=[audit_entry],
            )
            db.add(row)
        else:
            row.mode = mode_enum.value
            row.auto_resolve_min_confidence = dto.thresholds.auto_resolve_min_confidence
            row.auto_resolve_max_risk = dto.thresholds.auto_resolve_max_risk
            row.confirm_min_confidence = dto.thresholds.confirm_min_confidence
            row.confirm_max_risk = dto.thresholds.confirm_max_risk
            row.frustration_escalation_threshold = dto.thresholds.frustration_escalation_threshold
            row.max_attempts_before_escalate = dto.thresholds.max_attempts_before_escalate
            row.policy_overrides = overrides
            row.updated_by_user_id = user_id
            
            current_log = list(row.audit_log or [])
            current_log.append(audit_entry)
            row.audit_log = current_log[-50:]  # Keep recent 50 audit entries

        await db.commit()
        await db.refresh(row)

        # 5. Invalidate cache
        cls.invalidate_cache(tenant_id)
        cls._cache[tenant_id] = dto

        logger.info(
            "Autonomy configuration updated for tenant %s by user %s: mode=%s",
            tenant_id, user_id, mode_enum.value
        )
        return dto

    @classmethod
    async def reset_config(
        cls,
        db: AsyncSession,
        tenant_id: str,
        user_id: int,
        user_email: str = "",
    ) -> AutonomyConfigDTO:
        """
        Resets tenant configuration to the default Balanced mode and thresholds.
        """
        return await cls.update_config(
            db=db,
            tenant_id=tenant_id,
            mode=AutonomyMode.BALANCED.value,
            user_id=user_id,
            user_email=user_email,
            custom_overrides={},
        )

    @classmethod
    async def get_audit_trail(
        cls,
        db: AsyncSession,
        tenant_id: str = "default",
    ) -> List[Dict[str, Any]]:
        """Fetch audit log history for a tenant."""
        stmt = select(AutonomyConfig).where(AutonomyConfig.tenant_id == tenant_id)
        row = (await db.execute(stmt)).scalar_one_or_none()
        if not row or not row.audit_log:
            return []
        return list(row.audit_log)
