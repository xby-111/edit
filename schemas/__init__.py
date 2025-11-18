from pydantic import BaseModel
from datetime import datetime
from typing import Optional

# User schemas
class UserBase(BaseModel):
    username: str
    email: str
    is_active: Optional[bool] = True
    role: Optional[str] = "viewer"

class UserCreate(UserBase):
    password: str

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