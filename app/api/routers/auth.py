from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from app.core.security import create_access_token, verify_password, get_password_hash, get_current_user
from app.db.session import get_db
from app.schemas import UserCreate, User as UserSchema, Token
from app.services.user_service import get_user_by_username, get_user_by_email, get_user_by_phone, create_user
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["认证与登录"])

@router.post("/register", response_model=UserSchema, summary="用户注册", description="创建新用户账户")
def register(user: UserCreate, db = Depends(get_db)):
    # Check if user already exists
    db_user = get_user_by_username(db, username=user.username)
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已被注册"
        )
    
    db_user = get_user_by_email(db, email=user.email)
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="邮箱已被注册"
        )
    
    # 检查手机号唯一性（如果提供了手机号）
    if hasattr(user, 'phone') and user.phone:
        db_user = get_user_by_phone(db, phone=user.phone)
        if db_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="手机号已被注册"
            )
    
    # Create new user
    try:
        db_user = create_user(db, user=user)
        if not db_user:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="注册失败，无法创建用户"
            )
        
        return UserSchema(
            id=db_user['id'],
            username=db_user['username'],
            email=db_user['email'],
            phone=db_user.get('phone'),
            is_active=db_user['is_active'],
            role=db_user['role'],
            created_at=db_user['created_at'],
            updated_at=db_user.get('updated_at')
        )
    except HTTPException:
        # 重新抛出 HTTP 异常
        raise
    except Exception as e:
        logger.error(f"用户注册失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="注册失败，请稍后重试"
        )

@router.post("/token", response_model=Token, summary="用户登录", description="验证用户身份并返回访问令牌")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db = Depends(get_db)):
    # 使用 user_service 中的函数获取用户信息，适配 py-opengauss API
    rows = db.query("SELECT id, username, hashed_password FROM users WHERE username = %s LIMIT 1", (form_data.username,))
    
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 获取用户信息
    result = rows[0]  # py-opengauss 返回的是列表，取第一个元素
    
    # 验证密码
    if not verify_password(form_data.password, result[2]):  # result[2] is hashed_password
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = {'id': result[0], 'username': result[1], 'hashed_password': result[2]}
    
    # 生成访问令牌
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user['username']}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=UserSchema, summary="获取当前用户信息", description="获取当前登录用户的详细信息")
async def read_users_me(current_user: UserSchema = Depends(get_current_user)):
    # Return JSON serialized user info, avoiding sensitive info disclosure
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "is_active": current_user.is_active
    }