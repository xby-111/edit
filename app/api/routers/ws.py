from datetime import datetime
import asyncio
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, Depends
from jose import JWTError, jwt, ExpiredSignatureError
from app.db.session import get_db_connection, close_connection_safely
from app.services.websocket_service import ConnectionManager as ServiceConnectionManager

from app.core.config import settings

logger = logging.getLogger(__name__)

# 心跳配置常量
HEARTBEAT_INTERVAL = 25  # 秒，心跳发送间隔
HEARTBEAT_TIMEOUT = HEARTBEAT_INTERVAL * 3  # 75秒，超时时间为3倍心跳间隔

router = APIRouter()


@router.websocket(f"{settings.API_V1_STR}/ws/test")
async def test_websocket(websocket: WebSocket):
    """简单的测试WebSocket端点"""
    logger.info("测试WebSocket连接请求")
    await websocket.accept()
    logger.info("测试WebSocket连接已接受")
    await websocket.send_text("WebSocket连接成功")
    await websocket.close()


# 使用 service 层实现的 ConnectionManager（支持 CRDT、写后持久化）
manager = ServiceConnectionManager()


def decode_username_from_token(token: str) -> str:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise JWTError("Missing username")
        return username
    except JWTError as exc:  # pragma: no cover - simple guard
        raise exc


@router.websocket(f"{settings.API_V1_STR}/ws/documents/{{document_id}}")
async def document_collab_ws(
    websocket: WebSocket,
    document_id: int,
    token: str | None = Query(None),
):
    logger.info(f"WebSocket 连接请求: document_id={document_id}, token={'***' if token else 'None'}")
    
    # 先接受连接，再验证token（确保握手成功，失败时用code=1008关闭）
    await websocket.accept()
    logger.debug("WebSocket 连接已接受")
    
    if not token:
        logger.warning("WebSocket 连接未提供 token，拒绝访问")
        await websocket.close(code=1008, reason="Authentication required")
        return

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
    except Exception:
        logger.error("WebSocket JWT 验证出现未知错误")
        await websocket.close(code=1011, reason="Internal server error")
        return

    current_username = token_username
    
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
        
        # 先检查文档权限（在注册连接之前）
        from app.services.document_service import get_document_with_collaborators, check_document_permission
        permission = check_document_permission(db, document_id, user_id)
        
        if not permission["can_view"]:
            logger.warning(f"用户 {user_id} 无权限访问文档 {document_id}，关闭连接")
            try:
                await websocket.close(code=1008, reason="Access denied")
            except Exception:
                pass
            close_connection_safely(db)
            return
        
        # 权限验证通过，现在使用 service 层进行连接注册
        # 获取文档内容并用作初始化内容传给 service
        doc = get_document_with_collaborators(db, document_id, user_id)
        if not doc:
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

        initial_content = doc.get("content") if doc else ""
        await manager.connect(websocket, document_id, user_id, initial_content, username=token_username)

        # 发送初始化存在信息（在线用户与权限）
        await websocket.send_json({
            "type": "presence",
            "action": "init",
            "doc_id": document_id,
            "online_users": [u.get("user_id") for u in manager.get_online_users(document_id)],
            "online_users_info": manager.get_online_users(document_id),
            "ts": datetime.utcnow().isoformat(),
            "permissions": permission,
        })
            
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
            "online_users": [u.get("username", "") for u in manager.get_online_users(document_id)],
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

            # 已知消息类型白名单（包含 CRDT 增量同步）
            known_types = {"content_update", "content", "cursor", "selection", "presence", "crdt_ops"}
            if msg_type not in known_types:
                logger.warning(f"收到未知消息类型: {msg_type}")
                continue

            # payload 检查：cursor/selection 可能直接在 message 中，不强制要求 payload
            # crdt_ops 使用 ops 字段，也不需要 payload
            if msg_type in {"content_update", "content"} and payload is None:
                logger.warning(f"收到{msg_type}消息但缺少payload")
                continue

            try:
                # 对所有已知消息类型，委托给 service 层统一处理
                # 但对于会修改文档的消息（全文 content/content_update 或增量 crdt_ops），先做权限和大小校验
                edit_types = {"content_update", "content", "crdt_ops"}
                if msg_type in edit_types:
                    # 简单大小检测（仅对 content_update 的 html 字段）
                    if msg_type == "content_update" and isinstance(payload, dict) and "html" in payload:
                        html_content = payload.get("html")
                        if not isinstance(html_content, str):
                            logger.warning(f"无效的HTML内容类型: {type(html_content)}，断开连接")
                            break
                        if len(html_content.encode('utf-8')) > 2 * 1024 * 1024:
                            error_message = {"type": "error", "payload": {"message": "内容过大，超过2MB限制"}, "doc_id": document_id, "user": "System"}
                            try:
                                await websocket.send_json(error_message)
                            except Exception:
                                pass
                            continue

                    # 权限检查
                    permission = check_document_permission(db, document_id, user_id)
                    if not permission.get("can_edit"):
                        try:
                            await websocket.send_json({"type": "error", "payload": {"message": "无编辑权限"}})
                        except Exception:
                            pass
                        continue

                # 委托给 service 层来处理（CRDT、广播、标记脏数据等）
                logger.info(f"处理消息: type={msg_type}, user_id={user_id}, doc_id={document_id}")
                await manager.handle_message(document_id, user_id, message, websocket, db)
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
            await asyncio.sleep(HEARTBEAT_INTERVAL)  # 每25秒发送一次心跳
        except Exception as e:
            logger.error(f"心跳任务出错: {e}")
            await asyncio.sleep(HEARTBEAT_INTERVAL)