import asyncio
import logging
from typing import Dict, Set

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class NotificationWebSocketManager:
    def __init__(self) -> None:
        self.connections: Dict[int, Set[WebSocket]] = {}

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        if user_id not in self.connections:
            self.connections[user_id] = set()
        self.connections[user_id].add(websocket)
        logger.info("通知WebSocket连接: user_id=%s", user_id)

    async def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        if user_id in self.connections:
            self.connections[user_id].discard(websocket)
            if not self.connections[user_id]:
                self.connections.pop(user_id, None)
        try:
            await websocket.close()
        except WebSocketDisconnect:
            pass
        except Exception as e:  # pragma: no cover
            logger.debug("关闭通知WebSocket时异常: %s", e)

    def send_notification(self, user_id: int, notification: dict) -> None:
        connections = self.connections.get(user_id)
        if not connections:
            return
        message = {"type": "notification", "data": notification}
        for ws in list(connections):
            try:
                asyncio.create_task(ws.send_json(message))
            except Exception as e:
                logger.warning("推送通知到用户%s失败: %s", user_id, e)

    async def async_send_notification(self, user_id: int, notification: dict) -> None:
        connections = self.connections.get(user_id)
        if not connections:
            return
        message = {"type": "notification", "data": notification}
        dead_connections = []
        for ws in list(connections):
            try:
                await ws.send_json(message)
            except Exception as e:
                logger.warning("异步推送通知失败: %s", e)
                dead_connections.append(ws)
        for ws in dead_connections:
            await self.disconnect(user_id, ws)

    def has_connection(self, user_id: int) -> bool:
        return bool(self.connections.get(user_id))


notification_ws_manager = NotificationWebSocketManager()
