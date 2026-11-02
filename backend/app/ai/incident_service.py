"""
ResolveAIV2 — Incident Persistence Service

Handles durable database storage, status transition validation, audit logging,
and safe cluster matching for cross-ticket incidents across workers.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.incident_models import IncidentRecord
from app.ai.intelligence.incidents import IncidentHypothesis, IncidentStateManager

logger = logging.getLogger(__name__)

# Valid lifecycle statuses
ALLOWED_STATUSES: Set[str] = {
    "candidate",
    "investigating",
    "confirmed",
    "mitigated",
    "resolved",
}

# Strict lifecycle state transition rules
VALID_TRANSITIONS: Dict[str, Set[str]] = {
    "candidate": {"investigating", "confirmed", "resolved"},
    "investigating": {"confirmed", "mitigated", "resolved", "candidate"},
    "confirmed": {"investigating", "mitigated", "resolved"},
    "mitigated": {"resolved", "investigating", "confirmed"},
    "resolved": {"investigating", "confirmed"},  # Reopened if incident recurs
}


class IncidentPersistenceService:
    """Service for managing durable incident lifecycle state and cross-worker consistency."""

    @classmethod
    def validate_transition(cls, current_status: str, new_status: str) -> None:
        """
        Validate that the requested status transition is allowed.
        Raises ValueError if invalid.
        """
        curr = current_status.lower().strip()
        new_st = new_status.lower().strip()

        if new_st not in ALLOWED_STATUSES:
            raise ValueError(
                f"Invalid status '{new_status}'. Allowed statuses are: {', '.join(sorted(ALLOWED_STATUSES))}"
            )

        if curr == new_st:
            return  # Idempotent no-op transition is allowed

        allowed = VALID_TRANSITIONS.get(curr, set())
        if new_st not in allowed:
            raise ValueError(
                f"Invalid status transition from '{curr}' to '{new_st}'. "
                f"Allowed transitions from '{curr}' are: {', '.join(sorted(allowed)) if allowed else 'none'}"
            )

    @classmethod
    async def get_incident(
        cls,
        db: AsyncSession,
        incident_id: str,
        tenant_id: str = "default",
    ) -> Optional[IncidentRecord]:
        """Fetch incident record by tenant and incident ID."""
        stmt = select(IncidentRecord).where(
            IncidentRecord.tenant_id == tenant_id,
            IncidentRecord.incident_id == incident_id,
        )
        return (await db.execute(stmt)).scalar_one_or_none()

    @classmethod
    async def get_status(
        cls,
        db: AsyncSession,
        incident_id: str,
        tenant_id: str = "default",
        default: str = "candidate",
    ) -> str:
        """Get incident status from database with fallback to default."""
        record = await cls.get_incident(db, incident_id, tenant_id=tenant_id)
        if record:
            IncidentStateManager.set_status(incident_id, record.status)
            return record.status
        return IncidentStateManager.get_status(incident_id, default=default)

    @classmethod
    async def update_status(
        cls,
        db: AsyncSession,
        incident_id: str,
        status: str,
        tenant_id: str = "default",
        user_id: Optional[int] = None,
        user_email: Optional[str] = None,
        title: Optional[str] = None,
        category: Optional[str] = None,
        severity: str = "MEDIUM",
        affected_ticket_ids: Optional[List[int]] = None,
    ) -> IncidentRecord:
        """
        Persist a validated status update transactionally with audit history.
        """
        normalized_status = status.lower().strip()
        record = await cls.get_incident(db, incident_id, tenant_id=tenant_id)

        now_utc = datetime.now(timezone.utc)
        clean_tickets = sorted(list(set(affected_ticket_ids or [])))

        if record is None:
            # New incident record: transition from default 'candidate'
            cls.validate_transition(current_status="candidate", new_status=normalized_status)

            history = []
            if normalized_status != "candidate":
                history.append({
                    "from_status": "candidate",
                    "to_status": normalized_status,
                    "updated_by_user_id": user_id,
                    "updated_by_email": user_email,
                    "timestamp": now_utc.isoformat(),
                })

            record = IncidentRecord(
                incident_id=incident_id,
                tenant_id=tenant_id,
                status=normalized_status,
                title=title or f"Incident {incident_id}",
                category=category or "General",
                severity=severity or "MEDIUM",
                affected_ticket_ids=clean_tickets,
                status_history=history,
                updated_by_user_id=user_id,
                created_at=now_utc,
                updated_at=now_utc,
            )
            db.add(record)
        else:
            # Existing incident record: validate transition from current persisted status
            cls.validate_transition(current_status=record.status, new_status=normalized_status)

            if normalized_status != record.status:
                history_list = list(record.status_history or [])
                history_list.append({
                    "from_status": record.status,
                    "to_status": normalized_status,
                    "updated_by_user_id": user_id,
                    "updated_by_email": user_email,
                    "timestamp": now_utc.isoformat(),
                })
                record.status_history = history_list
                record.status = normalized_status

            record.updated_by_user_id = user_id
            record.updated_at = now_utc
            if title:
                record.title = title
            if category:
                record.category = category
            if severity:
                record.severity = severity
            if clean_tickets:
                existing_tids = set(record.affected_ticket_ids or [])
                record.affected_ticket_ids = sorted(list(existing_tids | set(clean_tickets)))

        await db.commit()
        await db.refresh(record)

        # Update in-memory state manager for sync lookups
        IncidentStateManager.set_status(incident_id, record.status)
        return record

    @classmethod
    async def load_tenant_statuses(
        cls,
        db: AsyncSession,
        tenant_id: str = "default",
    ) -> Dict[str, IncidentRecord]:
        """
        Load all incident records for a tenant and populate in-memory state.
        Returns a dictionary mapping incident_id -> IncidentRecord.
        """
        stmt = select(IncidentRecord).where(IncidentRecord.tenant_id == tenant_id)
        records = (await db.execute(stmt)).scalars().all()
        result: Dict[str, IncidentRecord] = {}
        for r in records:
            result[r.incident_id] = r
            IncidentStateManager.set_status(r.incident_id, r.status)
        return result

    @classmethod
    def match_cluster_to_incident(
        cls,
        cluster_tickets: List[int],
        category: str,
        saved_records: Dict[str, IncidentRecord],
        idx: int = 0,
    ) -> Tuple[str, str]:
        """
        Safely matches a dynamically detected ticket cluster to an existing saved incident record.
        
        Logic:
        1. Check if any saved record in the same category has overlapping ticket IDs.
        2. If overlapping tickets exist for the same category, associate with that saved incident.
        3. If no overlap, generate a stable deterministic ID:
           INC-{CATEGORY_PREFIX}-{MIN_TICKET_ID:04d}
        4. If that ID matches an existing record, verify ticket compatibility before assigning status.
           Never silently assign an unrelated incident's status.
        
        Returns:
            (incident_id, status)
        """
        cluster_set = set(cluster_tickets)
        norm_cat = (category or "General").lower().strip()

        # 1. Overlap match: Look for an existing record with overlapping tickets in the same category
        for inc_id, rec in saved_records.items():
            rec_cat = (rec.category or "General").lower().strip()
            if rec_cat == norm_cat and rec.affected_ticket_ids:
                if cluster_set & set(rec.affected_ticket_ids):
                    return rec.incident_id, rec.status

        # 2. Stable deterministic identifier based on anchor ticket and category
        anchor_id = min(cluster_tickets) if cluster_tickets else (idx + 1)
        clean_cat = re.sub(r'[^A-Za-z0-9]', '', category or "GENR").upper()[:4] or "GENR"
        stable_id = f"INC-{clean_cat}-{anchor_id:04d}"

        # 3. Check if stable_id already exists in saved_records
        if stable_id in saved_records:
            rec = saved_records[stable_id]
            rec_tickets = set(rec.affected_ticket_ids or [])
            # Safe check: if the record has tickets and there is zero overlap, this is an unrelated cluster
            if rec_tickets and not (cluster_set & rec_tickets):
                # Disambiguate with cluster size / index to prevent unsafe assignment
                stable_id = f"{stable_id}-{idx + 1}"
            else:
                return stable_id, rec.status

        # 4. Check IncidentStateManager as fallback
        in_memory_status = IncidentStateManager.get_status(stable_id, default="candidate")
        return stable_id, in_memory_status

    @classmethod
    async def reconcile_hypotheses(
        cls,
        db: AsyncSession,
        hypotheses: List[IncidentHypothesis],
        tenant_id: str = "default",
    ) -> List[IncidentHypothesis]:
        """
        Reconciles dynamically detected incident hypotheses with persisted database state.
        Ensures matching is safe and assigns durable statuses.
        """
        saved_records = await cls.load_tenant_statuses(db, tenant_id=tenant_id)

        for idx, hyp in enumerate(hypotheses):
            matched_id, matched_status = cls.match_cluster_to_incident(
                cluster_tickets=hyp.affected_tickets,
                category=hyp.category,
                saved_records=saved_records,
                idx=idx,
            )
            hyp.incident_id = matched_id
            hyp.status = matched_status

        return hypotheses
