from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException
from app.conversations.models import Conversation
from app.handoff.models import Handoff
from app.feedback.models import Feedback
from app.feedback.schemas import FeedbackCreate
from app.shared.models import ResolutionType, ConversationStatus, HandoffStatus

class FeedbackService:
    @staticmethod
    async def create_feedback(
        db: AsyncSession,
        conversation_id: int,
        customer_id: int,
        data: FeedbackCreate
    ) -> Feedback:
        # 1. Fetch conversation and handoff
        stmt = select(Conversation).where(Conversation.id == conversation_id)
        result = await db.execute(stmt)
        convo = result.scalar_one_or_none()

        if not convo or convo.customer_id != customer_id:
            raise HTTPException(status_code=404, detail="Conversation not found")

        if convo.status != ConversationStatus.RESOLVED:
            raise HTTPException(status_code=400, detail="Cannot leave feedback until conversation is resolved")

        # 2. Derive authoritative resolution type
        handoff_stmt = select(Handoff).where(Handoff.conversation_id == conversation_id)
        handoff_res = await db.execute(handoff_stmt)
        handoff = handoff_res.scalar_one_or_none()

        if handoff and handoff.status == HandoffStatus.RESOLVED and handoff.assigned_expert_id:
            res_type = ResolutionType.AI_ESCALATED_TO_HUMAN
        else:
            res_type = ResolutionType.AI

        # 3. Check duplicate (DB unique constraint will also enforce this, but providing a clean 409 is good API design)
        existing = await db.scalar(select(Feedback).where(Feedback.conversation_id == conversation_id))
        if existing:
            raise HTTPException(status_code=409, detail="Feedback already submitted for this conversation")

        from app.tickets.models import Ticket
        ticket = await db.scalar(select(Ticket).where(Ticket.conversation_id == conversation_id))
        actual_ticket_id = ticket.id if ticket else 0

        # 4. Insert feedback
        feedback = Feedback(
            conversation_id=conversation_id,
            ticket_id=actual_ticket_id,
            customer_id=customer_id,
            rating=data.rating,
            comment=data.comment,
            resolution_type=res_type
        )
        db.add(feedback)
        await db.commit()
        await db.refresh(feedback)
        
        return feedback

    @staticmethod
    async def get_feedback(
        db: AsyncSession,
        conversation_id: int,
        user_id: int,
        is_expert: bool = False
    ) -> Feedback | None:
        # Ensure conversation visibility first
        stmt = select(Conversation).where(Conversation.id == conversation_id)
        convo = await db.scalar(stmt)
        if not convo:
            raise HTTPException(status_code=404, detail="Conversation not found")
            
        if not is_expert and convo.customer_id != user_id:
            raise HTTPException(status_code=404, detail="Conversation not found")
            
        if is_expert:
            handoff = await db.scalar(select(Handoff).where(Handoff.conversation_id == conversation_id))
            if not handoff or handoff.assigned_expert_id != user_id:
                raise HTTPException(status_code=404, detail="Conversation not found")
                
        return await db.scalar(select(Feedback).where(Feedback.conversation_id == conversation_id))
