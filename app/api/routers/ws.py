"""WebSocket router implementing the collaborative editing protocol."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.db.session import SessionLocal
from app.models import Document
from app.services.websocket_service import ConnectionManager

router = APIRouter()
manager = ConnectionManager()


@router.websocket("/ws/documents/{document_id}")
async def websocket_document_endpoint(websocket: WebSocket, document_id: int) -> None:
    """Handle collaborative editing events for a document."""

    initial_content = _get_document_content(document_id)
    if initial_content is None:
        await websocket.close(code=1008, reason="Document not found")
        return

    user_id = await manager.connect(websocket, document_id, initial_content)

    try:
        while True:
            payload = await websocket.receive_json()
            message_type = payload.get("type")

            if message_type == "content":
                await _handle_content_message(document_id, user_id, payload)
            elif message_type == "cursor":
                await _handle_cursor_message(document_id, user_id, payload)
            else:
                await websocket.send_json(
                    {"type": "error", "message": "Unsupported message type"}
                )
    except WebSocketDisconnect:
        manager.disconnect(document_id, user_id)
    except Exception:
        manager.disconnect(document_id, user_id)
        await websocket.close(code=1011, reason="Internal server error")
        raise


def _get_document_content(document_id: int) -> str | None:
    """Fetch the current document content."""

    with SessionLocal() as session:
        document = session.get(Document, document_id)
        return None if document is None else document.content or ""


async def _handle_content_message(
    document_id: int, user_id: int, payload: Dict[str, Any]
) -> None:
    """Persist and broadcast content updates."""

    content = payload.get("content", "")
    _update_document_content(document_id, content)

    message = {"type": "content", "content": content, "user_id": user_id}
    await manager.broadcast(document_id, message, sender_id=user_id)


async def _handle_cursor_message(
    document_id: int, user_id: int, payload: Dict[str, Any]
) -> None:
    """Broadcast cursor updates to other users."""

    cursor = payload.get("cursor", {})
    message = {"type": "cursor", "cursor": cursor, "user_id": user_id}
    await manager.broadcast(document_id, message, sender_id=user_id)


def _update_document_content(document_id: int, content: str) -> None:
    """Persist the latest document content in the database."""

    with SessionLocal() as session:
        document = session.get(Document, document_id)
        if not document:
            return
        document.content = content
        document.updated_at = datetime.utcnow()
        session.add(document)
        session.commit()
