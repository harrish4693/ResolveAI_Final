from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import logging

from app.database import get_db
from app.auth.deps import get_current_user
from app.users.models import User
from app.conversations.models import Conversation, ConversationMessage
from app.conversations.schemas import (
    ConversationOut,
    ConversationCreate,
    ConversationUpdate,
    ConversationMessageOut,
    ConversationMessageCreate,
)
from app.conversations.service import ConversationService
from app.conversations.message_service import MessageService
from app.shared.models import UserRole, WorkflowState, SenderType, ConversationStatus
from app.handoff.models import Handoff
from app.experts.models import Expert

logger = logging.getLogger(__name__)

router = APIRouter(tags=["conversations"])

async def _get_expert_ids(db: AsyncSession, user_id: int) -> list[int]:
    expert = await db.scalar(select(Expert).where(Expert.user_id == user_id))
    return [user_id, expert.id] if expert else [user_id]


# Singleton service for dependency injection (or just instantiate it)
conversation_service = ConversationService()


@router.post("", response_model=ConversationOut)
async def create_conversation(
    data: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Creates a new conversation, linked ticket, and processes the initial message."""
    convo = await conversation_service.create_conversation(
        db=db,
        customer_id=current_user.id,
        initial_message=data.initial_message,
        subject=data.subject,
        channel=data.channel,
    )
    return convo


@router.get("", response_model=List[ConversationOut])
async def list_conversations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lists conversations: customer's own, expert's assigned handoffs, or all for admin."""
    if current_user.role == UserRole.CUSTOMER:
        stmt = (
            select(Conversation)
            .where(Conversation.customer_id == current_user.id)
            .order_by(Conversation.created_at.desc())
        )
    elif current_user.role == UserRole.ADMIN:
        stmt = (
            select(Conversation)
            .order_by(Conversation.created_at.desc())
        )
    else:
        # For experts, list conversations assigned to them via handoff
        expert_ids = await _get_expert_ids(db, current_user.id)
        stmt = (
            select(Conversation)
            .join(Handoff, Handoff.conversation_id == Conversation.id)
            .where(Handoff.assigned_expert_id.in_(expert_ids))
            .distinct()
            .order_by(Conversation.created_at.desc())
        )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{conversation_id}", response_model=ConversationOut)
async def get_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieves conversation details. Enforces ownership with a 404."""
    stmt = select(Conversation).where(Conversation.id == conversation_id)
    result = await db.execute(stmt)
    convo = result.scalar_one_or_none()

    if not convo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    if current_user.role == UserRole.CUSTOMER and convo.customer_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        
    if current_user.role == UserRole.EXPERT:
        handoff = await db.scalar(
            select(Handoff)
            .where(Handoff.conversation_id == conversation_id)
            .order_by(Handoff.created_at.desc())
        )
        expert_ids = await _get_expert_ids(db, current_user.id)
        if not handoff or handoff.assigned_expert_id not in expert_ids:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    return convo


@router.patch("/{conversation_id}", response_model=ConversationOut)
async def update_conversation(
    conversation_id: int,
    data: ConversationUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Updates conversation properties such as preferred language or subject."""
    from app.memory.service import MemoryService

    stmt = select(Conversation).where(Conversation.id == conversation_id)
    result = await db.execute(stmt)
    convo = result.scalar_one_or_none()

    if not convo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    if current_user.role == UserRole.CUSTOMER and convo.customer_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    if data.preferred_language is not None:
        convo.preferred_language = data.preferred_language.lower().strip()
        await MemoryService.save_memory(
            db=db,
            customer_id=convo.customer_id,
            content=f"Customer preferred language: {convo.preferred_language}",
            source="language_preference"
        )

    if data.subject is not None:
        convo.subject = data.subject

    await db.commit()
    await db.refresh(convo)
    return convo



@router.get("/{conversation_id}/messages", response_model=List[ConversationMessageOut])
async def list_messages(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lists messages for a conversation. Enforces ownership with a 404."""
    # Enforce ownership first
    stmt = select(Conversation).where(Conversation.id == conversation_id)
    result = await db.execute(stmt)
    convo = result.scalar_one_or_none()

    if not convo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    if current_user.role == UserRole.CUSTOMER and convo.customer_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        
    if current_user.role == UserRole.EXPERT:
        handoff = await db.scalar(
            select(Handoff)
            .where(Handoff.conversation_id == conversation_id)
            .order_by(Handoff.created_at.desc())
        )
        expert_ids = await _get_expert_ids(db, current_user.id)
        if not handoff or handoff.assigned_expert_id not in expert_ids:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    exclude_internal = (current_user.role == UserRole.CUSTOMER)
    return await MessageService.list_messages(db, conversation_id, exclude_internal=exclude_internal)


@router.post("/{conversation_id}/messages", response_model=List[ConversationMessageOut])
async def add_message(
    conversation_id: int,
    data: ConversationMessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Adds a customer message and triggers the AI response, 
    or adds an expert message directly.
    """
    logger.info("[API] Chat request received")
    logger.info(f"[API] User ID: {current_user.id}")
    logger.info(f"[API] Conversation ID: {conversation_id}")
    logger.info(f"[API] Message: {data.content}")
    
    stmt = select(Conversation).where(Conversation.id == conversation_id)
    result = await db.execute(stmt)
    convo = result.scalar_one_or_none()

    if not convo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        
    if current_user.role == UserRole.EXPERT:
        handoff = await db.scalar(select(Handoff).where(Handoff.conversation_id == conversation_id))
        expert_ids = await _get_expert_ids(db, current_user.id)
        if not handoff or handoff.assigned_expert_id not in expert_ids:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
            
        msg = await MessageService.create_message(
            db=db,
            conversation_id=convo.id,
            sender_type=SenderType.EXPERT,
            content=data.content,
            sender_id=current_user.id,
            metadata={"is_internal": True} if data.is_internal else None
        )
        await db.commit()
        
        from app.websockets.manager import manager
        from app.websockets.events import new_message_event
        await manager.send_to_conversation_participants(
            customer_id=convo.customer_id,
            expert_id=current_user.id,
            event=new_message_event(
                conversation_id=convo.id,
                message_id=msg.id,
                sender_type="expert",
                content=msg.content,
                created_at=msg.created_at.isoformat(),
            ),
            is_internal=data.is_internal
        )
    else:
        if convo.customer_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

        # Idempotency / Duplicate submission guard:
        # Ignore duplicate submissions with identical content within 2.0 seconds from the same customer
        latest_cust_msg = await db.scalar(
            select(ConversationMessage)
            .where(
                ConversationMessage.conversation_id == conversation_id,
                ConversationMessage.sender_type == SenderType.CUSTOMER,
            )
            .order_by(ConversationMessage.created_at.desc())
            .limit(1)
        )
        if latest_cust_msg and latest_cust_msg.content.strip() == data.content.strip():
            # Check elapsed time from the most recent activity in this conversation
            # (either the customer message or the immediate AI response)
            latest_any_msg = await db.scalar(
                select(ConversationMessage)
                .where(ConversationMessage.conversation_id == conversation_id)
                .order_by(ConversationMessage.created_at.desc())
                .limit(1)
            )
            msg_ref = latest_any_msg or latest_cust_msg
            import datetime
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            msg_time = msg_ref.created_at
            if msg_time.tzinfo is None:
                msg_time = msg_time.replace(tzinfo=datetime.timezone.utc)
            if (now_utc - msg_time).total_seconds() < 2.0:
                logger.warning(
                    f"Ignored duplicate customer message submission within 2s for conversation {conversation_id}"
                )
                exclude_internal = (current_user.role == UserRole.CUSTOMER)
                return await MessageService.list_messages(db, conversation_id, exclude_internal=exclude_internal)

        if convo.workflow_state in [WorkflowState.WAITING_FOR_EXPERT, WorkflowState.WITH_EXPERT]:
            # Add message but don't trigger AI response
            msg = await MessageService.create_message(
                db=db,
                conversation_id=convo.id,
                sender_type=SenderType.CUSTOMER,
                content=data.content,
                sender_id=current_user.id,
            )
            await db.commit()
            
            from app.websockets.manager import manager
            from app.websockets.events import new_message_event
            handoff = await db.scalar(select(Handoff).where(Handoff.conversation_id == conversation_id))
            expert_user_id = None
            if handoff and handoff.assigned_expert_id:
                expert_rec = await db.scalar(select(Expert).where(Expert.id == handoff.assigned_expert_id))
                if expert_rec:
                    expert_user_id = expert_rec.user_id
            
            await manager.send_to_conversation_participants(
                customer_id=convo.customer_id,
                expert_id=expert_user_id,
                event=new_message_event(
                    conversation_id=convo.id,
                    message_id=msg.id,
                    sender_type="customer",
                    content=msg.content,
                    created_at=msg.created_at.isoformat(),
                ),
            )
        else:
            logger.info("[API] Calling Conversation Service")
            await conversation_service.process_customer_message(
                db=db,
                conversation=convo,
                customer_id=current_user.id,
                message_content=data.content,
            )
            logger.info("[API] Conversation Service returned")

    # Return the full list of messages so the frontend can easily update state
    exclude_internal = (current_user.role == UserRole.CUSTOMER)
    return await MessageService.list_messages(db, conversation_id, exclude_internal=exclude_internal)


@router.post("/{conversation_id}/messages/voice", response_model=List[ConversationMessageOut])
async def add_voice_message(
    conversation_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Accepts a voice upload, processes STT, and triggers the AI voice response.
    """
    stmt = select(Conversation).where(Conversation.id == conversation_id)
    result = await db.execute(stmt)
    convo = result.scalar_one_or_none()

    if not convo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        
    if current_user.role == UserRole.EXPERT:
        raise HTTPException(status_code=403, detail="Experts cannot send voice messages yet")
        
    if convo.customer_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    if convo.workflow_state in [WorkflowState.WAITING_FOR_EXPERT, WorkflowState.WITH_EXPERT]:
        raise HTTPException(status_code=400, detail="Cannot use voice while with expert")

    try:
        await conversation_service.process_customer_voice_message(
            db=db,
            conversation=convo,
            customer_id=current_user.id,
            file=file,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    exclude_internal = (current_user.role == UserRole.CUSTOMER)
    return await MessageService.list_messages(db, conversation_id, exclude_internal=exclude_internal)


from pydantic import BaseModel

class ToolConfirmationRequest(BaseModel):
    action: str  # "accept" or "reject"

from fastapi import BackgroundTasks

@router.post("/{conversation_id}/tools/{execution_id}/confirm")
async def confirm_tool(
    conversation_id: int,
    execution_id: int,
    data: ToolConfirmationRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Conversation).where(Conversation.id == conversation_id)
    result = await db.execute(stmt)
    convo = result.scalar_one_or_none()
    if not convo or convo.customer_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        
    from app.ai.tools.models import ToolExecution
    exec_stmt = select(ToolExecution).where(
        ToolExecution.id == execution_id,
        ToolExecution.conversation_id == conversation_id
    )
    exec_result = await db.execute(exec_stmt)
    execution = exec_result.scalar_one_or_none()
    
    if not execution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool execution not found")
        
    if execution.customer_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot confirm another customer's execution")
        
    if data.action == "accept":
        execution.confirmed = True
        from datetime import datetime, timezone
        execution.confirmed_at = datetime.now(timezone.utc)
        await db.commit()
        
        from app.database import async_session_factory
        async def background_resume():
            async with async_session_factory() as bg_db:
                await conversation_service.resume_tool_execution(
                    db=bg_db, 
                    conversation_id=conversation_id, 
                    execution_id=execution_id
                )
                
        background_tasks.add_task(background_resume)
    else:
        from app.ai.tools.models import ToolExecutionStatus
        execution.status = ToolExecutionStatus.FAILED
        execution.error_code = "REJECTED_BY_USER"
        execution.result_summary = "Customer rejected the action."
        await db.commit()
        
        import asyncio
        from app.database import async_session_factory
        
        async def background_resume_reject():
            async with async_session_factory() as bg_db:
                await conversation_service.resume_tool_execution(
                    db=bg_db, 
                    conversation_id=conversation_id, 
                    execution_id=execution_id
                )
                
        asyncio.create_task(background_resume_reject())

    return {"status": "success"}
