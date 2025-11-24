# services/websocket_service.py   ←←← 直接全选替换成这个！！！
from typing import Dict, Any
from fastapi import WebSocket
from models import Document, User  # 新增这行
import json

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, list] = {}  # doc_id -> list of conn

    async def connect(self, websocket: WebSocket, document_id: int, user: User, db):
        await websocket.accept()
        if document_id not in self.active_connections:
            self.active_connections[document_id] = []

        # 把整个 user 对象存进去
        self.active_connections[document_id].append({
            "websocket": websocket,
            "user": user
        })

        # 初始化内容发给新人
        document = db.query(Document).filter(Document.id == document_id).first()
        await websocket.send_json({
            "type": "init",
            "content": document.content if document else ""
        })

        # 告诉房间里其他人：有真人进来了（带真实用户名）
        for conn in self.active_connections[document_id]:
            if conn["websocket"] != websocket:
                await conn["websocket"].send_json({
                    "type": "user_joined",
                    "user_id": user.id,
                    "username": user.username,
                    "color": self.get_user_color(user.id)  # 给每个用户固定颜色
                })

    def disconnect(self, websocket: WebSocket, document_id: int):
        if document_id in self.active_connections:
            self.active_connections[document_id] = [
                c for c in self.active_connections[document_id] if c["websocket"] != websocket
            ]
            if not self.active_connections[document_id]:
                del self.active_connections[document_id]

    async def broadcast_to_room(self, document_id: int, data: dict, sender_ws: WebSocket):
        if document_id not in self.active_connections:
            return
        for conn in self.active_connections[document_id]:
            if conn["websocket"] != sender_ws:
                try:
                    await conn["websocket"].send_json(data)
                except:
                    pass

    def get_user_color(self, user_id: int) -> str:
        # 固定颜色列表，用户ID取模，保证同一个人永远同一种颜色
        colors = ["#FF5733", "#33FF57", "#3357FF", "#F333FF", "#FF33A1", "#33FFF0", "#FFBD33", "#8D33FF"]
        return colors[user_id % len(colors)]

    async def handle_message(self, document_id: int, user_id: int, data: dict, sender_ws: WebSocket, db):
        """处理来自客户端的消息"""
        if data["type"] == "content":
            # 更新文档内容到数据库
            document = db.query(Document).filter(Document.id == document_id).first()
            if document:
                document.content = data["content"]
                db.commit()
            
            # 广播内容更新给其他用户
            await self.broadcast_to_room(document_id, {
                "type": "content",
                "content": data["content"],
                "user_id": user_id
            }, sender_ws)
            
        elif data["type"] == "cursor":
            # 广播光标位置给其他用户
            await self.broadcast_to_room(document_id, {
                "type": "cursor",
                "user_id": user_id,
                "username": self.get_username_by_id(user_id, db),
                "cursor": data["cursor"],
                "color": self.get_user_color(user_id)
            }, sender_ws)
    
    def get_username_by_id(self, user_id: int, db) -> str:
        """根据用户ID获取用户名"""
        user = db.query(User).filter(User.id == user_id).first()
        return user.username if user else "匿名"
