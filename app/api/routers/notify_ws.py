import logging
from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt, ExpiredSignatureError

from app.core.config import settings
from app.db.session import close_connection_safely, get_db_connection
from app.services.notification_service import list_notifications
from app.services.notification_ws_manager import notification_ws_manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket(f"{settings.API_V1_STR}/ws/notifications")
async def notifications_ws(websocket: WebSocket, token: Optional[str] = Query(None)):
    await websocket.accept()
    user_id = 0
    username = None

    if token:
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            username = payload.get("sub")
            if not username:
                await websocket.close(code=1008, reason="Invalid token: missing username")
                return
        except ExpiredSignatureError:
            await websocket.close(code=1008, reason="Token expired")
            return
        except JWTError:
            await websocket.close(code=1008, reason="Invalid token")
            return
        db = None
        try:
            db = get_db_connection()
            rows = db.query("SELECT id FROM users WHERE username = %s LIMIT 1", (username,))
            if not rows:
                close_connection_safely(db)
                await websocket.close(code=1008, reason="User not found")
                return
            user_id = rows[0][0]
        except Exception as e:
            logger.error("通知WS获取用户失败: %s", e)
            await websocket.close(code=1011, reason="Internal server error")
            return
        finally:
            try:
                close_connection_safely(db)
            except Exception:
                pass

    await notification_ws_manager.connect(user_id, websocket)

    if user_id:
        try:
            db_conn = get_db_connection()
            initial = list_notifications(db_conn, user_id, None, None, 1, 20)
            close_connection_safely(db_conn)
            await websocket.send_json({"type": "init", "data": initial.get("items", [])})
        except Exception as e:
            logger.warning("初始化通知列表失败: %s", e)

    try:
        while True:
            try:
                message = await websocket.receive_text()
            except WebSocketDisconnect:
                break
            except RuntimeError as e:
                if "disconnect" in str(e).lower():
                    break
                logger.warning("通知WS接收消息失败: %s", e)
                break
            except Exception as e:
                logger.warning("通知WS接收消息失败: %s", e)
                break

            if message.strip().lower() == "ping":
                try:
                    await websocket.send_text("pong")
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    finally:
        try:
            await notification_ws_manager.disconnect(user_id, websocket)
        except Exception as e:
            logger.debug("通知WS断开清理失败: %s", e)
