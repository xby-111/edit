from datetime import datetime
from typing import Dict, List, Set

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt

from app.core.config import settings

router = APIRouter()


class ConnectionManager:
    def __init__(self) -> None:
        self.rooms: Dict[int, Set[WebSocket]] = {}
        self.usernames: Dict[WebSocket, str] = {}

    async def connect(self, document_id: int, websocket: WebSocket, username: str) -> None:
        await websocket.accept()
        if document_id not in self.rooms:
            self.rooms[document_id] = set()
        self.rooms[document_id].add(websocket)
        self.usernames[websocket] = username
        await self.broadcast(
            document_id,
            {
                "type": "presence",
                "action": "join",
                "doc_id": document_id,
                "user": username,
                "ts": datetime.utcnow().isoformat(),
            },
            sender=websocket,
        )

    def disconnect(self, document_id: int, websocket: WebSocket) -> None:
        if document_id in self.rooms:
            self.rooms[document_id].discard(websocket)
            username = self.usernames.pop(websocket, "")
            if self.rooms[document_id]:
                # Broadcast leave to others
                import asyncio

                asyncio.create_task(
                    self.broadcast(
                        document_id,
                        {
                            "type": "presence",
                            "action": "leave",
                            "doc_id": document_id,
                            "user": username,
                            "ts": datetime.utcnow().isoformat(),
                        },
                        sender=websocket,
                    )
                )
            else:
                self.rooms.pop(document_id, None)

    async def broadcast(self, document_id: int, message: dict, sender: WebSocket | None = None) -> None:
        if document_id not in self.rooms:
            return
        for connection in list(self.rooms[document_id]):
            if connection is sender:
                continue
            try:
                await connection.send_json(message)
            except RuntimeError:
                # Connection might be closed
                self.rooms[document_id].discard(connection)
                self.usernames.pop(connection, None)

    def get_online_users(self, document_id: int) -> List[str]:
        if document_id not in self.rooms:
            return []
        return [self.usernames.get(ws, "") for ws in self.rooms[document_id]]


manager = ConnectionManager()


def decode_username_from_token(token: str) -> str:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise JWTError("Missing username")
        return username
    except JWTError as exc:  # pragma: no cover - simple guard
        raise exc


@router.websocket("/documents/{document_id}")
async def document_collab_ws(
    websocket: WebSocket,
    document_id: int,
    token: str = Query(...),
    username: str | None = Query(None),
):
    try:
        token_username = decode_username_from_token(token)
    except JWTError:
        await websocket.close(code=1008)
        return

    current_username = token_username or username or "匿名用户"

    await manager.connect(document_id, websocket, current_username)

    # Send current online users to the newly connected client
    await websocket.send_json(
        {
            "type": "presence",
            "action": "init",
            "doc_id": document_id,
            "online_users": manager.get_online_users(document_id),
            "ts": datetime.utcnow().isoformat(),
        }
    )

    try:
        while True:
            message = await websocket.receive_json()
            msg_type = message.get("type")
            payload = message.get("data") or message.get("payload")

            if msg_type not in {"content_update", "cursor", "presence"}:
                continue

            broadcast_message = {
                "type": msg_type,
                "doc_id": document_id,
                "user": current_username,
                "payload": payload,
                "ts": datetime.utcnow().isoformat(),
            }
            await manager.broadcast(document_id, broadcast_message, sender=websocket)
    except WebSocketDisconnect:
        manager.disconnect(document_id, websocket)
    except Exception:
        manager.disconnect(document_id, websocket)
        await websocket.close(code=1011)
