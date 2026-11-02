"""
ResolveAIV2 — Autonomy Configuration Database Model

Persists Admin-configurable autonomy settings per tenant.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from sqlalchemy import String, Float, Integer, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.shared.models import TimestampMixin


class AutonomyConfig(Base, TimestampMixin):
    """
    Durable settings model for Admin-configurable dynamic autonomy controls.
    Enforces tenant scoping, calibrated thresholds, and audit logging.
    """
    __tablename__ = "autonomy_configurations"

    tenant_id: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True, default="default", index=True
    )
    mode: Mapped[str] = mapped_column(
        String(30), nullable=False, default="balanced"
    )

    # Calibrated Thresholds
    auto_resolve_min_confidence: Mapped[float] = mapped_column(
        Float, nullable=False, default=75.0
    )
    auto_resolve_max_risk: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.25
    )
    confirm_min_confidence: Mapped[float] = mapped_column(
        Float, nullable=False, default=45.0
    )
    confirm_max_risk: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.55
    )
    frustration_escalation_threshold: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.70
    )
    max_attempts_before_escalate: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3
    )

    # Optional bounded overrides
    policy_overrides: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True, default=dict
    )

    # Audit Trail
    updated_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    audit_log: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSON, nullable=True, default=list
    )
