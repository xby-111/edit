from fastapi import FastAPI, WebSocket, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from passlib.context import CryptContext
import json
from datetime import datetime, timedelta
from jose import JWTError, jwt
from typing import Optional
import os

from models import Base, User, Document, DocumentVersion, get_db

# 密码哈希配置
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT配置
# 从环境变量读取配置，如果没有则使用默认值
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

app = FastAPI()


templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

active_users = []

# 用户认证相关函数
# 使用恒定时间比较防止时间攻击
def verify_password(plain_password: str, hashed_password: str):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    return user


@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# 用户认证路由
@app.post("/register")
async def register(username: str, email: str, password: str, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.username == username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    user = User.create_user(username=username, email=email, password=password)
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "username": user.username}

@app.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/me")
async def read_users_me(current_user: User = Depends(get_current_user)):
    # 返回JSON序列化的用户信息，避免敏感信息泄露
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "is_active": current_user.is_active
    }



@app.websocket("/ws/documents/{doc_id}")
async def websocket_document_endpoint(doc_id: int, ws: WebSocket, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    await ws.accept()
    active_users.append(ws)

    try:
        while True:
            data = await ws.receive_json()

            # 消息格式处理
            if data["type"] == "content":
                for user in active_users:
                    if user != ws:
                        await user.send_json({
                            "type": "content",
                            "user_id": current_user.id,
                            "content": data["content"]
                        })

            elif data["type"] == "cursor":
                for user in active_users:
                    if user != ws:
                        await user.send_json({
                            "type": "cursor",
                            "user_id": current_user.id,
                            "cursor": data["cursor"]
                        })

    except:
        active_users.remove(ws)

@app.get("/documents")
async def get_documents(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    documents = db.query(Document).filter(Document.owner_id == current_user.id).all()
    return [{
        "id": doc.id,
        "title": doc.title,
        "status": doc.status,
        "created_at": doc.created_at,
        "updated_at": doc.updated_at
    } for doc in documents]

@app.post("/documents")
async def create_document(title: str, content: str = "", current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    new_document = Document(
        title=title,
        content=content,
        owner_id=current_user.id
    )
    db.add(new_document)
    db.commit()
    db.refresh(new_document)
    return {
        "id": new_document.id,
        "title": new_document.title,
        "status": new_document.status,
        "created_at": new_document.created_at,
        "updated_at": new_document.updated_at
    }

@app.get("/documents/{doc_id}")
async def get_document(doc_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    document = db.query(Document).filter(Document.id == doc_id, Document.owner_id == current_user.id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return {
        "id": document.id,
        "title": document.title,
        "content": document.content,
        "status": document.status,
        "created_at": document.created_at,
        "updated_at": document.updated_at
    }

@app.get("/documents/{doc_id}/versions")
async def get_document_versions(doc_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    document_versions = db.query(DocumentVersion).filter(DocumentVersion.document_id == doc_id).all()
    return [{
        "id": version.id,
        "version_number": version.version_number,
        "user_id": version.user_id,
        "summary": version.summary,
        "created_at": version.created_at
    } for version in document_versions]

@app.post("/documents/{doc_id}/versions")
async def create_document_version(doc_id: int, content: str, summary: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    document = db.query(Document).filter(Document.id == doc_id, Document.owner_id == current_user.id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    new_version = DocumentVersion(
        document_id=doc_id,
        user_id=current_user.id,
        version_number=len(document.versions) + 1,
        content_snapshot=content,
        summary=summary
    )
    db.add(new_version)
    db.commit()
    db.refresh(new_version)
    return {
        "id": new_version.id,
        "version_number": new_version.version_number,
        "summary": new_version.summary,
        "created_at": new_version.created_at
    }
