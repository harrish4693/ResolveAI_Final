from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case
from pydantic import BaseModel
from typing import List, Dict, Any, Optional, Tuple
import time

from app.database import get_db
from app.auth.deps import get_current_user
from app.users.models import User
from app.shared.models import UserRole, ConversationStatus
from app.conversations.models import Conversation
from app.handoff.models import Handoff
from app.feedback.models import Feedback

# In-memory TTL cache for incident analytics response: tenant_id -> (timestamp, IncidentAnalyticsResponse)
_INCIDENT_ANALYTICS_CACHE: Dict[str, Tuple[float, Any]] = {}
_ANALYTICS_CACHE_TTL_SECONDS = 30.0

def invalidate_incident_analytics_cache(tenant_id: str = "default"):
    """Invalidates cached incident analytics for a tenant."""
    _INCIDENT_ANALYTICS_CACHE.pop(tenant_id, None)

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])

class OverviewStats(BaseModel):
    total_conversations: int
    ai_resolved: int
    expert_resolved: int
    escalated: int
    avg_csat: float | None
    total_feedback: int
    ai_avg_rating: float | None
    human_avg_rating: float | None
    rating_distribution: Dict[int, int]

class IntentStat(BaseModel):
    intent: str
    count: int

class AnalyticsResponse(BaseModel):
    overview: OverviewStats
    intents: List[IntentStat]

@router.get("", response_model=AnalyticsResponse)
async def get_analytics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    # Total conversations
    total_res = await db.execute(select(func.count(Conversation.id)))
    total_convs = total_res.scalar() or 0
    
    # Handoff counts
    handoffs_res = await db.execute(
        select(
            func.count(Handoff.id),
            func.sum(case((Handoff.status == 'resolved', 1), else_=0))
        )
    )
    total_handoffs, expert_resolved = handoffs_res.first()
    total_handoffs = total_handoffs or 0
    expert_resolved = expert_resolved or 0
    
    # AI Resolved: total resolved conversations - expert resolved
    resolved_convs_res = await db.execute(
        select(func.count(Conversation.id)).where(Conversation.status == ConversationStatus.RESOLVED)
    )
    total_resolved_convs = resolved_convs_res.scalar() or 0
    ai_resolved = total_resolved_convs - expert_resolved
    if ai_resolved < 0:
        ai_resolved = 0
        
    # CSAT & Feedback Metrics
    csat_res = await db.execute(
        select(
            func.count(Feedback.id),
            func.avg(Feedback.rating),
            func.avg(case((Feedback.resolution_type == 'ai', Feedback.rating), else_=None)),
            func.avg(case((Feedback.resolution_type.in_(['human', 'ai_escalated_to_human']), Feedback.rating), else_=None))
        )
    )
    total_fb, avg_csat, ai_avg, human_avg = csat_res.first()
    
    # Rating Distribution
    dist_res = await db.execute(
        select(Feedback.rating, func.count(Feedback.id)).group_by(Feedback.rating)
    )
    rating_distribution = {i: 0 for i in range(1, 6)}
    for row in dist_res.all():
        if row[0]:
            rating_distribution[int(row[0])] = row[1]
            
    if avg_csat is not None:
        avg_csat = round(float(avg_csat), 1)
    if ai_avg is not None:
        ai_avg = round(float(ai_avg), 1)
    if human_avg is not None:
        human_avg = round(float(human_avg), 1)
        
    overview = OverviewStats(
        total_conversations=total_convs,
        ai_resolved=ai_resolved,
        expert_resolved=expert_resolved,
        escalated=total_handoffs,
        avg_csat=avg_csat,
        total_feedback=total_fb or 0,
        ai_avg_rating=ai_avg,
        human_avg_rating=human_avg,
        rating_distribution=rating_distribution
    )
    
    # Intent distribution from Handoffs
    intents_res = await db.execute(
        select(Handoff.category, func.count(Handoff.id))
        .group_by(Handoff.category)
        .order_by(func.count(Handoff.id).desc())
    )
    
    intents = [
        IntentStat(intent=row[0] or "unknown", count=row[1])
        for row in intents_res.all()
    ]
    
    return AnalyticsResponse(overview=overview, intents=intents)


class IncidentItemRead(BaseModel):
    incident_id: str
    title: str
    description: str
    category: str
    status: str
    severity: str
    confidence: float
    affected_tickets: List[int]
    affected_ticket_count: int
    affected_customer_count: int
    time_window_start: str | None = None
    time_window_end: str | None = None
    is_spike: bool = False
    spike_ratio: float | None = None
    evidence: List[str] = []


class IncidentAnalyticsResponse(BaseModel):
    candidates: List[IncidentItemRead]
    confirmed: List[IncidentItemRead]
    spike_alerts: List[Dict[str, Any]]
    total_incidents: int
    total_affected_tickets: int


class IncidentStatusUpdate(BaseModel):
    status: str


@router.get("/incidents", response_model=IncidentAnalyticsResponse)
async def get_incident_analytics(
    tenant_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    user_tenant = getattr(current_user, "tenant_id", "default") or "default"
    if tenant_id and tenant_id != user_tenant and user_tenant != "default":
        raise HTTPException(status_code=403, detail="Cannot access incidents for a different tenant.")
    effective_tenant = tenant_id if (tenant_id and user_tenant == "default") else user_tenant

    now_mono = time.monotonic()
    cached = _INCIDENT_ANALYTICS_CACHE.get(effective_tenant)
    if cached and (now_mono - cached[0] < _ANALYTICS_CACHE_TTL_SECONDS):
        return cached[1]

    from app.tickets.models import Ticket
    from app.ai.intelligence.incidents import IncidentDetector, TicketSnapshot
    from app.ai.incident_service import IncidentPersistenceService

    tickets_res = await db.execute(
        select(Ticket)
        .join(User, Ticket.customer_id == User.id)
        .where(User.tenant_id == effective_tenant)
        .order_by(Ticket.created_at.desc())
        .limit(200)
    )
    tickets = tickets_res.scalars().all()

    snapshots = [
        TicketSnapshot(
            ticket_id=t.id,
            subject=t.subject or "",
            category=t.category or "General",
            created_at=t.created_at,
            customer_id=t.customer_id,
            tenant_id=effective_tenant,
            status=str(t.status.value if hasattr(t.status, "value") else t.status),
        )
        for t in tickets
    ]

    detector = IncidentDetector()
    hypotheses = detector.detect_incidents(snapshots, tenant_id=effective_tenant)
    hypotheses = await IncidentPersistenceService.reconcile_hypotheses(db, hypotheses, tenant_id=effective_tenant)
    overall_spike = detector.detect_spike(snapshots)

    spike_alerts: List[Dict[str, Any]] = []
    if overall_spike.get("is_spike"):
        spike_alerts.append({
            "scope": "Overall Operations",
            "ratio": overall_spike.get("spike_ratio"),
            "current_rate": overall_spike.get("current_rate"),
            "baseline_rate": overall_spike.get("baseline_rate"),
            "message": f"Organization-wide complaint surge: {overall_spike.get('spike_ratio')}x above baseline",
        })

    candidates: List[IncidentItemRead] = []
    confirmed: List[IncidentItemRead] = []
    all_affected_tickets: set[int] = set()

    detected_ids: set[str] = set()

    for hyp in hypotheses:
        detected_ids.add(hyp.incident_id)
        all_affected_tickets.update(hyp.affected_tickets)
        if hyp.is_spike and hyp.spike_ratio:
            spike_alerts.append({
                "scope": f"Incident {hyp.incident_id} ({hyp.category})",
                "ratio": hyp.spike_ratio,
                "message": f"Spike detected in {hyp.category}: {hyp.spike_ratio}x above historical baseline",
            })

        item = IncidentItemRead(
            incident_id=hyp.incident_id,
            title=hyp.title,
            description=hyp.description,
            category=hyp.category,
            status=hyp.status,
            severity=hyp.severity,
            confidence=hyp.confidence,
            affected_tickets=hyp.affected_tickets,
            affected_ticket_count=len(hyp.affected_tickets),
            affected_customer_count=hyp.affected_customer_count,
            time_window_start=hyp.time_window_start.isoformat() if hyp.time_window_start else None,
            time_window_end=hyp.time_window_end.isoformat() if hyp.time_window_end else None,
            is_spike=hyp.is_spike,
            spike_ratio=hyp.spike_ratio,
            evidence=hyp.evidence,
        )

        if hyp.status in ("confirmed", "investigating", "mitigated", "resolved"):
            confirmed.append(item)
        else:
            candidates.append(item)

    # Include persisted confirmed/investigating/mitigated records not in current detected window
    saved_records = await IncidentPersistenceService.load_tenant_statuses(db, tenant_id=effective_tenant)
    for inc_id, rec in saved_records.items():
        if inc_id not in detected_ids and rec.status in ("investigating", "confirmed", "mitigated"):
            confirmed.append(
                IncidentItemRead(
                    incident_id=rec.incident_id,
                    title=rec.title or f"Incident {rec.incident_id}",
                    description=f"Persisted incident ({rec.status})",
                    category=rec.category or "General",
                    status=rec.status,
                    severity=rec.severity or "MEDIUM",
                    confidence=0.9,
                    affected_tickets=rec.affected_ticket_ids or [],
                    affected_ticket_count=len(rec.affected_ticket_ids or []),
                    affected_customer_count=len(rec.affected_ticket_ids or []),
                    evidence=["Persisted incident state from database"],
                )
            )

    response = IncidentAnalyticsResponse(
        candidates=candidates,
        confirmed=confirmed,
        spike_alerts=spike_alerts,
        total_incidents=len(candidates) + len(confirmed),
        total_affected_tickets=len(all_affected_tickets),
    )
    _INCIDENT_ANALYTICS_CACHE[effective_tenant] = (now_mono, response)
    return response


@router.post("/incidents/{incident_id}/status")
async def update_incident_status(
    incident_id: str,
    payload: IncidentStatusUpdate,
    tenant_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    user_tenant = getattr(current_user, "tenant_id", "default") or "default"
    if tenant_id and tenant_id != user_tenant and user_tenant != "default":
        raise HTTPException(status_code=403, detail="Cannot modify incident for a different tenant.")
    effective_tenant = tenant_id if (tenant_id and user_tenant == "default") else user_tenant

    from app.ai.incident_service import IncidentPersistenceService

    try:
        record = await IncidentPersistenceService.update_status(
            db=db,
            incident_id=incident_id,
            status=payload.status,
            tenant_id=effective_tenant,
            user_id=current_user.id,
            user_email=current_user.email,
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to persist incident status: {str(e)}")

    # Invalidate both analytics and queue/context caches for this tenant
    invalidate_incident_analytics_cache(record.tenant_id)
    try:
        from app.handoff.router import invalidate_incident_map_cache
        invalidate_incident_map_cache(record.tenant_id)
    except Exception:
        pass

    return {
        "incident_id": record.incident_id,
        "status": record.status,
        "tenant_id": record.tenant_id,
        "message": f"Incident {record.incident_id} status updated to {record.status}",
    }


class RiskCategoryDistribution(BaseModel):
    category: str
    high_risk: int
    moderate_risk: int
    low_risk: int
    total: int


class OutcomeMetrics(BaseModel):
    ai_resolved_success: int
    expert_resolved: int
    observed_tool_failures: int
    low_csat_feedback_count: int


class FailureRiskAnalyticsResponse(BaseModel):
    # Predictions
    high_risk_ticket_count: int
    moderate_risk_ticket_count: int
    low_risk_ticket_count: int
    total_evaluated_tickets: int

    # Observed Outcomes
    observed_failure_count: int
    escalated_ticket_count: int
    repeat_contact_rate: float
    repeat_customer_count: int
    escalation_rate: float

    # Breakdown & Correlation
    category_distribution: List[RiskCategoryDistribution]
    outcomes: OutcomeMetrics
    incident_failure_correlation: Dict[str, Any]
    limitations: List[str]


@router.get("/failure-risk", response_model=FailureRiskAnalyticsResponse)
async def get_failure_risk_analytics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    from app.tickets.models import Ticket

    # 1. Total conversations & Escalation counts
    total_convs_res = await db.execute(select(func.count(Conversation.id)))
    total_convs = total_convs_res.scalar() or 0

    total_handoffs_res = await db.execute(select(func.count(Handoff.id)))
    total_handoffs = total_handoffs_res.scalar() or 0

    escalation_rate = round((total_handoffs / total_convs * 100), 1) if total_convs > 0 else 0.0

    # 2. Repeat-contact rate
    conv_by_cust_res = await db.execute(
        select(Conversation.customer_id, func.count(Conversation.id))
        .group_by(Conversation.customer_id)
    )
    cust_rows = conv_by_cust_res.all()
    total_customers = len(cust_rows)
    repeat_customers = sum(1 for _, count in cust_rows if count > 1)
    repeat_contact_rate = round((repeat_customers / total_customers * 100), 1) if total_customers > 0 else 0.0

    # 3. Analyze Handoffs for Predicted Failure Risk vs Observed Failures
    handoffs_res = await db.execute(select(Handoff))
    all_handoffs = handoffs_res.scalars().all()

    high_risk_count = 0
    moderate_risk_count = 0
    low_risk_count = 0
    observed_handoff_failures = 0
    tool_failures = 0
    cat_map: Dict[str, Dict[str, int]] = {}

    for h in all_handoffs:
        cat = h.category or "General"
        if cat not in cat_map:
            cat_map[cat] = {"high": 0, "moderate": 0, "low": 0, "total": 0}

        meta = h.ai_analysis if (h.ai_analysis and isinstance(h.ai_analysis, dict)) else {}
        fr = meta.get("failure_risk") if isinstance(meta.get("failure_risk"), dict) else {}
        obs_f = meta.get("observed_failure") if isinstance(meta.get("observed_failure"), dict) else {}

        risk_level = (fr.get("likelihood") or fr.get("risk_level") or "LOW").upper()
        if risk_level in ("HIGH", "VERY_HIGH"):
            high_risk_count += 1
            cat_map[cat]["high"] += 1
        elif risk_level == "MODERATE":
            moderate_risk_count += 1
            cat_map[cat]["moderate"] += 1
        else:
            low_risk_count += 1
            cat_map[cat]["low"] += 1
        cat_map[cat]["total"] += 1

        if obs_f.get("failed") or obs_f.get("type") == "tool_execution_error":
            tool_failures += 1
            observed_handoff_failures += 1
        elif fr.get("has_prior_solution_failed") or int(fr.get("observed_failure_count", 0)) > 0:
            observed_handoff_failures += 1

    # 4. Low CSAT Feedback (Observed customer-reported failures)
    low_csat_res = await db.execute(
        select(func.count(Feedback.id)).where(Feedback.rating <= 2)
    )
    low_csat_count = low_csat_res.scalar() or 0

    expert_resolved_res = await db.execute(
        select(func.count(Handoff.id)).where(Handoff.status == "resolved")
    )
    expert_resolved = expert_resolved_res.scalar() or 0

    resolved_convs_res = await db.execute(
        select(func.count(Conversation.id)).where(Conversation.status == ConversationStatus.RESOLVED)
    )
    total_resolved = resolved_convs_res.scalar() or 0
    ai_resolved_success = max(0, total_resolved - expert_resolved)

    total_observed_failures = observed_handoff_failures + low_csat_count

    # 5. Incident-to-failure correlation
    incident_corr = {"incidents_analyzed": 0, "incident_affected_escalations": 0}
    try:
        from app.ai.intelligence.incidents import IncidentDetector, TicketSnapshot
        recent_tickets_res = await db.execute(select(Ticket).order_by(Ticket.created_at.desc()).limit(100))
        recent_tickets = recent_tickets_res.scalars().all()
        snapshots = [
            TicketSnapshot(
                ticket_id=t.id,
                subject=t.subject or "",
                category=t.category or "General",
                created_at=t.created_at,
                customer_id=t.customer_id,
                tenant_id="default",
                status=str(t.status.value if hasattr(t.status, "value") else t.status),
            )
            for t in recent_tickets
        ]
        detector = IncidentDetector()
        detected = detector.detect_incidents(snapshots, tenant_id="default")
        incident_corr["incidents_analyzed"] = len(detected)
        affected_ticket_ids = set()
        for inc in detected:
            affected_ticket_ids.update(inc.affected_tickets)
        
        # Check how many handoffs match affected ticket IDs
        matched_escalations = sum(1 for h in all_handoffs if h.ticket_id in affected_ticket_ids or h.conversation_id in affected_ticket_ids)
        incident_corr["incident_affected_escalations"] = matched_escalations
    except Exception as e:
        logger.warning("Error computing incident-failure correlation: %s", e)

    category_distribution = [
        RiskCategoryDistribution(
            category=cat,
            high_risk=counts["high"],
            moderate_risk=counts["moderate"],
            low_risk=counts["low"],
            total=counts["total"],
        )
        for cat, counts in cat_map.items()
    ]

    limitations = [
        "Metrics are strictly derived from recorded database entities; unpersisted interactions are excluded.",
        "Failure risk levels are model-estimated warning signals and must not be treated as confirmed failures.",
        "Observed failures count verified tool execution exceptions, low CSAT feedback (<=2), and customer-reported failures.",
    ]

    return FailureRiskAnalyticsResponse(
        high_risk_ticket_count=high_risk_count,
        moderate_risk_ticket_count=moderate_risk_count,
        low_risk_ticket_count=low_risk_count,
        total_evaluated_tickets=len(all_handoffs),
        observed_failure_count=total_observed_failures,
        escalated_ticket_count=total_handoffs,
        repeat_contact_rate=repeat_contact_rate,
        repeat_customer_count=repeat_customers,
        escalation_rate=escalation_rate,
        category_distribution=category_distribution,
        outcomes=OutcomeMetrics(
            ai_resolved_success=ai_resolved_success,
            expert_resolved=expert_resolved,
            observed_tool_failures=tool_failures,
            low_csat_feedback_count=low_csat_count,
        ),
        incident_failure_correlation=incident_corr,
        limitations=limitations,
    )


