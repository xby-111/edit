import asyncio
import json
import logging
from typing import Dict, List, Optional

from app.services.notification_ws_manager import notification_ws_manager

logger = logging.getLogger(__name__)


def _row_to_notification(row) -> Dict:
    return {
        "id": row[0],
        "user_id": row[1],
        "type": row[2],
        "title": row[3],
        "content": row[4],
        "payload": json.loads(row[5]) if row[5] else None,
        "is_read": row[6],
        "created_at": row[7],
        "updated_at": row[8] if len(row) > 8 else row[7],  # 兼容没有updated_at的情况
    }


def get_notification_settings(db, user_id: int) -> Dict:
    rows = db.query(
        """
        SELECT user_id, mute_all, mute_types, updated_at
        FROM notification_settings
        WHERE user_id = %s
        LIMIT 1
        """,
        (user_id,),
    )
    if not rows:
        return {"user_id": user_id, "mute_all": False, "mute_types": []}

    mute_types_raw = rows[0][2]
    try:
        mute_types = json.loads(mute_types_raw) if mute_types_raw else []
    except Exception:
        mute_types = []

    return {
        "user_id": rows[0][0],
        "mute_all": bool(rows[0][1]),
        "mute_types": mute_types or [],
        "updated_at": rows[0][3],
    }


def upsert_notification_settings(db, user_id: int, mute_all: bool, mute_types: Optional[List[str]] = None) -> Dict:
    mute_types = mute_types or []
    mute_types_str = json.dumps(mute_types)
    try:
        affected = db.execute(
            """
            UPDATE notification_settings
            SET mute_all = %s, mute_types = %s, updated_at = now()
            WHERE user_id = %s
            """,
            (mute_all, mute_types_str, user_id),
        )
        if affected is not None and affected == 0:
            raise RuntimeError("no rows updated")
    except Exception:
        # 如果没有受影响行，则尝试插入
        db.execute(
            """
            INSERT INTO notification_settings (user_id, mute_all, mute_types, updated_at)
            VALUES (%s, %s, %s, now())
            ON CONFLICT (user_id) DO NOTHING
            """,
            (user_id, mute_all, mute_types_str),
        )
    return get_notification_settings(db, user_id)


def _is_muted(db, user_id: int, notif_type: str) -> bool:
    try:
        settings = get_notification_settings(db, user_id)
    except Exception as e:
        logger.warning("读取通知设置失败，忽略静音: %s", e)
        return False

    if settings.get("mute_all"):
        return True

    mute_types = settings.get("mute_types") or []
    return notif_type in mute_types


def create_notification(
    db,
    user_id: int,
    type: str,
    title: str,
    content: Optional[str] = None,
    payload: Optional[dict] = None,
) -> Optional[Dict]:
    if _is_muted(db, user_id, type):
        return None
    payload_str = json.dumps(payload) if payload is not None else None
    # openGauss可能不支持RETURNING，使用INSERT后查询的方式
    db.execute(
        """
        INSERT INTO notifications (user_id, type, title, content, payload)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (user_id, type, title, content, payload_str),
    )
    
    # 查询刚插入的通知（按id DESC取最新一条，更精确）
    rows = db.query(
        """
        SELECT id, user_id, type, title, content, payload, is_read, created_at, COALESCE(updated_at, created_at) as updated_at
        FROM notifications
        WHERE user_id = %s
        ORDER BY id DESC
        LIMIT 1
        """,
        (user_id,),
    )
    notification = _row_to_notification(rows[0]) if rows else None

    if notification and user_id:
        # 异步推送通知到WebSocket
        # 尝试获取当前运行的事件循环
        try:
            loop = asyncio.get_running_loop()
            # 如果事件循环正在运行，创建任务
            loop.create_task(notification_ws_manager.async_send_notification(user_id, notification))
        except RuntimeError:
            # 如果没有运行的事件循环，尝试获取或创建
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(notification_ws_manager.async_send_notification(user_id, notification))
                else:
                    # 事件循环未运行，使用同步方法（不太可能，但保险）
                    notification_ws_manager.send_notification(user_id, notification)
            except Exception:
                # 最后fallback到同步方法
                try:
                    notification_ws_manager.send_notification(user_id, notification)
                except Exception as e:
                    logger.warning("推送通知到WebSocket失败: %s", e)
        except Exception as e:
            logger.warning("推送通知到WebSocket失败: %s", e)

    return notification


def list_notifications(
    db,
    user_id: int,
    notif_type: Optional[str] = None,
    unread: Optional[bool] = None,
    limit: int = 20,
    offset: int = 0,
) -> Dict:
    filters = ["user_id = %s"]
    params: List = [user_id]

    if notif_type:
        filters.append("type = %s")
        params.append(notif_type)

    if unread is not None:
        filters.append("is_read = %s")
        params.append(not unread)

    where_clause = " AND ".join(filters)
    count_rows = db.query(
        f"SELECT COUNT(*) FROM notifications WHERE {where_clause}",
        tuple(params),
    )
    total = count_rows[0][0] if count_rows else 0

    params_with_paging = params + [limit, offset]
    rows = db.query(
        f"""
        SELECT id, user_id, type, title, content, payload, is_read, created_at, COALESCE(updated_at, created_at) as updated_at
        FROM notifications
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
        """,
        tuple(params_with_paging),
    )

    page = offset // max(limit, 1) + 1
    return {
        "items": [_row_to_notification(row) for row in rows] if rows else [],
        "page": page,
        "page_size": limit,
        "total": total,
    }


def get_notification(db, notification_id: int, user_id: int) -> Optional[Dict]:
    rows = db.query(
        """
        SELECT id, user_id, type, title, content, payload, is_read, created_at, COALESCE(updated_at, created_at) as updated_at
        FROM notifications
        WHERE id = %s AND user_id = %s
        LIMIT 1
        """,
        (notification_id, user_id),
    )
    return _row_to_notification(rows[0]) if rows else None


def mark_notification_read(db, notification_id: int, user_id: int) -> Optional[Dict]:
    from datetime import datetime
    db.execute(
        """
        UPDATE notifications
        SET is_read = TRUE, updated_at = %s
        WHERE id = %s AND user_id = %s
        """,
        (datetime.utcnow(), notification_id, user_id),
    )
    return get_notification(db, notification_id, user_id)


def mark_notifications_read_batch(db, notification_ids: List[int], user_id: int) -> int:
    if not notification_ids:
        return 0

    placeholders = ",".join(["%s"] * len(notification_ids))
    params = [user_id] + notification_ids
    db.execute(
        f"""
        UPDATE notifications
        SET is_read = TRUE, updated_at = now()
        WHERE user_id = %s AND id IN ({placeholders})
        """,
        tuple(params),
    )
    return len(notification_ids)
