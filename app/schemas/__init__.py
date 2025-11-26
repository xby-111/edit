from pydantic import BaseModel, field_validator, model_validator
from datetime import datetime
from typing import Optional, List, Literal
from pydantic import EmailStr

# User schemas
class UserBase(BaseModel):
    username: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = True
    role: Literal['admin', 'user'] | None = "user"

class UserCreate(UserBase):
    password: str
    
    @model_validator(mode='after')
    def validate_email_or_phone(self):
        """验证邮箱或手机号至少提供一个"""
        if not self.email and not self.phone:
            raise ValueError("邮箱或手机号至少需要提供一个")
        return self

class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None
    role: Literal['admin', 'user'] | None = None
    full_name: Optional[str] = None
    bio: Optional[str] = None
    address: Optional[str] = None
    avatar_url: Optional[str] = None

class User(UserBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    full_name: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None

    class Config:
        from_attributes = True

# Auth schemas
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    username: Optional[str] = None

# Document schemas
class DocumentBase(BaseModel):
    title: str
    content: Optional[str] = ""
    status: Literal['active', 'archived', 'draft', 'deleted'] | None = "active"
    folder_name: Optional[str] = None
    tags: Optional[str] = None

class DocumentCreate(DocumentBase):
    pass

class DocumentUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    status: Optional[str] = None
    folder_name: Optional[str] = None
    tags: Optional[str] = None

class Document(DocumentBase):
    id: int
    owner_id: Optional[int] = None
    is_locked: Optional[bool] = False
    locked_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

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

class DocumentVersion(DocumentVersionBase):
    id: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# Template schemas
class TemplateBase(BaseModel):
    name: str
    description: Optional[str] = None
    content: str
    category: Optional[str] = "general"
    is_active: Optional[bool] = True

class TemplateCreate(TemplateBase):
    pass

class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    is_active: Optional[bool] = None

class Template(TemplateBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
