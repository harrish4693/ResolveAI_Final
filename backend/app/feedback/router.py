from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.auth.deps import get_current_user
from app.users.models import User
from app.shared.models import UserRole
from app.feedback.schemas import FeedbackCreate, FeedbackRead
from app.feedback.service import FeedbackService

router = APIRouter(prefix="/api/conversations", tags=["Feedback"])

@router.post("/{conversation_id}/feedback", response_model=FeedbackRead)
async def submit_feedback(
    conversation_id: int,
    data: FeedbackCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Submit customer feedback for a resolved conversation."""
    return await FeedbackService.create_feedback(
        db=db,
        conversation_id=conversation_id,
        customer_id=current_user.id,
        data=data
    )

@router.get("/{conversation_id}/feedback", response_model=FeedbackRead | dict)
async def get_feedback(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Retrieve feedback for a conversation."""
    is_expert = current_user.role == UserRole.EXPERT
    feedback = await FeedbackService.get_feedback(
        db=db,
        conversation_id=conversation_id,
        user_id=current_user.id,
        is_expert=is_expert
    )
    if not feedback:
        return {} # Or 404, but {} is friendlier for UI
    return feedback
