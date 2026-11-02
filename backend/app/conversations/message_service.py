from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.conversations.models import ConversationMessage
from app.shared.models import SenderType, MessageType

class MessageService:
    @staticmethod
    async def create_message(
        db: AsyncSession,
        conversation_id: int,
        sender_type: SenderType,
        content: str,
        sender_id: int | None = None,
        message_type: MessageType = MessageType.TEXT,
        metadata: dict | None = None,
        audio_url: str | None = None,
    ) -> ConversationMessage:
        msg = ConversationMessage(
            conversation_id=conversation_id,
            sender_type=sender_type,
            sender_id=sender_id,
            content=content,
            message_type=message_type,
            metadata_=metadata,
            audio_url=audio_url,
        )
        db.add(msg)
        await db.commit()
        await db.refresh(msg)
        return msg

    @staticmethod
    async def list_messages(db: AsyncSession, conversation_id: int, exclude_internal: bool = False) -> List[ConversationMessage]:
        stmt = (
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation_id)
            .order_by(ConversationMessage.created_at.asc())
        )
        result = await db.execute(stmt)
        messages = result.scalars().all()
        
        if exclude_internal:
            # Filter out messages where metadata_ contains {"is_internal": true}
            return [m for m in messages if not (m.metadata_ and m.metadata_.get("is_internal") is True)]
            
        return messages
