from pydantic import BaseModel, field_validator, model_validator
from datetime import datetime
from typing import Optional

# User schemas
class UserBase(BaseModel):
    username: str
    email: Optional[str] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = True
    role: Optional[str] = "viewer"


class UserCreate(BaseModel):
    username: str
    email: Optional[str] = None
    phone: Optional[str] = None
    password: str
    is_active: Optional[bool] = True
    role: Optional[str] = "viewer"

    @model_validator(mode='after')
    def validate_email_or_phone(self):
        """验证邮箱或手机号至少提供一个"""
        if not self.email and not self.phone:
            raise ValueError("邮箱或手机号至少需要提供一个")
        return self


class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    is_active: Optional[bool] = None
    role: Optional[str] = None


class UserInDB(UserBase):
    id: int
    hashed_password: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class User(UserBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserLogin(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None


# Document schemas
class DocumentBase(BaseModel):
    title: str
    content: Optional[str] = ""
    status: Optional[str] = "active"


class DocumentCreate(DocumentBase):
    pass


class DocumentUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    status: Optional[str] = None


class DocumentInDB(DocumentBase):
    id: int
    owner_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class Document(DocumentBase):
    id: int
    owner_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# DocumentVersion schemas
class DocumentVersionBase(BaseModel):
    document_id: int
    user_id: int
    version_number: int
    content_snapshot: str
    summary: Optional[str] = None


class DocumentVersionCreate(DocumentVersionBase):
    pass


class DocumentVersionUpdate(BaseModel):
    summary: Optional[str] = None


class DocumentVersionInDB(DocumentVersionBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class DocumentVersion(DocumentVersionBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# Comment schemas
class CommentBase(BaseModel):
    content: str
    range_start: Optional[int] = None
    range_end: Optional[int] = None
    parent_id: Optional[int] = None
    mentions: Optional[str] = None


class CommentCreate(CommentBase):
    pass


class Comment(CommentBase):
    id: int
    document_id: int
    user_id: int
    created_at: datetime


# Task schemas
class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    assignee_id: Optional[int] = None
    due_at: Optional[str] = None
    status: Optional[str] = None


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    status: Optional[str] = None
    due_at: Optional[str] = None
    assignee_id: Optional[int] = None


class Task(TaskBase):
    id: int
    document_id: int
    creator_id: int
    created_at: datetime
    updated_at: datetime
