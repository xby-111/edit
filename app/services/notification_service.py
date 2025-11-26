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
    }


def create_notification(
    db,
    user_id: int,
    type: str,
    title: str,
    content: Optional[str] = None,
    payload: Optional[dict] = None,
) -> Optional[Dict]:
    payload_str = json.dumps(payload) if payload is not None else None
    rows = db.query(
        """
        INSERT INTO notifications (user_id, type, title, content, payload)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id, user_id, type, title, content, payload, is_read, created_at
        """,
        (user_id, type, title, content, payload_str),
    )
    notification = _row_to_notification(rows[0]) if rows else None

    if notification and user_id:
        try:
            notification_ws_manager.send_notification(user_id, notification)
        except RuntimeError:
            loop = asyncio.get_event_loop()
            loop.create_task(notification_ws_manager.async_send_notification(user_id, notification))
        except Exception as e:  # pragma: no cover - best effort logging
            logger.warning("推送通知到WebSocket失败: %s", e)

    return notification


def list_notifications(
    db,
    user_id: int,
    notif_type: Optional[str] = None,
    unread: Optional[bool] = None,
    page: int = 1,
    page_size: int = 20,
) -> Dict:
    filters = ["user_id = %s"]
    params: List = [user_id]

    if notif_type:
        filters.append("type = %s")
        params.append(notif_type)

    if unread is not None:
        filters.append("is_read = %s")
        params.append(unread)

    where_clause = " AND ".join(filters)
    count_rows = db.query(
        f"SELECT COUNT(*) FROM notifications WHERE {where_clause}",
        tuple(params),
    )
    total = count_rows[0][0] if count_rows else 0

    offset = (page - 1) * page_size
    params_with_paging = params + [page_size, offset]
    rows = db.query(
        f"""
        SELECT id, user_id, type, title, content, payload, is_read, created_at
        FROM notifications
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
        """,
        tuple(params_with_paging),
    )

    return {
        "items": [_row_to_notification(row) for row in rows] if rows else [],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


def get_notification(db, notification_id: int, user_id: int) -> Optional[Dict]:
    rows = db.query(
        """
        SELECT id, user_id, type, title, content, payload, is_read, created_at
        FROM notifications
        WHERE id = %s AND user_id = %s
        LIMIT 1
        """,
        (notification_id, user_id),
    )
    return _row_to_notification(rows[0]) if rows else None


def mark_notification_read(db, notification_id: int, user_id: int) -> Optional[Dict]:
    db.execute(
        """
        UPDATE notifications
        SET is_read = TRUE
        WHERE id = %s AND user_id = %s
        """,
        (notification_id, user_id),
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
        SET is_read = TRUE
        WHERE user_id = %s AND id IN ({placeholders})
        """,
        tuple(params),
    )
    return len(notification_ids)
