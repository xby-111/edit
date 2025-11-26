from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class Notification(BaseModel):
    id: int
    user_id: int
    type: str
    title: str
    content: Optional[str] = None
    payload: Optional[dict] = None
    is_read: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class NotificationListResponse(BaseModel):
    items: List[Notification] = Field(default_factory=list)
    page: int = 1
    page_size: int = 20
    total: int = 0


class NotificationReadBatchRequest(BaseModel):
    ids: List[int] = Field(default_factory=list)
