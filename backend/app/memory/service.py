import logging
import json
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from datetime import datetime
from pydantic import BaseModel, Field
from app.ai.schemas import MemoryExtractionSchema
from app.memory.models import ConversationMemory, MemoryType, MemorySourceType, MemoryImportance, MemoryConfidence
from app.conversations.models import Conversation, ConversationMessage
from app.users.models import User
from app.config import settings

logger = logging.getLogger(__name__)

class MemoryService:
    
    @staticmethod
    async def extract_memory(db: AsyncSession, conversation_id: int):
        """
        Extracts long-term memory facts and summaries from a resolved conversation.
        """
        # 0. Check if already extracted
        existing = await db.scalar(select(ConversationMemory).where(ConversationMemory.conversation_id == conversation_id))
        if existing:
            logger.info(f"Memory already extracted for conversation {conversation_id}")
            return
            
        # 1. Fetch conversation and messages
        stmt = select(Conversation).where(Conversation.id == conversation_id)
        convo = await db.scalar(stmt)
        if not convo:
            return
            
        msg_stmt = select(ConversationMessage).where(
            ConversationMessage.conversation_id == conversation_id
        ).order_by(ConversationMessage.created_at.asc())
        messages = (await db.scalars(msg_stmt)).all()
        
        # Don't extract if too short
        if len(messages) < 2:
            return
            
        history_text = "\n".join([f"{msg.sender_type.upper()}: {msg.content}" for msg in messages if msg.sender_type != "system"])
        
        # 2. Use LLM to extract facts
        # If we use M4 mock, we skip extraction or mock it.
        # But we can try to use OpenAIProvider directly if configured.
        if settings.ai_provider == "openai":
            from openai import AsyncOpenAI
            
            system_prompt = (
                "You are an expert customer support context extractor. Your job is to extract long-term, reusable facts from the support conversation.\n"
                "DO NOT extract ephemeral conversational pleasantries.\n"
                "DO NOT extract sensitive credentials, passwords, or full credit card numbers.\n"
                "Extract ONLY confident facts that will be useful if the customer returns in the future.\n"
                "Respond ONLY with structured data."
            )
            
            user_prompt = f"Extract memories from this conversation:\n\n{history_text}"
            
            try:
                if settings.ai_provider == "openai":
                    from app.ai.openai_provider import OpenAIProvider
                    provider = OpenAIProvider()
                elif settings.ai_provider == "gemini":
                    from app.ai.gemini_provider import GeminiProvider
                    provider = GeminiProvider()
                else:
                    logger.warning(f"Memory extraction skipped for provider: {settings.ai_provider}")
                    return

                extracted: MemoryExtractionSchema = await provider.generate_structured(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    response_format=MemoryExtractionSchema
                )
                
                for m in extracted.memories:
                    memory = ConversationMemory(
                        customer_id=convo.customer_id,
                        conversation_id=conversation_id,
                        memory_type=m.type,
                        source_type=MemorySourceType.AI,
                        content=m.content,
                        importance=m.importance,
                        confidence=m.confidence
                    )
                    db.add(memory)
                    
                await db.commit()
            except Exception as e:
                logger.error(f"Memory extraction failed: {e}")
        else:
            # Mock extraction for M4 tests
            mock_memory = ConversationMemory(
                customer_id=convo.customer_id,
                conversation_id=conversation_id,
                memory_type=MemoryType.ISSUE_HISTORY,
                source_type=MemorySourceType.SYSTEM,
                content=f"Customer reported an issue previously: {history_text[:100]}",
                importance=MemoryImportance.MEDIUM,
                confidence=MemoryConfidence.MEDIUM
            )
            db.add(mock_memory)
            await db.commit()

    @staticmethod
    async def save_memory(
        db: AsyncSession,
        customer_id: int,
        content: str,
        memory_type: MemoryType = MemoryType.PREFERENCE,
        importance: MemoryImportance = MemoryImportance.HIGH,
        confidence: MemoryConfidence = MemoryConfidence.HIGH,
        source_type: MemorySourceType = MemorySourceType.CUSTOMER,
        source: str | None = None,
        conversation_id: int | None = None,
        **kwargs,
    ) -> ConversationMemory:
        """Saves a single memory record directly to the database."""
        mem = ConversationMemory(
            customer_id=customer_id,
            conversation_id=conversation_id,
            content=content,
            memory_type=memory_type,
            importance=importance,
            confidence=confidence,
            source_type=source_type,
            is_active=True,
        )
        db.add(mem)
        await db.commit()
        await db.refresh(mem)
        return mem

    @staticmethod
    async def retrieve_relevant_memory(
        db: AsyncSession, 
        customer_id: int, 
        context_data: Dict[str, Any], 
        limit: int = 5
    ) -> List[ConversationMemory]:
        """
        Retrieves relevant long-term memories for a specific customer based on the current conversation context.
        SECURITY: customer_id is strictly enforced.
        """
        # Fetch all active memories for the customer (tenant isolation enforced here)
        stmt = select(ConversationMemory).where(
            and_(
                ConversationMemory.customer_id == customer_id,
                ConversationMemory.is_active == True
            )
        ).order_by(ConversationMemory.importance.desc(), ConversationMemory.created_at.desc())
        
        result = await db.execute(stmt)
        all_memories = result.scalars().all()
        
        if not all_memories:
            return []
            
        # We need to rank them based on the context data.
        # context_data typically includes: latest_message, history, intent, entities
        latest_message = str(context_data.get("latest_message", "")).lower()
        intent = str(context_data.get("intent", "")).lower()
        entities = context_data.get("entities", {})
        
        ranked_memories = []
        for memory in all_memories:
            score = 0
            mem_content = memory.content.lower()
            
            # 1. Match entities (strongest signal)
            for entity_val in entities.values():
                if str(entity_val).lower() in mem_content:
                    score += 5
                    
            # 2. Keyword matches from latest message
            words = [w for w in latest_message.split() if len(w) > 3]
            for w in words:
                if w in mem_content:
                    score += 2
            
            # 3. Intent alignment
            if "payment" in intent and ("payment" in mem_content or "charge" in mem_content or "refund" in mem_content):
                score += 2
            if "delivery" in intent and ("delivery" in mem_content or "order" in mem_content or "shipping" in mem_content):
                score += 2
                
            # If the user says "same problem" or "happened again", we highly boost recent ISSUE_HISTORY
            if any(phrase in latest_message for phrase in ["same problem", "happened again", "same issue"]):
                if memory.memory_type in [MemoryType.ISSUE_HISTORY, "ISSUE_HISTORY"]:
                    score += 10
                    
            # Base score from importance
            if memory.importance == MemoryImportance.HIGH:
                score += 3
            elif memory.importance == MemoryImportance.MEDIUM:
                score += 1
                
            if score > 0: # Only include if there is some relevance
                ranked_memories.append((score, memory))
                
        # Sort by score descending and take top N
        ranked_memories.sort(key=lambda x: x[0], reverse=True)
        return [m[1] for m in ranked_memories[:limit]]
