from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Any

from app.database import get_db
from app.auth.deps import get_current_user
from app.users.models import User
from app.tickets.models import Ticket
from app.tickets.schemas import TicketOut
from app.shared.models import TicketStatus

router = APIRouter(tags=["tickets"])


@router.get("/summary", response_model=Dict[str, int])
async def get_tickets_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns counts of tickets by status for the current customer dashboard.
    """
    stmt = (
        select(Ticket.status, func.count(Ticket.id))
        .where(Ticket.customer_id == current_user.id)
        .group_by(Ticket.status)
    )
    result = await db.execute(stmt)
    counts = dict(result.all())
    
    # Ensure all statuses have at least 0
    return {
        "open": counts.get(TicketStatus.OPEN, 0),
        "ai_processing": counts.get(TicketStatus.AI_PROCESSING, 0),
        "waiting_for_user": counts.get(TicketStatus.WAITING_FOR_USER, 0),
        "escalated": counts.get(TicketStatus.ESCALATED, 0),
        "assigned": counts.get(TicketStatus.ASSIGNED, 0),
        "human_handling": counts.get(TicketStatus.HUMAN_HANDLING, 0),
        "resolved": counts.get(TicketStatus.RESOLVED, 0),
    }


@router.get("", response_model=List[TicketOut])
async def list_tickets(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns all tickets for the current customer.
    """
    stmt = (
        select(Ticket)
        .where(Ticket.customer_id == current_user.id)
        .order_by(Ticket.created_at.desc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{ticket_id}", response_model=TicketOut)
async def get_ticket(
    ticket_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns a specific ticket. Enforces customer ownership.
    Returns 404 if ticket doesn't exist or belongs to another user.
    """
    stmt = select(Ticket).where(Ticket.id == ticket_id)
    result = await db.execute(stmt)
    ticket = result.scalar_one_or_none()

    if not ticket or ticket.customer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        )

    return ticket
