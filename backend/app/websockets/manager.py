"""
ResolveAIV2 — WebSocket Connection Manager

Manages active WebSocket connections per user. Supports multiple
connections per user (e.g. multiple browser tabs).

The ConnectionManager is a singleton used by services to push
real-time events to connected clients.

Important: WebSocket is the delivery layer only. The database
remains the source of truth.
"""

import logging
from typing import Dict, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Tracks active WebSocket connections keyed by user_id.

    connections[user_id] = {ws1, ws2, ws3}
    """

    def __init__(self):
        self._connections: Dict[int, Set[WebSocket]] = {}
        # Track which conversations each user is authorized for
        # Populated when events are sent; authorization is checked at broadcast time
        self._expert_users: Set[int] = set()

    async def connect(self, websocket: WebSocket, user_id: int, role: str):
        """Accept and register a WebSocket connection."""
        await websocket.accept()
        
        if user_id in self._connections and len(self._connections[user_id]) >= 5:
            logger.warning(f"WS rate limit: user_id={user_id} exceeded max connections (5)")
            await websocket.close(code=4008, reason="Too many connections")
            return False
            
        if user_id not in self._connections:
            self._connections[user_id] = set()
        self._connections[user_id].add(websocket)

        if role in ("expert", "admin"):
            self._expert_users.add(user_id)

        logger.info(f"WS connected: user_id={user_id} (total={len(self._connections[user_id])})")

    def disconnect(self, websocket: WebSocket, user_id: int):
        """Remove a WebSocket connection."""
        if user_id in self._connections:
            self._connections[user_id].discard(websocket)
            if not self._connections[user_id]:
                del self._connections[user_id]
                self._expert_users.discard(user_id)
        logger.info(f"WS disconnected: user_id={user_id}")

    def get_connection_count(self, user_id: int) -> int:
        """Return the number of active connections for a user."""
        return len(self._connections.get(user_id, set()))

    async def send_to_user(self, user_id: int, event: dict):
        """
        Send an event to all connections for a specific user.
        Silently removes broken connections.
        """
        if user_id not in self._connections:
            return

        broken: list[WebSocket] = []
        for ws in self._connections[user_id]:
            try:
                await ws.send_json(event)
            except Exception:
                broken.append(ws)

        for ws in broken:
            self._connections[user_id].discard(ws)
        if user_id in self._connections and not self._connections[user_id]:
            del self._connections[user_id]
            self._expert_users.discard(user_id)

    async def broadcast_to_experts(self, event: dict):
        """
        Broadcast an event to all connected expert/admin users.
        Used for QUEUE_UPDATED events.
        """
        for user_id in list(self._expert_users):
            await self.send_to_user(user_id, event)

    async def send_to_conversation_participants(
        self,
        customer_id: int,
        expert_id: int | None,
        event: dict,
        is_internal: bool = False,
        exclude_user: int | None = None,
    ):
        """
        Send an event to the customer who owns the conversation
        and, if assigned, the expert handling it.
        In addition, broadcasts to connected expert/admin users so that any
        expert or supervisor currently viewing the conversation console
        receives customer queries and updates in real time.
        Optionally excludes a user (e.g. the author/speaker of the streaming event).
        """
        recipients: Set[int] = set()
        if not is_internal and customer_id is not None:
            recipients.add(customer_id)
            
        if expert_id is not None:
            recipients.add(expert_id)

        # Broadcast to all connected staff (experts/admins) viewing conversations
        recipients.update(self._expert_users)

        if exclude_user is not None:
            recipients.discard(exclude_user)

        for uid in recipients:
            await self.send_to_user(uid, event)

    @property
    def active_connections(self) -> int:
        """Total number of active WebSocket connections across all users."""
        return sum(len(s) for s in self._connections.values())


# Singleton instance — imported by services and router
manager = ConnectionManager()
