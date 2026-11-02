import asyncio
from app.main import app as _app
import json
from sqlalchemy import select
from app.database import async_session_factory
from app.conversations.models import Conversation, ConversationMessage

async def check_db():
    async with async_session_factory() as db:
        # Get the latest conversation
        stmt = select(Conversation).order_by(Conversation.created_at.desc())
        result = await db.execute(stmt)
        latest_convo = result.scalars().first()
        
        if not latest_convo:
            print("No conversations found in DB.")
            return
            
        print(f"Latest Conversation ID: {latest_convo.id}")
        print(f"Status: {latest_convo.status}")
        print(f"Workflow State: {latest_convo.workflow_state}")
        
        # Get its messages
        stmt = select(ConversationMessage).where(
            ConversationMessage.conversation_id == latest_convo.id
        ).order_by(ConversationMessage.created_at.asc())
        result = await db.execute(stmt)
        messages = result.scalars().all()
        
        print("\nMessages:")
        for msg in messages:
            print(f"[{msg.created_at}] {msg.sender_type.name if hasattr(msg.sender_type, 'name') else msg.sender_type}: {msg.content}")
            if msg.metadata_:
                print(f"  Metadata: {json.dumps(msg.metadata_)}")

if __name__ == "__main__":
    asyncio.run(check_db())
