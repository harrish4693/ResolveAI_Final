from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.auth.deps import get_current_user
from app.users.models import User
from app.shared.models import UserRole, ConversationChannel
from app.conversations.models import Conversation
from app.voice.service import VoiceService
from app.voice.livekit_service import (
    LiveKitService,
    LiveKitTokenRequest,
    LiveKitTokenResponse,
    LiveKitUtteranceRequest,
)

router = APIRouter()


@router.post("/livekit/token", response_model=LiveKitTokenResponse)
async def get_livekit_token(
    payload: LiveKitTokenRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a short-lived, room-scoped LiveKit JWT token for an authenticated participant.
    Enforces authorization:
    - Customers can only join rooms for their own conversations.
    - Experts can join rooms to assist customers (auto-assigns if waiting/unclaimed).
    - Admins can join any room for monitoring.
    """
    # 1. Fetch conversation to check ownership
    stmt = select(Conversation).where(Conversation.id == payload.conversation_id)
    result = await db.execute(stmt)
    convo = result.scalar_one_or_none()

    if not convo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    # 2. Authorization
    if current_user.role == UserRole.CUSTOMER:
        if convo.customer_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this conversation",
            )
    elif current_user.role == UserRole.EXPERT:
        from app.handoff.models import Handoff
        from app.experts.models import Expert
        from app.shared.models import HandoffStatus, WorkflowState, Priority
        from app.websockets.manager import manager
        from app.websockets.events import conversation_updated_event

        expert = await db.scalar(select(Expert).where(Expert.user_id == current_user.id))
        if not expert:
            expert = Expert(user_id=current_user.id, is_available=True)
            db.add(expert)
            await db.flush()
        expert_ids = [current_user.id, expert.id]

        handoff = await db.scalar(
            select(Handoff)
            .where(Handoff.conversation_id == payload.conversation_id)
            .order_by(Handoff.created_at.desc())
        )

        if handoff:
            if handoff.status == HandoffStatus.WAITING or handoff.assigned_expert_id is None:
                handoff.status = HandoffStatus.ASSIGNED
                handoff.assigned_expert_id = expert.id
                convo.workflow_state = WorkflowState.WITH_EXPERT
                await db.commit()
                await manager.send_to_user(
                    convo.customer_id,
                    conversation_updated_event(
                        conversation_id=convo.id,
                        status=convo.status.value if hasattr(convo.status, 'value') else str(convo.status),
                        workflow_state="with_expert",
                    ),
                )
        else:
            # Expert is directly joining this customer conversation on voice
            from app.tickets.models import Ticket
            ticket = await db.scalar(select(Ticket).where(Ticket.conversation_id == convo.id))
            if not ticket:
                ticket = Ticket(
                    customer_id=convo.customer_id,
                    conversation_id=convo.id,
                    subject=convo.subject or "Voice Call Support",
                    priority=Priority.MEDIUM,
                    status="in_progress",
                )
                db.add(ticket)
                await db.flush()

            handoff = Handoff(
                conversation_id=payload.conversation_id,
                ticket_id=ticket.id,
                customer_id=convo.customer_id,
                status=HandoffStatus.ASSIGNED,
                assigned_expert_id=expert.id,
                escalation_reason="Expert joined live voice channel directly",
                priority=Priority.MEDIUM,
            )
            db.add(handoff)
            convo.workflow_state = WorkflowState.WITH_EXPERT
            await db.commit()
            await manager.send_to_user(
                convo.customer_id,
                conversation_updated_event(
                    conversation_id=convo.id,
                    status=convo.status.value if hasattr(convo.status, 'value') else str(convo.status),
                    workflow_state="with_expert",
                ),
            )

    # 3. Generate room-scoped LiveKit token
    return LiveKitService.generate_token(current_user, convo.id)


@router.post("/livekit/utterance")
async def handle_livekit_utterance(
    payload: LiveKitUtteranceRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Process a voice utterance received from the LiveKit session.
    - If sent by an EXPERT or ADMIN: record as an expert message and broadcast to customer.
    - If sent by a CUSTOMER: feed into ResolveAI intelligence pipeline (or forward if with expert).
    """
    stmt = select(Conversation).where(Conversation.id == payload.conversation_id)
    convo = await db.scalar(stmt)
    if not convo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    from app.voice.noise_filter import validate_spoken_utterance
    val_result = validate_spoken_utterance(payload.transcript)
    if not val_result.is_valid:
        return {
            "status": "ignored",
            "reason": val_result.reason,
            "message": f"Utterance ignored: {val_result.reason}",
            "transcript": payload.transcript,
        }
    clean_text = val_result.cleaned_text

    if current_user.role in [UserRole.EXPERT, UserRole.ADMIN]:
        # Expert speech is recorded as an expert message in the conversation
        from app.conversations.models import ConversationMessage
        from app.shared.models import SenderType
        from app.websockets.manager import manager
        from app.websockets.events import new_message_event

        msg = ConversationMessage(
            conversation_id=convo.id,
            sender_type=SenderType.EXPERT,
            content=clean_text,
        )
        db.add(msg)
        await db.commit()
        await db.refresh(msg)

        await manager.send_to_user(
            convo.customer_id,
            new_message_event(
                conversation_id=convo.id,
                message_id=msg.id,
                sender_type="expert",
                content=msg.content,
                created_at=msg.created_at.isoformat(),
            ),
        )
        return {
            "status": "expert_message",
            "message_id": msg.id,
            "transcript": clean_text,
            "ai_response": None,
        }

    # Customer utterance authorization
    if convo.customer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this conversation",
        )

    # If conversation is with an expert, save customer message and notify expert without AI answering back
    from app.shared.models import WorkflowState
    if convo.workflow_state == WorkflowState.WITH_EXPERT:
        from app.conversations.models import ConversationMessage
        from app.shared.models import SenderType
        from app.websockets.manager import manager
        from app.websockets.events import new_message_event
        from app.handoff.models import Handoff
        from app.experts.models import Expert

        msg = ConversationMessage(
            conversation_id=convo.id,
            sender_type=SenderType.CUSTOMER,
            content=clean_text,
        )
        db.add(msg)
        await db.commit()
        await db.refresh(msg)

        handoff = await db.scalar(
            select(Handoff)
            .where(Handoff.conversation_id == convo.id)
            .order_by(Handoff.created_at.desc())
        )
        if handoff and handoff.assigned_expert_id:
            expert = await db.scalar(select(Expert).where(Expert.id == handoff.assigned_expert_id))
            target_user_id = expert.user_id if expert else handoff.assigned_expert_id
            await manager.send_to_user(
                target_user_id,
                new_message_event(
                    conversation_id=convo.id,
                    message_id=msg.id,
                    sender_type="customer",
                    content=msg.content,
                    created_at=msg.created_at.isoformat(),
                ),
            )

        return {
            "status": "with_expert",
            "message_id": msg.id,
            "transcript": clean_text,
            "ai_response": None,
        }

    result = await LiveKitService.process_spoken_utterance(
        db=db,
        conversation_id=payload.conversation_id,
        customer_id=current_user.id,
        utterance_id=payload.utterance_id,
        transcript=payload.transcript,
    )
    if result.get("status") == "duplicate":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Utterance {payload.utterance_id} has already been processed.",
        )
    return result


from pydantic import BaseModel, Field

class LiveKitEndCallRequest(BaseModel):
    conversation_id: int = Field(..., gt=0)


@router.post("/livekit/end-call")
async def end_livekit_call(
    payload: LiveKitEndCallRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Mutual call termination: When either customer or expert ends the call,
    broadcasts VOICE_CALL_ENDED via WebSockets and LiveKit room teardown
    so the call ends immediately for BOTH parties.
    """
    stmt = select(Conversation).where(Conversation.id == payload.conversation_id)
    convo = await db.scalar(stmt)
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Authorization check: must be conversation owner or expert/admin
    if current_user.role == UserRole.CUSTOMER and convo.customer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to end this conversation's call")

    from app.websockets.manager import manager
    from app.websockets.events import voice_call_ended_event
    from app.handoff.models import Handoff
    from app.experts.models import Expert
    from app.config import settings
    import logging
    _logger = logging.getLogger(__name__)

    ended_by_role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)

    # 1. Determine participants and broadcast VOICE_CALL_ENDED via WebSocket
    expert_user_id = None
    handoff = await db.scalar(
        select(Handoff)
        .where(Handoff.conversation_id == convo.id)
        .order_by(Handoff.created_at.desc())
    )
    if handoff and handoff.assigned_expert_id:
        expert = await db.scalar(select(Expert).where(Expert.id == handoff.assigned_expert_id))
        expert_user_id = expert.user_id if expert else handoff.assigned_expert_id

    if current_user.role in (UserRole.EXPERT, UserRole.ADMIN) and (expert_user_id is None or expert_user_id != current_user.id):
        expert_user_id = current_user.id

    call_ended_evt = voice_call_ended_event(convo.id, ended_by=ended_by_role)
    await manager.send_to_conversation_participants(
        customer_id=convo.customer_id,
        expert_id=expert_user_id,
        event=call_ended_evt,
    )

    # 2. Teardown LiveKit room server-side so LiveKit disconnects all WebRTC peers
    room_name = LiveKitService.get_room_name(convo.id)
    if settings.livekit_url and settings.livekit_api_key and settings.livekit_api_secret:
        try:
            from livekit.api import LiveKitAPI, DeleteRoomRequest
            lk_api = LiveKitAPI(settings.livekit_url, settings.livekit_api_key, settings.livekit_api_secret)
            await lk_api.room.delete_room(DeleteRoomRequest(room=room_name))
            await lk_api.aclose()
        except Exception as e:
            _logger.info(f"LiveKit room delete note: {e}")

    return {"status": "call_ended", "conversation_id": convo.id, "ended_by": ended_by_role}


@router.get("/conversations/{conversation_id}/{filename}")
async def get_audio_file(
    conversation_id: int,
    filename: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Serve an audio file for a conversation.
    Enforces authorization:
    - Customers can only access audio for their own conversations.
    - Experts can only access audio if they are assigned.
    """
    # 1. Fetch conversation to check ownership
    stmt = select(Conversation).where(Conversation.id == conversation_id)
    result = await db.execute(stmt)
    convo = result.scalar_one_or_none()

    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # 2. Authorization
    if current_user.role == UserRole.CUSTOMER:
        if convo.customer_id != current_user.id:
            raise HTTPException(status_code=404, detail="Conversation not found")
    elif current_user.role == UserRole.EXPERT:
        from app.handoff.models import Handoff
        from app.experts.models import Expert
        expert = await db.scalar(select(Expert).where(Expert.user_id == current_user.id))
        expert_ids = [current_user.id, expert.id] if expert else [current_user.id]

        handoff = await db.scalar(
            select(Handoff)
            .where(Handoff.conversation_id == conversation_id)
            .order_by(Handoff.created_at.desc())
        )

        if not handoff or (handoff.assigned_expert_id not in expert_ids and handoff.status != HandoffStatus.WAITING):
            raise HTTPException(status_code=403, detail="Not authorized to access this conversation's audio")

    # 3. Resolve path and serve
    audio_url = f"/api/audio/conversations/{conversation_id}/{filename}"
    try:
        file_path = VoiceService.get_absolute_path(audio_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")

    return FileResponse(path=file_path, media_type="audio/webm")


# ── Neural TTS endpoint (Fast-Path) ────────────────────────────────
from pydantic import BaseModel, Field
from fastapi.responses import Response


class TTSSynthesizeRequest(BaseModel):
    conversation_id: int
    text: str = Field(..., max_length=400)
    emotion: str | None = None
    language: str = "en-IN"


@router.post("/tts")
async def synthesize_tts(
    payload: TTSSynthesizeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Synthesize text to neural speech audio.

    Returns audio/mpeg on success.
    Returns JSON with {fallback: "browser"} if neural TTS is unavailable,
    so the frontend can fall back to browser speechSynthesis.
    """
    from app.config import settings as cfg

    # 1. Ownership check
    stmt = select(Conversation).where(Conversation.id == payload.conversation_id)
    result = await db.execute(stmt)
    convo = result.scalar_one_or_none()

    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if current_user.role == UserRole.CUSTOMER and convo.customer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    # 2. Text length check (pydantic max_length also enforces, but be explicit)
    if len(payload.text) > 400:
        raise HTTPException(status_code=400, detail="Text exceeds 400 character limit")

    # 3. Check if neural TTS is configured
    if cfg.tts_provider not in ("sarvam",):
        return JSONResponse(
            status_code=200,
            content={"fallback": "browser", "reason": f"tts_provider={cfg.tts_provider}"},
        )

    # 4. Clean text for speech
    from app.voice.sarvam_tts import clean_text_for_tts, synthesize_sarvam, SarvamTTSError

    cleaned = clean_text_for_tts(payload.text)
    if not cleaned:
        return JSONResponse(
            status_code=200,
            content={"fallback": "browser", "reason": "empty after cleaning"},
        )

    # 5. Call Sarvam TTS
    try:
        audio_bytes = await synthesize_sarvam(
            text=cleaned,
            language_code=payload.language,
            emotion=payload.emotion,
        )
        return Response(
            content=audio_bytes,
            media_type="audio/mpeg",
            headers={
                "X-TTS-Provider": "sarvam",
                "X-TTS-Pace": str(
                    __import__("app.voice.sarvam_tts", fromlist=["EMOTION_PACE_MAP"])
                    .EMOTION_PACE_MAP.get((payload.emotion or "calm").lower(), 1.0)
                ),
            },
        )
    except SarvamTTSError as e:
        import logging
        logging.getLogger(__name__).warning(f"Sarvam TTS failed, falling back to browser: {e}")
        return JSONResponse(
            status_code=200,
            content={"fallback": "browser", "reason": str(e)},
        )


@router.post("/stt")
async def transcribe_speech(
    file: UploadFile = File(...),
    language_code: str = Form("unknown"),
    mode: str = Form("translit"),
    keyterms: str | None = Form(None),
    current_user: User = Depends(get_current_user),
):
    """
    Speech-to-Text endpoint powered by Sarvam Saaras STT (saaras:v4).
    Accepts 16kHz mono WAV or other audio formats from client VAD or chat dictation.
    Supports auto language detection ('unknown'), translit/codemix modes, and keyterm prompting.
    Returns transcript and confidence score. Falls back to browser flag on failure.
    """
    import json
    from app.voice.sarvam_stt import transcribe_sarvam, SarvamSTTError
    from app.config import settings as cfg

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Audio file cannot be empty")

    if not cfg.sarvam_api_key:
        return JSONResponse(
            status_code=200,
            content={"fallback": "browser", "reason": "sarvam_api_key not configured"},
        )

    parsed_keyterms = None
    if keyterms:
        try:
            parsed_keyterms = json.loads(keyterms)
            if not isinstance(parsed_keyterms, list):
                parsed_keyterms = [k.strip() for k in keyterms.split(",") if k.strip()]
        except Exception:
            parsed_keyterms = [k.strip() for k in keyterms.split(",") if k.strip()]

    try:
        result = await transcribe_sarvam(
            audio_bytes=audio_bytes,
            language_code=language_code,
            mode=mode,
            keyterms=parsed_keyterms,
        )
        return JSONResponse(
            status_code=200,
            content=result,
        )
    except SarvamSTTError as e:
        import logging
        logging.getLogger(__name__).warning(f"Sarvam STT failed: {e}")
        return JSONResponse(
            status_code=200,
            content={"fallback": "browser", "reason": str(e)},
        )


@router.post("/livekit/audio-turn")
async def handle_livekit_audio_turn(
    file: UploadFile = File(...),
    conversation_id: int = Form(...),
    utterance_id: str = Form(...),
    language_code: str = Form("unknown"),
    mode: str = Form("translit"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Process a raw recorded audio turn from the client microphone (VAD-segmented).
    1. Transcribes raw audio with Sarvam Saaras v4 STT in real time.
    2. Enforces customer/expert/admin role routing & utterance idempotency.
    3. Feeds verified transcript directly into ResolveAI intelligence pipeline.
    4. Preserves language detection & confidence metadata in turn response.
    """
    from app.voice.sarvam_stt import transcribe_sarvam, get_audio_duration_seconds, SarvamSTTError
    from app.shared.models import WorkflowState, SenderType
    from app.config import settings as cfg

    # 1. Fetch conversation to verify existence & ownership
    stmt = select(Conversation).where(Conversation.id == conversation_id)
    convo = await db.scalar(stmt)
    if not convo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    # 2. Read and validate audio binary
    audio_bytes = await file.read()
    if not audio_bytes:
        return {"status": "ignored", "message": "Empty audio turn"}

    # 3. Check 30-second duration limit
    duration = get_audio_duration_seconds(audio_bytes)
    if duration is not None and duration > 30.0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Audio duration ({duration:.1f}s) exceeds documented 30-second limit for REST transcription.",
        )

    # 4. Transcribe using Saaras v4
    try:
        stt_res = await transcribe_sarvam(
            audio_bytes=audio_bytes,
            language_code=language_code or cfg.sarvam_stt_language_code or "unknown",
            mode=mode or cfg.sarvam_stt_mode or "translit",
        )
    except SarvamSTTError as e:
        import logging
        logging.getLogger(__name__).warning(f"Audio turn transcription error: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Speech recognition service error: {e}",
        )

    from app.voice.noise_filter import validate_spoken_utterance
    val_result = validate_spoken_utterance(stt_res.get("transcript"), confidence=stt_res.get("confidence"))
    if not val_result.is_valid:
        return {
            "status": "ignored",
            "reason": val_result.reason,
            "message": f"Utterance ignored: {val_result.reason}",
            "transcript": stt_res.get("transcript") or "",
            "detected_language": stt_res.get("language_code"),
            "confidence": stt_res.get("confidence"),
        }
    clean_transcript = val_result.cleaned_text

    # 5. Handle Expert / Admin Speech
    if current_user.role in [UserRole.EXPERT, UserRole.ADMIN]:
        from app.conversations.models import ConversationMessage
        from app.websockets.manager import manager
        from app.websockets.events import new_message_event

        msg = ConversationMessage(
            conversation_id=convo.id,
            sender_type=SenderType.EXPERT,
            content=clean_transcript,
        )
        db.add(msg)
        await db.commit()
        await db.refresh(msg)

        await manager.send_to_user(
            convo.customer_id,
            new_message_event(
                conversation_id=convo.id,
                message_id=msg.id,
                sender_type="expert",
                content=msg.content,
                created_at=msg.created_at.isoformat(),
            ),
        )
        return {
            "status": "expert_message",
            "message_id": msg.id,
            "transcript": clean_transcript,
            "ai_response": None,
            "language_code": stt_res.get("language_code"),
            "confidence": stt_res.get("confidence"),
        }

    # 6. Customer Authorization Check
    if convo.customer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this conversation",
        )

    # 7. If conversation is with an expert, save customer message & broadcast without AI replying
    if convo.workflow_state == WorkflowState.WITH_EXPERT:
        from app.conversations.models import ConversationMessage
        from app.websockets.manager import manager
        from app.websockets.events import new_message_event
        from app.handoff.models import Handoff
        from app.experts.models import Expert

        msg = ConversationMessage(
            conversation_id=convo.id,
            sender_type=SenderType.CUSTOMER,
            content=clean_transcript,
        )
        db.add(msg)
        await db.commit()
        await db.refresh(msg)

        handoff = await db.scalar(
            select(Handoff)
            .where(Handoff.conversation_id == convo.id)
            .order_by(Handoff.created_at.desc())
        )
        if handoff and handoff.assigned_expert_id:
            expert = await db.scalar(select(Expert).where(Expert.id == handoff.assigned_expert_id))
            target_user_id = expert.user_id if expert else handoff.assigned_expert_id
            await manager.send_to_user(
                target_user_id,
                new_message_event(
                    conversation_id=convo.id,
                    message_id=msg.id,
                    sender_type="customer",
                    content=msg.content,
                    created_at=msg.created_at.isoformat(),
                ),
            )

        return {
            "status": "with_expert",
            "message_id": msg.id,
            "transcript": clean_transcript,
            "ai_response": None,
            "language_code": stt_res.get("language_code"),
            "confidence": stt_res.get("confidence"),
        }

    # 8. Standard customer turn through ResolveAI intelligence pipeline
    result = await LiveKitService.process_spoken_utterance(
        db=db,
        conversation_id=conversation_id,
        customer_id=current_user.id,
        utterance_id=utterance_id,
        transcript=clean_transcript,
    )
    if result.get("status") == "duplicate":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Utterance {utterance_id} has already been processed.",
        )

    # Preserve and return STT metadata alongside intelligence pipeline output
    result["transcript"] = clean_transcript
    result["stt_language_code"] = stt_res.get("language_code")
    result["stt_confidence"] = stt_res.get("confidence")
    result["stt_mode"] = stt_res.get("mode")
    result["stt_request_id"] = stt_res.get("request_id")
    return result



