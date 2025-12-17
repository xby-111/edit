"""
WebSocket 服务层

处理文档协作的 WebSocket 连接管理、消息广播和 CRDT 同步。
"""
from typing import Dict, Any, Optional, List, Set
from datetime import datetime
import logging
import asyncio

from fastapi import WebSocket

from app.crdt import get_document_crdt
from app.core.utils import get_utc_now
from app.db.session import get_db_connection, close_connection_safely
from app.services.document_service import update_document_internal

logger = logging.getLogger(__name__)

# 用户颜色列表，用于区分不同用户的光标
USER_COLORS = [
    "#FF5733", "#33FF57", "#3357FF", "#F333FF",
    "#FF33A1", "#33FFF0", "#FFBD33", "#8D33FF"
]


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, list] = {}  # doc_id -> list of conn
        self.document_crdts: Dict[int, Any] = {}  # 文档 CRDT 管理器
        self.last_heartbeat: Dict[WebSocket, datetime] = {}
        self.dirty_docs: Set[int] = set()
        self._dirty_lock = asyncio.Lock()
        self._background_task: Optional[asyncio.Task] = None

    async def connect(self, websocket: WebSocket, document_id: int, user_id: int, initial_content: str, username: str = ""):
        # 注意：WebSocket 应该在路由层已经 accept，这里不再重复 accept
        if document_id not in self.active_connections:
            self.active_connections[document_id] = []

        # 初始化文档 CRDT
        doc_crdt = get_document_crdt(document_id)
        if not doc_crdt.master_crdt.sequence:
            doc_crdt.master_crdt.from_text(initial_content)
        
        # 创建客户端 CRDT
        client_crdt = doc_crdt.get_client(f"user_{user_id}")

        # 存储连接信息（包含 username）
        self.active_connections[document_id].append({
            "websocket": websocket,
            "user_id": user_id,
            "username": username,
            "client_id": f"user_{user_id}",
            "crdt": client_crdt,
        })

        # 初始化内容发给新人
        await websocket.send_json({
            "type": "init",
            "content": initial_content,
            "crdt_state": doc_crdt.get_document_state(),
        })

        # 告诉房间里其他人：有真人进来了（带用户ID）
        for conn in list(self.active_connections[document_id]):
            if conn["websocket"] != websocket:
                try:
                    await conn["websocket"].send_json({
                        "type": "user_joined",
                        "user_id": user_id,
                        "color": self.get_user_color(user_id)  # 给每个用户固定颜色
                    })
                except Exception:
                    # 移除失效连接
                    await self._safe_remove_connection(conn["websocket"], document_id)

    async def disconnect(self, document_id: int, websocket: WebSocket):
        """异步断开连接并在房间空时触发保存"""
        await self._safe_remove_connection(websocket, document_id)

    async def _safe_remove_connection(self, websocket: WebSocket, document_id: int):
        if document_id not in self.active_connections:
            return
        before = len(self.active_connections[document_id])
        self.active_connections[document_id] = [
            c for c in self.active_connections[document_id]
            if c["websocket"] != websocket
        ]
        # 清理客户端 CRDT 记录
        for cid, conn in list(get_document_crdt(document_id).clients.items()):
            if conn.client_id == f"user_{getattr(websocket, '_user_id', '')}":
                get_document_crdt(document_id).remove_client(conn.client_id)

        if not self.active_connections.get(document_id):
            # 🔥 修复 Issue C: 房间为空时立即同步保存,不依赖后台任务
            logger.info(f"📤 房间 {document_id} 已空,最后一人离开,触发立即保存")
            
            # 使用新的 save_document_now() 方法
            await self.save_document_now(document_id)
            
            self.active_connections.pop(document_id, None)
            logger.info(f"🧹 房间 {document_id} 已清理")
        else:
            # 仍有其他连接，无需强制保存，但广播离开事件
            for conn in list(self.active_connections.get(document_id, [])):
                try:
                    await conn["websocket"].send_json({
                        "type": "presence",
                        "action": "leave",
                        "user_id": getattr(websocket, '_user_id', None),
                    })
                except Exception:
                    await self._safe_remove_connection(conn["websocket"], document_id)

    async def broadcast_to_room(self, document_id: int, data: dict, sender_user_id: int, sender_ws: WebSocket):
        if document_id not in self.active_connections:
            logger.debug(f"房间 {document_id} 不存在，跳过广播")
            return
        conn_count = len(self.active_connections[document_id])
        logger.info(f"广播到房间 {document_id}，共 {conn_count} 个连接，发送者 user_id={sender_user_id}")
        for conn in self.active_connections[document_id]:
            if conn["websocket"] != sender_ws:
                try:
                    await conn["websocket"].send_json(data)
                    logger.debug(f"已发送给 user_id={conn['user_id']}")
                except:
                    # 如果发送失败，移除连接
                    await self._safe_remove_connection(conn["websocket"], document_id)

    def get_user_color(self, user_id: int) -> str:
        """获取用户的固定颜色（根据用户ID取模）"""
        return USER_COLORS[user_id % len(USER_COLORS)]

    def _get_username_by_user_id(self, document_id: int, user_id: int) -> str:
        """根据 user_id 获取用户名"""
        if document_id not in self.active_connections:
            return ""
        for conn in self.active_connections[document_id]:
            if conn.get("user_id") == user_id:
                return conn.get("username", "")
        return ""

    async def handle_pong(self, websocket: WebSocket) -> None:
        """更新心跳时间戳（兼容 ws.py 的调用）"""
        self.last_heartbeat[websocket] = datetime.utcnow()

    async def send_heartbeat_to_all(self) -> None:
        """向所有活跃连接发送心跳（兼容 ws.py）"""
        now = datetime.utcnow()
        for doc_id, conns in list(self.active_connections.items()):
            for conn in list(conns):
                try:
                    await conn["websocket"].send_json({"type": "ping", "ts": now.isoformat()})
                except Exception:
                    await self._safe_remove_connection(conn["websocket"], doc_id)

    async def cleanup_dead_connections(self, document_id: int = None) -> None:
        """清理心跳超时或无响应连接（兼容 ws.py）"""
        rooms_to_check = [document_id] if document_id else list(self.active_connections.keys())
        current_time = datetime.utcnow()
        for doc_id in rooms_to_check:
            for conn in list(self.active_connections.get(doc_id, [])):
                ws = conn["websocket"]
                last = self.last_heartbeat.get(ws)
                if not last or (current_time - last).seconds > 3 * 25:
                    await self._safe_remove_connection(ws, doc_id)

    async def handle_message(self, document_id: int, user_id: int, data: dict, sender_ws: WebSocket, db):
        """处理来自客户端的消息"""
        msg_type = data.get("type")
        
        # CRDT 操作处理
        if msg_type == "crdt_ops":
            await self._handle_crdt_ops(document_id, user_id, data, sender_ws, db)
            return
        
        # 协议兼容：支持 content 和 content_update 两种消息类型
        content = None
        if msg_type == "content":
            content = data.get("content", "")
        elif msg_type == "content_update":
            # 优先读取 payload.html，fallback 到 content
            payload = data.get("payload", {})
            content = payload.get("html") or data.get("content", "")
        elif msg_type == "cursor":
            # 广播光标位置给其他用户（包含 username）
            username = self._get_username_by_user_id(document_id, user_id)
            await self.broadcast_to_room(document_id, {
                "type": "cursor",
                "user_id": user_id,
                "username": username,
                "cursor": data.get("cursor"),
                "color": self.get_user_color(user_id)
            }, user_id, sender_ws)
            return
        elif msg_type == "selection":
            # 广播选区信息给其他用户
            username = self._get_username_by_user_id(document_id, user_id)
            await self.broadcast_to_room(document_id, {
                "type": "selection",
                "user_id": user_id,
                "username": username,
                "user_id": user_id,
                "selection": data.get("selection"),
                "color": self.get_user_color(user_id)
            }, user_id, sender_ws)
            return
        else:
            # 未知消息类型安全忽略，不抛异常
            return
        
        # 更新内存中的文档状态，并标记为脏（延迟持久化）
        if content is not None:
            # 更新 CRDT master（以全文兼容的方式）
            doc_crdt = get_document_crdt(document_id)
            doc_crdt.master_crdt.from_text(content)

            # 标记为脏，稍后后台任务会持久化
            await self.mark_dirty(document_id)

            # 广播内容更新给其他用户，保持协议兼容性
            broadcast_data = {
                "type": msg_type,
                "user_id": user_id
            }
            if msg_type == "content_update":
                broadcast_data["payload"] = {"html": content}
            else:
                broadcast_data["content"] = content

            logger.info(f"广播内容更新: doc_id={document_id}, user_id={user_id}, type={msg_type}")
            await self.broadcast_to_room(document_id, broadcast_data, user_id, sender_ws)
    
    async def _handle_crdt_ops(self, document_id: int, user_id: int, data: dict, sender_ws: WebSocket, db):
        """处理 CRDT 操作"""
        ops = data.get("ops", [])
        if not ops:
            return
        
        doc_crdt = get_document_crdt(document_id)
        client_id = f"user_{user_id}"
        
        # 应用操作
        result = doc_crdt.apply_client_ops(client_id, ops)
        
        # 更新内存并标记为脏（由后台保存）
        new_content = result["text"]
        await self.mark_dirty(document_id)

        # 广播给其他客户端
        await self.broadcast_to_room(document_id, {
            "type": "crdt_ops",
            "ops": result["broadcast"],
            "version": result["version"],
            "user_id": user_id,
        }, user_id, sender_ws)

        # 发送确认给发送者
        await sender_ws.send_json({
            "type": "crdt_ack",
            "version": result["version"],
            "applied": result["applied"],
        })
    
    def get_online_users(self, document_id: int) -> List[Dict[str, Any]]:
        """获取文档的在线用户列表（包含 username）"""
        if document_id not in self.active_connections:
            return []
        
        users = []
        for conn in self.active_connections[document_id]:
            users.append({
                "user_id": conn["user_id"],
                "username": conn.get("username", ""),
                "color": self.get_user_color(conn["user_id"]),
            })
        return users

    async def mark_dirty(self, document_id: int) -> None:
        """标记文档为脏，稍后由后台任务持久化"""
        async with self._dirty_lock:
            self.dirty_docs.add(document_id)
    
    async def save_document_now(self, document_id: int) -> bool:
        """🔥 修复 Issue C: 立即同步保存文档 (不依赖后台任务)
        
        用于关键时刻的数据持久化:
        - 最后一个用户断开连接时
        - 服务器即将关闭时
        - 用户明确请求保存时
        
        Returns:
            bool: 保存是否成功
        """
        try:
            db = None
            try:
                db = get_db_connection()
                # 获取CRDT当前文本
                doc_crdt = get_document_crdt(document_id)
                content = doc_crdt.master_crdt.to_text()
                content_size = len(content)
                
                logger.info(f"⚡ 立即同步保存文档 {document_id} ({content_size} 字节)")
                
                # 使用内部更新函数（无权限检查,包含 commit）
                success = update_document_internal(db, document_id, content)
                
                if success:
                    logger.info(f"✅ 文档 {document_id} 立即保存成功")
                    # 从脏文档列表中移除
                    async with self._dirty_lock:
                        self.dirty_docs.discard(document_id)
                else:
                    logger.warning(f"⚠️ 文档 {document_id} 保存返回 False")
                
                return success
            finally:
                if db:
                    close_connection_safely(db)
        except Exception as e:
            logger.exception(f"❌ 立即保存文档 {document_id} 失败: {e}")
            return False

    async def background_save_task(self, interval_seconds: int = 5) -> None:
        """后台周期性保存脏文档到数据库"""
        logger.info(f"🚀 后台保存任务已启动 (间隔: {interval_seconds}秒)")
        while True:
            try:
                await asyncio.sleep(interval_seconds)
                # 取出待保存文档列表
                async with self._dirty_lock:
                    to_save = list(self.dirty_docs)
                    self.dirty_docs.clear()

                if not to_save:
                    continue
                
                logger.info(f"💾 后台保存: 发现 {len(to_save)} 个待保存文档")

                for doc_id in to_save:
                    try:
                        db = None
                        try:
                            db = get_db_connection()
                            # 获取CRDT当前文本
                            doc_crdt = get_document_crdt(doc_id)
                            content = doc_crdt.master_crdt.to_text()
                            content_size = len(content)
                            logger.info(f"📝 准备保存文档 {doc_id} ({content_size} 字节)")
                            # 使用内部更新函数（无权限检查）
                            update_document_internal(db, doc_id, content)
                            logger.info(f"✅ 后台保存文档 {doc_id} 完成")
                        finally:
                            if db:
                                close_connection_safely(db)
                    except Exception as e:
                        logger.exception(f"❌ 后台保存文档 {doc_id} 失败: {e}")
            except asyncio.CancelledError:
                logger.info("🛑 后台保存任务已取消")
                break
            except Exception as e:
                logger.exception(f"❌ 后台保存任务异常: {e}")