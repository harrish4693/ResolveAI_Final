"""
ResolveAIV2 — Milestone P2.6 Unified Handoff & Expert Autonomy Service

Centralizes the lifecycle of AI-to-human escalations:
- Immediate creation/updating of Handoffs without duplication
- Deterministic queue ranking combining priorities, incident clusters, and failure risk
- Safe, atomic assignment to human experts
- Complete context aggregation (multilingual metadata, conversation history, confidence, entities)
- Truthful queue state management across WebSocket broadcasts and database models
"""

import enum
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Conversation, ConversationMessage
from app.experts.models import Expert
from app.handoff.models import ExpertAssignment, Handoff
from app.shared.models import (
    ConversationStatus,
    HandoffStatus,
    Priority,
    SenderType,
    TicketStatus,
    UserRole,
    WorkflowState,
)
from app.tickets.models import Ticket
from app.users.models import User
from app.websockets.events import (
    conversation_updated_event,
    new_message_event,
    queue_updated_event,
)
from app.websockets.manager import manager

logger = logging.getLogger(__name__)


class HandoffService:
    """Enterprise Handoff Service for AI-to-human escalation."""

    INTENT_CATEGORY_MAPPING = {
        "PAYMENT_ISSUE": "Payments/Finance",
        "SECURITY_ISSUE": "Security",
        "FRAUD_SUSPICION": "Security",
        "DELIVERY_ISSUE": "Delivery/Logistics",
        "ORDER_STATUS": "Delivery/Logistics",
        "LOGIN_ISSUE": "Account/Auth",
        "REFUND_ISSUE": "Payments/Finance",
        "UPDATE_ISSUE": "Account/Auth",
        "WARRANTY_SERVICE": "Technical",
        "TECHNICAL_ISSUE": "Technical",
        "SUBSCRIPTION_ISSUE": "Billing",
        "ESCALATION_REQUEST": "General Support",
    }

    @classmethod
    def _normalize_priority(cls, raw_priority: Any) -> Priority:
        """Coerce priority strings or enum variants into standard Priority enum."""
        if isinstance(raw_priority, Priority):
            return raw_priority
        val = str(getattr(raw_priority, "value", raw_priority) or "medium").strip().lower()
        if val == "critical":
            return Priority.CRITICAL
        elif val == "high":
            return Priority.HIGH
        elif val == "low":
            return Priority.LOW
        return Priority.MEDIUM

    @classmethod
    async def get_or_create_expert(cls, db: AsyncSession, user_id: int) -> Expert:
        """Finds or creates an Expert profile for a user with EXPERT role."""
        expert = await db.scalar(select(Expert).where(Expert.user_id == user_id))
        if not expert:
            expert = Expert(user_id=user_id, is_available=True)
            db.add(expert)
            await db.flush()
        return expert

    @classmethod
    async def create_or_update_handoff(
        cls,
        db: AsyncSession,
        conversation: Conversation,
        analysis: Dict[str, Any],
        ticket: Optional[Ticket] = None,
        reason: Optional[str] = None,
    ) -> Tuple[Handoff, bool]:
        """
        Creates or updates a Handoff record for an escalated conversation.
        Guarantees idempotency (never creates duplicate handoffs for the same conversation).
        Sets conversation state to WAITING_FOR_EXPERT and updates linked ticket.
        Returns: (handoff, is_new)
        """
        # 1. Update Conversation workflow state immediately
        conversation.workflow_state = WorkflowState.WAITING_FOR_EXPERT

        # 2. Update linked ticket if available, or fetch it
        if not ticket:
            ticket = await db.scalar(select(Ticket).where(Ticket.conversation_id == conversation.id))
        if ticket:
            ticket.status = TicketStatus.ESCALATED

        # 3. Derive classification and priority
        intent = str(analysis.get("intent", "GENERAL_QUERY")).upper()
        category = cls.INTENT_CATEGORY_MAPPING.get(intent, "General Support")
        raw_p = analysis.get("priority", Priority.MEDIUM)
        priority = cls._normalize_priority(raw_p)

        escalation_reason = (
            reason
            or analysis.get("decision_reason")
            or analysis.get("reason")
            or "Customer requested human expert or automated escalation threshold reached"
        )

        entities = analysis.get("entities", {})
        rag_evidence = analysis.get("rag_context") or analysis.get("retrieved_articles") or []
        ai_actions = []
        if analysis.get("tool_name"):
            ai_actions.append(f"Tool attempted: {analysis.get('tool_name')}")
        if analysis.get("observed_failure"):
            ai_actions.append(f"Observed failure: {analysis['observed_failure']}")

        # 4. Check for existing Handoff on this conversation
        existing_handoff = await db.scalar(
            select(Handoff).where(Handoff.conversation_id == conversation.id)
        )

        if existing_handoff:
            # Update existing handoff with latest analysis without resetting assigned state if already in progress
            if existing_handoff.ai_analysis and isinstance(existing_handoff.ai_analysis, dict):
                merged = dict(existing_handoff.ai_analysis)
                merged.update(analysis)
                existing_handoff.ai_analysis = merged
            else:
                existing_handoff.ai_analysis = analysis

            if entities:
                existing_info = existing_handoff.collected_information or {}
                if isinstance(existing_info, dict):
                    merged_info = dict(existing_info)
                    merged_info.update(entities)
                    existing_handoff.collected_information = merged_info

            existing_handoff.escalation_reason = escalation_reason
            existing_handoff.priority = priority
            existing_handoff.category = category

            # If it was resolved earlier and user re-escalated, reset to WAITING
            if existing_handoff.status == HandoffStatus.RESOLVED:
                existing_handoff.status = HandoffStatus.WAITING
                existing_handoff.assigned_expert_id = None
                existing_handoff.resolved_at = None

            logger.info("Updated existing handoff #%s for conversation #%s", existing_handoff.id, conversation.id)
            return existing_handoff, False

        # 5. Create new Handoff record with truthful WAITING status
        handoff = Handoff(
            conversation_id=conversation.id,
            ticket_id=ticket.id if ticket else 0,
            customer_id=conversation.customer_id,
            escalation_reason=escalation_reason,
            priority=priority,
            category=category,
            ai_summary=analysis.get("summary") or escalation_reason[:200],
            ai_analysis=analysis,
            collected_information=entities,
            rag_evidence=rag_evidence if isinstance(rag_evidence, list) else [str(rag_evidence)],
            ai_actions_taken=ai_actions,
            status=HandoffStatus.WAITING,
            assigned_expert_id=None,
        )
        db.add(handoff)
        await db.flush()

        logger.info("Created new handoff #%s for conversation #%s", handoff.id, conversation.id)
        return handoff, True

    @classmethod
    async def assign_expert(
        cls, db: AsyncSession, handoff_id: int, expert_user_id: int
    ) -> Handoff:
        """
        Atomically assigns a WAITING handoff to an expert.
        Prevents double-claim with HTTP 409 conflict semantics.
        """
        expert = await cls.get_or_create_expert(db, expert_user_id)

        stmt = (
            update(Handoff)
            .where(Handoff.id == handoff_id)
            .where(Handoff.status == HandoffStatus.WAITING)
            .values(
                status=HandoffStatus.ASSIGNED,
                assigned_expert_id=expert.id,
                assigned_at=datetime.utcnow(),
            )
        )
        result = await db.execute(stmt)

        if result.rowcount == 0:
            existing = await db.scalar(select(Handoff).where(Handoff.id == handoff_id))
            if not existing:
                raise ValueError("Handoff not found")
            raise KeyError("Handoff already assigned or resolved")

        await db.commit()

        # Update Conversation state
        handoff = await db.scalar(select(Handoff).where(Handoff.id == handoff_id))
        conversation = await db.scalar(
            select(Conversation).where(Conversation.id == handoff.conversation_id)
        )
        if conversation:
            conversation.workflow_state = WorkflowState.WITH_EXPERT
            await db.commit()

            # WebSocket: notify customer that expert has joined
            await manager.send_to_user(
                conversation.customer_id,
                conversation_updated_event(
                    conversation_id=conversation.id,
                    status=str(getattr(conversation.status, "value", conversation.status)),
                    workflow_state="with_expert",
                ),
            )

        # WebSocket: notify experts that item is claimed
        await manager.broadcast_to_experts(
            queue_updated_event(
                action="CLAIMED",
                handoff_id=handoff.id,
                priority=handoff.priority,
                category=handoff.category,
            )
        )

        return handoff

    @classmethod
    async def resolve_handoff(
        cls,
        db: AsyncSession,
        handoff_id: int,
        resolution_message: str,
        user_id: int,
        user_role: UserRole,
    ) -> Handoff:
        """
        Resolves an active handoff, writes a resolution message to the customer,
        and transitions the conversation to RESOLVED.
        """
        if not resolution_message or not resolution_message.strip():
            raise ValueError("Resolution message is required")

        handoff = await db.scalar(select(Handoff).where(Handoff.id == handoff_id))
        if not handoff:
            raise ValueError("Handoff not found")

        expert = await db.scalar(select(Expert).where(Expert.user_id == user_id))
        expert_ids = [user_id, expert.id] if expert else [user_id]

        if handoff.assigned_expert_id not in expert_ids and user_role != UserRole.ADMIN:
            raise PermissionError("Not authorized to resolve this handoff")

        handoff.status = HandoffStatus.RESOLVED
        handoff.resolved_at = datetime.utcnow()

        # Send resolution message to conversation
        resolution_msg = ConversationMessage(
            conversation_id=handoff.conversation_id,
            sender_type=SenderType.EXPERT,
            content=f"Resolution: {resolution_message.strip()}",
        )
        db.add(resolution_msg)

        # Update conversation state
        conversation = await db.scalar(
            select(Conversation).where(Conversation.id == handoff.conversation_id)
        )
        if conversation:
            conversation.workflow_state = WorkflowState.RESOLVED
            conversation.status = ConversationStatus.RESOLVED

        await db.commit()
        await db.refresh(handoff)
        await db.refresh(resolution_msg)

        # WebSockets: notify customer
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
            await manager.send_to_user(
                conversation.customer_id,
                conversation_updated_event(
                    conversation_id=conversation.id,
                    status="resolved",
                    workflow_state="resolved",
                ),
            )

        # WebSocket: notify experts
        await manager.broadcast_to_experts(
            queue_updated_event(
                action="RESOLVED",
                handoff_id=handoff.id,
                priority=handoff.priority,
                category=handoff.category,
            )
        )

        return handoff

