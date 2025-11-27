import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.config import settings
from app.core.security import get_current_user
from app.db.session import get_db
from app.schemas.notification import (
    Notification,
    NotificationListResponse,
    NotificationReadBatchRequest,
    NotificationSettings,
    NotificationSettingsUpdate,
)
from app.services.notification_service import (
    list_notifications,
    mark_notification_read,
    mark_notifications_read_batch,
    get_notification_settings,
    upsert_notification_settings,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix=settings.API_V1_STR, tags=["通知"])


@router.get("/notifications", response_model=NotificationListResponse)
async def get_notifications(
    notif_type: Optional[str] = Query(None, alias="type"),  # 支持type和notif_type两种参数名
    unread: Optional[bool] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        return list_notifications(db, current_user.id, notif_type, unread, limit, offset)
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


@router.get("/notifications/settings", response_model=NotificationSettings)
async def get_settings(db=Depends(get_db), current_user=Depends(get_current_user)):
    try:
        return get_notification_settings(db, current_user.id)
    except Exception as e:
        logger.error("获取通知设置失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="获取通知设置失败")


@router.put("/notifications/settings", response_model=NotificationSettings)
async def update_settings(
    payload: NotificationSettingsUpdate,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        mute_all = payload.mute_all if payload.mute_all is not None else False
        mute_types = payload.mute_types if payload.mute_types is not None else []
        if not isinstance(mute_types, list):
            raise HTTPException(status_code=400, detail="mute_types 必须是字符串数组")
        for t in mute_types:
            if not isinstance(t, str):
                raise HTTPException(status_code=400, detail="mute_types 必须是字符串数组")
        return upsert_notification_settings(db, current_user.id, mute_all, mute_types)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("更新通知设置失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="更新通知设置失败")
