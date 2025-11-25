from datetime import datetime
from typing import Dict, List, Set

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from jose import JWTError, jwt, ExpiredSignatureError, JWSError
from app.db.session import get_db
from app.services.document_service import get_document, update_document

from app.core.config import settings

router = APIRouter()


class ConnectionManager:
    def __init__(self) -> None:
        self.rooms: Dict[int, Set[WebSocket]] = {}
        self.usernames: Dict[WebSocket, str] = {}
        self.user_ids: Dict[WebSocket, int] = {}  # 存储用户ID
        self.connection_times: Dict[WebSocket, datetime] = {}  # 连接时间

    async def connect(self, document_id: int, websocket: WebSocket, username: str, user_id: int) -> None:
        # WebSocket 已在 endpoint 中接受，这里不再接受
        if document_id not in self.rooms:
            self.rooms[document_id] = set()
        self.rooms[document_id].add(websocket)
        self.usernames[websocket] = username
        self.user_ids[websocket] = user_id
        self.connection_times[websocket] = datetime.utcnow()
        
        print(f"用户 {username}({user_id}) 连接到文档 {document_id}")
        
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
            
            print(f"用户 {username}({user_id}) 断开与文档 {document_id} 的连接")
            
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
                print(f"发现死连接，移除: {e}")
                dead_connections.append(connection)
            except Exception as e:
                # Any other exception also indicates a dead connection
                print(f"发送消息时出现异常，移除连接: {e}")
                dead_connections.append(connection)
        
        # Remove dead connections
        for connection in dead_connections:
            self.rooms[document_id].discard(connection)
            username = self.usernames.pop(connection, "未知用户")
            user_id = self.user_ids.pop(connection, None)
            self.connection_times.pop(connection, None)
            print(f"已清理死连接: {username}({user_id})")
        
        # Clean up empty room
        if not self.rooms[document_id]:
            self.rooms.pop(document_id, None)
        
        print(f"广播完成，活跃连接数: {active_connections}")

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
        """清理死连接"""
        rooms_to_check = [document_id] if document_id else list(self.rooms.keys())
        
        for doc_id in rooms_to_check:
            if doc_id not in self.rooms:
                continue
                
            dead_connections = []
            for connection in self.rooms[doc_id]:
                try:
                    # 发送心跳测试连接
                    await connection.ping()
                except Exception:
                    dead_connections.append(connection)
            
            # 清理死连接
            for connection in dead_connections:
                await self.disconnect(doc_id, connection)


@router.websocket("/ws/test")
async def test_websocket(websocket: WebSocket):
    """简单的测试WebSocket端点"""
    print("测试WebSocket连接请求")
    await websocket.accept()
    print("测试WebSocket连接已接受")
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
    token: str = Query(...),
    username: str | None = Query(None)
):
    print(f"WebSocket 连接请求: document_id={document_id}, token={token[:20]}...")
    
    # 先接受连接，避免 403 错误
    await websocket.accept()
    print("WebSocket 连接已接受")
    
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        token_username = payload.get("sub")
        if not token_username:
            await websocket.close(code=1008, reason="Invalid token: missing username")
            return
        print(f"JWT 验证成功，用户: {token_username}")
    except ExpiredSignatureError:
        print("WebSocket JWT 验证失败: Token expired")
        await websocket.close(code=1008, reason="Token expired")
        return
    except JWTError as e:
        # 细分JWT错误类型
        error_msg = str(e)
        if "Invalid crypto padding" in error_msg or "Invalid base64-encoded string" in error_msg:
            print("WebSocket JWT 验证失败: Invalid token format")
            await websocket.close(code=1008, reason="Invalid token format")
        else:
            print(f"WebSocket JWT 验证失败: {e}")
            await websocket.close(code=1008, reason="Invalid token")
        return
    except Exception as e:
        print(f"WebSocket JWT 验证出现未知错误: {e}")
        await websocket.close(code=1011, reason="Internal server error")
        return

    current_username = token_username or username or "匿名用户"
    await manager.connect(document_id, websocket, current_username, user_id)

    # 获取文档内容并发送初始快照
    # sub字段存储的是username，需要查询获取user_id
    token_username = payload.get("sub")
    
    # 获取数据库连接
    from app.db.session import get_db_connection
    db = get_db_connection()
    
    # 从数据库查询用户ID
    try:
        from app.services.user_service import get_user_by_username, _escape
        username_safe = _escape(token_username)
        user_rows = db.query(f"SELECT id FROM users WHERE username = {username_safe} LIMIT 1")
        
        if not user_rows:
            print(f"用户不存在: {token_username}")
            await websocket.close(code=1008, reason="User not found")
            return
            
        user_id = user_rows[0][0]  # 获取用户ID
        
        # 检查文档权限
        from app.services.document_service import get_document_with_collaborators, check_document_permission
        permission = check_document_permission(db, document_id, user_id)
        
        if not permission["can_view"]:
            print(f"用户 {user_id} 无权限访问文档 {document_id}")
            await websocket.close(code=1008, reason="Access denied")
            return
        
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
            print(f"无法加载文档 {document_id} 的内容")
            await websocket.close(code=1008, reason="Document not found")
            return
            
    except Exception as e:
        print(f"获取文档内容时出错: {e}")
        await websocket.close(code=1011, reason="Internal server error")
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
                print(f"接收WebSocket消息失败: {e}")
                break
            except Exception as e:
                print(f"接收WebSocket消息失败: {e}")
                break
                
            msg_type = message.get("type")
            payload = message.get("data") or message.get("payload")

            # 健壮性检查：确保消息有type字段
            if not msg_type:
                print(f"收到无效消息（缺少type字段）: {message}")
                continue

            # 只处理已知消息类型
            if msg_type not in {"content_update", "cursor", "presence"}:
                print(f"收到未知消息类型: {msg_type}")
                continue

            # 健壮性检查：确保payload存在
            if payload is None:
                print(f"收到{msg_type}消息但缺少payload")
                continue

            try:
                # 构建广播消息
                broadcast_message = {
                    "type": msg_type,
                    "doc_id": document_id,
                    "user": current_username,
                    "payload": payload,
                    "ts": datetime.utcnow().isoformat(),
                }
                
                # 广播更新
                await manager.broadcast(document_id, broadcast_message, sender=websocket)
                
                # 持久化到数据库（仅content_update）
                if msg_type == "content_update" and isinstance(payload, dict) and "html" in payload:
                    try:
                        # 校验payload结构
                        html_content = payload.get("html")
                        if not isinstance(html_content, str):
                            print(f"无效的HTML内容类型: {type(html_content)}，断开连接")
                            break
                        
                        # 检查内容大小（2MB限制）
                        if len(html_content.encode('utf-8')) > 2 * 1024 * 1024:
                            print(f"HTML内容过大，拒绝保存: {len(html_content.encode('utf-8'))} bytes")
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
                                print("已发送内容过大错误消息")
                            except Exception as e:
                                print(f"发送错误消息失败: {e}")
                            continue
                            
                        # 检查编辑权限
                        permission = check_document_permission(db, document_id, user_id)
                        if not permission["can_edit"]:
                            print(f"用户{user_id}无编辑权限（角色: {'viewer' if not permission['can_edit'] else 'editor'}）")
                            # 发送权限错误消息
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
                            continue
                        
                        # 获取文档信息，使用所有者权限进行更新
                        from app.schemas import DocumentUpdate
                        doc_update = DocumentUpdate(content=html_content)
                        
                        # 获取文档的owner_id
                        doc_info_rows = db.query(f"SELECT owner_id FROM documents WHERE id = {document_id}")
                        if not doc_info_rows:
                            print(f"无法获取文档{document_id}信息")
                            continue
                            
                        owner_id = doc_info_rows[0][0]
                        updated_doc = update_document(db, document_id, doc_update, owner_id)
                        
                        if updated_doc:
                            print(f"文档{document_id}内容已保存")
                        else:
                            print(f"用户{user_id}无权更新文档{document_id}")
                            continue
                    except Exception as e:
                        print(f"保存文档内容失败: {e}")
                        continue
                        
            except Exception as e:
                print(f"处理{msg_type}消息时出错: {e}")
                # 继续处理其他消息，不中断连接
                
    except WebSocketDisconnect:
        print(f"用户 {current_username} 正常断开连接")
    except Exception as e:
        print(f"WebSocket连接异常: {e}")
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except Exception:
            pass  # 连接可能已经关闭
    finally:
        await manager.disconnect(document_id, websocket)
