"""
ResolveAIV2 — WebSocket Router

Handles the /api/ws endpoint. Authenticates via query parameter token,
validates JWT before accepting the connection, and maintains the
connection in a receive loop.

Security rules:
- JWT is validated BEFORE websocket.accept()
- Tokens are never logged
- Expired/invalid tokens result in clean close (4001/4003)
"""

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from jose import JWTError

from app.auth.jwt import verify_token
from app.websockets.manager import manager
from app.websockets.events import typing_event, transcript_stream_event
from app.database import async_session_factory
from app.conversations.models import Conversation
from app.handoff.models import Handoff
from app.experts.models import Expert
from sqlalchemy import select
from app.websockets.voice_session import VoiceSessionManager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(default=None),
):
    """
    WebSocket endpoint at /api/ws?token=<jwt_access_token>

    1. Validate JWT from query param (before accept)
    2. Accept connection and register with ConnectionManager
    3. Listen for incoming messages (typing events, pings)
    4. Clean up on disconnect
    """

    # ── 1. Authenticate before accepting ──
    if not token:
        await websocket.close(code=4001, reason="Missing authentication token")
        return

    try:
        payload = verify_token(token, expected_type="access")
        user_id = int(payload["sub"])
        role = payload.get("role", "customer")
    except (JWTError, Exception):
        # Don't log the token itself — security requirement
        logger.warning("WS auth failed: invalid or expired token")
        await websocket.close(code=4003, reason="Invalid or expired token")
        return

    # ── 2. Accept and register ──
    success = await manager.connect(websocket, user_id, role)
    if success is False:
        return

    try:
        # ── 3. Receive loop ──
        # Instantiate a voice session manager for this connection
        voice_manager = VoiceSessionManager(websocket, user_id)
        
        while True:
            # Use websocket.receive() to support both text and binary frames
            message = await websocket.receive()
            
            # Handle Binary Frame (Audio Chunk)
            if "bytes" in message:
                chunk = message["bytes"]
                # Optional: limit chunk size to prevent unbounded memory usage per frame
                if len(chunk) > 32768: # 32KB max
                    logger.warning(f"Voice chunk too large: {len(chunk)} bytes")
                    continue
                await voice_manager.handle_audio_chunk(chunk)
                continue
                
            # Handle Text Frame (JSON)
            if "text" in message:
                raw = message["text"]
                
                # Payload size limit
                if len(raw) > 4096:
                    logger.warning(f"WS payload too large: user_id={user_id}")
                    await websocket.close(code=4009, reason="Payload too large")
                    break

                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                msg_type = data.get("type")

                # Voice session routing
                if msg_type == "VOICE_START":
                    await voice_manager.handle_voice_start(data)
                elif msg_type == "VOICE_END":
                    await voice_manager.handle_voice_end(data)
                elif msg_type == "INTERRUPT":
                    await voice_manager.handle_interrupt(data)

                # Handle typing indicators
                elif msg_type in ("TYPING_START", "TYPING_END"):
                    conversation_id = data.get("conversation_id")
                    if conversation_id is not None:
                        event = typing_event(
                            conversation_id=conversation_id,
                            sender_type="expert" if role == "expert" else "customer",
                            is_start=(msg_type == "TYPING_START"),
                        )
                        async with async_session_factory() as db:
                            convo = await db.scalar(select(Conversation).where(Conversation.id == conversation_id))
                            if convo:
                                handoff = await db.scalar(select(Handoff).where(Handoff.conversation_id == conversation_id))
                                expert_user_id = None
                                if handoff and handoff.assigned_expert_id:
                                    expert_rec = await db.scalar(select(Expert).where(Expert.id == handoff.assigned_expert_id))
                                    if expert_rec:
                                        expert_user_id = expert_rec.user_id
                                
                                await manager.send_to_conversation_participants(
                                    customer_id=convo.customer_id,
                                    expert_id=expert_user_id,
                                    event=event
                                )

                # Handle real-time incremental transcript streaming
                elif msg_type == "TRANSCRIPT_UPDATE":
                    conversation_id = data.get("conversation_id")
                    if conversation_id is not None:
                        turn_id = str(data.get("turn_id", ""))
                        text = str(data.get("text", ""))
                        is_final = bool(data.get("is_final", False))
                        sender_type = "expert" if role == "expert" else "customer"

                        async with async_session_factory() as db:
                            convo = await db.scalar(select(Conversation).where(Conversation.id == conversation_id))
                            if convo:
                                handoff = await db.scalar(select(Handoff).where(Handoff.conversation_id == conversation_id))
                                expert_user_id = None
                                if handoff and handoff.assigned_expert_id:
                                    expert_rec = await db.scalar(select(Expert).where(Expert.id == handoff.assigned_expert_id))
                                    if expert_rec:
                                        expert_user_id = expert_rec.user_id

                                event = transcript_stream_event(
                                    conversation_id=conversation_id,
                                    turn_id=turn_id,
                                    sender_type=sender_type,
                                    text=text,
                                    is_final=is_final,
                                )
                                await manager.send_to_conversation_participants(
                                    customer_id=convo.customer_id,
                                    expert_id=expert_user_id,
                                    event=event,
                                    exclude_user=user_id,
                                )

                # Handle ping/pong keepalive
                elif msg_type == "PING":
                    await websocket.send_json({"type": "PONG"})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WS error for user_id={user_id}: {e}")
    finally:
        manager.disconnect(websocket, user_id)
