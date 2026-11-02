import asyncio
import logging
import time
import enum
import re
from typing import Optional, List, Dict, Any, Set, Tuple
logger = logging.getLogger(__name__)
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from fastapi import HTTPException, status, UploadFile

from app.conversations.models import Conversation, ConversationMessage
from app.tickets.models import Ticket
from app.shared.models import SenderType, TicketStatus, WorkflowState, MessageType, ConversationChannel
from app.handoff.models import Handoff
from app.experts.models import Expert
from app.conversations.message_service import MessageService
from app.ai.m4.provider import M4AIProvider
from sqlalchemy import select
from app.voice.service import VoiceService

from app.websockets.manager import manager
import json
from app.websockets.events import (
    typing_event,
    new_message_event,
    conversation_updated_event,
    queue_updated_event,
    tool_execution_started_event,
    tool_confirmation_required_event,
    tool_execution_completed_event,
    tool_execution_failed_event,
)


class ConversationService:
    def __init__(self, ai_provider=None):
        self._custom_ai_provider = ai_provider
        self._providers = {}

    @property
    def ai_provider(self):
        if self._custom_ai_provider is not None:
            return self._custom_ai_provider
        from app.config import settings
        prov_key = (settings.ai_provider or "mock").lower()
        if prov_key not in self._providers:
            if prov_key == "openai":
                from app.ai.openai_provider import OpenAIProvider
                self._providers[prov_key] = OpenAIProvider()
            elif prov_key == "gemini":
                from app.ai.gemini_provider import GeminiProvider
                self._providers[prov_key] = GeminiProvider()
            elif prov_key == "groq":
                from app.ai.groq_provider import GroqProvider
                self._providers[prov_key] = GroqProvider()
            else:
                from app.ai.m4.provider import M4AIProvider
                self._providers[prov_key] = M4AIProvider()
        return self._providers[prov_key]

    @ai_provider.setter
    def ai_provider(self, provider):
        self._custom_ai_provider = provider

    async def create_conversation(
        self,
        db: AsyncSession,
        customer_id: int,
        initial_message: str | None = None,
        subject: str | None = None,
        channel: ConversationChannel | str = ConversationChannel.TEXT,
    ) -> Conversation:
        channel_val = channel if isinstance(channel, ConversationChannel) else (
            ConversationChannel.VOICE if str(channel).lower() == "voice" else ConversationChannel.TEXT
        )
        if not subject:
            if initial_message and initial_message.strip():
                subject = (initial_message[:47] + "...") if len(initial_message) > 47 else initial_message
            else:
                subject = "Voice Call with ResolveAI" if channel_val == ConversationChannel.VOICE else "New Support Request"

        # 1. Create conversation
        convo = Conversation(customer_id=customer_id, channel=channel_val)
        db.add(convo)
        await db.flush()  # to get convo.id

        # 2. Create linked ticket
        initial_ticket_status = (
            TicketStatus.OPEN
            if (channel_val == ConversationChannel.VOICE and not (initial_message and initial_message.strip()))
            else TicketStatus.AI_PROCESSING
        )
        ticket = Ticket(
            customer_id=customer_id,
            conversation_id=convo.id,
            subject=subject,
            status=initial_ticket_status,
        )
        db.add(ticket)
        await db.flush()

        # 3. Only if initial_message is provided, add message and trigger AI
        if initial_message and initial_message.strip():
            customer_msg = await MessageService.create_message(
                db=db,
                conversation_id=convo.id,
                sender_type=SenderType.CUSTOMER,
                content=initial_message.strip(),
                sender_id=customer_id,
            )

            # 4. Broadcast typing indicator (ephemeral — not stored)
            await manager.send_to_user(
                customer_id,
                typing_event(convo.id, "ai", is_start=True),
            )

            # 5. Trigger AI Response
            await self._trigger_ai_response(db, convo, initial_message.strip())

            await db.commit()
            await db.refresh(convo)

            # 6. Broadcast typing end
            await manager.send_to_user(
                customer_id,
                typing_event(convo.id, "ai", is_start=False),
            )

            # 7. Broadcast the AI response message (last message in conversation)
            last_msg = convo.messages[-1] if convo.messages else None
            if last_msg and last_msg.sender_type == SenderType.AI:
                await manager.send_to_user(
                    customer_id,
                    new_message_event(
                        conversation_id=convo.id,
                        message_id=last_msg.id,
                        sender_type=last_msg.sender_type.value if hasattr(last_msg.sender_type, 'value') else str(last_msg.sender_type),
                        content=last_msg.content,
                        created_at=last_msg.created_at.isoformat(),
                    ),
                )

            # 8. If escalated, broadcast queue update to experts
            if convo.workflow_state == WorkflowState.WAITING_FOR_EXPERT:
                handoff = await db.scalar(
                    select(Handoff).where(Handoff.conversation_id == convo.id)
                )
                if handoff:
                    await manager.broadcast_to_experts(
                        queue_updated_event(
                            action="ADDED",
                            handoff_id=handoff.id,
                            priority=handoff.priority,
                            category=handoff.category,
                        )
                    )
        else:
            await db.commit()
            await db.refresh(convo)

        return convo

    async def process_customer_message(
        self, db: AsyncSession, conversation: Conversation, customer_id: int, message_content: str,
        tts_callback = None,
        reply_with_voice: bool = False,
    ):
        """Processes an incoming customer message on an existing conversation."""
        # 1. Add customer message
        customer_msg = await MessageService.create_message(
            db=db,
            conversation_id=conversation.id,
            sender_type=SenderType.CUSTOMER,
            content=message_content,
            sender_id=customer_id,
        )

        # 2. Broadcast customer message to any assigned expert
        handoff = await db.scalar(
            select(Handoff).where(
                Handoff.conversation_id == conversation.id,
            )
        )
        expert_user_id = None
        if handoff and handoff.assigned_expert_id:
            expert_rec = await db.scalar(select(Expert).where(Expert.id == handoff.assigned_expert_id))
            if expert_rec:
                expert_user_id = expert_rec.user_id

        await manager.send_to_conversation_participants(
            customer_id=customer_id,
            expert_id=expert_user_id,
            event=new_message_event(
                conversation_id=conversation.id,
                message_id=customer_msg.id,
                sender_type=customer_msg.sender_type.value if hasattr(customer_msg.sender_type, 'value') else str(customer_msg.sender_type),
                content=customer_msg.content,
                created_at=customer_msg.created_at.isoformat(),
                message_type=customer_msg.message_type.value if hasattr(customer_msg.message_type, 'value') else str(customer_msg.message_type),
                audio_url=customer_msg.audio_url,
            ),
        )

        # 3. Broadcast typing indicator
        await manager.send_to_user(
            customer_id,
            typing_event(conversation.id, "ai", is_start=True),
        )

        # 4. Trigger AI Response
        await self._trigger_ai_response(
            db,
            conversation,
            message_content,
            reply_with_voice=reply_with_voice,
            tts_callback=tts_callback,
        )
        await db.commit()
        await db.refresh(conversation)

        # 5. Broadcast typing end
        await manager.send_to_user(
            customer_id,
            typing_event(conversation.id, "ai", is_start=False),
        )

        # 6. Broadcast the AI response
        # Explicitly query the last message since conversation.messages might be stale
        from app.conversations.models import ConversationMessage
        stmt = select(ConversationMessage).where(
            ConversationMessage.conversation_id == conversation.id
        ).order_by(ConversationMessage.created_at.desc())
        
        result = await db.execute(stmt)
        last_msg = result.scalars().first()
        
        if last_msg and last_msg.sender_type == SenderType.AI:
            await manager.send_to_conversation_participants(
                customer_id=customer_id,
                expert_id=expert_user_id,
                event=new_message_event(
                    conversation_id=conversation.id,
                    message_id=last_msg.id,
                    sender_type=last_msg.sender_type.value if hasattr(last_msg.sender_type, 'value') else str(last_msg.sender_type),
                    content=last_msg.content,
                    created_at=last_msg.created_at.isoformat(),
                ),
            )

        # 7. If escalated, broadcast queue update
        if conversation.workflow_state == WorkflowState.WAITING_FOR_EXPERT:
            handoff = await db.scalar(
                select(Handoff).where(Handoff.conversation_id == conversation.id)
            )
            if handoff:
                await manager.broadcast_to_experts(
                    queue_updated_event(
                        action="ADDED",
                        handoff_id=handoff.id,
                        priority=handoff.priority,
                        category=handoff.category,
                    )
                )

    async def process_customer_voice_message(
        self, db: AsyncSession, conversation: Conversation, customer_id: int, file: UploadFile
    ):
        """Processes an incoming customer voice message."""
        # 1. Save customer audio
        audio_url = await VoiceService.save_customer_audio(conversation.id, file)
        
        # 2. Transcribe
        try:
            message_content = await VoiceService.transcribe(audio_url)
        except Exception:
            raise ValueError("Sorry, I couldn't understand the audio. Please try again or type your message.")

        # 3. Add customer message
        customer_msg = await MessageService.create_message(
            db=db,
            conversation_id=conversation.id,
            sender_type=SenderType.CUSTOMER,
            content=message_content,
            sender_id=customer_id,
            message_type=MessageType.VOICE,
            audio_url=audio_url,
        )

        # 4. Broadcast customer message
        handoff = await db.scalar(
            select(Handoff).where(Handoff.conversation_id == conversation.id)
        )
        expert_user_id = None
        if handoff and handoff.assigned_expert_id:
            expert_rec = await db.scalar(select(Expert).where(Expert.id == handoff.assigned_expert_id))
            if expert_rec:
                expert_user_id = expert_rec.user_id

        await manager.send_to_conversation_participants(
            customer_id=customer_id,
            expert_id=expert_user_id,
            event=new_message_event(
                conversation_id=conversation.id,
                message_id=customer_msg.id,
                sender_type=customer_msg.sender_type.value if hasattr(customer_msg.sender_type, 'value') else str(customer_msg.sender_type),
                content=customer_msg.content,
                created_at=customer_msg.created_at.isoformat(),
                message_type=customer_msg.message_type.value if hasattr(customer_msg.message_type, 'value') else str(customer_msg.message_type),
                audio_url=customer_msg.audio_url,
            ),
        )

        # 5. Broadcast typing indicator
        await manager.send_to_user(
            customer_id,
            typing_event(conversation.id, "ai", is_start=True),
        )

        # 6. Trigger AI Response (with voice)
        await self._trigger_ai_response(db, conversation, message_content, reply_with_voice=True)
        await db.commit()
        await db.refresh(conversation)

        # 7. Broadcast typing end
        await manager.send_to_user(
            customer_id,
            typing_event(conversation.id, "ai", is_start=False),
        )

        # 8. Broadcast the AI response
        last_msg = conversation.messages[-1] if conversation.messages else None
        if last_msg and last_msg.sender_type == SenderType.AI:
            await manager.send_to_conversation_participants(
                customer_id=customer_id,
                expert_id=expert_user_id,
                event=new_message_event(
                    conversation_id=conversation.id,
                    message_id=last_msg.id,
                    sender_type=last_msg.sender_type.value if hasattr(last_msg.sender_type, 'value') else str(last_msg.sender_type),
                    content=last_msg.content,
                    created_at=last_msg.created_at.isoformat(),
                    message_type=last_msg.message_type.value if hasattr(last_msg.message_type, 'value') else str(last_msg.message_type),
                    audio_url=last_msg.audio_url,
                ),
            )

        # 9. If escalated, broadcast queue update
        if conversation.workflow_state == WorkflowState.WAITING_FOR_EXPERT:
            handoff = await db.scalar(
                select(Handoff).where(Handoff.conversation_id == conversation.id)
            )
            if handoff:
                await manager.broadcast_to_experts(
                    queue_updated_event(
                        action="ADDED",
                        handoff_id=handoff.id,
                        priority=handoff.priority,
                        category=handoff.category,
                    )
                )

    async def _trigger_ai_response(
        self, db: AsyncSession, conversation: Conversation, latest_message: str, reply_with_voice: bool = False, tts_callback = None
    ):
        """Orchestrates the AI provider to generate a response."""
        if hasattr(latest_message, "content"):
            latest_message = latest_message.content
        elif hasattr(latest_message, "text"):
            latest_message = latest_message.text
        latest_message = str(latest_message or "")
        
        # 1. Fetch previous context if any (the last AI message might have the previous analysis)
        # We now fetch the entire conversation history to provide to the AI Provider
        stmt = select(ConversationMessage).where(
            ConversationMessage.conversation_id == conversation.id
        ).order_by(ConversationMessage.created_at.asc())
        
        result = await db.execute(stmt)
        all_messages = result.scalars().all()
        
        from app.users.models import User
        tenant_id = await db.scalar(
            select(User.tenant_id).where(User.id == conversation.customer_id)
        ) or "default"
        
        # Count previous AI attempts in this conversation
        ai_attempt_count = sum(1 for m in all_messages if m.sender_type == SenderType.AI)

        # Pull previous tickets for recurring complaint detection
        prior_tickets_res = await db.execute(
            select(Ticket)
            .where(Ticket.customer_id == conversation.customer_id)
            .where(Ticket.conversation_id != conversation.id)
            .order_by(Ticket.created_at.desc())
            .limit(5)
        )
        prior_tickets = prior_tickets_res.scalars().all()
        ticket_history_list = [
            {"id": pt.id, "category": pt.category or "General", "subject": pt.subject or "", "status": str(pt.status)}
            for pt in prior_tickets
        ]

        from app.ai.autonomy_service import AutonomyConfigService
        autonomy_cfg = await AutonomyConfigService.get_effective_config(db, tenant_id=tenant_id)

        is_voice_conv = (
            (conversation.channel == ConversationChannel.VOICE)
            or str(getattr(conversation, "channel", "")).lower() == "voice"
            or bool(reply_with_voice)
        )
        is_voice_turn = bool(is_voice_conv or (tts_callback is not None))
        context = {
            "conversation_id": conversation.id,
            "history": [],
            "tenant_id": tenant_id,
            "attempt_count": ai_attempt_count,
            "ticket_history": ticket_history_list,
            "autonomy_config": autonomy_cfg,
            "reply_with_voice": reply_with_voice,
            "is_voice": is_voice_conv,
        }
        
        last_ai_msg = None
        for msg in all_messages:
            context["history"].append({
                "sender_type": msg.sender_type.value if hasattr(msg.sender_type, 'value') else str(msg.sender_type),
                "content": msg.content,
                "created_at": msg.created_at.isoformat()
            })
            if msg.sender_type == SenderType.AI:
                last_ai_msg = msg
        
        if last_ai_msg and last_ai_msg.metadata_:
            context["previous_analysis"] = last_ai_msg.metadata_

        from app.conversations.state import ConversationStateManager
        conversation_state = ConversationStateManager.load_state(conversation, all_messages, tenant_id=tenant_id)
        context["conversation_state"] = conversation_state
        active_preferred_language = getattr(conversation_state, "language_preference", None) or "english"

        try:
            # 1.5. Incorporate Long-Term Memory
            from app.memory.service import MemoryService
            
            mem_context_data = {
                "latest_message": latest_message,
                "history": context["history"]
            }
            
            # Pull basic analysis if possible to help memory ranking
            if last_ai_msg and last_ai_msg.metadata_:
                mem_context_data["intent"] = last_ai_msg.metadata_.get("intent", "")
                mem_context_data["entities"] = last_ai_msg.metadata_.get("entities", {})
                
            relevant_memories = await MemoryService.retrieve_relevant_memory(
                db=db, 
                customer_id=conversation.customer_id,
                context_data=mem_context_data
            )
            context["relevant_memories"] = [m.content for m in relevant_memories]

            # ── Milestone P2.5 & RC-4 & Step 3: Voice Language Controller ──
            from app.voice.language_controller import VoiceLanguageController, VoiceLanguagePolicy, SUPPORTED_LANGUAGES
            stt_meta = context.get("stt_metadata")
            prior_policy_data = getattr(conversation_state, "language_policy", None) if conversation_state else None
            if prior_policy_data and isinstance(prior_policy_data, dict):
                current_policy = VoiceLanguagePolicy.from_dict(prior_policy_data)
            else:
                current_policy = VoiceLanguageController.from_conversation(conversation, context)

            prev_lang = current_policy.response_language
            updated_policy = VoiceLanguageController.evaluate_turn(current_policy, latest_message, stt_meta)

            is_language_switch = (updated_policy.response_language != prev_lang)
            if is_language_switch or conversation.preferred_language != updated_policy.response_language:
                conversation.preferred_language = updated_policy.response_language
                if updated_policy.customer_language_preference and updated_policy.customer_language_preference.startswith("explicit:"):
                    await MemoryService.save_memory(
                        db=db,
                        customer_id=conversation.customer_id,
                        content=f"Customer preferred language: {updated_policy.response_language}",
                        source="language_preference"
                    )
                await db.commit()

            active_preferred_language = updated_policy.response_language
            if conversation_state:
                conversation_state.language_preference = active_preferred_language
                setattr(conversation_state, "language_policy", updated_policy.to_dict())

            context["preferred_language"] = active_preferred_language
            context["bcp47_code"] = updated_policy.bcp47_code
            context["language_policy"] = updated_policy.to_dict()
            context["is_language_switch"] = is_language_switch

            # RC-6: If language switch, check for any active unresolved request from conversation state or history
            pending_query = ""
            pending_intent = ""
            is_task_resolved = False
            if conversation_state:
                if getattr(conversation_state, "resolution_status", "") == "resolved" and not getattr(conversation_state, "unresolved_request", None):
                    is_task_resolved = True
                elif getattr(conversation_state, "unresolved_request", None):
                    pending_query = str(conversation_state.unresolved_request).strip()
                if getattr(conversation_state, "active_intent", None) and conversation_state.active_intent not in ("GREETING", "UNCLEAR", "LANGUAGE_SWITCH", "ACKNOWLEDGMENT"):
                    pending_intent = str(conversation_state.active_intent).upper()

            if not pending_query and not is_task_resolved:
                # Scan backwards excluding explicit switch requests, greetings, AND pure acknowledgments ("seri", "ok", etc.)
                ack_tokens = {"ok", "okay", "seri", "sari", "theek hai", "thik hai", "got it", "noted", "understood", "thanks", "thank you", "k", "kk", "sure", "fine"}
                for msg in reversed(context.get("history", [])[:-1]):
                    if str(msg.get("sender_type", "")).lower() == "customer":
                        c_text = str(msg.get("content", "")).strip()
                        c_low = c_text.lower().strip(".!?, ")
                        if (
                            not self.detect_explicit_language_request(c_text)
                            and not any(c_low == g for g in ["hi", "hello", "hey", "vanakkam", "namaste"])
                            and c_low not in ack_tokens
                            and len(c_text.split()) > 1
                        ):
                            pending_query = c_text
                            break

            if not pending_intent and context.get("previous_analysis"):
                prev_int = str(context["previous_analysis"].get("intent", "")).upper()
                if prev_int not in ("GREETING", "UNCLEAR", "LANGUAGE_SWITCH", "ACKNOWLEDGMENT"):
                    pending_intent = prev_int

            from app.ai.intelligence.escalation_keywords import is_supervisor_demand, is_fraud_or_security
            from app.ai.intelligence.language import UniversalMeaningEngine
            from app.ai.m4.decision import ResponseGenerator

            is_voice_turn = context.get("is_voice", False) or context.get("reply_with_voice", False) or bool(is_voice_conv or (tts_callback is not None))
            is_explicit_switch = bool(self.detect_explicit_language_request(latest_message))
            latest_meaning = UniversalMeaningEngine().understand_utterance(latest_message)
            is_ack_or_greeting = (
                latest_meaning.conversational_function in ("ACKNOWLEDGMENT", "GREETING", "DISMISSAL")
                or str(latest_meaning.intent).upper() in ("ACKNOWLEDGMENT", "GREETING")
            )

            effective_message = latest_message
            if is_language_switch and pending_query and not is_ack_or_greeting:
                # Retain pending customer inquiry only for explicit switch requests
                if is_explicit_switch:
                    effective_message = f"{pending_query} (continue in {active_preferred_language})"
                    context["pending_query"] = pending_query
                    context["pending_intent"] = pending_intent

            # Fast Path: Check for Unsupported Language Request or Explicit Language Switch
            if updated_policy.unsupported_requested_language:
                unsupported_msg = VoiceLanguageController.get_unsupported_language_message(
                    updated_policy.unsupported_requested_language,
                    active_preferred_language
                )
                if is_voice_turn and tts_callback:
                    await tts_callback(unsupported_msg)
                decision = "RESOLVE"
                response_text = unsupported_msg
                preserved_entities = dict(getattr(conversation_state, "entities", {}) or {}) if conversation_state else {}
                analysis = {
                    "original_message": latest_message,
                    "intent": "LANGUAGE_SWITCH_UNSUPPORTED",
                    "sentiment": "neutral",
                    "priority": "LOW",
                    "language": active_preferred_language.capitalize(),
                    "bcp47_code": updated_policy.bcp47_code,
                    "emotion": "calm",
                    "emotion_confidence": 0.95,
                    "entities": preserved_entities,
                    "decision_state": "RESOLVE",
                    "decision_reason": f"Customer requested unsupported language '{updated_policy.unsupported_requested_language}'",
                    "spoken_response": unsupported_msg,
                    "validation_latency_ms": 0.0,
                }
            elif is_explicit_switch and not pending_query:
                ack_text = self.LANGUAGE_SWITCH_ACKNOWLEDGMENTS.get(
                    active_preferred_language,
                    SUPPORTED_LANGUAGES.get(active_preferred_language, {}).get("ack", f"Sure, let's continue in {active_preferred_language.capitalize()}.")
                )
                if is_voice_turn and tts_callback:
                    await tts_callback(ack_text)
                decision = "RESOLVE"
                response_text = ack_text
                # RC-2 & RC-6: Preserve existing known entities during language switch acknowledgment!
                preserved_entities = dict(getattr(conversation_state, "entities", {}) or {}) if conversation_state else {}
                analysis = {
                    "original_message": latest_message,
                    "intent": "LANGUAGE_SWITCH",
                    "sentiment": "neutral",
                    "priority": "LOW",
                    "language": active_preferred_language.capitalize(),
                    "bcp47_code": updated_policy.bcp47_code,
                    "emotion": "calm",
                    "emotion_confidence": 0.95,
                    "entities": preserved_entities,
                    "decision_state": "RESOLVE",
                    "decision_reason": "Language preference updated",
                    "spoken_response": ack_text,
                    "validation_latency_ms": 0.0,
                }
            # A. Check for pending handoff confirmation first
            elif conversation_state and getattr(conversation_state, "pending_handoff_confirmation", False):
                is_affirmative = UniversalMeaningEngine.is_affirmative_confirmation(latest_message)
                is_negative = UniversalMeaningEngine.is_negative_confirmation(latest_message)
                is_frustrated_or_failure = any(w in latest_message.lower() for w in ["nothing works", "terrible", "unresponsive", "broken", "useless", "already tried", "not working", "still"])

                if is_affirmative or is_frustrated_or_failure:
                    # Execute handoff
                    pending_reason = getattr(conversation_state, "pending_handoff_reason", None) or "Customer confirmed expert handoff"
                    pending_analysis = getattr(conversation_state, "pending_handoff_analysis", None) or {
                        "original_message": latest_message,
                        "intent": "ESCALATION_REQUEST",
                        "decision_state": "ESCALATE",
                        "language": active_preferred_language.capitalize(),
                    }
                    from app.handoff.service import HandoffService
                    await HandoffService.create_or_update_handoff(
                        db=db,
                        conversation=conversation,
                        analysis=pending_analysis,
                        reason=pending_reason,
                    )
                    conversation_state.pending_handoff_confirmation = False
                    conversation_state.handoff_confirmed = True
                    conversation_state.pending_handoff_reason = None
                    conversation.workflow_state = "waiting_for_expert"
                    await db.commit()

                    decision = "ESCALATE"
                    response_text = ResponseGenerator().generate({
                        "decision": "RESOLVE",
                        "action_type": "handoff_confirmed"
                    }, language=active_preferred_language)
                    analysis = {
                        "original_message": latest_message,
                        "intent": "HANDOFF_CONFIRMED",
                        "decision_state": "ESCALATE",
                        "decision_reason": pending_reason,
                        "language": active_preferred_language.capitalize(),
                        "entities": dict(conversation_state.entities or {}),
                    }
                elif is_negative:
                    # Cancel handoff and continue with AI
                    conversation_state.pending_handoff_confirmation = False
                    conversation_state.handoff_rejected = True
                    conversation_state.pending_handoff_reason = None
                    conversation_state.pending_handoff_analysis = None
                    conversation.workflow_state = "asking_user"
                    await db.commit()

                    decision = "ASK_USER"
                    response_text = ResponseGenerator().generate({
                        "decision": "RESOLVE",
                        "action_type": "handoff_rejected"
                    }, language=active_preferred_language)
                    analysis = {
                        "original_message": latest_message,
                        "intent": "HANDOFF_REJECTED",
                        "decision_state": "ASK_USER",
                        "decision_reason": "Customer declined expert handoff; continuing with AI",
                        "language": active_preferred_language.capitalize(),
                        "entities": dict(conversation_state.entities or {}),
                    }
                else:
                    # Unclear: ask short clarification without transferring
                    decision = "ASK_USER"
                    response_text = ResponseGenerator().generate({
                        "decision": "ASK_USER",
                        "missing_entity": "handoff_unclear"
                    }, language=active_preferred_language)
                    analysis = {
                        "original_message": latest_message,
                        "intent": "HANDOFF_UNCLEAR",
                        "decision_state": "ASK_USER",
                        "decision_reason": "Clarifying whether customer wants human expert",
                        "language": active_preferred_language.capitalize(),
                        "requires_handoff_confirmation": True,
                        "entities": dict(conversation_state.entities or {}),
                    }

            # B. High-risk safety / fraud policy: immediate escalation with clear explanation
            elif is_fraud_or_security(latest_message):
                decision = "ESCALATE"
                lang_l = active_preferred_language.lower()
                if "tanglish" in lang_l:
                    response_text = "Security matrum account protection kaaga, indha issue-ah namma security expert kitta udane escalate panren. Oru expert seekiram join pannuvaanga."
                elif "tamil" in lang_l or lang_l in ("ta", "ta-in"):
                    response_text = "பாதுகாப்புக் காரணங்களுக்காக, இந்த சிக்கலை உடனடியாக எங்கள் பாதுகாப்பு நிபுணரிடம் மாற்றுகிறேன்."
                elif "hinglish" in lang_l:
                    response_text = "Suraksha aur account protection ke liye, main is request ko turant hamare security expert ko escalate kar raha hoon."
                elif "hindi" in lang_l or lang_l in ("hi", "hi-in"):
                    response_text = "सुरक्षा कारणों से, मैं आपका अनुरोध तुरंत हमारे सुरक्षा विशेषज्ञ को ट्रांसफर कर रहा हूँ।"
                elif "kannada" in lang_l or "kanglish" in lang_l or lang_l in ("kn", "kn-in"):
                    response_text = "ಸುರಕ್ಷತಾ ಕಾರಣಗಳಿಗಾಗಿ, ನಾನು ಈ ಸಮಸ್ಯೆಯನ್ನು ತಕ್ಷಣ ನಮ್ಮ ಭದ್ರತಾ ತಜ್ಞರಿಗೆ ವರ್ಗಾಯಿಸುತ್ತೇನೆ."
                elif "telugu" in lang_l or "tenglish" in lang_l or lang_l in ("te", "te-in"):
                    response_text = "భద్రతా కారణాల దృష్ట్యా, నేను ఈ సమస్యను వెంటనే మా సెక్యూరిటీ నిపుణుడికి బదిలీ చేస్తున్నాను."
                elif "malayalam" in lang_l or "manglish" in lang_l or lang_l in ("ml", "ml-in"):
                    response_text = "സുരക്ഷാ കാരണങ്ങളാൽ, ഞാൻ ഈ പ്രശ്നം ഉടൻ തന്നെ ഞങ്ങളുടെ സുരക്ഷാ വിദഗ്ദ്ധന് കൈമാറുന്നു."
                elif "bengali" in lang_l or "benglish" in lang_l or lang_l in ("bn", "bn-in"):
                    response_text = "নিরাপত্তার স্বার্থে, আমি এই সমস্যাটি অবিলম্বে আমাদের নিরাপত্তা বিশেষজ্ঞের কাছে স্থানান্তর করছি।"
                elif "marathi" in lang_l or "marathish" in lang_l or lang_l in ("mr", "mr-in"):
                    response_text = "सुरक्षेच्या कारणास्तव, मी ही समस्या त्वरित आमच्या सुरक्षा तज्ज्ञांकडे हस्तांतरित करत आहे."
                elif "gujarati" in lang_l or "gujlish" in lang_l or lang_l in ("gu", "gu-in"):
                    response_text = "સુરક્ષાના કારણોસર, હું આ સમસ્યાને તરત જ અમારા સુરક્ષા નિષ્ણાતને ટ્રાન્સફર કરી રહ્યો છું."
                elif "punjabi" in lang_l or "punglish" in lang_l or lang_l in ("pa", "pa-in"):
                    response_text = "ਸੁਰੱਖਿਆ ਕਾਰਨਾਂ ਕਰਕੇ, ਮੈਂ ਇਸ ਮੁੱਦੇ ਨੂੰ ਤੁਰੰਤ ਸਾਡੇ ਸੁਰੱਖਿਆ ਮਾਹਰ ਨੂੰ ਟਰਾਂਸਫਰ ਕਰ ਰਿਹਾ ਹਾਂ।"
                else:
                    response_text = "For security and account protection, I am immediately escalating your request to a security expert."
                analysis = {
                    "original_message": latest_message,
                    "intent": "SECURITY_ISSUE",
                    "priority": "CRITICAL",
                    "decision_state": "ESCALATE",
                    "decision_reason": "High-risk safety or security policy triggered immediate escalation",
                    "language": active_preferred_language.capitalize(),
                    "entities": dict(getattr(conversation_state, "entities", {}) or {}),
                }
                from app.handoff.service import HandoffService
                await HandoffService.create_or_update_handoff(
                    db=db,
                    conversation=conversation,
                    analysis=analysis,
                    reason="High-risk safety or security policy triggered immediate escalation",
                )

            # C. Explicit supervisor requests: immediate escalation per policy
            elif is_supervisor_demand(latest_message):
                decision = "ESCALATE"
                lang_l = active_preferred_language.lower()
                from app.ai.m4.decision import ResponseGenerator
                response_text = ResponseGenerator().generate({
                    "decision": "ESCALATE",
                    "action_type": "handoff_confirmed"
                }, language=lang_l)
                analysis = {
                    "original_message": latest_message,
                    "intent": "ESCALATION_REQUEST",
                    "priority": "HIGH",
                    "decision_state": "ESCALATE",
                    "decision_reason": "Customer explicitly requested human expert",
                    "language": active_preferred_language.capitalize(),
                    "entities": dict(getattr(conversation_state, "entities", {}) or {}),
                }
                from app.handoff.service import HandoffService
                await HandoffService.create_or_update_handoff(
                    db=db,
                    conversation=conversation,
                    analysis=analysis,
                    reason="Customer explicitly requested human expert",
                )
            elif is_voice_turn and hasattr(self.ai_provider, "process_voice_turn"):
                conversation.workflow_state = "understanding"
                await db.commit()

                # ── P1.7 Latency Pass: Fast Cached Opener with Policy Filter BEFORE ANY LLM CALL ──
                t_stt_done = time.perf_counter()
                used_openers = context.setdefault("used_openers", set())
                fast_signals = self._detect_cheap_voice_signals(latest_message)
                # Enforce active session language from controller so opener and filler never diverge
                fast_signals["language"] = active_preferred_language.capitalize()
                turn_index = context.get("turn_index") or (len(context["history"]) // 2 + 1)
                
                safe_opener = ""
                if self.should_play_opener(
                    turn_index=turn_index,
                    emotion=fast_signals.get("emotion", "neutral"),
                    emotion_confidence=fast_signals.get("emotion_confidence", 0.0),
                    reply_ready_within_threshold=True
                ):
                    safe_opener = self._generate_safe_opener(
                        fast_signals, latest_message, used_openers=used_openers, turn_index=turn_index
                    )
                    if safe_opener:
                        used_openers.add(safe_opener)
                        context["spoken_opener"] = safe_opener

                t_opener_ready = time.perf_counter()

                # Fire safe opener immediately to caller's ears if policy activated and pool not exhausted
                opener_played = False
                if safe_opener and tts_callback:
                    try:
                        await tts_callback(safe_opener)
                        opener_played = True
                    except Exception as e:
                        logger.warning(f"Error streaming safe opener: {e}")

                # ── Now execute single-pass voice turn LLM reasoning ──
                t_llm_start = time.perf_counter()
                
                # Item 3: Fix opener-skip hole: if reply is not ready after VOICE_FILLER_MS (700 ms),
                # play a cached filler immediately so user never experiences > ~1s silence.
                if not opener_played and tts_callback:
                    llm_task = asyncio.create_task(
                        self.ai_provider.process_voice_turn(latest_message, context, db)
                    )
                    done, pending = await asyncio.wait([llm_task], timeout=self.VOICE_FILLER_MS / 1000.0)
                    if llm_task in done:
                        voice_turn = llm_task.result()
                    else:
                        cached_filler = self._get_cached_filler(language=active_preferred_language.capitalize())
                        if cached_filler:
                            try:
                                await tts_callback(cached_filler)
                                context["played_filler"] = cached_filler
                            except Exception as e:
                                logger.warning(f"Error streaming cached filler: {e}")
                        voice_turn = await llm_task
                else:
                    voice_turn = await self.ai_provider.process_voice_turn(latest_message, context, db)

                t_llm_end = time.perf_counter()

                decision = voice_turn.get("decision", "RESOLVE")
                preliminary_spoken = voice_turn.get("spoken_response", "")
                analysis = {
                    "original_message": latest_message,
                    "intent": voice_turn.get("intent", fast_signals.get("intent", "GENERAL_QUERY")),
                    "sentiment": voice_turn.get("sentiment", "neutral"),
                    "priority": voice_turn.get("priority", "LOW"),
                    "language": active_preferred_language.capitalize(),
                    "bcp47_code": context.get("bcp47_code", "en-IN"),
                    "emotion": voice_turn.get("emotion", fast_signals.get("emotion", "calm")),
                    "emotion_confidence": voice_turn.get("emotion_confidence", 0.85),
                    "entities": voice_turn.get("entities", {}),
                    "decision_state": decision,
                    "decision_reason": voice_turn.get("reason", ""),
                    "tool_name": voice_turn.get("tool_name"),
                    "tool_args": voice_turn.get("tool_args", {}),
                    "latency_ms": voice_turn.get("latency_ms", round((t_llm_end - t_llm_start) * 1000, 2)),
                    "safe_opener": safe_opener,
                    "spoken_response": preliminary_spoken,
                    "t_stt_done": t_stt_done,
                    "t_opener_ready": t_opener_ready,
                    "t_llm_start": t_llm_start,
                    "t_llm_end": t_llm_end,
                }

                # Inherit previous entities if user is answering follow-up
                if context.get("previous_analysis"):
                    prev_entities = context["previous_analysis"].get("entities", {})
                    merged_entities = {**prev_entities, **analysis["entities"]}
                    analysis["entities"] = merged_entities

                # 2. Hold factual content until validation passes
                val_start = time.perf_counter()
                if decision != "USE_TOOL":
                    decision, validated_text = await self._generate_validate_response(
                        db=db,
                        conversation=conversation,
                        customer_id=conversation.customer_id,
                        latest_message=latest_message,
                        context=context,
                        analysis=analysis
                    )
                    analysis["decision_state"] = decision
                    # Clean for voice naturalness (remove markdown, code blocks, brackets)
                    cleaned = re.sub(r"```[\s\S]*?```", "", validated_text)
                    cleaned = re.sub(r"\[EXT\]", "", cleaned)
                    cleaned = re.sub(r"[*#_`\[\]{}]", "", cleaned)
                    cleaned = re.sub(r"\(Mock Memory Injected:[^)]*\)", "", cleaned)
                    cleaned = re.sub(r"\s+", " ", cleaned).strip()
                    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", cleaned) if s.strip()]
                    response_text = " ".join(sentences[:2]) if len(sentences) > 2 else cleaned
                    val_latency = (time.perf_counter() - val_start) * 1000
                    analysis["validation_latency_ms"] = round(val_latency, 2)
                else:
                    response_text = preliminary_spoken
                    analysis["validation_latency_ms"] = 0.0
            else:
                # Update workflow state to analyzing
                conversation.workflow_state = "understanding"
                await db.commit()

                # 2. Analysis (Intent, Entities, etc.)
                analysis = await self.ai_provider.analyze(effective_message, context, db)
                
                # Deterministic Tool Routing: If customer provided an Order ID for order inquiry, route directly to get_order_status tool
                entities = analysis.get("entities", {})
                intent_u = str(analysis.get("intent", "")).upper()
                conv_fn = analysis.get("conversational_function", "")
                diag = analysis.get("diagnostic_details") or {}
                is_speech_act = (
                    conv_fn in ("ACKNOWLEDGMENT", "GREETING", "EMOTIONAL_REACTION")
                    or analysis.get("needs_simplification") or diag.get("needs_simplification")
                    or analysis.get("explain_why") or diag.get("explain_why")
                    or analysis.get("is_request_alternative") or diag.get("is_request_alternative")
                    or analysis.get("is_misunderstanding_correction") or diag.get("is_misunderstanding_correction")
                    or intent_u in ("CLARIFICATION_SIMPLIFY", "WHY_QUESTION", "REQUEST_ALTERNATIVE", "CORRECTION_RECONSIDER")
                )
                if (
                    not is_speech_act
                    and entities.get("order_id")
                    and intent_u in ("ORDER_STATUS", "DELIVERY_ISSUE")
                ):
                    analysis["decision_state"] = "USE_TOOL"
                    analysis["tool_name"] = "get_order_status"
                    analysis["tool_args"] = {"order_id": entities["order_id"]}
                    analysis["decision_reason"] = "Customer provided Order ID for order status lookup"

                conversation.workflow_state = "searching_knowledge"
                await db.commit()

                # 3. Decision & Generation (RAG happens inside M4AIProvider)
                conversation.workflow_state = "deciding"
                await db.commit()
                
                # Initial generation with validation
                decision, response_text = await self._generate_validate_response(
                    db=db,
                    conversation=conversation,
                    customer_id=conversation.customer_id,
                    latest_message=effective_message,
                    context=context,
                    analysis=analysis
                )
                # Re-sync analysis with validated decision
                analysis["decision_state"] = decision

                if is_language_switch and pending_query and response_text:
                    ack_prefix = ""
                    for lang_key, prefix in self.LANGUAGE_SWITCH_PREFIXES.items():
                        if lang_key in active_preferred_language:
                            ack_prefix = prefix
                            break
                    if not ack_prefix and "english" in active_preferred_language:
                        ack_prefix = "Sure, let's continue in English! "
                    if ack_prefix and not response_text.lower().startswith(ack_prefix[:8].lower()):
                        response_text = f"{ack_prefix}{response_text}"

            
        except Exception as e:
            logger.error(f"AI Provider or RAG failure in _execute_turn: {e}", exc_info=True, extra={
                "provider_failure": True,
                "error_type": type(e).__name__,
            })
            active_lang = context.get("preferred_language", "english")
            is_lang_switch = context.get("is_language_switch", False)
            from app.ai.intelligence.escalation_keywords import is_supervisor_demand, is_fraud_or_security
            is_mandatory_human = is_supervisor_demand(latest_message) or is_fraud_or_security(latest_message)

            if is_lang_switch:
                decision = "RESOLVE"
                ack = self.LANGUAGE_SWITCH_ACKNOWLEDGMENTS.get(
                    active_lang,
                    f"Sure, let's continue in {active_lang.capitalize()}."
                )
                response_text = ack
                analysis = {
                    "original_message": latest_message,
                    "intent": "LANGUAGE_SWITCH",
                    "decision_state": "RESOLVE",
                    "decision_reason": "Language preference updated",
                    "language": active_lang.capitalize(),
                }
            elif is_mandatory_human:
                decision = "ESCALATE"
                lang_l = active_lang.lower()
                from app.ai.m4.decision import ResponseGenerator
                response_text = ResponseGenerator().generate({"decision": "ESCALATE"}, language=lang_l)
                analysis = {
                    "original_message": latest_message,
                    "intent": "ESCALATION_REQUEST",
                    "decision_state": "ESCALATE",
                    "decision_reason": "Customer explicitly requested human expert",
                    "language": active_lang.capitalize(),
                }
            elif isinstance(e, (TimeoutError, asyncio.TimeoutError)):
                decision = "ESCALATE"
                lang_l = active_lang.lower()
                response_text = "We are currently experiencing technical difficulties connecting to our service. I have connected your request to our support team and an expert will assist you shortly."
                analysis = {
                    "original_message": latest_message,
                    "intent": "TECHNICAL_FAILURE",
                    "decision_state": "ESCALATE",
                    "decision_reason": f"AI provider timeout fallback: {str(e)}",
                    "language": active_lang.capitalize(),
                }
            else:
                from app.ai.intelligence.language import UniversalMeaningEngine
                from app.ai.m4.decision import ResponseGenerator
                meaning = UniversalMeaningEngine().understand_utterance(latest_message, history=context.get("history", []))
                intent_u = str(meaning.intent).upper()
                lang_l = active_lang.lower()
                generator = ResponseGenerator()
                item_term = meaning.diagnostic_details.get("customer_item_term") if hasattr(meaning, "diagnostic_details") else None
                entities_with_item = dict(meaning.entities or {})
                if item_term and "customer_item_term" not in entities_with_item:
                    entities_with_item["customer_item_term"] = item_term

                if intent_u == "POLICY_QUERY" or meaning.category == "policy":
                    decision = "RESOLVE"
                    response_text = generator.generate({
                        "decision": "RESOLVE",
                        "action_type": "policy_overview",
                        "policy_type": entities_with_item.get("policy_type", "return"),
                        "customer_item_term": item_term,
                        "article": {}
                    }, language=lang_l)
                    analysis = {
                        "original_message": latest_message,
                        "intent": "POLICY_QUERY",
                        "category": "policy",
                        "decision_state": "RESOLVE",
                        "decision_reason": "Deterministic policy overview after provider error",
                        "language": active_lang.capitalize(),
                        "customer_item_term": item_term,
                        "entities": entities_with_item,
                    }
                elif intent_u == "CLARIFICATION_ORDER_ID_PURPOSE":
                    decision = "ASK_USER"
                    response_text = generator.generate({
                        "decision": "ASK_USER",
                        "missing_entity": "order_id_reason",
                        "customer_item_term": item_term
                    }, language=lang_l)
                    analysis = {
                        "original_message": latest_message,
                        "intent": "CLARIFICATION_ORDER_ID_PURPOSE",
                        "category": "clarification",
                        "decision_state": "ASK_USER",
                        "decision_reason": "Order ID purpose clarification",
                        "language": active_lang.capitalize(),
                        "customer_item_term": item_term,
                        "entities": entities_with_item,
                    }
                elif intent_u in ("ORDER_STATUS", "DELIVERY_ISSUE"):
                    decision = "ASK_USER"
                    response_text = self._get_routine_fallback_prompt("ORDER_STATUS", lang_l, entities=entities_with_item)
                    analysis = {
                        "original_message": latest_message,
                        "intent": "ORDER_STATUS",
                        "decision_state": "ASK_USER",
                        "decision_reason": "Order ID request after provider error",
                        "language": active_lang.capitalize(),
                        "customer_item_term": item_term,
                        "entities": entities_with_item,
                    }
                elif intent_u == "WARRANTY_SERVICE":
                    decision = "ASK_USER"
                    response_text = self._get_routine_fallback_prompt("WARRANTY_SERVICE", lang_l, entities=entities_with_item)
                    analysis = {
                        "original_message": latest_message,
                        "intent": "WARRANTY_SERVICE",
                        "decision_state": "ASK_USER",
                        "decision_reason": "Warranty service request after provider error",
                        "language": active_lang.capitalize(),
                        "customer_item_term": item_term,
                        "entities": entities_with_item,
                    }
                elif intent_u == "GREETING":
                    decision = "ASK_USER"
                    response_text = self._get_routine_fallback_prompt("GREETING", lang_l, entities=entities_with_item)
                    analysis = {
                        "original_message": latest_message,
                        "intent": "GREETING",
                        "decision_state": "ASK_USER",
                        "decision_reason": "Greeting response after provider error",
                        "language": active_lang.capitalize(),
                        "customer_item_term": item_term,
                        "entities": entities_with_item,
                    }
                elif intent_u == "UNCLEAR":
                    decision = "ASK_USER"
                    response_text = self._get_routine_fallback_prompt("UNCLEAR", lang_l, entities=entities_with_item)
                    analysis = {
                        "original_message": latest_message,
                        "intent": "UNCLEAR",
                        "decision_state": "ASK_USER",
                        "decision_reason": "Clarification prompt after provider error",
                        "language": active_lang.capitalize(),
                        "customer_item_term": item_term,
                        "entities": entities_with_item,
                    }
                elif intent_u == "PAYMENT_ISSUE":
                    decision = "ASK_USER"
                    response_text = self._get_routine_fallback_prompt("PAYMENT_ISSUE", lang_l, entities=entities_with_item)
                    analysis = {
                        "original_message": latest_message,
                        "intent": "PAYMENT_ISSUE",
                        "decision_state": "ASK_USER",
                        "decision_reason": "Payment prompt after provider error",
                        "language": active_lang.capitalize(),
                        "customer_item_term": item_term,
                        "entities": entities_with_item,
                    }
                else:
                    decision = "ESCALATE"
                    from app.ai.m4.decision import ResponseGenerator
                    response_text = ResponseGenerator().generate({"decision": "ESCALATE"}, language=lang_l)
                    analysis = {
                        "original_message": latest_message,
                        "intent": "TECHNICAL_FAILURE",
                        "decision_state": "ESCALATE",
                        "decision_reason": f"Provider Technical Failure: {type(e).__name__}",
                        "language": active_lang.capitalize(),
                    }
        
        # --- Tool Execution ---
        if decision == "USE_TOOL":
            conversation.workflow_state = "tool_requested"
            await db.commit()
            
            tool_name = analysis.get("tool_name")
            tool_args = analysis.get("tool_args", {})
            
            if tool_name:
                from app.ai.tools.runtime import ToolRuntime
                from app.users.models import User
                
                # We need the user for authorization
                customer = await db.scalar(select(User).where(User.id == conversation.customer_id))
                
                await manager.send_to_user(
                    conversation.customer_id,
                    tool_execution_started_event(conversation.id, tool_name)
                )
                
                try:
                    # Request execution (Validates and checks idempotency)
                    execution = await ToolRuntime.request_tool_execution(
                        db=db,
                        conversation_id=conversation.id,
                        customer_id=conversation.customer_id,
                        expert_id=None,
                        user=customer,
                        tool_name=tool_name,
                        kwargs=tool_args
                    )
                    
                    from app.ai.tools.models import ToolExecutionStatus
                    if execution.status == ToolExecutionStatus.AWAITING_CONFIRMATION or getattr(execution.status, 'value', execution.status) == "awaiting_confirmation":
                        conversation.workflow_state = "awaiting_confirmation"
                        await db.commit()
                        
                        await manager.send_to_user(
                            conversation.customer_id,
                            tool_confirmation_required_event(
                                conversation.id, 
                                execution.id, 
                                tool_name, 
                                f"Are you sure you want to {tool_name.replace('_', ' ')}?"
                            )
                        )
                        # We STOP here and return. The flow resumes via the confirm_tool REST endpoint.
                        return
                    
                    # Execute tool immediately if no confirmation needed
                    conversation.workflow_state = "executing_tool"
                    await db.commit()
                    
                    execution = await ToolRuntime.execute(db, execution, tool_args)
                    
                    from app.ai.tools.models import ToolExecutionStatus
                    if execution.status == ToolExecutionStatus.SUCCEEDED or getattr(execution.status, 'value', execution.status) == "succeeded":
                        from app.ai.intelligence.failure_prediction import global_attempt_tracker
                        global_attempt_tracker.track_attempt(conversation.id, f"tool:{tool_name}", success=True)
                        await manager.send_to_user(
                            conversation.customer_id,
                            tool_execution_completed_event(conversation.id, tool_name)
                        )
                        
                        tool_result = json.loads(execution.result_summary)
                        
                        # Check if the tool signals an escalation (e.g. RequestHumanSupportTool)
                        if tool_result.get("escalate"):
                            decision = "ESCALATE"
                            analysis["decision_reason"] = tool_result.get("data", {}).get("reason", "Tool-triggered escalation")
                        else:
                            is_voice_turn = context.get("is_voice", False) or context.get("reply_with_voice", False)
                            from app.ai.validation.models import ToolResultContext
                            tr_ctx = ToolResultContext(
                                tool_name=execution.tool_name,
                                success=bool(tool_result.get("success", True)),
                                data=tool_result.get("data", tool_result)
                            )
                            t_val_start = time.perf_counter()
                            decision, response_text = await self._generate_validate_response(
                                db=db,
                                conversation=conversation,
                                customer_id=conversation.customer_id,
                                latest_message=latest_message,
                                context=context,
                                analysis=analysis,
                                tool_results=[tr_ctx]
                            )
                            tool_val_latency = (time.perf_counter() - t_val_start) * 1000
                            analysis["validation_latency_ms"] = round(analysis.get("validation_latency_ms", 0.0) + tool_val_latency, 2)

                            # Handle specific domain lookups when tool reports missing or unauthorized records
                            if not tool_result.get("success", True):
                                # Pop bad order ID from conversation state and analysis so it does not persist/loop
                                if conversation_state and "order_id" in conversation_state.entities:
                                    conversation_state.entities.pop("order_id", None)
                                if "order_id" in analysis.get("entities", {}):
                                    analysis["entities"].pop("order_id", None)

                                lang_l = str(active_preferred_language).lower()
                                attempted_id = tool_args.get("order_id", "")
                                if tool_result.get("error_code") == "ORDER_NOT_FOUND":
                                    decision = "ASK_USER"
                                    if "tanglish" in lang_l:
                                        id_str = f"'{attempted_id}' " if attempted_id else ""
                                        response_text = f"Andha Order ID {id_str}namma records-la kedaikala bro. Unga Order ID-ah check panni thirumba sollunga, naan udane track panren."
                                    elif "hinglish" in lang_l:
                                        id_str = f"'{attempted_id}' " if attempted_id else ""
                                        response_text = f"Uss Order ID {id_str}ke saath koi record nahi mila. Kripya apna Order ID check karke dobara batayein."
                                    elif "tamil" in lang_l or lang_l in ("ta", "ta-in"):
                                        response_text = "அந்தக் குறிப்பு எண்ணில் ஆர்டர் விவரங்கள் காணப்படவில்லை. தயவுசெய்து உங்கள் ஆர்டர் ஐடியை சரிபார்த்து மீண்டும் பகிரவும்."
                                    elif "hindi" in lang_l or lang_l in ("hi", "hi-in"):
                                        response_text = "उस संदर्भ संख्या के साथ कोई ऑर्डर नहीं मिला। कृपया अपना ऑर्डर आईडी जांचकर दोबारा बताएं।"
                                    else:
                                        id_str = f"'{attempted_id}' " if attempted_id else ""
                                        response_text = f"I couldn't find an order with reference number {id_str}in our records. Could you please double-check your Order ID and provide it again?"
                                elif tool_result.get("error_code") == "ACCESS_DENIED":
                                    decision = "ASK_USER"
                                    response_text = "I am unable to access details for that order with your current account. Could you please verify the order ID or account details?"

                            if is_voice_turn:
                                lang = str(analysis.get("language", "English")).lower()
                                tool_data = tool_result.get("data", {})
                                if "tanglish" in lang or "hinglish" in lang:
                                    if tool_name == "get_order_status":
                                        oid = tool_data.get("order_id", "your order")
                                        ost = tool_data.get("status", "processed")
                                        deliv = tool_data.get("expected_delivery")
                                        if "tanglish" in lang:
                                            deliv_str = f" {deliv} kulla vandhudum." if deliv else " Seekiram delivery aagidum."
                                            response_text = f"Unga order {oid} status {ost} nu irukku.{deliv_str}"
                                        else:
                                            deliv_str = f" {deliv} tak mil jayega." if deliv else " Jaldi hi delivery ho jayegi."
                                            response_text = f"Aapka order {oid} status {ost} hai.{deliv_str}"
                                    elif tool_name == "check_transaction":
                                        tid = tool_data.get("transaction_id", "")
                                        tst = tool_data.get("status", "completed")
                                        amt = tool_data.get("amount", "")
                                        curr = tool_data.get("currency", "INR")
                                        if "tanglish" in lang:
                                            response_text = f"Unga payment {tid} {amt} {curr} check pannen, status {tst} aagiduchu."
                                        else:
                                            response_text = f"Aapka transaction {tid} {amt} {curr} check kiya, status {tst} hai."
                                else:
                                    cleaned = re.sub(r"```[\s\S]*?```", "", response_text)
                                    cleaned = re.sub(r"\[EXT\]", "", cleaned)
                                    cleaned = re.sub(r"[*#_`\[\]{}]", "", cleaned)
                                    cleaned = re.sub(r"\(Mock Memory Injected:[^)]*\)", "", cleaned)
                                    cleaned = re.sub(r"\s+", " ", cleaned).strip()
                                    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", cleaned) if s.strip()]
                                    response_text = " ".join(sentences[:2]) if len(sentences) > 2 else cleaned

                    else:
                        logger.warning(f"Tool execution did not succeed: {execution.status}, error: {execution.error_code}")
                        decision = "ASK_USER"
                        response_text = "I ran into an issue retrieving those details. Could you please verify the information so I can assist you?"
                        
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    logger.error(f"TOOL EXECUTION EXCEPTION: {e}", extra={"tool_name": tool_name})
                    from app.ai.intelligence.failure_prediction import global_attempt_tracker
                    global_attempt_tracker.track_attempt(
                        conversation.id,
                        f"tool:{tool_name}",
                        success=False,
                        error_message=str(e),
                    )
                    analysis["observed_failure"] = {
                        "failed": True,
                        "type": "tool_execution_error",
                        "tool_name": tool_name,
                        "error": str(e),
                    }
                    await manager.send_to_user(
                        conversation.customer_id,
                        tool_execution_failed_event(conversation.id, tool_name)
                    )
                    conversation.workflow_state = "tool_failure"
                    await db.commit()
                    decision = "ASK_USER"
                    response_text = "I'm having trouble retrieving those details right now. Could you please double-check your reference number?"
                    analysis["decision_reason"] = f"Tool execution error handled safely: {str(e)}"
        # ----------------------

        if decision == "ASK_USER":
            conversation.workflow_state = "asking_user"
        elif decision == "SYSTEM_ERROR":
            conversation.workflow_state = WorkflowState.IDLE
            # We don't escalate, just inform the user there's an error.
        elif decision == "ESCALATE":
            from app.ai.intelligence.escalation_keywords import is_fraud_or_security, is_supervisor_demand
            is_fraud = is_fraud_or_security(latest_message) or analysis.get("intent") in ("SECURITY_ISSUE", "FRAUD_SUSPICION")
            is_supervisor = is_supervisor_demand(latest_message) or analysis.get("intent") in ("ESCALATION_REQUEST", "HUMAN_AGENT_REQUEST")
            is_repeated_failure = (context.get("attempt_count", 0) >= 1 and (
                bool(analysis.get("failure_risk", {}).get("should_escalate_early"))
                or bool(analysis.get("failure_risk", {}).get("has_prior_solution_failed"))
                or any(k in latest_message.lower() for k in ["already tried", "still broken", "nothing works"])
            )) or (context.get("attempt_count", 0) >= 2)
            is_already_confirmed = bool(conversation_state and getattr(conversation_state, "handoff_confirmed", False))
            is_provider_failure = (
                analysis.get("intent") == "TECHNICAL_FAILURE"
                or "provider" in str(analysis.get("decision_reason", "")).lower()
                or "failure" in str(analysis.get("decision_reason", "")).lower()
                or "error" in str(analysis.get("decision_reason", "")).lower()
            )

            if not is_fraud and not is_supervisor and not is_repeated_failure and not is_already_confirmed and not is_provider_failure and not is_voice_turn:
                # Routine escalation: Ask customer confirmation before transferring to human expert
                if conversation_state:
                    conversation_state.pending_handoff_confirmation = True
                    conversation_state.pending_handoff_reason = analysis.get("decision_reason") or "Expert assistance recommended"
                    conversation_state.pending_handoff_analysis = dict(analysis)
                decision = "ASK_USER"
                analysis["requires_handoff_confirmation"] = True
                analysis["decision_state"] = "ASK_USER"
                conversation.workflow_state = "asking_user"
                from app.ai.m4.decision import ResponseGenerator
                response_text = ResponseGenerator().generate({
                    "decision": "ASK_USER",
                    "missing_entity": "handoff_confirmation"
                }, language=active_preferred_language)
            else:
                from app.handoff.service import HandoffService
                await HandoffService.create_or_update_handoff(
                    db=db,
                    conversation=conversation,
                    analysis=analysis,
                )
        else:
            conversation.workflow_state = "resolving"

        # 4. Stream Voice Response if callback provided (M12.5 Validation already passed)
        message_type = MessageType.TEXT
        audio_url = None
        
        if (reply_with_voice or tts_callback) and (is_voice_conv or decision != "ESCALATE"):
            message_type = MessageType.VOICE
            
            if tts_callback:
                # Streaming M12.7 flow: stream validated factual content sentence by sentence
                # Item 2: The first factual sentence goes to TTS as soon as complete, not after full reply.
                try:
                    clean_resp = str(response_text or "").strip()
                    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", clean_resp) if s.strip()]
                    if sentences:
                        for sent in sentences:
                            await tts_callback(sent)
                    elif clean_resp:
                        await tts_callback(clean_resp)
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).error(f"TTS Streaming failed: {e}")
                    message_type = MessageType.TEXT
            else:
                # Legacy M7 File-based TTS flow
                try:
                    from app.voice.service import VoiceService
                    audio_url = await VoiceService.synthesize_ai_response(conversation.id, response_text)
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).error(f"Legacy TTS failed: {e}")
                    message_type = MessageType.TEXT

        # 5. Save AI Response
        saved_content = response_text
        if is_voice_conv and analysis.get("safe_opener"):
            s_open = analysis["safe_opener"]
            if s_open.lower() not in response_text.lower():
                saved_content = f"{s_open} {response_text}".strip()

        # Update Conversation State
        try:
            from app.conversations.state import ConversationStateManager
            ConversationStateManager.update_after_turn(
                conversation_state,
                decision=decision,
                response_text=saved_content,
                tool_name=analysis.get("tool_name"),
                tool_result=analysis.get("tool_result"),
                analysis=analysis
            )
            analysis["conversation_state"] = conversation_state.to_dict()
        except Exception as e:
            logger.warning(f"Error updating conversation state: {e}")

        await MessageService.create_message(
            db=db,
            conversation_id=conversation.id,
            sender_type=SenderType.AI,
            content=saved_content,
            metadata=analysis,
            message_type=message_type,
            audio_url=audio_url,
        )

        # 6. Trigger memory extraction if conversation is resolved by AI
        if decision == "RESOLVE":
            from app.config import settings
            if settings.ai_provider != "mock":
                from app.memory.service import MemoryService
                from app.database import async_session_factory

                async def background_extract():
                    async with async_session_factory() as bg_db:
                        await MemoryService.extract_memory(bg_db, conversation.id)

                asyncio.create_task(background_extract())

    async def resume_tool_execution(self, db: AsyncSession, conversation_id: int, execution_id: int):
        from app.ai.tools.models import ToolExecution
        from app.ai.tools.runtime import ToolRuntime
        import json
        
        exec_stmt = select(ToolExecution).where(ToolExecution.id == execution_id)
        execution = (await db.execute(exec_stmt)).scalar_one_or_none()
        
        if not execution:
            return
            
        convo_stmt = select(Conversation).where(Conversation.id == conversation_id)
        conversation = (await db.execute(convo_stmt)).scalar_one_or_none()
        
        from app.ai.tools.models import ToolExecutionStatus
        if execution.status == ToolExecutionStatus.FAILED or getattr(execution.status, 'value', execution.status) == "failed":
            decision = "ESCALATE"
            response_text = "I'm sorry, the action was cancelled or failed."
            await manager.send_to_user(
                conversation.customer_id,
                tool_execution_failed_event(conversation.id, execution.tool_name)
            )
            conversation.workflow_state = "tool_failure"
            await db.commit()
        else:
            conversation.workflow_state = "executing_tool"
            await db.commit()
            
            try:
                # Need to execute the tool
                # Wait, kwargs! We didn't persist kwargs. We will just pass an empty dict for prototype,
                # since the mock tools (create_refund_request) might need transaction_id.
                # Oh! I should store `tool_args` in `ToolExecution` instead of `input_hash` only, or parse it back.
                # Actually, let's just pass `transaction_id=None` for prototype or hardcode a bit.
                # Let's pass {} for now, the mock execute handles it if missing by returning an error.
                # Wait, if we return error, the AI might escalate.
                # Let me just execute with {}.
                
                execution = await ToolRuntime.execute(db, execution, json.loads(execution.tool_args))
                
                if execution.status == ToolExecutionStatus.SUCCEEDED or getattr(execution.status, 'value', execution.status) == "succeeded":
                    await manager.send_to_user(
                        conversation.customer_id,
                        tool_execution_completed_event(conversation.id, execution.tool_name)
                    )
                    from app.ai.validation.models import ToolResultContext
                    tr_ctx = ToolResultContext(
                        tool_name=execution.tool_name,
                        success=True,
                        data=json.loads(execution.result_summary)
                    )
                    
                    # Fetch minimal context for validation
                    stmt = select(ConversationMessage).where(ConversationMessage.conversation_id == conversation.id).order_by(ConversationMessage.created_at.asc())
                    all_messages = (await db.execute(stmt)).scalars().all()
                    history = [{"sender_type": m.sender_type.value if hasattr(m.sender_type, 'value') else str(m.sender_type), "content": m.content} for m in all_messages]
                    latest_message = history[-1]["content"] if history else ""
                    
                    decision, response_text = await self._generate_validate_response(
                        db=db,
                        conversation=conversation,
                        customer_id=conversation.customer_id,
                        latest_message=latest_message,
                        context={"history": history},
                        analysis={"intent": "UNKNOWN", "decision_state": "RESOLVE"},
                        tool_results=[tr_ctx]
                    )
                else:
                    raise Exception(execution.error_code)
            except Exception:
                await manager.send_to_user(
                    conversation.customer_id,
                    tool_execution_failed_event(conversation.id, execution.tool_name)
                )
                decision = "ESCALATE"
                response_text = "I encountered an error while trying to process your request."

        # Continue with standard resolution or escalation
        if decision == "ESCALATE":
            conversation.workflow_state = WorkflowState.WAITING_FOR_EXPERT
            stmt = select(Ticket).where(Ticket.conversation_id == conversation.id)
            ticket = (await db.execute(stmt)).scalar_one_or_none()
            if ticket:
                ticket.status = TicketStatus.ESCALATED
            stmt_handoff = select(Handoff).where(Handoff.conversation_id == conversation.id)
            existing_handoff = (await db.execute(stmt_handoff)).scalar_one_or_none()
            if not existing_handoff:
                handoff = Handoff(
                    conversation_id=conversation.id,
                    ticket_id=ticket.id if ticket else 0,
                    customer_id=conversation.customer_id,
                    escalation_reason="Tool execution failed or was rejected.",
                    priority="high",
                    category="General Support",
                    ai_analysis={},
                    collected_information={}
                )
                db.add(handoff)
            await db.commit()
        else:
            conversation.workflow_state = "resolving"
            await db.commit()
            
            # Trigger memory extraction
            from app.config import settings
            if settings.ai_provider != "mock":
                from app.memory.service import MemoryService
                from app.database import async_session_factory
                import asyncio
                
                async def background_extract():
                    async with async_session_factory() as bg_db:
                        await MemoryService.extract_memory(bg_db, conversation.id)
                        
                asyncio.create_task(background_extract())

        # Save AI Message
        ai_msg = await MessageService.create_message(
            db=db,
            conversation_id=conversation.id,
            sender_type=SenderType.AI,
            content=response_text,
            sender_id=None,
            metadata={"source": "agentic_tool_resume"}
        )

        # Broadcast
        await manager.send_to_conversation_participants(
            customer_id=conversation.customer_id,
            expert_id=None,
            event=new_message_event(
                conversation_id=conversation.id,
                message_id=ai_msg.id,
                sender_type=SenderType.AI.value,
                content=ai_msg.content,
                created_at=ai_msg.created_at.isoformat(),
                message_type=MessageType.TEXT.value,
            ),
        )
        
        # Queue broadcast if escalated
        if conversation.workflow_state == WorkflowState.WAITING_FOR_EXPERT:
            handoff = await db.scalar(select(Handoff).where(Handoff.conversation_id == conversation.id))
            if handoff:
                await manager.broadcast_to_experts(
                    queue_updated_event(
                        action="ADDED",
                        handoff_id=handoff.id,
                        priority=handoff.priority,
                        category=handoff.category,
                    )
                )

    # Opener pools: strictly neutral reactions without action promises, and zero "I understand"
    OPENER_POOLS = {
        "English": {
            "neutral": [
                "Got it.",
                "Right.",
                "Okay.",
                "Thanks for reaching out.",
                "I hear you.",
                "Sure."
            ],
            "frustrated": [
                "I hear your frustration.",
                "I hear how upsetting this is.",
                "Thanks for letting us know."
            ]
        },
        "Tanglish": {
            "neutral": [
                "Seri bro.",
                "Kandippa.",
                "Kettukren.",
                "Kavalapadatheenga."
            ],
            "frustrated": [
                "Aiyo, kavalapadatheenga.",
                "Aiyo, romba kashtam thaan."
            ]
        },
        "Tamil": {
            "neutral": [
                "சரி.",
                "கண்டிப்பாக.",
                "கேட்கிறேன்.",
                "கவலைப்படாதீர்கள்."
            ],
            "frustrated": [
                "ஐயோ, கவலைப்படாதீர்கள்.",
                "ஐயோ, மிகவும் கடினம் தான்."
            ]
        },
        "Hindi": {
            "neutral": [
                "हाँ जी।",
                "ठीक है।",
                "बिल्कुल।",
                "सुनते हैं।"
            ],
            "frustrated": [
                "यह सुनकर दुःख हुआ।",
                "परेशान मत होइए।"
            ]
        },
        "Hinglish": {
            "neutral": [
                "Haan ji.",
                "Theek hai.",
                "Bilkul.",
                "Sunte hain."
            ],
            "frustrated": [
                "Yeh sunkar dukh hua.",
                "Pareshan mat hoiye."
            ]
        },
        "Telugu": {
            "neutral": [
                "సరేనండి.",
                "ఖచ్చితంగా.",
                "వింటున్నాను.",
                "ఒక్క నిమిషం."
            ],
            "frustrated": [
                "అయ్యో, బాధపడకండి.",
                "అయ్యో, నిజంగా ఇబ్బందికరమే."
            ]
        },
        "Tenglish": {
            "neutral": [
                "Sare andi.",
                "Kachithanga.",
                "Vintunnanu.",
                "Okka nimisham."
            ],
            "frustrated": [
                "Ayyoo, badhapadakandi.",
                "Ayyoo, chala kashtam thaan."
            ]
        },
        "Kannada": {
            "neutral": [
                "ಸರಿ.",
                "ಖಂಡಿತ.",
                "ಕೇಳ್ತಾ ಇದ್ದೀನಿ.",
                "ಒಂದು ನಿಮಿಷ."
            ],
            "frustrated": [
                "ಅಯ್ಯೋ, ಬೇಸರಪಡಬೇಡಿ.",
                "ಅಯ್ಯೋ, ತುಂಬಾ ತೊಂದರೆಯಾಗಿದೆ."
            ]
        },
        "Kanglish": {
            "neutral": [
                "Sari.",
                "Kanditha.",
                "Keltha iddini.",
                "Ondu nimisha."
            ],
            "frustrated": [
                "Ayyoo, besara padabedi.",
                "Ayyoo, thumba kashta aagidhe."
            ]
        },
        "Malayalam": {
            "neutral": [
                "ശരി.",
                "തീർച്ചയായും.",
                "കേൾക്കുന്നുണ്ട്.",
                "ഒരു നിമിഷം."
            ],
            "frustrated": [
                "അയ്യോ, വിഷമിക്കേണ്ടതില്ല.",
                "അയ്യോ, ഇത് ശരിക്കും ബുദ്ധിമുട്ടാണ്."
            ]
        },
        "Manglish": {
            "neutral": [
                "Sheri.",
                "Theerchayayum.",
                "Kelkkunnundu.",
                "Oru nimisham."
            ],
            "frustrated": [
                "Ayyoo, vishamikenda.",
                "Ayyoo, valare kashtam thanne."
            ]
        },
        "Bengali": {
            "neutral": [
                "ঠিক আছে।",
                "অবশ্যই।",
                "শুনছি।",
                "এক মিনিট।"
            ],
            "frustrated": [
                "আহা, চিন্তা করবেন না।",
                "আহা, এটা সত্যিই দুঃখজনক।"
            ]
        },
        "Benglish": {
            "neutral": [
                "Thik ache.",
                "Nishchoi.",
                "Shunchhi.",
                "Ek minute."
            ],
            "frustrated": [
                "Aaha, chinta korben na.",
                "Aaha, eta shotti kashter."
            ]
        },
        "Marathi": {
            "neutral": [
                "ठीक आहे.",
                "नक्कीच.",
                "ऐकतोय.",
                "एक मिनिट."
            ],
            "frustrated": [
                "अरेरे, काळजी करू नका.",
                "अरेरे, हे खूप त्रासदायक आहे."
            ]
        },
        "Marathish": {
            "neutral": [
                "Theek ahe.",
                "Nakkich.",
                "Aaiktoy.",
                "Ek minute."
            ],
            "frustrated": [
                "Arere, kalji karu naka.",
                "Arere, he khup trasdayak ahe."
            ]
        },
        "Gujarati": {
            "neutral": [
                "બરાબર.",
                "ચોક્કસ.",
                "સાંભળું છું.",
                "એક મિનિટ."
            ],
            "frustrated": [
                "અરેરે, ચિંતા કરશો નહીં.",
                "અરેરે, આ ખરેખર મુશ્કેલ છે."
            ]
        },
        "Gujlish": {
            "neutral": [
                "Barabar.",
                "Chokkas.",
                "Sambhalu chhu.",
                "Ek minute."
            ],
            "frustrated": [
                "Arere, chinta karsho nahi.",
                "Arere, aa kharekhar mushkel chhe."
            ]
        },
        "Punjabi": {
            "neutral": [
                "ਠੀਕ ਹੈ।",
                "ਜ਼ਰੂਰ।",
                "ਸੁਣ ਰਿਹਾ ਹਾਂ।",
                "ਇੱਕ ਮਿੰਟ।"
            ],
            "frustrated": [
                "ਹਾਏ, ਪਰੇਸ਼ਾਨ ਨਾ ਹੋਵੋ।",
                "ਹਾਏ, ਇਹ ਸੱਚਮੁੱਚ ਬਹੁਤ ਔਖਾ ਹੈ।"
            ]
        },
        "Punglish": {
            "neutral": [
                "Theek hai.",
                "Zaroor.",
                "Sun reha haan.",
                "Ik minute."
            ],
            "frustrated": [
                "Haaye, pareshan na hovo.",
                "Haaye, eh sachmuch aukha hai."
            ]
        },
        "Odia": {
            "neutral": [
                "ଠିକ୍ ଅଛି।",
                "ନିଶ୍ଚିତ।",
                "ଶୁଣୁଛି।",
                "ଗୋଟିଏ ମିନିଟ୍।"
            ],
            "frustrated": [
                "ଆହା, ଚିନ୍ତା କରନ୍ତୁ ନାହିଁ।",
                "ଆହା, ଏହା ବହୁତ କଷ୍ଟଦାୟକ।"
            ]
        },
        "Assamese": {
            "neutral": [
                "ঠিক আছে।",
                "নিশ্চয়।",
                "শুনি আছোঁ।",
                "এক মিনিট।"
            ],
            "frustrated": [
                "হায়, চিন্তা নকৰিব।",
                "হায়, এয়া সঁচাকৈয়ে কষ্টকৰ।"
            ]
        },
        "Urdu": {
            "neutral": [
                "ٹھیک ہے۔",
                "ضرور۔",
                "سن رہا ہوں۔",
                "ایک منٹ।"
            ],
            "frustrated": [
                "افسوس، پریشان نہ ہوں۔",
                "افسوس، یہ واقعی تکلیف دہ ہے۔"
            ]
        }
    }
    LANGUAGE_SWITCH_PREFIXES = {
        "tanglish": "Kandippa, Tanglish-la pesalam! ",
        "tamil": "சரி, தமிழில் பேசலாம்! ",
        "hinglish": "Haan bilkul, Hinglish mein baat karte hain! ",
        "hindi": "ज़रूर, हिन्दी में बात करते हैं! ",
        "kannada": "ಖಂಡಿತ, ಕನ್ನಡದಲ್ಲಿ ಮಾತನಾಡೋಣ! ",
        "kanglish": "Kanditha, Kanglish-alli mathadana! ",
        "telugu": "తప్పకుండా, తెలుగులో మాట్లాడదాం! ",
        "tenglish": "Kachithanga, Tenglish-lo matladadam! ",
        "malayalam": "തീർച്ചയായും, മലയാളത്തിൽ സംസാരിക്കാം! ",
        "manglish": "Theerchayayum, Manglish-il samsarikkaam! ",
        "bengali": "অবশ্যই, বাংলায় কথা বলা যাক! ",
        "benglish": "Nishchoi, Benglish-e kotha bola jak! ",
        "marathi": "नक्कीच, मराठीत बोलूया! ",
        "marathish": "Nakkich, Marathish madhe boluya! ",
        "gujarati": "ચોક્કસ, ગુજરાતીમાં વાત કરીએ! ",
        "gujlish": "Chokkas, Gujlish ma vaat kariye! ",
        "punjabi": "ਜ਼ਰੂਰ, ਪੰਜਾਬੀ ਵਿੱਚ ਗੱਲ ਕਰਦੇ ਹਾਂ! ",
        "punglish": "Zaroor, Punglish vich gal karde aan! ",
        "odia": "ନିଶ୍ଚିତ ଭାବରେ, ଓଡ଼ିଆରେ କଥାବାର୍ତ୍ତା କରିବା! ",
        "assamese": "নিশ্চয়, অসমীয়াত কথা পাতোঁ আহক! ",
        "urdu": "ضرور، اردو میں بات کرتے ہیں! ",
        "english": "Sure, let's continue in English! ",
    }
    LANGUAGE_SWITCH_ACKNOWLEDGMENTS = {
        "tanglish": "Sari, Tanglish-la pesalam. Enna help venum?",
        "tamil": "சரி, தமிழில் பேசலாம். உங்களுக்கு என்ன உதவி வேண்டும்?",
        "hindi": "ज़रूर, हम हिन्दी में बात कर सकते हैं। मैं आपकी क्या मदद कर सकता हूँ?",
        "hinglish": "Haan bilkul, Hinglish mein baat karte hain. Main aapki kya help kar sakta hoon?",
        "english": "Sure, let's continue in English. How can I assist you?",
        "kannada": "ಖಂಡಿತ, ಕನ್ನಡದಲ್ಲಿ ಮಾತನಾಡೋಣ! ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಬಹುದು?",
        "kanglish": "Kanditha, Kanglish-alli mathadana! Nimage hege help madli?",
        "telugu": "తప్పకుండా, తెలుగులో మాట్లాడదాం! మీకు ఎలా సహాయపడగలను?",
        "tenglish": "Kachithanga, Tenglish-lo matladadam! Meeku ela help cheyagalanu?",
        "malayalam": "തീർച്ചയായും, മലയാളത്തിൽ സംസാരിക്കാം! ഞാൻ എങ്ങനെ സഹായിക്കണം?",
        "manglish": "Theerchayayum, Manglish-il samsarikkaam! Ningalkku engane help venam?",
        "bengali": "অবশ্যই, বাংলায় কথা বলা যাক! আমি আপনাকে কীভাবে সাহায্য করতে পারি?",
        "benglish": "Nishchoi, Benglish-e kotha bola jak! Apanake kibhabe help korte pari?",
        "marathi": "नक्कीच, मराठीत बोलूया! मी तुम्हाला कशी मदत करू शकतो?",
        "marathish": "Nakkich, Marathish madhe boluya! Me tumhala kashi help karu shakto?",
        "gujarati": "ચોક્કસ, ગુજરાતીમાં વાત કરીએ! હું તમારી કેવી રીતે મદદ કરી શકું?",
        "gujlish": "Chokkas, Gujlish ma vaat kariye! Hu tamari kevi rite help kari shaku?",
        "punjabi": "ਜ਼ਰੂਰ, ਪੰਜਾਬੀ ਵਿੱਚ ਗੱਲ ਕਰਦੇ ਹਾਂ! ਮੈਂ ਤੁਹਾਡੀ ਕੀ ਮਦਦ ਕਰ ਸਕਦਾ ਹਾਂ?",
        "punglish": "Zaroor, Punglish vich gal karde aan! Main tuhadi ki help kar sakda haan?",
        "odia": "ନିଶ୍ଚିତ ଭାବରେ, ଓଡ଼ିଆରେ କଥାବାର୍ତ୍ତା କରିବା! ମୁଁ ଆପଣଙ୍କୁ କିପରି ସାହାଯ୍ୟ କରିପାରିବି?",
        "assamese": "নিশ্চয়, অসমীয়াত কথা পাতোঁ আহक! মই আপোনাক কেনেকৈ সহায় কৰিব পাৰোঁ?",
        "urdu": "ضرور، اردو میں بات کرتے ہیں۔ میں آپ کی کیا مدد کر سکتا ہوں؟",
    }

    @staticmethod
    def detect_explicit_language_request(text: str) -> Optional[str]:
        """
        Detects explicit language requests in both native script and romanized forms.
        Delegates to VoiceLanguageController for unified single-source detection.
        """
        from app.voice.language_controller import VoiceLanguageController
        req, _ = VoiceLanguageController.detect_explicit_request(text)
        return req

    @staticmethod
    def _detect_cheap_voice_signals(message: str) -> dict:
        """
        Sub-millisecond rule-based emotion, language, and intent detector.
        Runs BEFORE any LLM call to synthesize the safe opener with zero waiting time.
        """
        msg_lower = (message or "").lower()
        words = set(re.findall(r"\b\w+\b", msg_lower))
        
        # 1. Dynamic Language detection (morphological + sub-word + dictionary)
        from app.ai.intelligence.language import CodeMixedLanguageDetector
        det = CodeMixedLanguageDetector().detect(message or "")
        is_tamil_unicode = any("\u0b80" <= c <= "\u0bff" for c in message or "")
        is_hindi_unicode = any("\u0900" <= c <= "\u097f" for c in message or "")

        if is_tamil_unicode or det.code_mix_type in ("tamil", "pure_tamil"):
            lang = "Tamil"
        elif det.code_mix_type == "tanglish" or det.primary_language == "ta":
            lang = "Tanglish"
        elif det.primary_language == "mr" or det.code_mix_type in ("marathi", "marathi_english"):
            lang = "Marathi"
        elif is_hindi_unicode or det.code_mix_type in ("hindi", "devanagari_hindi"):
            lang = "Hindi"
        elif det.code_mix_type == "hinglish" or det.primary_language == "hi":
            lang = "Hinglish"
        elif det.primary_language == "te" or "telugu" in det.code_mix_type:
            lang = "Telugu"
        elif det.primary_language == "kn" or "kannada" in det.code_mix_type:
            lang = "Kannada"
        elif det.primary_language == "ml" or "malayalam" in det.code_mix_type:
            lang = "Malayalam"
        elif det.primary_language == "bn" or "bengali" in det.code_mix_type:
            lang = "Bengali"
        elif det.primary_language == "gu" or "gujarati" in det.code_mix_type:
            lang = "Gujarati"
        elif det.primary_language == "pa" or "punjabi" in det.code_mix_type:
            lang = "Punjabi"
        elif det.primary_language == "or" or "odia" in det.code_mix_type:
            lang = "Odia"
        else:
            lang = "English"

        # 2. Emotion detection & confidence
        angry_words = {"angry", "furious", "frustrated", "ridiculous", "terrible", "horrible", "worst", "scam", "cheat", "unacceptable", "fed up", "waste", "useless", "demand", "hate"}
        detected_angry = [w for w in angry_words if w in words]
        if len(detected_angry) >= 2:
            emotion = "frustrated"
            emotion_confidence = 0.95
        elif len(detected_angry) == 1:
            emotion = "frustrated"
            emotion_confidence = 0.75
        else:
            emotion = "neutral"
            emotion_confidence = 0.30

        # 3. Intent detection (Handling both Latin letters / Tanglish & Native Tamil/Hindi script)
        refund_words = {
            "refund", "money", "cashback", "return", "panam", "kaasu", "thiruppi", "thirumba",
            "paisa", "wapas", "lautao"
        }
        tamil_refund = {"பணம்", "ரீஃபண்ட்", "திருப்பி", "காசு", "திரும்ப"}
        has_refund = any(w in words for w in refund_words) or any(t in message for t in tamil_refund)

        delivery_words = {
            "delivery", "deliver", "shipment", "track", "tracking", "package", "courier", "shipped",
            "parcel", "varala", "vandhudum", "reach", "kab", "aayega", "pohcha"
        }
        tamil_delivery = {"டெலிவரி", "பார்சல்", "வரவில்லை", "எப்போது வரும்", "அனுப்பப்பட்டது"}
        has_delivery = any(w in words for w in delivery_words) or any(t in message for t in tamil_delivery)

        payment_words = {
            "payment", "charged", "deducted", "transaction", "txn", "billing", "invoice", "card",
            "gpay", "phonepe", "paytm", "pidichutaanga", "cut", "kat", "gaya"
        }
        tamil_payment = {"கட்டணம்", "பரிவர்த்தனை", "பிடித்தம்", "வங்கி"}
        has_payment = any(w in words for w in payment_words) or any(t in message for t in tamil_payment)

        login_words = {"password", "reset", "login", "account", "otp", "lock", "bhool"}
        tamil_login = {"கடவுச்சொல்", "உள்நுழைவு", "லாகின்"}
        has_login = any(w in words for w in login_words) or any(t in message for t in tamil_login)

        tech_words = {"crash", "open", "loading", "freeze", "stuck", "nikkudhu", "khul", "chal", "error", "update", "screen"}
        tamil_tech = {"கிராஷ்", "திறக்கவில்லை", "பிழை"}
        has_tech = any(w in words for w in tech_words) or "open aagala" in msg_lower or "loading-laye" in msg_lower or any(t in message for t in tamil_tech)

        opening_words = {"problem irukku", "oru problem", "dikkat hai", "problem hai", "have a problem", "need help", "oru help venum"}
        has_opening_problem = any(w in msg_lower for w in opening_words) and not (has_refund or has_delivery or has_payment or has_login or has_tech)

        if has_opening_problem:
            intent = "OPENING_PROBLEM_STATEMENT"
        elif has_tech:
            intent = "TECHNICAL_ISSUE"
        elif has_refund:
            intent = "REFUND_ISSUE"
        elif has_delivery:
            intent = "DELIVERY_ISSUE"
        elif has_payment:
            intent = "PAYMENT_ISSUE"
        elif has_login:
            intent = "LOGIN_ISSUE"
        else:
            intent = "GENERAL_QUERY"

        return {
            "language": lang,
            "emotion": emotion,
            "emotion_confidence": emotion_confidence,
            "intent": intent
        }

    VOICE_FILLER_MS: int = 700

    @classmethod
    def _get_cached_filler(cls, language: str = "English") -> str:
        """
        Retrieves a cached filler / backchannel (e.g. 'One moment.') for the detected language.
        Pre-synthesized in opener cache to guarantee instant audio response.
        """
        from app.voice.opener_cache import STANDARD_FILLERS
        lang_lower = (language or "English").lower()
        lang_key = "English"
        for k in STANDARD_FILLERS:
            if k.lower() == lang_lower or k.lower() in lang_lower:
                lang_key = k
                break
        fillers = STANDARD_FILLERS.get(lang_key, STANDARD_FILLERS["English"])
        return fillers[-1] if fillers else "One moment."

    @staticmethod
    def should_play_opener(
        turn_index: int = 1,
        emotion: str = "neutral",
        emotion_confidence: float = 0.0,
        reply_ready_within_threshold: bool = False,
    ) -> bool:
        """
        Parity P1.7 Opener Policy:
        Play safe opener ONLY when:
        1) turn_index == 1 (initial conversational opening), OR
        2) Emotion is detected (frustrated/angry with confidence >= 0.70), OR
        3) The real reply is not ready within threshold (e.g. LLM reasoning takes longer).
        Otherwise (e.g. calm turn 2+ where reply is ready quickly), opener is skipped.
        """
        if turn_index == 1:
            return True
        if emotion in ("frustrated", "angry") and emotion_confidence >= 0.70:
            return True
        if not reply_ready_within_threshold:
            return True
        return False

    @classmethod
    def _generate_safe_opener(
        cls, 
        analysis: dict, 
        message: str, 
        used_openers: set[str] | list[str] | None = None,
        turn_index: int = 1,
    ) -> str:
        """
        Parity Row 13 & P1.7 Opener Rules:
        - (a) No action promises ('let me check', 'will check') before decision is known.
        - (b) Zero 'I understand'.
        - (c) Never repeat the same opener within a conversation (tracks used_openers).
        - (d) Spoken opener is passed to LLM to prevent duplicate reaction.
        - (e) If emotion confidence from keywords is low (< 0.70), use neutral opener.
        - (f) Remove 'Thanks for reaching out.' from mid-conversation turns (turn_index > 1).
        - (g) If the pool is exhausted, skip the opener (return "").
        """
        used_set = set(used_openers or [])
        lang_raw = str(analysis.get("language", "English")).lower()
        lang_key = "English"
        for k in cls.OPENER_POOLS:
            if k.lower() == lang_raw or k.lower() in lang_raw:
                lang_key = k
                break

        emo = str(analysis.get("emotion", "neutral")).lower()
        emo_conf = float(analysis.get("emotion_confidence", 0.0))

        # Rule (e): if emotion confidence from keywords is low, use neutral opener
        if emo in ("frustrated", "angry") and emo_conf >= 0.70:
            category = "frustrated"
        else:
            category = "neutral"

        pool = cls.OPENER_POOLS.get(lang_key, cls.OPENER_POOLS["English"])
        candidates = list(pool.get(category, pool["neutral"]))

        # Rule (f): Remove "Thanks for reaching out." from mid-conversation turns (turn > 1)
        if turn_index > 1:
            candidates = [c for c in candidates if "thanks for reaching out" not in c.lower()]

        # Rule (c): Select first candidate not in used_set
        for c in candidates:
            if c not in used_set:
                return c

        # If all category candidates used, try neutral candidates (filtered for turn > 1)
        neutral_candidates = list(pool.get("neutral", []))
        if turn_index > 1:
            neutral_candidates = [c for c in neutral_candidates if "thanks for reaching out" not in c.lower()]

        for c in neutral_candidates:
            if c not in used_set:
                return c

        # Rule (g): If pool is exhausted, skip the opener
        return ""

    @staticmethod
    def _get_routine_fallback_prompt(intent: str, language: str, entities: dict | None = None) -> str:
        intent_u = str(intent or "").upper()
        lang_l = str(language or "english").lower()
        entities = entities or {}
        item_term = entities.get("customer_item_term") or "order"
        from app.ai.m4.decision import ResponseGenerator
        generator = ResponseGenerator()

        is_tamil = "tanglish" in lang_l or "tamil" in lang_l or lang_l in ("ta", "ta-in")
        is_hindi = "hinglish" in lang_l or "hindi" in lang_l or lang_l in ("hi", "hi-in")
        is_kannada = "kannada" in lang_l or "kanglish" in lang_l or lang_l in ("kn", "kn-in")
        is_telugu = "telugu" in lang_l or "tenglish" in lang_l or lang_l in ("te", "te-in")
        is_malayalam = "malayalam" in lang_l or "manglish" in lang_l or lang_l in ("ml", "ml-in")
        is_bengali = "bengali" in lang_l or "bangla" in lang_l or "benglish" in lang_l or lang_l in ("bn", "bn-in")
        is_marathi = "marathi" in lang_l or "marathish" in lang_l or lang_l in ("mr", "mr-in")
        is_gujarati = "gujarati" in lang_l or "gujlish" in lang_l or lang_l in ("gu", "gu-in")
        is_punjabi = "punjabi" in lang_l or "punglish" in lang_l or lang_l in ("pa", "pa-in")
        is_odia = "odia" in lang_l or "oriya" in lang_l or lang_l in ("od", "od-in", "or", "or-in")
        is_urdu = "urdu" in lang_l or lang_l in ("ur", "ur-in")

        if intent_u == "GREETING":
            return generator.generate({
                "decision": "ASK_USER",
                "missing_entity": "greeting",
                "customer_item_term": item_term
            }, language=lang_l)

        elif intent_u == "UNCLEAR":
            return generator.generate({
                "decision": "ASK_USER",
                "missing_entity": "unclear",
                "customer_item_term": item_term
            }, language=lang_l)

        elif intent_u in ("ORDER_STATUS", "DELIVERY_ISSUE"):
            if entities.get("order_id"):
                oid = entities["order_id"]
                if is_tamil:
                    return f"Oru nimisham, unga {item_term} {oid} status-ah check panren..."
                elif is_hindi:
                    return f"Ek pal, main aapke {item_term} {oid} ka status check karta hoon..."
                elif is_kannada:
                    return f"ಒಂದು ಕ್ಷಣ, ನಿಮ್ಮ {item_term} {oid} ಸ್ಥಿತಿಯನ್ನು ಪರಿಶೀಲಿಸುತ್ತೇನೆ..." if "kn" in lang_l or "kannada" in lang_l else f"Ondu nimisha, nimma {item_term} {oid} status check madthini..."
                elif is_telugu:
                    return f"ఒక్క క్షణం, మీ {item_term} {oid} స్థితిని తనిఖీ చేస్తాను..." if "te" in lang_l or "telugu" in lang_l else f"Oka nimisham, mee {item_term} {oid} status check chestanu..."
                elif is_malayalam:
                    return f"ഒരു നിമിഷം, നിങ്ങളുടെ {item_term} {oid} നില പരിശോധിക്കാം..." if "ml" in lang_l or "malayalam" in lang_l else f"Oru nimisham, ningalude {item_term} {oid} status check cheyyam..."
                elif is_bengali:
                    return f"এক মুহূর্ত, আমি আপনার {item_term} {oid} স্ট্যাটাস যাচাই করছি..."
                elif is_marathi:
                    return f"एक क्षण, मी तुमच्या {item_term} {oid} ची स्थिती तपासतो..."
                elif is_gujarati:
                    return f"એક ક્ષણ, હું તમારા {item_term} {oid} ની સ્થિતિ તપાસું છું..."
                elif is_punjabi:
                    return f"ਇੱਕ ਪਲ, ਮੈਂ ਤੁਹਾਡੇ {item_term} {oid} ਦੀ ਸਥਿਤੀ ਚੈੱਕ ਕਰਦਾ ਹਾਂ..."
                elif is_odia:
                    return f"ଗୋଟିଏ ମୁହୂର୍ତ୍ତ, ମୁଁ ଆପଣଙ୍କ {item_term} {oid} ସ୍ଥିତି ଯାଞ୍ଚ କରୁଛି..."
                elif is_urdu:
                    return f"ایک لمحہ، میں آپ کے {item_term} {oid} کی حیثیت چیک کر رہا ہوں..."
                return f"One moment while I check the status for {item_term} {oid}..."
            
            return generator.generate({
                "decision": "ASK_USER",
                "missing_entity": "order_id",
                "customer_item_term": item_term
            }, language=lang_l)

        elif intent_u == "PAYMENT_ISSUE":
            if entities.get("transaction_id"):
                tid = entities["transaction_id"]
                if is_tamil:
                    return f"Oru nimisham, unga transaction {tid} status-ah check panren..."
                elif is_hindi:
                    return f"Ek pal, main aapke transaction {tid} ka status check karta hoon..."
                elif is_kannada:
                    return f"ಒಂದು ಕ್ಷಣ, ನಿಮ್ಮ ಟ್ರಾನ್ಸಾಕ್ಷನ್ {tid} ಪರಿಶೀಲಿಸುತ್ತೇನೆ..."
                elif is_telugu:
                    return f"ఒక్క క్షణం, మీ లావాదేవీ {tid} తనిఖీ చేస్తాను..."
                elif is_malayalam:
                    return f"ഒരു നിമിഷം, നിങ്ങളുടെ ട്രാൻസാക്ഷൻ {tid} പരിശോധിക്കാം..."
                return f"One moment while I check the status for transaction {tid}..."
            
            return generator.generate({
                "decision": "ASK_USER",
                "missing_entity": "transaction_id",
                "customer_item_term": item_term
            }, language=lang_l)

        elif intent_u == "LOGIN_ISSUE":
            if is_tamil:
                return "Unga login problem-ku udhavuren. Ungal registered email address sollunga."
            elif is_hindi:
                return "Main aapki login samasya mein madad karta hoon. Kripya apna registered email batayein."
            elif is_kannada:
                return "ನಿಮ್ಮ ಲಾಗಿನ್ ಸಮಸ್ಯೆಗೆ ಸಹಾಯ ಮಾಡುತ್ತೇನೆ. ದಯವಿಟ್ಟು ನಿಮ್ಮ ನೋಂದಾಯಿತ ಇಮೇಲ್ ವಿಳಾಸ ತಿಳಿಸಿ."
            elif is_telugu:
                return "మీ లాగిన్ సమస్య పరిష్కరించడానికి సహాయం చేస్తాను. దయచేసి మీ రిజిస్టర్డ్ ఈమెయిల్ చెప్పండి."
            elif is_malayalam:
                return "നിങ്ങളുടെ ലോഗിൻ പ്രശ്നത്തിൽ ഞാൻ സഹായിക്കാം. രജിസ്റ്റർ ചെയ്ത ഇമെയിൽ വിലാസം നൽകുക."
            elif is_bengali:
                return "আমি আপনার লগইন সমস্যায় সাহায্য করতে পারি। আপনার নিবন্ধিত ইমেল ঠিকানা জানান।"
            elif is_marathi:
                return "मी तुमच्या लॉगिन समस्येत मदत करतो. कृपया तुमचा नोंदणीकृत ईमेल पत्ता सांगा."
            elif is_gujarati:
                return "હું તમારી લૉગિન સમસ્યામાં મદદ કરી શકું છું. કૃપા કરીને તમારો રજિસ્ટર્ડ ઈમેલ આપો."
            elif is_punjabi:
                return "ਮੈਂ ਤੁਹਾਡੀ ਲੌਗਇਨ ਸਮੱਸਿਆ ਵਿੱਚ ਮਦਦ ਕਰ ਸਕਦਾ ਹਾਂ। ਕਿਰਪਾ ਕਰਕੇ ਆਪਣਾ ਰਜਿਸਟਰਡ ਈਮੇਲ ਪਤਾ ਦੱਸੋ।"
            return "I can help with your login issue. Could you please provide your registered email address?"

        elif intent_u == "POLICY_QUERY":
            return generator.generate({
                "decision": "RESOLVE",
                "action_type": "policy_overview",
                "policy_type": entities.get("policy_type"),
                "customer_item_term": item_term,
                "article": {}
            }, language=lang_l)

        elif intent_u == "CLARIFICATION_ORDER_ID_PURPOSE":
            return generator.generate({
                "decision": "ASK_USER",
                "missing_entity": "order_id_reason",
                "customer_item_term": item_term
            }, language=lang_l)

        elif intent_u == "WARRANTY_SERVICE":
            if is_tamil:
                return f"Unga {item_term} damaged or defective aagi irundha, namma free replacement or repair support provide panrom. Unga Order ID sollunga bro, udane proceed panren."
            elif is_hindi:
                return f"Agar aapka {item_term} damage hai, to hum replacement ya repair support karte hain. Kripya apna Order ID batayein."
            elif is_kannada:
                return f"ನಿಮ್ಮ {item_term} ಹಾನಿಗೊಳಗಾಗಿದ್ದರೆ ನಾವು ರಿಪ್ಲೇಸ್‌ಮೆಂಟ್ ಅಥವಾ ರಿಪೇರಿ ಬೆಂಬಲ ನೀಡುತ್ತೇವೆ. ದಯವಿಟ್ಟು ಆರ್ಡರ್ ಐಡಿ ತಿಳಿಸಿ."
            elif is_telugu:
                return f"మీ {item_term} పాడైపోయినట్లయితే మేము రీప్లేస్‌మెంట్ లేదా రిపేర్ సపోర్ట్ అందిస్తాము. దయచేసి ఆర్డర్ ఐడి చెప్పండి."
            elif is_malayalam:
                return f"നിങ്ങളുടെ {item_term} തകരാറിലാണെങ്കിൽ ഞങ്ങൾ മാറ്റിസ്ഥാപിക്കൽ അല്ലെങ്കിൽ റിപ്പയർ നൽകുന്നു. ദയവായി ഓർഡർ ഐഡി നൽകുക."
            elif is_bengali:
                return f"আপনার {item_term} ক্ষতিগ্রস্ত হলে আমরা রিপ্লেসমেন্ট প্রদান করি। অনুগ্রহ করে অর্ডার আইডি জানান।"
            elif is_marathi:
                return f"तुमचा {item_term} खराब असल्यास आम्ही रिप्लेसमेंट किंवा रिपेअर सपोर्ट देतो. कृपया ऑर्डर आयडी सांगा."
            elif is_gujarati:
                return f"જો તમારો {item_term} ખરાબ હોય તો અમે રિપ્લેસમેન્ટ અથવા રિપેરિંગ સહાય આપીએ છીએ. કૃપા કરીને ઓર્ડર આઈડી આપો."
            elif is_punjabi:
                return f"ਜੇਕਰ ਤੁਹਾਡਾ {item_term} ਖਰਾਬ ਹੈ ਤਾਂ ਅਸੀਂ ਬਦਲਣ ਜਾਂ ਮੁਰੰਮਤ ਦੀ ਸਹਾਇਤਾ ਦਿੰਦੇ ਹਾਂ। ਕਿਰਪਾ ਕਰਕੇ ਆਰਡਰ ਆਈਡੀ ਦੱਸੋ।"
            return f"If your {item_term} arrived damaged or defective, we provide replacement or warranty support. Please provide your Order ID to get started."

        else:
            if is_tamil:
                return "Kandippa! Ungal kelviyai konjam vilakkamaaga solla mudiyuma?"
            elif is_hindi:
                return "Zaroor! Kya aap apni samasya ke baare mein thoda aur bata sakte hain?"
            elif is_kannada:
                return "ಖಂಡಿತ! ನಿಮ್ಮ ಪ್ರಶ್ನೆಯನ್ನು ಸ್ವಲ್ಪ ವಿವರವಾಗಿ ಹೇಳಬಹುದೇ?"
            elif is_telugu:
                return "ఖచ్చితంగా! మీ సమస్యను కొంచెం వివరంగా చెప్పగలరా?"
            elif is_malayalam:
                return "തീർച്ചയായും! നിങ്ങളുടെ ചോദ്യം കുറച്ചുകൂടി വ്യക്തമായി പറയാമോ?"
            elif is_bengali:
                return "নিশ্চয়ই! আপনার সমস্যাটি একটু বিস্তারিত বলতে পারবেন?"
            elif is_marathi:
                return "नक्कीच! तुमची समस्या थोडी सविस्तर सांगू शकाल का?"
            elif is_gujarati:
                return "ચોક્કસ! શું તમે તમારી સમસ્યા થોડી વિગતે જણાવી શકો છો?"
            elif is_punjabi:
                return "ਜ਼ਰੂਰ! ਕੀ ਤੁਸੀਂ ਆਪਣੀ ਸਮੱਸਿਆ ਬਾਰੇ ਥੋੜ੍ਹਾ ਹੋਰ ਦੱਸ ਸਕਦੇ ਹੋ?"
            return "How can I assist you with your request today?"

    async def _generate_validate_response(
        self,
        db: AsyncSession,
        conversation: Conversation,
        customer_id: int,
        latest_message: str,
        context: dict,
        analysis: dict,
        tool_results: list = None,
    ) -> tuple[str, str]:
        """
        Generates an AI response, validates it, and retries if necessary.
        Returns: (decision, response_text)
        """
        from app.ai.validation.service import ValidationService
        from app.ai.validation.models import ResponseValidationContext, ValidationStatus, ToolResultContext
        from app.users.models import User
        from app.tickets.models import Ticket
        from app.commerce.models import Order
        import asyncio
        
        user = await db.scalar(select(User).where(User.id == customer_id))
        
        # Dynamically load customer's real authorized orders from database
        db_orders = (await db.execute(select(Order.order_number).where(Order.customer_id == customer_id))).scalars().all()
        authorized_orders = list(db_orders)
        
        # Also include any orders verified by successful tool results in this turn
        if tool_results:
            for tr in tool_results:
                if tr.success and isinstance(tr.data, dict):
                    oid = tr.data.get("order_id")
                    if oid and str(oid) not in authorized_orders:
                        authorized_orders.append(str(oid))
        
        tickets = (await db.execute(select(Ticket).where(Ticket.customer_id == customer_id))).scalars().all()
        authorized_tickets = [f"TICKET-{t.id}" for t in tickets]
        
        internal_notes = []
        handoff = await db.scalar(select(Handoff).where(Handoff.conversation_id == conversation.id))
        if handoff and getattr(handoff, "internal_notes", None):
            internal_notes.append(handoff.internal_notes)
            
        val_ctx = ResponseValidationContext(
            conversation_id=conversation.id,
            customer_id=customer_id,
            user_message=latest_message,
            conversation_history=context.get("history", []),
            detected_intent=analysis.get("intent", ""),
            detected_language=analysis.get("language", "en"),
            preferred_language=conversation.preferred_language or context.get("preferred_language"),
            sentiment=analysis.get("sentiment", "neutral"),
            memory_context=context.get("relevant_memories", []),
            rag_context=context.get("rag_context", []),
            tool_results=tool_results or [],
            agent_decision=analysis.get("decision_state", ""),
            authorized_order_ids=authorized_orders,
            authorized_ticket_ids=authorized_tickets,
            internal_notes=internal_notes
        )

        MAX_RESPONSE_GENERATION_ATTEMPTS = 3
        attempt = 1
        
        while attempt <= MAX_RESPONSE_GENERATION_ATTEMPTS:
            val_ctx.attempt_number = attempt
            
            decision = analysis.get("decision_state", "RESOLVE")
            is_voice_turn = context.get("is_voice", False) or context.get("reply_with_voice", False)
            if is_voice_turn and attempt == 1 and analysis.get("spoken_response") and not tool_results and not val_ctx.previous_violations:
                response_text = analysis["spoken_response"]
                decision = analysis.get("decision", analysis.get("decision_state", "RESOLVE"))
                val_ctx.rag_context = context.get("rag_context", []) or analysis.get("rag_context", [])
            elif tool_results:
                from app.ai.m4.decision import ResponseGenerator
                generator = getattr(self.ai_provider, "response_generator", None) or ResponseGenerator()
                raw_tool_data = tool_results[-1].data if tool_results else {}
                err_code = getattr(tool_results[-1], "error_code", None) or (raw_tool_data.get("error_code") if isinstance(raw_tool_data, dict) else None)
                msg_val = getattr(tool_results[-1], "message", None) or (raw_tool_data.get("message") if isinstance(raw_tool_data, dict) else None)
                decision_obj = {
                    "decision": "USE_TOOL",
                    "tool_result": {
                        "success": tool_results[-1].success,
                        "data": raw_tool_data,
                        "error_code": err_code,
                        "message": msg_val,
                    } if tool_results else {},
                    "validation_feedback": val_ctx.previous_violations
                }
                target_lang = conversation.preferred_language or analysis.get("language") or context.get("preferred_language") or "english"
                response_text = generator.generate(decision_obj, language=str(target_lang))
                decision = "RESOLVE"
            else:
                if tool_results:
                    analysis["tool_result"] = tool_results[-1].data
                analysis["validation_feedback"] = val_ctx.previous_violations
                response_text = await self.ai_provider.generate_response(analysis, [], context, db)
                decision = analysis.get("decision_state", "RESOLVE")
                val_ctx.rag_context = context.get("rag_context", []) or analysis.get("rag_context", [])
                
            logger.info(f"[PLANNER] Input response: {response_text}")
            logger.info(f"[AGENT] Agent response: {response_text}")
            val_ctx.agent_decision = decision
            val_ctx.draft_response = response_text
            
            validation = await ValidationService.validate_response(val_ctx)
            
            if validation.status == ValidationStatus.VALID:
                # Anti-false-escalation guardrail: Ensure routine queries without required IDs ask for clarification instead of escalating
                from app.ai.intelligence.escalation_keywords import is_supervisor_demand, is_fraud_or_security
                fr_info = analysis.get("failure_risk") if isinstance(analysis.get("failure_risk"), dict) else {}
                is_mandatory_escalate = (
                    is_supervisor_demand(latest_message)
                    or is_fraud_or_security(latest_message)
                    or str(analysis.get("priority", "")).upper() == "CRITICAL"
                    or str(analysis.get("intent", "")).upper() in ["SECURITY_ISSUE", "FRAUD_SUSPICION", "ESCALATION_REQUEST"]
                    or context.get("attempt_count", 0) >= 3
                    or bool(fr_info.get("should_escalate_early"))
                    or fr_info.get("likelihood") in ("HIGH", "VERY_HIGH")
                )
                is_provider_failure = (
                    "technical failure" in str(analysis.get("decision_reason", "")).lower()
                    or "rate limit" in str(analysis.get("decision_reason", "")).lower()
                    or "quota exceeded" in str(analysis.get("decision_reason", "")).lower()
                    or "technical difficulties" in response_text.lower()
                    or "503" in str(analysis.get("decision_reason", ""))
                )
                if decision == "ESCALATE" and not is_mandatory_escalate and not is_provider_failure:
                    intent_u = str(analysis.get("intent", "")).upper()
                    if intent_u in ["ORDER_STATUS", "DELIVERY_ISSUE", "GENERAL_QUERY", "GREETING", "PAYMENT_ISSUE", "LOGIN_ISSUE", "UNCLEAR"]:
                        logger.warning(f"Service layer prevented false ESCALATE for intent {intent_u}. Converting to ASK_USER.")
                        decision = "ASK_USER"
                        lang_l = conversation.preferred_language or analysis.get("language") or "english"
                        response_text = self._get_routine_fallback_prompt(intent_u, lang_l, analysis.get("entities"))

                # Safeguards for conversational quality & preventing inappropriate Order ID prompts
                lang_l = conversation.preferred_language or analysis.get("language") or "english"
                intent_u = str(analysis.get("intent", "")).upper()
                has_order_id = bool(analysis.get("entities", {}).get("order_id"))
                exempt_intents = {
                    "ORDER_STATUS", "DELIVERY_ISSUE", "CLARIFICATION_ORDER_ID_PURPOSE",
                    "POLICY_QUERY", "REFUND_ISSUE", "WARRANTY_SERVICE", "RETURN_POLICY",
                    "EXCHANGE_ISSUE", "TECHNICAL_ISSUE", "FEEDBACK"
                }
                user_msg_low = str(context.get("message", "")).lower()
                is_explaining_purpose = any(q in user_msg_low for q in ["edhukku", "why", "kyun", "purpose", "theva", "karan", "reason"])

                if (
                    intent_u not in exempt_intents
                    and not is_explaining_purpose
                    and (intent_u in ("GREETING", "UNCLEAR") or not has_order_id)
                    and "order id" in response_text.lower()
                ):
                    logger.warning("Sanitizing response that inappropriately requested Order ID.")
                    response_text = self._get_routine_fallback_prompt(intent_u, lang_l, analysis.get("entities"))
                    decision = "ASK_USER"

                # Check against immediate previous AI response to prevent unwanted repeated generic prompts
                last_ai_content = ""
                for m in reversed(context.get("history", [])):
                    if str(m.get("sender_type", "")).upper() in ["AI", "AGENT", "ASSISTANT"]:
                        last_ai_content = str(m.get("content", "")).strip()
                        break
                category_l = str(analysis.get("category", "")).lower()
                is_policy_response = (category_l == "policy" or intent_u in ("POLICY_QUERY", "RETURN_POLICY") or "policy" in response_text.lower())
                if decision == "ASK_USER" and not is_policy_response and last_ai_content and last_ai_content == response_text.strip():
                    if intent_u == "GREETING":
                        response_text = self._get_routine_fallback_prompt("GREETING", lang_l, analysis.get("entities"))
                    elif "order id" in response_text.lower():
                        response_text = self._get_routine_fallback_prompt("CLARIFICATION_ORDER_ID_PURPOSE", lang_l, analysis.get("entities"))
                    else:
                        response_text = self._get_routine_fallback_prompt(intent_u, lang_l, analysis.get("entities"))

                logger.info(f"[PLANNER] Final response: {response_text}")
                logger.info(f"[API] Final response: {response_text}")
                analysis["validation_attempts"] = attempt
                analysis["regenerated"] = (attempt > 1)
                return decision, response_text
                
            elif validation.status in (ValidationStatus.REGENERATE, ValidationStatus.ASK_CLARIFICATION):
                attempt += 1
                val_ctx.previous_violations = validation.reasons
                
            elif validation.status == ValidationStatus.ESCALATE:
                # If the agent decided USE_TOOL, do not abort before tool execution
                if decision == "USE_TOOL":
                    logger.info(f"[VALIDATION] Allowing USE_TOOL holding text to proceed: {response_text}")
                    analysis["validation_attempts"] = attempt
                    return decision, response_text

                # Anti-false-escalation guardrail: if the query is a routine inquiry and not a real security threat or supervisor demand
                from app.ai.intelligence.escalation_keywords import is_supervisor_demand, is_fraud_or_security
                is_mandatory = (
                    is_supervisor_demand(latest_message)
                    or is_fraud_or_security(latest_message)
                    or str(analysis.get("priority", "")).upper() == "CRITICAL"
                    or str(analysis.get("intent", "")).upper() in ["SECURITY_ISSUE", "FRAUD_SUSPICION"]
                )
                is_provider_failure = (
                    "technical failure" in str(analysis.get("decision_reason", "")).lower()
                    or "rate limit" in str(analysis.get("decision_reason", "")).lower()
                    or "quota exceeded" in str(analysis.get("decision_reason", "")).lower()
                    or "technical difficulties" in response_text.lower()
                    or "503" in str(analysis.get("decision_reason", ""))
                )
                if not is_mandatory and not is_provider_failure:
                    intent_u = str(analysis.get("intent", "")).upper()
                    if intent_u in ["ORDER_STATUS", "DELIVERY_ISSUE", "GENERAL_QUERY", "GREETING", "PAYMENT_ISSUE", "LOGIN_ISSUE", "UNCLEAR", "ORDER_MANAGEMENT", "REFUND_ISSUE"]:
                        logger.warning(f"Intercepted validation ESCALATE on routine intent {intent_u}. Converting to safe ASK_USER.")
                        analysis["validation_attempts"] = attempt
                        lang_l = conversation.preferred_language or analysis.get("language") or "english"
                        clean_prompt = self._get_routine_fallback_prompt(intent_u, lang_l, analysis.get("entities"))
                        return "ASK_USER", clean_prompt

                analysis["validation_attempts"] = attempt
                analysis["regenerated"] = (attempt > 1)
                return "ESCALATE", "I need to connect you with an expert to assist you securely."

        analysis["validation_attempts"] = MAX_RESPONSE_GENERATION_ATTEMPTS
        analysis["regenerated"] = True
        return "ESCALATE", "I'm having trouble processing that safely right now. Let me connect you with an expert."
