"""
聊天相关 REST API 和 WebSocket 接口
"""
import logging
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from jose import JWTError, jwt

from app.core.config import settings
from app.core.security import get_current_user
from app.db.session import get_db, get_db_connection, close_connection_safely
from app.schemas import User as UserSchema
from app.services.chat_service import (
    create_chat_message,
    list_chat_messages,
    delete_chat_message,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix=f"{settings.API_V1_STR}/documents", tags=["文档聊天"])


# ==================== 数据模型 ====================

class ChatMessageCreate(BaseModel):
    """创建聊天消息"""
    content: str
    message_type: str = "text"


class ChatMessageResponse(BaseModel):
    """聊天消息响应"""
    id: int
    document_id: int
    user_id: int
    username: str
    avatar_url: Optional[str] = None
    content: str
    message_type: str
    created_at: datetime


# ==================== REST API ====================

@router.get("/{document_id}/chat", summary="获取聊天记录", description="获取文档的聊天消息列表")
async def get_chat_messages(
    document_id: int,
    before_id: Optional[int] = Query(None, description="获取此ID之前的消息"),
    limit: int = Query(50, ge=1, le=200),
    current_user: UserSchema = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    获取文档聊天记录
    - 支持分页加载历史消息
    """
    # TODO: 检查用户是否有权限访问此文档
    
    messages = list_chat_messages(db, document_id, before_id, limit)
    return {"messages": messages}


@router.post("/{document_id}/chat", summary="发送聊天消息", description="在文档中发送聊天消息")
async def send_chat_message(
    document_id: int,
    data: ChatMessageCreate,
    current_user: UserSchema = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    发送聊天消息
    - 消息会通过 WebSocket 广播给所有在线用户
    """
    # TODO: 检查用户是否有权限访问此文档
    
    if not data.content.strip():
        raise HTTPException(status_code=400, detail="消息内容不能为空")
    
    message = create_chat_message(
        db,
        document_id=document_id,
        user_id=current_user.id,
        content=data.content.strip(),
        message_type=data.message_type,
    )
    
    if not message:
        raise HTTPException(status_code=500, detail="发送消息失败")
    
    # TODO: 通过 WebSocket 广播消息
    
    return message


@router.delete("/{document_id}/chat/{message_id}", summary="删除聊天消息", description="删除自己发送的聊天消息")
async def remove_chat_message(
    document_id: int,
    message_id: int,
    current_user: UserSchema = Depends(get_current_user),
    db=Depends(get_db),
):
    """删除聊天消息（只能删除自己的）"""
    is_admin = getattr(current_user, 'role', '') == 'admin'
    
    success = delete_chat_message(db, message_id, current_user.id, is_admin)
    if success:
        return {"message": "消息已删除"}
    else:
        raise HTTPException(status_code=404, detail="消息不存在或无权删除")


# ==================== WebSocket 聊天管理器 ====================

class ChatWebSocketManager:
    """聊天 WebSocket 连接管理器"""
    
    def __init__(self):
        # document_id -> set of (websocket, user_id, username)
        self.rooms: dict[int, set] = {}
    
    async def connect(
        self,
        document_id: int,
        websocket: WebSocket,
        user_id: int,
        username: str,
    ):
        """加入聊天室"""
        if document_id not in self.rooms:
            self.rooms[document_id] = set()
        
        self.rooms[document_id].add((websocket, user_id, username))
        
        # 通知其他人有用户加入
        await self.broadcast(
            document_id,
            {
                "type": "chat_user_joined",
                "user_id": user_id,
                "username": username,
                "ts": datetime.utcnow().isoformat(),
            },
            exclude_websocket=websocket,
        )
    
    async def disconnect(self, document_id: int, websocket: WebSocket):
        """离开聊天室"""
        if document_id in self.rooms:
            # 找到并移除连接
            to_remove = None
            user_info = None
            for conn in self.rooms[document_id]:
                if conn[0] == websocket:
                    to_remove = conn
                    user_info = {"user_id": conn[1], "username": conn[2]}
                    break
            
            if to_remove:
                self.rooms[document_id].discard(to_remove)
                
                # 通知其他人有用户离开
                if user_info:
                    await self.broadcast(
                        document_id,
                        {
                            "type": "chat_user_left",
                            "user_id": user_info["user_id"],
                            "username": user_info["username"],
                            "ts": datetime.utcnow().isoformat(),
                        },
                    )
            
            # 清理空房间
            if not self.rooms[document_id]:
                del self.rooms[document_id]
    
    async def broadcast(
        self,
        document_id: int,
        message: dict,
        exclude_websocket: Optional[WebSocket] = None,
    ):
        """广播消息给房间内所有用户"""
        if document_id not in self.rooms:
            return
        
        dead_connections = []
        for conn in self.rooms[document_id]:
            ws, user_id, username = conn
            if exclude_websocket and ws == exclude_websocket:
                continue
            
            try:
                await ws.send_json(message)
            except Exception:
                dead_connections.append(conn)
        
        # 清理死连接
        for conn in dead_connections:
            self.rooms[document_id].discard(conn)
    
    def get_online_users(self, document_id: int) -> List[dict]:
        """获取在线用户列表"""
        if document_id not in self.rooms:
            return []
        
        return [
            {"user_id": conn[1], "username": conn[2]}
            for conn in self.rooms[document_id]
        ]


# 全局聊天管理器实例
chat_manager = ChatWebSocketManager()


# ==================== WebSocket 端点 ====================

@router.websocket("/{document_id}/chat/ws")
async def chat_websocket(
    websocket: WebSocket,
    document_id: int,
    token: Optional[str] = Query(None),
):
    """
    文档聊天 WebSocket 端点
    
    消息类型：
    - chat_message: 聊天消息
    - typing: 正在输入状态
    """
    await websocket.accept()
    
    # 验证 token
    user_id = None
    username = "anonymous"
    
    if token:
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            token_username = payload.get("sub")
            if token_username:
                # 获取用户信息
                db = get_db_connection()
                try:
                    rows = db.query(
                        "SELECT id, username FROM users WHERE username = %s LIMIT 1",
                        (token_username,)
                    )
                    if rows:
                        user_id = rows[0][0]
                        username = rows[0][1]
                finally:
                    close_connection_safely(db)
        except JWTError:
            await websocket.close(code=1008, reason="Invalid token")
            return
    
    if not user_id:
        await websocket.close(code=1008, reason="Authentication required")
        return
    
    # 加入聊天室
    await chat_manager.connect(document_id, websocket, user_id, username)
    
    # 发送在线用户列表
    await websocket.send_json({
        "type": "chat_init",
        "online_users": chat_manager.get_online_users(document_id),
    })
    
    db = None
    try:
        db = get_db_connection()
        
        while True:
            try:
                message = await websocket.receive_json()
            except WebSocketDisconnect:
                break
            except Exception:
                break
            
            msg_type = message.get("type")
            
            if msg_type == "chat_message":
                # 保存并广播聊天消息
                content = message.get("content", "").strip()
                if content:
                    saved_msg = create_chat_message(
                        db,
                        document_id=document_id,
                        user_id=user_id,
                        content=content,
                        message_type=message.get("message_type", "text"),
                    )
                    
                    if saved_msg:
                        # 广播给所有人（包括发送者）
                        await chat_manager.broadcast(
                            document_id,
                            {
                                "type": "chat_message",
                                "message": saved_msg,
                            },
                        )
            
            elif msg_type == "typing":
                # 广播正在输入状态（不包括发送者）
                await chat_manager.broadcast(
                    document_id,
                    {
                        "type": "typing",
                        "user_id": user_id,
                        "username": username,
                        "is_typing": message.get("is_typing", True),
                    },
                    exclude_websocket=websocket,
                )
    
    except Exception as e:
        logger.exception(f"Chat WebSocket error: {e}")
    
    finally:
        await chat_manager.disconnect(document_id, websocket)
        if db:
            close_connection_safely(db)
