from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class CommentBase(BaseModel):
    content: str
    anchor_json: Optional[str] = None
    parent_id: Optional[int] = None
    mentions: Optional[str] = None


class CommentCreate(CommentBase):
    line_no: Optional[int] = None
    anchor: Optional[str] = None


class Comment(CommentBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
