"""
ResolveAIV2 — LiveKit Voice Service (Step 2)

Handles LiveKit real-time voice integration:
1. Token generation with short-lived TTL and room-scoped video grants.
2. Room naming and participant identity management.
3. Spoken utterance deduplication via DB-level ProcessedUtterance idempotency.
4. Seamless dispatch into ConversationService.process_customer_message() ensuring
   full M1-M15 intelligence pipeline execution (multilingual, RAG, intent, autonomy,
   failure prediction, tools, and expert escalation).
"""

import datetime
import logging
from typing import Optional, Callable, Awaitable
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status

from app.config import settings
from app.users.models import User
from app.conversations.models import Conversation, ProcessedUtterance

logger = logging.getLogger(__name__)


class LiveKitTokenRequest(BaseModel):
    conversation_id: int = Field(..., gt=0, description="The ID of the conversation to join")


class LiveKitTokenResponse(BaseModel):
    server_url: str
    room_name: str
    token: str
    participant_identity: str
    participant_name: str
    expires_in_seconds: int


class LiveKitUtteranceRequest(BaseModel):
    conversation_id: int = Field(..., gt=0, description="The conversation ID")
    utterance_id: str = Field(..., min_length=1, description="Unique client utterance ID for idempotency")
    transcript: str = Field(..., min_length=1, description="Recognized customer speech transcript")


class LiveKitService:
    """Service managing LiveKit room access and spoken utterance processing."""

    DEFAULT_TTL_MINUTES = 15

    @classmethod
    def validate_configuration(cls) -> None:
        """Validates that LiveKit credentials are configured.
        
        Raises HTTP 503 if required variables are missing or blank.
        """
        if not (settings.livekit_url and settings.livekit_api_key and settings.livekit_api_secret):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "LiveKit real-time voice service is not configured. "
                    "Please set LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET in the backend environment."
                ),
            )

    @classmethod
    def get_room_name(cls, conversation_id: int) -> str:
        """Returns the canonical, room-scoped identifier for a conversation."""
        return f"resolveai-convo-{conversation_id}"

    @classmethod
    def get_participant_identity(cls, user: User) -> str:
        """Constructs a deterministic participant identity."""
        role_str = user.role.value if hasattr(user.role, "value") else str(user.role).lower()
        return f"{role_str}-{user.id}"

    @classmethod
    def generate_token(
        cls,
        user: User,
        conversation_id: int,
        ttl_minutes: int = DEFAULT_TTL_MINUTES,
    ) -> LiveKitTokenResponse:
        """Generates a short-lived, room-scoped LiveKit JWT token.
        
        Enforces minimal participant permissions (room_join, can_publish, can_subscribe).
        """
        cls.validate_configuration()

        room_name = cls.get_room_name(conversation_id)
        identity = cls.get_participant_identity(user)
        name = user.full_name or user.email or f"User {user.id}"

        try:
            from livekit.api import AccessToken, VideoGrants

            grants = VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )

            token = (
                AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
                .with_identity(identity)
                .with_name(name)
                .with_grants(grants)
                .with_ttl(datetime.timedelta(minutes=ttl_minutes))
                .to_jwt()
            )
        except ImportError:
            # Fallback to standard PyJWT generating standard LiveKit-compatible token
            import time
            import jwt

            now = int(time.time())
            exp = now + (ttl_minutes * 60)
            payload = {
                "iss": settings.livekit_api_key,
                "sub": identity,
                "name": name,
                "nbf": now - 5,
                "exp": exp,
                "video": {
                    "room": room_name,
                    "roomJoin": True,
                    "canPublish": True,
                    "canSubscribe": True,
                    "canPublishData": True,
                },
            }
            token = jwt.encode(payload, settings.livekit_api_secret, algorithm="HS256")
            if isinstance(token, bytes):
                token = token.decode("utf-8")

        return LiveKitTokenResponse(
            server_url=settings.livekit_url,
            room_name=room_name,
            token=token,
            participant_identity=identity,
            participant_name=name,
            expires_in_seconds=ttl_minutes * 60,
        )

    @classmethod
    async def process_spoken_utterance(
        cls,
        db: AsyncSession,
        conversation_id: int,
        customer_id: int,
        utterance_id: str,
        transcript: str,
        tts_callback: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> dict:
        """Processes a single transcribed spoken turn through the complete ResolveAI intelligence pipeline.
        
        Enforces:
        - DB-level utterance idempotency (rejects duplicates).
        - Full M1-M15 intelligence pipeline (RAG, intent, autonomy, failure prediction, tools).
        - AI response generation with optional streaming TTS callback.
        """
        # 1. Fetch conversation
        convo = await db.scalar(select(Conversation).where(Conversation.id == conversation_id))
        if not convo:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

        # 2. Verify ownership
        if convo.customer_id != customer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this conversation",
            )

        # 3. Guard against empty/silence and noise/hallucination utterances
        from app.voice.noise_filter import validate_spoken_utterance
        val_result = validate_spoken_utterance(transcript)
        if not val_result.is_valid:
            return {
                "status": "ignored",
                "reason": val_result.reason,
                "utterance_id": utterance_id,
                "conversation_id": conversation_id,
                "workflow_state": str(convo.workflow_state.value if hasattr(convo.workflow_state, "value") else convo.workflow_state),
                "ai_response": None,
                "message": f"Utterance ignored: {val_result.reason}",
            }
        clean_transcript = val_result.cleaned_text

        # 4. DB-level idempotency check
        existing = await db.scalar(
            select(ProcessedUtterance).where(
                ProcessedUtterance.utterance_id == utterance_id,
                ProcessedUtterance.customer_id == customer_id,
                ProcessedUtterance.conversation_id == conversation_id,
            )
        )
        if existing:
            logger.warning(
                f"Duplicate voice utterance {utterance_id} for conversation {conversation_id}. Rejecting."
            )
            return {
                "status": "duplicate",
                "utterance_id": utterance_id,
                "conversation_id": conversation_id,
                "message": "Duplicate utterance already processed",
            }

        # 5. Insert processed utterance record
        record = ProcessedUtterance(
            utterance_id=utterance_id,
            customer_id=customer_id,
            conversation_id=conversation_id,
        )
        db.add(record)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            logger.warning(
                f"IntegrityError on utterance {utterance_id} for conversation {conversation_id}. Race caught."
            )
            return {
                "status": "duplicate",
                "utterance_id": utterance_id,
                "conversation_id": conversation_id,
                "message": "Duplicate utterance already processed",
            }

        # 6. Hand off to ConversationService with voice flag
        from app.conversations.service import ConversationService
        svc = ConversationService()

        await svc.process_customer_message(
            db=db,
            conversation=convo,
            customer_id=customer_id,
            message_content=clean_transcript,
            tts_callback=tts_callback,
            reply_with_voice=True,
        )

        await db.refresh(convo)

        # Fetch the generated AI response to return to the voice client
        from app.conversations.models import ConversationMessage
        from app.shared.models import SenderType
        last_msg_stmt = (
            select(ConversationMessage)
            .where(
                ConversationMessage.conversation_id == conversation_id,
                ConversationMessage.sender_type == SenderType.AI,
            )
            .order_by(ConversationMessage.id.desc())
        )
        last_ai_msg = (await db.execute(last_msg_stmt)).scalars().first()

        ai_reply = last_ai_msg.content if last_ai_msg else None
        workflow_str = str(convo.workflow_state.value if hasattr(convo.workflow_state, "value") else convo.workflow_state)
        if workflow_str == "awaiting_confirmation":
            ai_reply = "I need your confirmation before I can proceed with this action. Please confirm on your screen."
        elif workflow_str in ("waiting_for_expert", "escalating") and not ai_reply:
            ai_reply = "I am connecting you with a human support specialist."

        if ai_reply:
            import re
            # Clean markdown formatting into natural spoken dialogue
            cleaned = re.sub(r"```[\s\S]*?```", "", ai_reply) # remove code blocks
            cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)    # remove inline code
            cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned) # remove bold
            cleaned = re.sub(r"\*([^*]+)\*", r"\1", cleaned)     # remove italics
            cleaned = re.sub(r"^#+\s*", "", cleaned, flags=re.MULTILINE) # remove headers
            cleaned = re.sub(r"^\s*[-*•]\s*", "", cleaned, flags=re.MULTILINE) # remove bullets
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            ai_reply = cleaned

        meta = last_ai_msg.metadata_ if (last_ai_msg and last_ai_msg.metadata_) else {}
        from app.voice.language_controller import VoiceLanguageController
        raw_lang = convo.preferred_language or meta.get("language") or "English"
        lang_str = str(raw_lang).strip()
        lang_name = "English" if lang_str.lower() in ["english", "en"] else lang_str.lower()
        bcp47 = meta.get("bcp47_code") or VoiceLanguageController.get_bcp47(lang_name.lower())
        return {
            "status": "processed",
            "utterance_id": utterance_id,
            "conversation_id": conversation_id,
            "workflow_state": workflow_str,
            "ai_response": ai_reply,
            "language": lang_name,
            "bcp47_code": bcp47,
            "emotion": meta.get("emotion", "calm"),
            "emotion_confidence": meta.get("emotion_confidence", 0.85),
            "latency_ms": meta.get("latency_ms", 0.0),
            "validation_latency_ms": meta.get("validation_latency_ms", 0.0),
            "intent": meta.get("intent", "GENERAL_QUERY"),
        }


