# services/websocket_service.py
from typing import Dict, Any
from fastapi import WebSocket
import json
from datetime import datetime

def _escape(value: str | None) -> str:
    """简单转义单引号，避免 SQL 语法错误（内部使用即可）"""
    if value is None:
        return "NULL"
    escaped_value = value.replace("'", "''")
    return f"'{escaped_value}'"

def _format_datetime(dt: datetime | None) -> str:
    """格式化日期时间为 SQL 字符串"""
    if dt is None:
        return "NULL"
    return f"'{dt.strftime('%Y-%m-%d %H:%M:%S')}'"

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, list] = {}  # doc_id -> list of conn

    async def connect(self, websocket: WebSocket, document_id: int, user_id: int, initial_content: str):
        await websocket.accept()
        if document_id not in self.active_connections:
            self.active_connections[document_id] = []

        # 存储连接信息
        self.active_connections[document_id].append({
            "websocket": websocket,
            "user_id": user_id
        })

        # 初始化内容发给新人
        await websocket.send_json({
            "type": "init",
            "content": initial_content
        })

        # 告诉房间里其他人：有真人进来了（带用户ID）
        for conn in self.active_connections[document_id]:
            if conn["websocket"] != websocket:
                await conn["websocket"].send_json({
                    "type": "user_joined",
                    "user_id": user_id,
                    "color": self.get_user_color(user_id)  # 给每个用户固定颜色
                })

    def disconnect(self, websocket: WebSocket, document_id: int, user_id: int):
        if document_id in self.active_connections:
            self.active_connections[document_id] = [
                c for c in self.active_connections[document_id] 
                if c["websocket"] != websocket
            ]
            if not self.active_connections[document_id]:
                del self.active_connections[document_id]

    async def broadcast_to_room(self, document_id: int, data: dict, sender_user_id: int, sender_ws: WebSocket):
        if document_id not in self.active_connections:
            return
        for conn in self.active_connections[document_id]:
            if conn["websocket"] != sender_ws:
                try:
                    await conn["websocket"].send_json(data)
                except:
                    # 如果发送失败，移除连接
                    self.disconnect(conn["websocket"], document_id, conn["user_id"])

    def get_user_color(self, user_id: int) -> str:
        # 固定颜色列表，用户ID取模，保证同一个人永远同一种颜色
        colors = ["#FF5733", "#33FF57", "#3357FF", "#F333FF", "#FF33A1", "#33FFF0", "#FFBD33", "#8D33FF"]
        return colors[user_id % len(colors)]

    async def handle_message(self, document_id: int, user_id: int, data: dict, sender_ws: WebSocket, db):
        """处理来自客户端的消息"""
        if data["type"] == "content":
            # 更新文档内容到数据库 - 使用 py-opengauss 的 execute 方法
            now = datetime.utcnow()
            content_safe = _escape(data["content"])
            now_sql = _format_datetime(now)
            db.execute(f"UPDATE documents SET content = {content_safe}, updated_at = {now_sql} WHERE id = {document_id}")
            
            # 广播内容更新给其他用户
            await self.broadcast_to_room(document_id, {
                "type": "content",
                "content": data["content"],
                "user_id": user_id
            }, user_id, sender_ws)
            
        elif data["type"] == "cursor":
            # 广播光标位置给其他用户
            await self.broadcast_to_room(document_id, {
                "type": "cursor",
                "user_id": user_id,
                "cursor": data["cursor"],
                "color": self.get_user_color(user_id)
            }, user_id, sender_ws)