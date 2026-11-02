"""
ResolveAIV2 — Incident Records Database Model

Durable persistence model for cross-ticket incident lifecycle status,
tenant scoping, affected ticket tracking, and administrative audit history.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from sqlalchemy import String, Integer, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.shared.models import TimestampMixin


class IncidentRecord(Base, TimestampMixin):
    """
    Durable storage for cross-ticket incidents and their lifecycle state.
    Enforces tenant scoping, lifecycle transitions, and status change audit trails.
    """
    __tablename__ = "incident_records"
    __table_args__ = (
        UniqueConstraint("tenant_id", "incident_id", name="uq_tenant_incident_id"),
    )

    incident_id: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    tenant_id: Mapped[str] = mapped_column(
        String(50), nullable=False, default="default", index=True
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="candidate", index=True
    )
    title: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    category: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )
    severity: Mapped[str] = mapped_column(
        String(20), nullable=False, default="MEDIUM"
    )

    # Affected ticket IDs (list of integer ticket IDs, preserving privacy/no PII)
    affected_ticket_ids: Mapped[Optional[List[int]]] = mapped_column(
        JSON, nullable=True, default=list
    )

    # Status transition audit log
    status_history: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSON, nullable=True, default=list
    )

    # Last updating admin user
    updated_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    def __repr__(self) -> str:
        return f"<IncidentRecord(incident_id='{self.incident_id}', tenant_id='{self.tenant_id}', status='{self.status}')>"
