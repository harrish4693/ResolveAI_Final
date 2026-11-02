"""
ResolveAIV2 — WebSocket Event Builders

Standardized event envelope for all WebSocket messages.
Every event follows the structure:

{
    "type": "EVENT_TYPE",
    "event_id": "uuid",
    "timestamp": "2026-08-30T12:00:00+00:00",
    "conversation_id": 123 | null,
    "data": { ... }
}
"""

import uuid
from datetime import datetime, timezone
from typing import Any


def create_event(
    event_type: str,
    data: dict[str, Any],
    conversation_id: int | None = None,
) -> dict[str, Any]:
    """Build a standard WebSocket event envelope."""
    return {
        "type": event_type,
        "event_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "conversation_id": conversation_id,
        "data": data,
    }


# ── Event type constants ──

NEW_MESSAGE = "NEW_MESSAGE"
CONVERSATION_UPDATED = "CONVERSATION_UPDATED"
QUEUE_UPDATED = "QUEUE_UPDATED"
TYPING_START = "TYPING_START"
TYPING_END = "TYPING_END"
VOICE_CALL_ENDED = "VOICE_CALL_ENDED"
TRANSCRIPT_STREAM = "TRANSCRIPT_STREAM"


def transcript_stream_event(
    conversation_id: int,
    turn_id: str,
    sender_type: str,
    text: str,
    is_final: bool,
) -> dict[str, Any]:
    """Event sent for real-time incremental transcription streaming."""
    return create_event(
        event_type=TRANSCRIPT_STREAM,
        conversation_id=conversation_id,
        data={
            "turn_id": turn_id,
            "sender_type": sender_type,
            "text": text,
            "is_final": is_final,
        },
    )


def voice_call_ended_event(
    conversation_id: int,
    ended_by: str = "user",
) -> dict[str, Any]:
    """Event sent when either participant terminates the live voice call."""
    return create_event(
        event_type=VOICE_CALL_ENDED,
        conversation_id=conversation_id,
        data={
            "ended_by": ended_by,
        },
    )


# ── Convenience builders ──

def new_message_event(
    conversation_id: int,
    message_id: int,
    sender_type: str,
    content: str,
    created_at: str,
    message_type: str = "text",
    audio_url: str | None = None,
) -> dict:
    """Event sent when a message is saved to the database."""
    return create_event(
        event_type=NEW_MESSAGE,
        conversation_id=conversation_id,
        data={
            "message_id": message_id,
            "sender_type": sender_type,
            "content": content,
            "created_at": created_at,
            "message_type": message_type,
            "audio_url": audio_url,
        },
    )


def conversation_updated_event(
    conversation_id: int,
    status: str,
    workflow_state: str,
) -> dict:
    """Event sent when conversation status or workflow state changes."""
    return create_event(
        event_type=CONVERSATION_UPDATED,
        conversation_id=conversation_id,
        data={
            "status": status,
            "workflow_state": workflow_state,
        },
    )


def queue_updated_event(
    action: str,
    handoff_id: int,
    priority: str,
    category: str,
) -> dict:
    """Minimal event broadcast to experts when the queue changes.
    Experts then fetch full data via REST."""
    return {
        "type": "QUEUE_UPDATED",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "conversation_id": None,
        "data": {
            "action": action,
            "handoff_id": handoff_id,
            "priority": priority,
            "category": category
        }
    }


def tool_execution_started_event(conversation_id: int, tool_name: str) -> dict[str, Any]:
    return {
        "type": "TOOL_EXECUTION_STARTED",
        "conversation_id": conversation_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {
            "tool_name": tool_name
        }
    }


def tool_confirmation_required_event(conversation_id: int, execution_id: int, tool_name: str, safe_summary: str) -> dict[str, Any]:
    return {
        "type": "TOOL_CONFIRMATION_REQUIRED",
        "conversation_id": conversation_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {
            "execution_id": execution_id,
            "tool_name": tool_name,
            "summary": safe_summary
        }
    }


def tool_execution_completed_event(conversation_id: int, tool_name: str) -> dict[str, Any]:
    return {
        "type": "TOOL_EXECUTION_COMPLETED",
        "conversation_id": conversation_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {
            "tool_name": tool_name
        }
    }


def tool_execution_failed_event(conversation_id: int, tool_name: str) -> dict[str, Any]:
    return {
        "type": "TOOL_EXECUTION_FAILED",
        "conversation_id": conversation_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {
            "tool_name": tool_name
        }
    }


def typing_event(
    conversation_id: int,
    sender_type: str,
    is_start: bool,
) -> dict:
    """Ephemeral typing indicator — never persisted to DB."""
    return create_event(
        event_type=TYPING_START if is_start else TYPING_END,
        conversation_id=conversation_id,
        data={
            "sender_type": sender_type,
        },
    )
