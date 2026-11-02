import os
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
import time
import json
import asyncio

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(BACKEND_DIR, ".env"))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool
from sqlalchemy import select

from app.database import Base
from app.main import app
from app.users.models import User
from app.notifications.models import Notification
from app.conversations.models import Conversation, ConversationMessage
from app.conversations.service import ConversationService
from app.commerce.models import Order
from app.shared.models import SenderType, WorkflowState
from app.ai.intelligence.language import UniversalMeaningEngine, CodeMixedLanguageDetector
from app.ai.groq_provider import GroqProvider
from app.rag.models import KnowledgeArticle
from tests.fixtures import INITIAL_ARTICLES
from app.rag.retriever import TFIDFRetriever

async def run_audit():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        poolclass=StaticPool
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    provider = GroqProvider()
    conversation_service = ConversationService(ai_provider=provider)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        for article_data in INITIAL_ARTICLES:
            article = KnowledgeArticle(**article_data)
            session.add(article)
        await session.commit()
        TFIDFRetriever.invalidate("default")
        await TFIDFRetriever.refresh(session, "default")

    async def send(session, conv, user, msg):
        await conversation_service.process_customer_message(
            db=session,
            conversation=conv,
            customer_id=user.id,
            message_content=msg
        )
        await session.commit()
        await session.refresh(conv)
        stmt = (
            select(ConversationMessage)
            .where(
                ConversationMessage.conversation_id == conv.id,
                ConversationMessage.sender_type == SenderType.AI
            )
            .order_by(ConversationMessage.created_at.desc())
        )
        res = await session.execute(stmt)
        ai_msg = res.scalars().first()
        return ai_msg.content if ai_msg else "", ai_msg.metadata_ if ai_msg else {}

    print("=== STARTING AUDIT REPRODUCTION ===")

    # -------------------------------------------------------------
    # Test 1: New Tanglish sentence not in existing dictionaries
    # -------------------------------------------------------------
    print("\n--- Test 1: Novel Tanglish Sentence ---")
    async with session_factory() as session:
        user1 = User(id=101, email="test1@example.com", name="Customer 1")
        session.add(user1)
        conv1 = Conversation(id=101, customer_id=101, preferred_language="tanglish")
        session.add(conv1)
        await session.commit()

        msg1 = "enakku vandha dress size romba perusa irukku, vera size maatha mudiyuma?"
        reply1, meta1 = await send(session, conv1, user1, msg1)
        print(f"Customer: {msg1}")
        print(f"Detected Lang: {meta1.get('language')}")
        print(f"Intent: {meta1.get('intent')}")
        print(f"Decision: {meta1.get('decision_state')}")
        print(f"Assistant: {reply1}\n")

    # -------------------------------------------------------------
    # Test 2: Short follow-up "why?"
    # -------------------------------------------------------------
    print("\n--- Test 2: Short Follow-up 'why?' ---")
    async with session_factory() as session:
        user2 = User(id=102, email="test2@example.com", name="Customer 2")
        session.add(user2)
        conv2 = Conversation(id=102, customer_id=102, preferred_language="english")
        session.add(conv2)
        await session.commit()

        # Turn 1: Trigger an order ID request
        t1_msg = "where is my parcel right now?"
        reply2_1, meta2_1 = await send(session, conv2, user2, t1_msg)
        print(f"Turn 1 Customer: {t1_msg}")
        print(f"Turn 1 Assistant: {reply2_1}")

        # Turn 2: Follow-up "why?"
        t2_msg = "why?"
        reply2_2, meta2_2 = await send(session, conv2, user2, t2_msg)
        print(f"Turn 2 Customer: {t2_msg}")
        print(f"Turn 2 Intent: {meta2_2.get('intent')}")
        print(f"Turn 2 Decision: {meta2_2.get('decision_state')}")
        print(f"Turn 2 Assistant: {reply2_2}\n")

    # -------------------------------------------------------------
    # Test 3: Clarification request "puriyala"
    # -------------------------------------------------------------
    print("\n--- Test 3: Clarification Request 'puriyala' ---")
    async with session_factory() as session:
        user3 = User(id=103, email="test3@example.com", name="Customer 3")
        session.add(user3)
        conv3 = Conversation(id=103, customer_id=103, preferred_language="tanglish")
        session.add(conv3)
        await session.commit()

        # Turn 1: Ask policy
        t1_msg = "thirumba thara rules enna?"
        reply3_1, meta3_1 = await send(session, conv3, user3, t1_msg)
        print(f"Turn 1 Customer: {t1_msg}")
        print(f"Turn 1 Assistant: {reply3_1}")

        # Turn 2: "puriyala"
        t2_msg = "puriyala"
        reply3_2, meta3_2 = await send(session, conv3, user3, t2_msg)
        print(f"Turn 2 Customer: {t2_msg}")
        print(f"Turn 2 Intent: {meta3_2.get('intent')}")
        print(f"Turn 2 Decision: {meta3_2.get('decision_state')}")
        print(f"Turn 2 Assistant: {reply3_2}\n")

    # -------------------------------------------------------------
    # Test 4: Customer correcting a misunderstood question
    # -------------------------------------------------------------
    print("\n--- Test 4: Customer Correcting a Misunderstood Question ---")
    async with session_factory() as session:
        user4 = User(id=104, email="test4@example.com", name="Customer 4")
        session.add(user4)
        conv4 = Conversation(id=104, customer_id=104, preferred_language="english")
        session.add(conv4)
        await session.commit()

        # Turn 1: Ambiguous inquiry about returning/exchanging
        t1_msg = "I have an issue with the product delivered."
        reply4_1, meta4_1 = await send(session, conv4, user4, t1_msg)
        print(f"Turn 1 Customer: {t1_msg}")
        print(f"Turn 1 Assistant: {reply4_1}")

        # Turn 2: Assistant asked for Order ID or assumed return, customer corrects:
        t2_msg = "no, I wasn't asking to return it, I want to know if you offer replacement for damaged parts"
        reply4_2, meta4_2 = await send(session, conv4, user4, t2_msg)
        print(f"Turn 2 Customer: {t2_msg}")
        print(f"Turn 2 Intent: {meta4_2.get('intent')}")
        print(f"Turn 2 Assistant: {reply4_2}\n")

    # -------------------------------------------------------------
    # Test 5: Multi-turn where assistant repeats its previous answer
    # -------------------------------------------------------------
    print("\n--- Test 5: Multi-turn Assistant Repetition ---")
    async with session_factory() as session:
        user5 = User(id=105, email="test5@example.com", name="Customer 5")
        session.add(user5)
        conv5 = Conversation(id=105, customer_id=105, preferred_language="tanglish")
        session.add(conv5)
        await session.commit()

        t1_msg = "courier eppo varum?"
        reply5_1, meta5_1 = await send(session, conv5, user5, t1_msg)
        print(f"Turn 1 Customer: {t1_msg}")
        print(f"Turn 1 Assistant: {reply5_1}")

        # Turn 2: Customer doesn't have order id yet, asks how to find
        t2_msg = "SMS varala bro, eppadi kandupidikiradhu?"
        reply5_2, meta5_2 = await send(session, conv5, user5, t2_msg)
        print(f"Turn 2 Customer: {t2_msg}")
        print(f"Turn 2 Intent: {meta5_2.get('intent')}")
        print(f"Turn 2 Assistant: {reply5_2}")

        # Turn 3: Customer asks again
        t3_msg = "email-layum illa, vera vazhi irukka?"
        reply5_3, meta5_3 = await send(session, conv5, user5, t3_msg)
        print(f"Turn 3 Customer: {t3_msg}")
        print(f"Turn 3 Intent: {meta5_3.get('intent')}")
        print(f"Turn 3 Assistant: {reply5_3}\n")

if __name__ == "__main__":
    asyncio.run(run_audit())
