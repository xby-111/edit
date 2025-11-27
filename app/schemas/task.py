from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from pydantic import BaseModel
class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    status: str = "pending"
    priority: str = "medium"
    assigned_to: Optional[int] = None


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    assigned_to: Optional[int] = None


class Task(TaskBase):
    id: int
    created_by: int
    creator_id: Optional[int] = None  # 保留 creator_id 以兼容现有代码
    created_at: datetime
    updated_at: datetime
    assigned_to: Optional[int] = None  # 确保与数据库字段 assignee_id 对应

    class Config:
        from_attributes = True
