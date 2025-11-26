import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.config import settings
from app.core.security import get_current_user
from app.db.session import get_db
from app.schemas.notification import Notification, NotificationListResponse, NotificationReadBatchRequest
from app.services.notification_service import (
    list_notifications,
    mark_notification_read,
    mark_notifications_read_batch,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix=settings.API_V1_STR, tags=["通知"])


@router.get("/notifications", response_model=NotificationListResponse)
async def get_notifications(
    notif_type: Optional[str] = Query(None, alias="type"),  # 支持type和notif_type两种参数名
    unread: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        return list_notifications(db, current_user.id, notif_type, unread, page, page_size)
    except Exception as e:
        logger.error("查询通知失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="查询通知失败")


@router.patch("/notifications/{notification_id}/read", response_model=Notification)
async def mark_read(
    notification_id: int,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    notification = mark_notification_read(db, notification_id, current_user.id)
    if not notification:
        raise HTTPException(status_code=404, detail="通知不存在")
    return notification


@router.post("/notifications/read_batch")
async def read_batch(
    payload: NotificationReadBatchRequest,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        updated = mark_notifications_read_batch(db, payload.ids, current_user.id)
        return {"updated": updated}
    except Exception as e:
        logger.error("批量标记通知失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="批量标记通知失败")
