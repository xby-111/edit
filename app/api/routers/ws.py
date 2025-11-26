from datetime import datetime
from typing import Dict, List, Set
import asyncio
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, Depends
from jose import JWTError, jwt, ExpiredSignatureError, JWSError
from app.db.session import get_db_connection, close_connection_safely
from app.services.document_service import get_document, update_document

from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionManager:
    def __init__(self) -> None:
        self.rooms: Dict[int, Set[WebSocket]] = {}
        self.usernames: Dict[WebSocket, str] = {}
        self.user_ids: Dict[WebSocket, int] = {}  # 存储用户ID
        self.connection_times: Dict[WebSocket, datetime] = {}  # 连接时间
        self.db_connections: Dict[WebSocket, object] = {}  # 每个WebSocket的独立数据库连接
        self.last_heartbeat: Dict[WebSocket, datetime] = {}  # 最后心跳时间

    async def connect(self, document_id: int, websocket: WebSocket, username: str, user_id: int, db_conn) -> None:
        # WebSocket 已在 endpoint 中接受，这里不再接受
        if document_id not in self.rooms:
            self.rooms[document_id] = set()
        self.rooms[document_id].add(websocket)
        self.usernames[websocket] = username
        self.user_ids[websocket] = user_id
        self.connection_times[websocket] = datetime.utcnow()
        self.db_connections[websocket] = db_conn
        self.last_heartbeat[websocket] = datetime.utcnow()
        
        logger.info(f"用户 {username}({user_id}) 连接到文档 {document_id}")
        
        await self.broadcast(
            document_id,
            {
                "type": "presence",
                "action": "join",
                "doc_id": document_id,
                "user": username,
                "user_id": user_id,
                "ts": datetime.utcnow().isoformat(),
            },
            sender=websocket,
        )

    async def disconnect(self, document_id: int, websocket: WebSocket) -> None:
        if document_id in self.rooms:
            self.rooms[document_id].discard(websocket)
            username = self.usernames.pop(websocket, "")
            user_id = self.user_ids.pop(websocket, None)
            self.connection_times.pop(websocket, None)
            db_conn = self.db_connections.pop(websocket, None)
            self.last_heartbeat.pop(websocket, None)
            
            # 关闭该WebSocket的数据库连接
            if db_conn:
                close_connection_safely(db_conn)
            
            logger.info(f"用户 {username}({user_id}) 断开与文档 {document_id} 的连接")
            
            if self.rooms[document_id]:
                # Broadcast leave to others
                await self.broadcast(
                    document_id,
                    {
                        "type": "presence",
                        "action": "leave",
                        "doc_id": document_id,
                        "user": username,
                        "user_id": user_id,
                        "ts": datetime.utcnow().isoformat(),
                    },
                    sender=websocket,
                )
            else:
                self.rooms.pop(document_id, None)

    async def broadcast(self, document_id: int, message: dict, sender: WebSocket | None = None) -> None:
        if document_id not in self.rooms:
            return
        
        dead_connections = []
        active_connections = 0
        
        for connection in list(self.rooms[document_id]):
            if connection is sender:
                continue
                
            try:
                await connection.send_json(message)
                active_connections += 1
            except (RuntimeError, WebSocketDisconnect) as e:
                # Connection might be closed or disconnected
                logger.debug(f"发现死连接，移除: {e}")
                dead_connections.append(connection)
            except Exception as e:
                # Any other exception also indicates a dead connection
                logger.debug(f"发送消息时出现异常，移除连接: {e}")
                dead_connections.append(connection)
        
        # Remove dead connections
        for connection in dead_connections:
            await self.disconnect(document_id, connection)
        
        logger.debug(f"广播完成，活跃连接数: {active_connections}")

    def get_online_users(self, document_id: int) -> List[Dict]:
        """获取在线用户列表，包含用户名和ID"""
        if document_id not in self.rooms:
            return []
        return [
            {
                "username": self.usernames.get(ws, ""), 
                "user_id": self.user_ids.get(ws, 0)
            } 
            for ws in self.rooms[document_id]
        ]
    
    async def cleanup_dead_connections(self, document_id: int = None) -> None:
        """清理死连接（使用应用层心跳）"""
        rooms_to_check = [document_id] if document_id else list(self.rooms.keys())
        current_time = datetime.utcnow()
        
        for doc_id in rooms_to_check:
            if doc_id not in self.rooms:
                continue
                
            dead_connections = []
            for connection in self.rooms[doc_id]:
                # 检查心跳超时（60秒无心跳视为死连接）
                last_heartbeat = self.last_heartbeat.get(connection)
                if not last_heartbeat or (current_time - last_heartbeat).seconds > 60:
                    dead_connections.append(connection)
                    continue
                
                # 尝试发送应用层心跳
                try:
                    await connection.send_json({"type": "ping", "ts": current_time.isoformat()})
                except Exception:
                    dead_connections.append(connection)
            
            # 清理死连接
            for connection in dead_connections:
                await self.disconnect(doc_id, connection)

    async def handle_pong(self, websocket: WebSocket) -> None:
        """处理心跳响应"""
        self.last_heartbeat[websocket] = datetime.utcnow()

    async def send_heartbeat_to_all(self) -> None:
        """向所有活跃连接发送心跳"""
        current_time = datetime.utcnow()
        for document_id, connections in self.rooms.items():
            for connection in connections:
                try:
                    await connection.send_json({
                        "type": "ping", 
                        "ts": current_time.isoformat()
                    })
                except Exception as e:
                    logger.debug(f"发送心跳失败，将标记为死连接: {e}")
                    # 下次清理任务会处理这个连接


@router.websocket("/ws/test")
async def test_websocket(websocket: WebSocket):
    """简单的测试WebSocket端点"""
    logger.info("测试WebSocket连接请求")
    await websocket.accept()
    logger.info("测试WebSocket连接已接受")
    await websocket.send_text("WebSocket连接成功")
    await websocket.close()


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


@router.websocket("/ws/documents/{document_id}")
async def document_collab_ws(
    websocket: WebSocket,
    document_id: int,
    token: str | None = Query(None),
    username: str | None = Query(None)
):
    logger.info(f"WebSocket 连接请求: document_id={document_id}, token={'***' if token else 'None'}")
    
    # 先接受连接，再验证token（确保握手成功，失败时用code=1008关闭）
    await websocket.accept()
    logger.debug("WebSocket 连接已接受")
    
    # 如果提供了 token，必须验证；如果没有 token，允许匿名连接
    token_username = None
    if token:
        # 验证token
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            token_username = payload.get("sub")
            if not token_username:
                logger.warning("WebSocket JWT 验证失败: Missing username in token")
                await websocket.close(code=1008, reason="Invalid token: missing username")
                return
            logger.info(f"JWT 验证成功，用户: {token_username}")
        except ExpiredSignatureError:
            logger.warning("WebSocket JWT 验证失败: Token expired")
            await websocket.close(code=1008, reason="Token expired")
            return
        except JWTError as e:
            # 细分JWT错误类型
            error_msg = str(e)
            if "Invalid crypto padding" in error_msg or "Invalid base64-encoded string" in error_msg:
                logger.warning("WebSocket JWT 验证失败: Invalid token format")
                await websocket.close(code=1008, reason="Invalid token format")
            else:
                logger.warning(f"WebSocket JWT 验证失败: {e}")
                await websocket.close(code=1008, reason="Invalid token")
            return
        except Exception as e:
            logger.error(f"WebSocket JWT 验证出现未知错误")
            await websocket.close(code=1011, reason="Internal server error")
            return
    else:
        # 没有 token，允许匿名连接
        logger.info("WebSocket 连接无 token，允许匿名连接")
        token_username = None

    current_username = token_username or username or "匿名用户"
    
    # 为每个WebSocket创建独立的数据库连接
    db = None
    try:
        db = get_db_connection()
    except Exception as e:
        logger.error(f"创建数据库连接失败: {e}")
        try:
            await websocket.close(code=1011, reason="Database connection failed")
        except Exception:
            pass
        return
    
    # 从数据库查询用户ID（必须在connect之前完成）
    try:
        if token_username:
            user_rows = db.query("SELECT id FROM users WHERE username = %s LIMIT 1", (token_username,))
            
            if not user_rows:
                logger.warning(f"用户不存在: {token_username}，关闭连接")
                try:
                    await websocket.close(code=1008, reason="User not found")
                except Exception:
                    pass
                close_connection_safely(db)
                return
                
            user_id = user_rows[0][0]  # 获取用户ID
        else:
            # 匿名用户，user_id = 0
            user_id = 0
            logger.info("使用匿名用户连接，user_id=0")
        
        # 先检查文档权限（在注册连接之前）
        from app.services.document_service import get_document_with_collaborators, check_document_permission
        permission = check_document_permission(db, document_id, user_id)
        
        # 对于匿名用户，即使权限检查失败，也允许连接（不关闭）
        if not permission["can_view"] and user_id != 0:
            logger.warning(f"用户 {user_id} 无权限访问文档 {document_id}，关闭连接")
            try:
                await websocket.close(code=1008, reason="Access denied")
            except Exception:
                pass
            close_connection_safely(db)
            return
        elif not permission["can_view"] and user_id == 0:
            # 匿名用户即使无权限也允许连接，但权限设为最小
            logger.info(f"匿名用户连接文档 {document_id}，文档不存在或无权限，但允许连接")
            permission = {"can_view": False, "can_edit": False, "is_owner": False}
        
        # 权限验证通过，现在可以安全地调用connect
        await manager.connect(document_id, websocket, current_username, user_id, db)
        
        # 获取文档内容
        doc = get_document_with_collaborators(db, document_id, user_id)
        if doc:
            await websocket.send_json({
                "type": "init",
                "payload": {"html": doc.get("content") or ""},
                "doc_id": document_id,
                "user": "System",
                "ts": datetime.utcnow().isoformat(),
                "permissions": permission  # 发送权限信息
            })
        else:
            # 对于匿名用户，即使文档不存在也允许连接保持
            if user_id == 0:
                logger.info(f"匿名用户连接文档 {document_id}，文档不存在，但允许连接保持")
                # 发送一个空的 init 消息，表示连接成功但文档不存在
                await websocket.send_json({
                    "type": "init",
                    "payload": {"html": ""},
                    "doc_id": document_id,
                    "user": "System",
                    "ts": datetime.utcnow().isoformat(),
                    "permissions": permission
                })
            else:
                logger.warning(f"无法加载文档 {document_id} 的内容，关闭连接")
                try:
                    await websocket.close(code=1008, reason="Document not found")
                except Exception:
                    pass
                # 如果连接已注册，需要清理
                try:
                    await manager.disconnect(document_id, websocket)
                except Exception:
                    pass
                return
            
    except Exception as e:
        logger.exception(f"获取文档内容时出错")
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except Exception:
            pass
        # 如果连接已注册，需要清理
        try:
            await manager.disconnect(document_id, websocket)
        except Exception:
            pass
        close_connection_safely(db)
        return

    # Send current online users to the newly connected client
    await websocket.send_json(
        {
            "type": "presence",
            "action": "init",
            "doc_id": document_id,
            "online_users": [user["username"] for user in manager.get_online_users(document_id)],
            "online_users_info": manager.get_online_users(document_id),
            "ts": datetime.utcnow().isoformat(),
        }
    )

    try:
        while True:
            try:
                message = await websocket.receive_json()
            except WebSocketDisconnect:
                break
            except RuntimeError as e:
                if "disconnect" in str(e).lower():
                    break
                logger.warning(f"接收WebSocket消息失败: {e}")
                break
            except Exception as e:
                logger.warning(f"接收WebSocket消息失败: {e}")
                break
                
            msg_type = message.get("type")
            payload = message.get("data") or message.get("payload")

            # 处理心跳响应
            if msg_type == "pong":
                await manager.handle_pong(websocket)
                continue

            # 健壮性检查：确保消息有type字段
            if not msg_type:
                logger.warning(f"收到无效消息（缺少type字段）: {message}")
                continue

            # 只处理已知消息类型
            if msg_type not in {"content_update", "cursor", "presence"}:
                logger.warning(f"收到未知消息类型: {msg_type}")
                continue

            # 健壮性检查：确保payload存在
            if payload is None:
                logger.warning(f"收到{msg_type}消息但缺少payload")
                continue

            try:
                # 对于content_update消息，需要先验证权限再广播
                if msg_type == "content_update" and isinstance(payload, dict) and "html" in payload:
                    try:
                        # 校验payload结构
                        html_content = payload.get("html")
                        if not isinstance(html_content, str):
                            logger.warning(f"无效的HTML内容类型: {type(html_content)}，断开连接")
                            break
                        
                        # 检查内容大小（2MB限制）
                        if len(html_content.encode('utf-8')) > 2 * 1024 * 1024:
                            logger.warning(f"HTML内容过大，拒绝保存: {len(html_content.encode('utf-8'))} bytes")
                            # 发送错误消息给客户端
                            error_message = {
                                "type": "error",
                                "payload": {"message": "内容过大，超过2MB限制"},
                                "doc_id": document_id,
                                "user": "System",
                                "ts": datetime.utcnow().isoformat(),
                            }
                            try:
                                await websocket.send_json(error_message)
                                logger.info("已发送内容过大错误消息")
                            except Exception as e:
                                logger.error(f"发送错误消息失败: {e}")
                            continue
                            
                        # 检查编辑权限（必须在广播之前检查）
                        permission = check_document_permission(db, document_id, user_id)
                        if not permission["can_edit"]:
                            logger.warning(f"用户{user_id}无编辑权限，拒绝content_update（角色: {'viewer' if not permission['can_edit'] else 'editor'}）")
                            # 发送权限错误消息，不广播，不落库
                            error_message = {
                                "type": "error",
                                "payload": {"message": "无编辑权限"},
                                "doc_id": document_id,
                                "user": "System",
                                "ts": datetime.utcnow().isoformat(),
                            }
                            try:
                                await websocket.send_json(error_message)
                            except Exception:
                                pass
                            continue  # 不广播，不落库
                        
                        # 权限验证通过，继续处理
                        # 更新文档内容到数据库（先持久化）
                        from app.schemas import DocumentUpdate
                        doc_update = DocumentUpdate(content=html_content)
                        
                        # 获取文档信息
                        doc_info = get_document_with_collaborators(db, document_id, user_id)
                        if not doc_info:
                            logger.warning(f"无法获取文档{document_id}信息")
                            continue
                            
                        # 使用实际操作者ID进行更新，而不是owner_id
                        # 修改update_document调用，传递user_id而不是owner_id
                        updated_doc = update_document(db, document_id, doc_update, user_id)
                        
                        if not updated_doc:
                            logger.warning(f"用户{user_id}更新文档{document_id}失败")
                            continue
                        
                        logger.info(f"文档{document_id}内容已保存（用户{user_id}）")
                        
                        # 持久化成功后，构建广播消息并广播
                        broadcast_message = {
                            "type": msg_type,
                            "doc_id": document_id,
                            "user": current_username,
                            "payload": payload,
                            "ts": datetime.utcnow().isoformat(),
                        }
                        await manager.broadcast(document_id, broadcast_message, sender=websocket)
                        
                    except Exception as e:
                        logger.exception(f"处理content_update消息失败")
                        continue
                else:
                    # 非content_update消息（如cursor、presence），直接广播
                    broadcast_message = {
                        "type": msg_type,
                        "doc_id": document_id,
                        "user": current_username,
                        "payload": payload,
                        "ts": datetime.utcnow().isoformat(),
                    }
                    await manager.broadcast(document_id, broadcast_message, sender=websocket)
                        
            except Exception as e:
                logger.error(f"处理{msg_type}消息时出错: {e}")
                # 继续处理其他消息，不中断连接
                
    except WebSocketDisconnect:
        logger.info(f"用户 {current_username} 正常断开连接")
    except Exception as e:
        logger.exception(f"WebSocket连接异常")
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except Exception:
            pass  # 连接可能已经关闭
    finally:
        # 确保连接被清理，避免CLOSE_WAIT堆积
        try:
            await manager.disconnect(document_id, websocket)
            logger.info(f"已清理用户 {current_username} 的连接")
        except Exception as e:
            logger.exception(f"清理连接时出错")


# 定期清理死连接的任务
async def cleanup_task():
    """定期清理死连接的后台任务"""
    while True:
        try:
            await manager.cleanup_dead_connections()
            await asyncio.sleep(30)  # 每30秒清理一次
        except Exception as e:
            logger.error(f"清理死连接任务出错: {e}")
            await asyncio.sleep(30)


async def heartbeat_task():
    """定期发送心跳的后台任务"""
    while True:
        try:
            await manager.send_heartbeat_to_all()
            await asyncio.sleep(25)  # 每25秒发送一次心跳（比清理间隔短）
        except Exception as e:
            logger.error(f"心跳任务出错: {e}")
            await asyncio.sleep(25)