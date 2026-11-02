"""
ResolveAIV2 — Voice Session Manager (M12.7)

Manages the state machine for streaming voice sessions on the WebSocket.
Enforces strict DB-level idempotency and barge-in cancellation.
"""

import asyncio
import logging
from enum import Enum
from typing import Optional

from fastapi import WebSocket
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select

from app.database import async_session_factory
from app.conversations.models import Conversation, ProcessedUtterance
from app.users.models import User
from app.shared.models import UserRole
from app.voice.streaming_providers import (
    StreamingSTTProvider,
    StreamingTTSProvider,
    MockStreamingSTTProvider,
    MockStreamingTTSProvider
)

logger = logging.getLogger(__name__)


class VoiceSessionState(str, Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    PROCESSING = "PROCESSING"
    SPEAKING = "SPEAKING"
    INTERRUPTED = "INTERRUPTED"


class VoiceSessionManager:
    """Manages real-time voice streaming for a single WebSocket connection."""

    def __init__(self, websocket: WebSocket, user_id: int):
        self.websocket = websocket
        self.user_id = user_id
        
        self.state = VoiceSessionState.IDLE
        self.conversation_id: Optional[int] = None
        self.stream_id: Optional[str] = None
        self.utterance_id: Optional[str] = None
        self.ai_stream_id: Optional[str] = None
        
        self.stt_session_id: Optional[str] = None
        
        # In a real app these would be instantiated via DI based on settings
        self.stt_provider: StreamingSTTProvider = MockStreamingSTTProvider()
        self.tts_provider: StreamingTTSProvider = MockStreamingTTSProvider()

        # Track the active TTS task so we can cancel it on barge-in
        self.active_tts_task: Optional[asyncio.Task] = None

    async def handle_voice_start(self, data: dict):
        """Called when Client sends VOICE_START JSON frame."""
        if self.state not in (VoiceSessionState.IDLE, VoiceSessionState.LISTENING):
            # Barge-in implicit logic: if we were speaking, user started talking again.
            await self.handle_interrupt({"ai_stream_id": self.ai_stream_id})

        self.conversation_id = data.get("conversation_id")
        self.stream_id = data.get("stream_id")
        self.utterance_id = data.get("utterance_id")
        
        if not all([self.conversation_id, self.stream_id, self.utterance_id]):
            logger.warning(f"Invalid VOICE_START payload: {data}")
            return

        # 1. Authorize: Ensure user owns the conversation
        async with async_session_factory() as db:
            convo = await db.scalar(select(Conversation).where(Conversation.id == self.conversation_id))
            if not convo or convo.customer_id != self.user_id:
                logger.warning(f"Unauthorized voice session attempt by user {self.user_id} for convo {self.conversation_id}")
                return

        # 2. Check duplicate utterance ID in DB
        async with async_session_factory() as db:
            existing = await db.scalar(
                select(ProcessedUtterance).where(
                    ProcessedUtterance.utterance_id == self.utterance_id,
                    ProcessedUtterance.customer_id == self.user_id,
                    ProcessedUtterance.conversation_id == self.conversation_id
                )
            )
            if existing:
                logger.warning(f"Duplicate utterance {self.utterance_id}. Ignoring.")
                return

        # 3. Transition to listening
        self.state = VoiceSessionState.LISTENING
        self.stt_session_id = await self.stt_provider.start_session()
        logger.info(f"Voice session {self.stream_id} LISTENING")

    async def handle_audio_chunk(self, chunk: bytes):
        """Called when Client sends binary frame."""
        if self.state != VoiceSessionState.LISTENING or not self.stt_session_id:
            # Drop chunks if not actively listening
            return
        
        await self.stt_provider.feed_audio(self.stt_session_id, chunk)

    async def handle_voice_end(self, data: dict):
        """Called when Client sends VOICE_END JSON frame."""
        if self.state != VoiceSessionState.LISTENING:
            return

        self.state = VoiceSessionState.PROCESSING
        
        try:
            # 1. Finalize STT
            transcript = await self.stt_provider.finalize(self.stt_session_id)
            self.stt_session_id = None
            
            # 2. Enforce DB Idempotency before processing
            async with async_session_factory() as db:
                record = ProcessedUtterance(
                    utterance_id=self.utterance_id,
                    customer_id=self.user_id,
                    conversation_id=self.conversation_id
                )
                db.add(record)
                try:
                    await db.commit()
                except IntegrityError:
                    # Raced with another request, ignore
                    logger.warning(f"IntegrityError: Duplicate utterance {self.utterance_id}")
                    self.state = VoiceSessionState.IDLE
                    return

            # 3. Hand off to ConversationService
            from app.conversations.service import ConversationService
            svc = ConversationService()
            
            # We wrap the TTS generation in a callback so ConversationService can invoke it
            # exactly when M12.5 validation passes.
            async def tts_callback(validated_text: str):
                await self._stream_ai_tts(validated_text)
                
            async with async_session_factory() as db:
                convo = await db.scalar(select(Conversation).where(Conversation.id == self.conversation_id))
                # Pass the transcript as text; but tell it to stream audio out
                await svc.process_customer_message(
                    db=db,
                    conversation=convo,
                    customer_id=self.user_id,
                    message_content=transcript,
                    tts_callback=tts_callback,
                    reply_with_voice=True,
                )


        except Exception as e:
            logger.error(f"Error processing voice turn: {e}")
        finally:
            # Ensure we reset to IDLE if we didn't transition to SPEAKING
            if self.state == VoiceSessionState.PROCESSING:
                self.state = VoiceSessionState.IDLE

    async def _stream_ai_tts(self, text: str):
        """Streams TTS audio chunks back to the client. Can be cancelled by barge-in."""
        self.state = VoiceSessionState.SPEAKING
        self.ai_stream_id = f"ai-{self.utterance_id}"
        
        await self.websocket.send_json({
            "type": "AUDIO_START",
            "conversation_id": self.conversation_id,
            "stream_id": self.ai_stream_id
        })
        
        try:
            # Capture the current async task so handle_interrupt can cancel it
            self.active_tts_task = asyncio.current_task()
            
            async for chunk in self.tts_provider.synthesize_stream(text):
                await self.websocket.send_bytes(chunk)
                
            await self.websocket.send_json({
                "type": "AUDIO_END",
                "stream_id": self.ai_stream_id
            })
            
        except asyncio.CancelledError:
            logger.info(f"TTS stream {self.ai_stream_id} was cancelled (Barge-in)")
            raise
        except Exception as e:
            logger.error(f"TTS streaming error: {e}")
        finally:
            self.active_tts_task = None
            if self.state == VoiceSessionState.SPEAKING:
                self.state = VoiceSessionState.IDLE

    async def handle_interrupt(self, data: dict):
        """Called when Client sends INTERRUPT JSON frame (Barge-in)."""
        interrupt_stream_id = data.get("ai_stream_id")
        
        # Only cancel if the ID matches what we're currently streaming
        if self.state == VoiceSessionState.SPEAKING and self.ai_stream_id == interrupt_stream_id:
            logger.info(f"Barge-in detected! Cancelling ai_stream_id: {interrupt_stream_id}")
            self.state = VoiceSessionState.INTERRUPTED
            
            if self.active_tts_task:
                self.active_tts_task.cancel()
                
            self.ai_stream_id = None
