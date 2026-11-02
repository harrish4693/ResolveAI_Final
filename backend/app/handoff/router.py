from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, case, func
from sqlalchemy.orm import noload, joinedload, selectinload
import logging
import time
from typing import List, Optional, Dict, Any, Tuple

logger = logging.getLogger(__name__)

from app.database import get_db
from app.auth.deps import get_current_user
from app.users.models import User
from app.shared.models import UserRole, HandoffStatus, WorkflowState, ConversationStatus, SenderType, Priority
from app.handoff.models import Handoff
from app.handoff.schemas import (
    HandoffRead,
    HandoffAssignRequest,
    HandoffResolveRequest,
    HandoffStats,
    HandoffContextResponse,
    IncidentContextRead,
    FailureRiskRead,
)
from app.conversations.models import Conversation
from app.feedback.models import Feedback
from app.experts.models import Expert

# WebSocket imports
from app.websockets.manager import manager
from app.websockets.events import (
    conversation_updated_event,
    queue_updated_event,
    new_message_event,
)

# In-memory TTL cache for cross-ticket incident mapping and context
_INCIDENT_MAP_CACHE: Dict[str, Tuple[float, Dict[int, Dict[str, Any]]]] = {}
_INCIDENT_FULL_CACHE: Dict[str, Tuple[float, List[Any], Dict[int, Tuple[str, Any]]]] = {}
_INCIDENT_CACHE_TTL_SECONDS = 30.0

def invalidate_incident_map_cache(tenant_id: str = "default"):
    """Invalidates cached incident-to-ticket mappings and full context."""
    _INCIDENT_MAP_CACHE.pop(tenant_id, None)
    _INCIDENT_FULL_CACHE.pop(tenant_id, None)
    try:
        from app.analytics.router import invalidate_incident_analytics_cache
        invalidate_incident_analytics_cache(tenant_id)
    except Exception:
        pass


async def _get_or_compute_tenant_incidents(
    db: AsyncSession,
    tenant_id: str = "default"
) -> Tuple[List[Any], Dict[int, Dict[str, Any]], Dict[int, Tuple[str, Any]]]:
    """
    Returns (detected_incidents, incident_map, ticket_subject_map) cached for tenant_id.
    Prevents duplicate expensive TF-IDF clustering across multiple endpoints.
    """
    now_mono = time.monotonic()
    cached_full = _INCIDENT_FULL_CACHE.get(tenant_id)
    cached_map = _INCIDENT_MAP_CACHE.get(tenant_id)
    if (
        cached_full
        and cached_map
        and (now_mono - cached_full[0] < _INCIDENT_CACHE_TTL_SECONDS)
        and (now_mono - cached_map[0] < _INCIDENT_CACHE_TTL_SECONDS)
    ):
        return cached_full[1], cached_map[1], cached_full[2]

    from app.tickets.models import Ticket
    from app.ai.intelligence.incidents import IncidentDetector, TicketSnapshot
    from app.ai.incident_service import IncidentPersistenceService

    recent_tickets_res = await db.execute(
        select(Ticket.id, Ticket.subject, Ticket.category, Ticket.created_at, Ticket.customer_id, Ticket.status)
        .order_by(Ticket.created_at.desc())
        .limit(100)
    )
    recent_tickets = recent_tickets_res.all()

    ticket_subject_map: Dict[int, Tuple[str, Any]] = {}
    snapshots = []
    for t_id, t_subj, t_cat, t_created, t_cust_id, t_stat in recent_tickets:
        ticket_subject_map[t_id] = (t_subj or f"Ticket #{t_id}", t_created)
        snapshots.append(
            TicketSnapshot(
                ticket_id=t_id,
                subject=t_subj or "",
                category=t_cat or "General",
                created_at=t_created,
                customer_id=t_cust_id,
                tenant_id=tenant_id,
                status=str(t_stat.value if hasattr(t_stat, "value") else t_stat),
            )
        )

    detector = IncidentDetector()
    detected_incidents = detector.detect_incidents(snapshots, tenant_id=tenant_id)
    detected_incidents = await IncidentPersistenceService.reconcile_hypotheses(db, detected_incidents, tenant_id=tenant_id)

    incident_map: Dict[int, Dict[str, Any]] = {}
    for inc in detected_incidents:
        for tid in inc.affected_tickets:
            incident_map[tid] = {
                "incident_id": inc.incident_id,
                "is_confirmed": inc.status in ("confirmed", "investigating"),
                "severity": inc.severity,
            }

    _INCIDENT_MAP_CACHE[tenant_id] = (now_mono, incident_map)
    _INCIDENT_FULL_CACHE[tenant_id] = (now_mono, detected_incidents, ticket_subject_map)

    return detected_incidents, incident_map, ticket_subject_map

router = APIRouter(tags=["handoffs"])

async def _get_expert_assign_id(db: AsyncSession, user_id: int) -> int:
    expert = await db.scalar(select(Expert).where(Expert.user_id == user_id))
    if not expert:
        expert = Expert(user_id=user_id, is_available=True)
        db.add(expert)
        await db.flush()
    return expert.id

async def _get_expert_ids(db: AsyncSession, user_id: int) -> list[int]:
    expert = await db.scalar(select(Expert).where(Expert.user_id == user_id))
    return [user_id, expert.id] if expert else [user_id]


@router.get("/queue", response_model=List[HandoffRead])
async def get_queue(
    limit: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    logger.info(">>> [API] GET /queue called with limit=%s (type=%s)", limit, type(limit))
    if current_user.role not in [UserRole.EXPERT, UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Avoid cascading selectin loads on conversation and message models while preserving conversation channel
    result = await db.execute(
        select(Handoff, Conversation.channel)
        .outerjoin(Conversation, Handoff.conversation_id == Conversation.id)
        .options(noload(Handoff.conversation))
        .where(Handoff.status == HandoffStatus.WAITING)
    )
    rows = result.all()
    if not rows:
        return []

    # Cross-ticket incident context lookup to factor into priority ranking
    # Cached with a 30s TTL to prevent expensive duplicate clustering on every poll/mount
    incident_map: Dict[int, Dict[str, Any]] = {}
    tenant_id = getattr(current_user, "tenant_id", "default") or "default"
    try:
        _, incident_map, _ = await _get_or_compute_tenant_incidents(db, tenant_id=tenant_id)
    except Exception as e:
        logger.warning("Error computing incidents for queue ranking: %s", e)

    # Deterministic Prioritization Policy:
    # 1. Base Priority: CRITICAL (100) > HIGH (200) > MEDIUM (300) > LOW (400)
    # 2. Incident Impact: Confirmed Incident (-30), Candidate Incident (-15)
    # 3. Failure Risk: VERY_HIGH (-20), HIGH (-15), MODERATE (-5), Reported Solution Failed (-10)
    # 4. Tie-breaking: Deterministic FIFO (created_at ASC)
    ranked_items = []
    for h, conv_channel in rows:
        conv_channel_str = (
            conv_channel.value if hasattr(conv_channel, "value")
            else (str(conv_channel) if conv_channel else "text")
        )
        h.channel = conv_channel_str
        meta = h.ai_analysis if (h.ai_analysis and isinstance(h.ai_analysis, dict)) else {}
        fr_meta = meta.get("failure_risk") if isinstance(meta.get("failure_risk"), dict) else {}
        
        # Risk fields
        risk_level = fr_meta.get("likelihood") or fr_meta.get("risk_level") or "LOW"
        risk_prob = float(fr_meta.get("probability", 0.0))
        pred_diff = fr_meta.get("predicted_difficulty") or "LOW"
        signals = list(fr_meta.get("reasons") or fr_meta.get("signals") or [])
        obs_fail_count = int(fr_meta.get("observed_failure_count", 0))
        prior_failed = bool(fr_meta.get("has_prior_solution_failed", False))
        suggested_action = fr_meta.get("suggested_action") or fr_meta.get("recommendation") or "Review case context"
        
        # Incident association
        inc_info = incident_map.get(h.ticket_id) or incident_map.get(h.conversation_id)
        incident_id = inc_info.get("incident_id") if inc_info else None
        is_confirmed_inc = inc_info.get("is_confirmed", False) if inc_info else False

        # Priority base score
        p_val = h.priority.value if hasattr(h.priority, 'value') else str(h.priority)
        p_val_upper = p_val.upper()
        if p_val_upper == "CRITICAL":
            base_score = 100
        elif p_val_upper == "HIGH":
            base_score = 200
        elif p_val_upper == "MEDIUM":
            base_score = 300
        else:
            base_score = 400

        # Adjustments
        adjustments = 0
        reasons = []
        if is_confirmed_inc:
            adjustments -= 30
            reasons.append("Active confirmed incident cluster")
        elif incident_id:
            adjustments -= 15
            reasons.append(f"Associated with candidate incident {incident_id}")

        if risk_level in ("HIGH", "VERY_HIGH"):
            adjustments -= 15
            reasons.append("High resolution failure risk")
        elif risk_level == "MODERATE":
            adjustments -= 5
            reasons.append("Moderate failure risk")

        if prior_failed:
            adjustments -= 10
            reasons.append("Customer reported previous solution failed")

        if not reasons:
            reasons.append("Standard priority queue ordering (FIFO)")

        rank = base_score + adjustments
        rationale = "; ".join(reasons)

        ranked_items.append({
            "handoff": h,
            "rank": rank,
            "created_at": h.created_at,
            "failure_risk_level": risk_level,
            "failure_probability": risk_prob,
            "predicted_difficulty": pred_diff,
            "warning_signals": signals,
            "observed_failure_count": obs_fail_count,
            "has_prior_solution_failed": prior_failed,
            "suggested_next_action": suggested_action,
            "priority_rationale": rationale,
            "incident_id": incident_id,
        })

    # Sort deterministically by rank ascending, then created_at ascending
    ranked_items.sort(key=lambda x: (x["rank"], x["created_at"]))
    if limit is not None and limit > 0:
        ranked_items = ranked_items[:limit]
    logger.info(">>> [API] GET /queue returning %d items (limit was %s)", len(ranked_items), limit)

    response_items = []
    for item in ranked_items:
        h = item["handoff"]
        item_dict = {
            "id": h.id,
            "conversation_id": h.conversation_id,
            "category": h.category,
            "escalation_reason": h.escalation_reason,
            "priority": h.priority,
            "assigned_expert_id": h.assigned_expert_id,
            "status": h.status,
            "resolution_message": getattr(h, "resolution_message", None),
            "created_at": h.created_at,
            "updated_at": h.updated_at,
            "failure_risk_level": item["failure_risk_level"],
            "failure_probability": item["failure_probability"],
            "predicted_difficulty": item["predicted_difficulty"],
            "warning_signals": item["warning_signals"],
            "observed_failure_count": item["observed_failure_count"],
            "has_prior_solution_failed": item["has_prior_solution_failed"],
            "suggested_next_action": item["suggested_next_action"],
            "priority_rationale": item["priority_rationale"],
            "incident_id": item["incident_id"],
            "priority_rank": item["rank"],
            "channel": h.channel if hasattr(h, "channel") else "text",
        }
        response_items.append(HandoffRead.model_validate(item_dict))

    return response_items


@router.get("/stats", response_model=HandoffStats)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role not in [UserRole.EXPERT, UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    expert_ids = await _get_expert_ids(db, current_user.id)

    # Combined single query for queue size, active chats, and resolved count
    stats_stmt = select(
        func.count(case((Handoff.status == HandoffStatus.WAITING, 1))),
        func.count(case(((Handoff.status == HandoffStatus.ASSIGNED) & (Handoff.assigned_expert_id.in_(expert_ids)), 1))),
        func.count(case(((Handoff.status == HandoffStatus.RESOLVED) & (Handoff.assigned_expert_id.in_(expert_ids)), 1))),
    )
    stats_res = await db.execute(stats_stmt)
    row = stats_res.one()
    queue_size = row[0] or 0
    active_chats = row[1] or 0
    resolved_count = row[2] or 0
    
    # Average CSAT for this expert's resolved handoffs
    csat_res = await db.execute(
        select(func.avg(Feedback.rating))
        .join(Handoff, Handoff.conversation_id == Feedback.conversation_id)
        .where(Handoff.status == HandoffStatus.RESOLVED)
        .where(Handoff.assigned_expert_id.in_(expert_ids))
    )
    average_csat = csat_res.scalar()
    
    if average_csat is not None:
        average_csat = round(float(average_csat), 1)
        
    return HandoffStats(
        queue_size=queue_size,
        active_chats=active_chats,
        resolved_count=resolved_count,
        average_csat=average_csat
    )


@router.post("/{handoff_id}/assign", response_model=HandoffRead)
async def assign_handoff(
    handoff_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role not in [UserRole.EXPERT, UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    expert_assign_id = await _get_expert_assign_id(db, current_user.id)

    # Atomic assignment: Only update if status is WAITING
    stmt = (
        update(Handoff)
        .where(Handoff.id == handoff_id)
        .where(Handoff.status == HandoffStatus.WAITING)
        .values(
            status=HandoffStatus.ASSIGNED,
            assigned_expert_id=expert_assign_id
        )
    )
    result = await db.execute(stmt)
    
    if result.rowcount == 0:
        # Either doesn't exist, or already assigned
        handoff = await db.scalar(
        select(Handoff)
        .options(selectinload(Handoff.conversation))
        .where(Handoff.id == handoff_id)
    )
        if not handoff:
            raise HTTPException(status_code=404, detail="Handoff not found")
        raise HTTPException(status_code=409, detail="Handoff already assigned")
        
    await db.commit()
    
    # Update conversation workflow state
    handoff = await db.scalar(
        select(Handoff)
        .options(selectinload(Handoff.conversation))
        .where(Handoff.id == handoff_id)
    )
    conversation = await db.scalar(select(Conversation).where(Conversation.id == handoff.conversation_id))
    if conversation:
        conversation.workflow_state = WorkflowState.WITH_EXPERT
        await db.commit()

        # ── WebSocket: notify customer that expert joined ──
        await manager.send_to_user(
            conversation.customer_id,
            conversation_updated_event(
                conversation_id=conversation.id,
                status=conversation.status.value if hasattr(conversation.status, 'value') else str(conversation.status),
                workflow_state="with_expert",
            ),
        )

    # ── WebSocket: notify experts that queue changed ──
    await manager.broadcast_to_experts(
        queue_updated_event(
            action="CLAIMED",
            handoff_id=handoff.id,
            priority=handoff.priority,
            category=handoff.category,
        )
    )
    invalidate_incident_map_cache(getattr(current_user, "tenant_id", "default") or "default")

    if handoff.conversation:
        ch_val = handoff.conversation.channel.value if hasattr(handoff.conversation.channel, "value") else str(handoff.conversation.channel)
        handoff.channel = ch_val
    
    return handoff

@router.post("/{handoff_id}/resolve", response_model=HandoffRead)
async def resolve_handoff(
    handoff_id: int,
    request: HandoffResolveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role not in [UserRole.EXPERT, UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    if not request.resolution_message or not request.resolution_message.strip():
        raise HTTPException(status_code=400, detail="Resolution message is required")
        
    handoff = await db.scalar(
        select(Handoff)
        .options(selectinload(Handoff.conversation))
        .where(Handoff.id == handoff_id)
    )
    if not handoff:
        raise HTTPException(status_code=404, detail="Handoff not found")
        
    expert_ids = await _get_expert_ids(db, current_user.id)
    if handoff.assigned_expert_id not in expert_ids and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized to resolve this handoff")
        
    handoff.status = HandoffStatus.RESOLVED
    
    # Send resolution message to conversation
    from app.conversations.models import ConversationMessage
    resolution_msg = ConversationMessage(
        conversation_id=handoff.conversation_id,
        sender_type=SenderType.EXPERT,
        content=f"Resolution: {request.resolution_message}"
    )
    db.add(resolution_msg)
    
    # Update conversation state
    conversation = await db.scalar(select(Conversation).where(Conversation.id == handoff.conversation_id))
    if conversation:
        conversation.workflow_state = WorkflowState.RESOLVED
        conversation.status = ConversationStatus.RESOLVED
        
    await db.commit()
    await db.refresh(handoff)
    await db.refresh(resolution_msg)

    # ── WebSocket: broadcast resolution message to customer ──
    if conversation:
        await manager.send_to_user(
            conversation.customer_id,
            new_message_event(
                conversation_id=conversation.id,
                message_id=resolution_msg.id,
                sender_type="expert",
                content=resolution_msg.content,
                created_at=resolution_msg.created_at.isoformat(),
            ),
        )

        # ── WebSocket: notify customer that conversation is resolved ──
        await manager.send_to_user(
            conversation.customer_id,
            conversation_updated_event(
                conversation_id=conversation.id,
                status="resolved",
                workflow_state="resolved",
            ),
        )

    # ── WebSocket: notify experts that queue changed ──
    await manager.broadcast_to_experts(
        queue_updated_event(
            action="RESOLVED",
            handoff_id=handoff.id,
            priority=handoff.priority,
            category=handoff.category,
        )
    )
    invalidate_incident_map_cache(getattr(current_user, "tenant_id", "default") or "default")
    
    # ── Trigger asynchronous memory extraction ──
    if conversation:
        from app.memory.service import MemoryService
        from app.database import async_session_factory
        import asyncio

        async def background_extract():
            async with async_session_factory() as bg_db:
                await MemoryService.extract_memory(bg_db, conversation.id)

        asyncio.create_task(background_extract())
    
    if handoff.conversation:
        ch_val = handoff.conversation.channel.value if hasattr(handoff.conversation.channel, "value") else str(handoff.conversation.channel)
        handoff.channel = ch_val
    
    return handoff

@router.get("/conversation/{conversation_id}", response_model=HandoffRead)
async def get_handoff_by_conversation(
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get active handoff for a conversation."""
    if current_user.role not in [UserRole.EXPERT, UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    handoff = await db.scalar(
        select(Handoff)
        .options(selectinload(Handoff.conversation))
        .where(Handoff.conversation_id == conversation_id)
        .where(Handoff.status != HandoffStatus.RESOLVED)
    )
    if not handoff:
        raise HTTPException(status_code=404, detail="Active handoff not found")
        
    if handoff.conversation:
        ch_val = handoff.conversation.channel.value if hasattr(handoff.conversation.channel, "value") else str(handoff.conversation.channel)
        handoff.channel = ch_val
    
    return handoff

from app.handoff.schemas import HandoffTransferRequest

@router.post("/{handoff_id}/transfer", response_model=HandoffRead)
async def transfer_handoff(
    handoff_id: int,
    request: HandoffTransferRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role not in [UserRole.EXPERT, UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    handoff = await db.scalar(
        select(Handoff)
        .options(selectinload(Handoff.conversation))
        .where(Handoff.id == handoff_id)
    )
    if not handoff:
        raise HTTPException(status_code=404, detail="Handoff not found")
        
    expert_ids = await _get_expert_ids(db, current_user.id)
    if handoff.assigned_expert_id not in expert_ids and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized to transfer this handoff")
        
    conversation = await db.scalar(select(Conversation).where(Conversation.id == handoff.conversation_id))
        
    if request.expert_id is None:
        # Release to queue
        handoff.status = HandoffStatus.WAITING
        handoff.assigned_expert_id = None
        if conversation:
            conversation.workflow_state = WorkflowState.WAITING_FOR_EXPERT
    else:
        # Transfer to another expert
        if request.expert_id == current_user.id:
            raise HTTPException(status_code=400, detail="Cannot transfer to yourself")
            
        target_expert = await db.scalar(select(User).where(User.id == request.expert_id).where(User.role == UserRole.EXPERT).where(User.is_active == True))
        if not target_expert:
            target_expert_by_exp = await db.scalar(select(Expert).where(Expert.id == request.expert_id))
            if target_expert_by_exp:
                target_expert = await db.scalar(select(User).where(User.id == target_expert_by_exp.user_id).where(User.is_active == True))
        if not target_expert:
            raise HTTPException(status_code=400, detail="Target expert not found or inactive")
            
        target_assign_id = target_expert.id
        handoff.status = HandoffStatus.ASSIGNED
        handoff.assigned_expert_id = target_assign_id
        # State remains WITH_EXPERT
        
    await db.commit()
    await db.refresh(handoff)
    
    # Notify experts
    await manager.broadcast_to_experts(
        queue_updated_event(
            action="TRANSFERRED",
            handoff_id=handoff.id,
            priority=handoff.priority,
            category=handoff.category,
        )
    )
    
    if handoff.conversation:
        ch_val = handoff.conversation.channel.value if hasattr(handoff.conversation.channel, "value") else str(handoff.conversation.channel)
        handoff.channel = ch_val
    
    return handoff

async def _build_handoff_context(
    handoff: Handoff,
    db: AsyncSession,
    current_user: User
) -> dict:
    conversation = handoff.conversation
    if not conversation:
        conversation = await db.scalar(select(Conversation).where(Conversation.id == handoff.conversation_id))
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    customer = handoff.customer
    if not customer:
        customer = await db.scalar(select(User).where(User.id == conversation.customer_id))
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Fetch ticket history (past 5 conversations) - scalar columns only to avoid loading relationships
    history_res = await db.execute(
        select(Conversation.id, Conversation.status, Conversation.created_at)
        .where(Conversation.customer_id == customer.id)
        .where(Conversation.id != conversation.id)
        .order_by(Conversation.created_at.desc())
        .limit(5)
    )
    history_rows = history_res.all()

    # Fetch messages in a single query
    from app.conversations.models import ConversationMessage
    msgs_res = await db.execute(
        select(ConversationMessage.sender_type, ConversationMessage.content, ConversationMessage.metadata_)
        .where(ConversationMessage.conversation_id == conversation.id)
        .order_by(ConversationMessage.created_at.asc())
    )
    all_msgs = msgs_res.all()

    ai_msgs_meta = []
    ai_msgs_content = []
    cust_msg = None
    for sender_type, content, meta in all_msgs:
        if sender_type == SenderType.AI:
            if meta and isinstance(meta, dict):
                ai_msgs_meta.append(meta)
            if content:
                ai_msgs_content.append(content)
        elif sender_type == SenderType.CUSTOMER:
            cust_msg = content

    # Safely merge metadata from handoff and AI messages
    merged_meta: dict = {}
    if handoff.ai_analysis and isinstance(handoff.ai_analysis, dict):
        merged_meta.update(handoff.ai_analysis)

    for meta in ai_msgs_meta:
        for k, v in meta.items():
            if v is not None:
                merged_meta[k] = v

    intent = merged_meta.get("intent") or "Unknown"
    sentiment = merged_meta.get("sentiment") or "Neutral"
    summary = merged_meta.get("summary") or handoff.ai_summary or handoff.escalation_reason or "No AI summary available"

    # Extract language context
    detected_language = merged_meta.get("language") or merged_meta.get("detected_language")
    is_code_mixed = bool(merged_meta.get("is_code_mixed", False))
    code_mix_type = merged_meta.get("code_mix_type")
    normalized_message = merged_meta.get("normalized_message")
    original_message = merged_meta.get("original_message") or cust_msg
    negation_detected = bool(merged_meta.get("negation_detected", False))
    normalized_search_query = merged_meta.get("normalized_search_query")

    language_context = None
    if detected_language or is_code_mixed or normalized_message:
        language_context = {
            "detected_language": str(detected_language) if detected_language else None,
            "is_code_mixed": is_code_mixed,
            "code_mix_type": str(code_mix_type) if code_mix_type else None,
            "normalized_message": str(normalized_message) if normalized_message else None,
            "original_message": str(original_message) if original_message else None,
            "negation_detected": negation_detected,
            "normalized_search_query": str(normalized_search_query) if normalized_search_query else None,
        }

    # Extract confidence score (only genuine numeric value, do not fabricate)
    raw_confidence = merged_meta.get("confidence_score")
    if raw_confidence is None:
        raw_confidence = merged_meta.get("confidence")

    confidence_score = None
    if raw_confidence is not None:
        try:
            val = float(raw_confidence)
            if 0.0 <= val <= 1.0 and val > 0:
                val = round(val * 100, 1)
            else:
                val = round(val, 1)
            confidence_score = val
        except (ValueError, TypeError):
            confidence_score = None

    autonomy_meta = merged_meta.get("autonomy") or {}
    autonomy_mode = autonomy_meta.get("mode") if isinstance(autonomy_meta, dict) else None

    ai_context = {
        "intent": intent,
        "sentiment": sentiment,
        "summary": summary,
        "language_context": language_context,
        "confidence_score": confidence_score,
        "autonomy_mode": autonomy_mode,
    }

    # Cross-Ticket Incident Discovery (Reuses tenant cache to prevent expensive repeated clustering)
    incident_context = None
    try:
        tenant_id = getattr(customer, "tenant_id", "default") or "default"
        detected_incidents, _, ticket_subject_map = await _get_or_compute_tenant_incidents(db, tenant_id=tenant_id)

        target_ticket_id = handoff.ticket_id or (handoff.ticket.id if handoff.ticket else conversation.id)
        matching_inc = next((inc for inc in detected_incidents if target_ticket_id in inc.affected_tickets), None)

        if matching_inc:
            related_list = []
            for tid in matching_inc.affected_tickets:
                if tid != target_ticket_id:
                    sub, c_at = ticket_subject_map.get(tid, (f"Ticket #{tid}", None))
                    related_list.append({
                        "id": tid,
                        "subject": sub,
                        "created_at": c_at.isoformat() if c_at and hasattr(c_at, "isoformat") else None,
                    })

            incident_context = {
                "incident_id": matching_inc.incident_id,
                "title": matching_inc.title,
                "description": matching_inc.description,
                "category": matching_inc.category,
                "status": matching_inc.status,
                "severity": matching_inc.severity,
                "confidence": matching_inc.confidence,
                "related_ticket_count": len(matching_inc.affected_tickets),
                "related_tickets": related_list,
                "time_window_start": matching_inc.time_window_start.isoformat() if matching_inc.time_window_start else None,
                "time_window_end": matching_inc.time_window_end.isoformat() if matching_inc.time_window_end else None,
                "evidence": matching_inc.evidence,
                "is_spike": matching_inc.is_spike,
                "spike_ratio": matching_inc.spike_ratio,
            }
    except Exception as e:
        logger.warning("Error computing incident context for handoff %s: %s", handoff.id, e)
        incident_context = None

    # Failure Risk & Proactive Escalation Context
    failure_risk = None
    raw_fr = merged_meta.get("failure_risk")
    if raw_fr and isinstance(raw_fr, dict):
        failure_risk = {
            "risk_level": raw_fr.get("likelihood") or raw_fr.get("risk_level") or "LOW",
            "probability": float(raw_fr.get("probability", 0.0)),
            "predicted_difficulty": raw_fr.get("predicted_difficulty") or "LOW",
            "signals": list(raw_fr.get("reasons") or raw_fr.get("signals") or []),
            "observed_failure_count": int(raw_fr.get("observed_failure_count", 0)),
            "has_prior_solution_failed": bool(raw_fr.get("has_prior_solution_failed", False)),
            "suggested_action": raw_fr.get("suggested_action") or raw_fr.get("recommendation"),
            "priority_rationale": raw_fr.get("priority_rationale"),
        }
    else:
        # Fallback evaluation for cases without precomputed failure_risk
        try:
            from app.ai.intelligence.failure_prediction import FailurePredictor
            predictor = FailurePredictor()
            pred = predictor.predict(
                analysis={
                    "intent": intent,
                    "sentiment": sentiment,
                    "original_message": cust_msg or "",
                    "category": handoff.category,
                },
                context={
                    "history": [{"content": c} for c in ai_msgs_content],
                    "ticket_history": [{"category": row[1]} for row in history_rows],
                },
                conversation_id=conversation.id,
            )
            failure_risk = {
                "risk_level": pred.likelihood.value,
                "probability": pred.probability,
                "predicted_difficulty": pred.predicted_difficulty,
                "signals": pred.reasons,
                "observed_failure_count": pred.observed_failure_count,
                "has_prior_solution_failed": pred.has_prior_solution_failed,
                "suggested_action": pred.suggested_action,
                "priority_rationale": None,
            }
        except Exception as e:
            logger.warning("Error evaluating fallback failure risk for handoff %s: %s", handoff.id, e)
            failure_risk = {
                "risk_level": "LOW",
                "probability": 0.0,
                "predicted_difficulty": "LOW",
                "signals": [],
                "observed_failure_count": 0,
                "has_prior_solution_failed": False,
                "suggested_action": "Review case context",
                "priority_rationale": None,
            }

    cust_name = getattr(customer, "full_name", None) or getattr(customer, "name", None) or "Customer"
    account_status = getattr(customer, "account_status", "Active")

    return {
        "customer": {
            "id": customer.id,
            "name": cust_name,
            "email": customer.email,
            "account_status": account_status,
        },
        "active_ticket": {
            "id": conversation.id,
            "category": handoff.category,
            "priority": handoff.priority.value if hasattr(handoff.priority, 'value') else str(handoff.priority),
            "reason": handoff.escalation_reason,
            "channel": conversation.channel.value if hasattr(conversation.channel, 'value') else str(conversation.channel),
        },
        "ai_context": ai_context,
        "language_context": language_context,
        "confidence_score": confidence_score,
        "incident_context": incident_context,
        "failure_risk": failure_risk,
        "ticket_history": [
            {
                "id": c_id,
                "status": c_stat.value if hasattr(c_stat, 'value') else str(c_stat),
                "created_at": c_date.isoformat(),
            } for c_id, c_stat, c_date in history_rows
        ],
    }


@router.get("/{handoff_id}/context", response_model=HandoffContextResponse)
async def get_handoff_context(
    handoff_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role not in [UserRole.EXPERT, UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    handoff = await db.scalar(
        select(Handoff)
        .options(
            joinedload(Handoff.customer),
            joinedload(Handoff.ticket),
            joinedload(Handoff.conversation).noload(Conversation.messages),
        )
        .where(Handoff.id == handoff_id)
    )
    if not handoff:
        raise HTTPException(status_code=404, detail="Handoff not found")
        
    if current_user.role != UserRole.ADMIN:
        expert_ids = await _get_expert_ids(db, current_user.id)
        if handoff.assigned_expert_id not in expert_ids and handoff.status != HandoffStatus.WAITING:
            raise HTTPException(status_code=403, detail="Not authorized to view context for this handoff")

    return await _build_handoff_context(handoff, db, current_user)


@router.get("/conversation/{conversation_id}/context", response_model=HandoffContextResponse)
async def get_handoff_context_by_conversation(
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Fetch handoff context directly by conversation_id."""
    if current_user.role not in [UserRole.EXPERT, UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    handoff = await db.scalar(
        select(Handoff)
        .options(
            joinedload(Handoff.customer),
            joinedload(Handoff.ticket),
            joinedload(Handoff.conversation).noload(Conversation.messages),
        )
        .where(Handoff.conversation_id == conversation_id)
        .where(Handoff.status != HandoffStatus.RESOLVED)
    )
    if not handoff:
        handoff = await db.scalar(
            select(Handoff)
            .options(
                joinedload(Handoff.customer),
                joinedload(Handoff.ticket),
                joinedload(Handoff.conversation).noload(Conversation.messages),
            )
            .where(Handoff.conversation_id == conversation_id)
            .order_by(Handoff.id.desc())
        )
    if not handoff:
        raise HTTPException(status_code=404, detail="Handoff not found for conversation")
        
    if current_user.role != UserRole.ADMIN:
        expert_ids = await _get_expert_ids(db, current_user.id)
        if handoff.assigned_expert_id not in expert_ids and handoff.status != HandoffStatus.WAITING:
            raise HTTPException(status_code=403, detail="Not authorized to view context for this handoff")

    return await _build_handoff_context(handoff, db, current_user)


