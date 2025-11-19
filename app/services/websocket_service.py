"""Utilities for managing collaborative WebSocket connections."""
from __future__ import annotations

import asyncio
import itertools
from typing import Any, Dict, Optional

from fastapi import WebSocket


class ConnectionManager:
    """Track active WebSocket connections grouped by document."""

    def __init__(self) -> None:
        self._rooms: Dict[int, Dict[int, WebSocket]] = {}
        self._id_sequence = itertools.count(1)
        self._id_lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, document_id: int, content: str) -> int:
        """Accept the WebSocket connection and send initial state."""

        user_id = await self._generate_user_id()
        await websocket.accept()

        room = self._rooms.setdefault(document_id, {})
        room[user_id] = websocket

        await websocket.send_json({"type": "init", "content": content})
        return user_id

    def disconnect(self, document_id: int, user_id: int) -> None:
        """Remove a WebSocket connection when it closes."""

        room = self._rooms.get(document_id)
        if not room:
            return
        room.pop(user_id, None)
        if not room:
            self._rooms.pop(document_id, None)

    async def broadcast(
        self,
        document_id: int,
        message: Dict[str, Any],
        sender_id: Optional[int] = None,
    ) -> None:
        """Broadcast a message to every participant in a room."""

        room = self._rooms.get(document_id)
        if not room:
            return

        dead_users: list[int] = []
        for user_id, websocket in list(room.items()):
            if sender_id is not None and user_id == sender_id:
                continue
            try:
                await websocket.send_json(message)
            except Exception:
                dead_users.append(user_id)

        for user_id in dead_users:
            room.pop(user_id, None)
        if room == {}:
            self._rooms.pop(document_id, None)

    async def _generate_user_id(self) -> int:
        """Generate a unique in-memory user identifier."""

        async with self._id_lock:
            return next(self._id_sequence)
