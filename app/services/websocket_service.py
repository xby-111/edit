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
        # 注意：WebSocket 应该在路由层已经 accept，这里不再重复 accept
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
        msg_type = data.get("type")
        
        # 协议兼容：支持 content 和 content_update 两种消息类型
        content = None
        if msg_type == "content":
            content = data.get("content", "")
        elif msg_type == "content_update":
            # 优先读取 payload.html，fallback 到 content
            payload = data.get("payload", {})
            content = payload.get("html") or data.get("content", "")
        elif msg_type == "cursor":
            # 广播光标位置给其他用户
            await self.broadcast_to_room(document_id, {
                "type": "cursor",
                "user_id": user_id,
                "cursor": data.get("cursor"),
                "color": self.get_user_color(user_id)
            }, user_id, sender_ws)
            return
        else:
            # 未知消息类型安全忽略，不抛异常
            return
        
        # 更新文档内容到数据库 - 使用参数化查询避免SQL注入
        if content is not None:
            now = datetime.utcnow()
            # 使用参数化查询，直接传datetime对象
            db.execute("UPDATE documents SET content = %s, updated_at = %s WHERE id = %s", 
                      (content, now, document_id))
            
            # 广播内容更新给其他用户，保持协议兼容性
            broadcast_data = {
                "type": msg_type,  # 保持原始消息类型
                "user_id": user_id
            }
            
            # 根据消息类型调整广播格式
            if msg_type == "content_update":
                broadcast_data["payload"] = {"html": content}
            else:
                broadcast_data["content"] = content
                
            await self.broadcast_to_room(document_id, broadcast_data, user_id, sender_ws)