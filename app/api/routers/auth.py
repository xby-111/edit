from fastapi import APIRouter, Depends, HTTPException, Request, status
from typing import List
from app.core.security import create_access_token, verify_password, get_password_hash, get_current_user
from app.db.session import get_db
from app.schemas import UserCreate, User as UserSchema, Token, PasswordForgotRequest, PasswordResetRequest
from app.services.user_service import (
    get_user_by_username,
    get_user_by_email,
    get_user_by_phone,
    create_user,
    generate_password_reset_token,
    get_password_reset_token,
    mark_password_reset_used,
    update_user_password,
)
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
from app.core.config import settings
import logging
from app.services.audit_service import log_action, log_user_event
from datetime import datetime

def _escape(value: str) -> str:
    """SQL字符串字面量转义"""
    if value is None:
        return "NULL"
    escaped_value = value.replace("'", "''")
    return f"'{escaped_value}'"

logger = logging.getLogger(__name__)

router = APIRouter(tags=["认证与登录"])

@router.post("/register", response_model=UserSchema, summary="用户注册", description="创建新用户账户")
def register(user: UserCreate, db = Depends(get_db), request: Request = None):
    # Check if user already exists
    db_user = get_user_by_username(db, username=user.username)
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已被注册"
        )
    
    db_user = get_user_by_email(db, email=user.email) if user.email else None
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

        try:
            log_action(
                db,
                user_id=db_user.get("id"),
                action="auth.register",
                resource_type="user",
                resource_id=db_user.get("id"),
                request=request,
            )
        except Exception:
            pass

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
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db = Depends(get_db), request: Request = None):
    identifier = form_data.username
    rows = db.query(
        """
        SELECT id, username, hashed_password
        FROM users
        WHERE username = %s OR email = %s OR phone = %s
        LIMIT 1
        """,
        (identifier, identifier, identifier),
    )

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="账号或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = rows[0]  # py-opengauss 返回的是列表，取第一行

    # 验证密码
    if not verify_password(form_data.password, result[2]):  # result[2] is hashed_password
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="账号或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = {'id': result[0], 'username': result[1], 'hashed_password': result[2]}
    
    # 生成访问令牌
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user['username']}, expires_delta=access_token_expires
    )
    try:
        log_action(
            db,
            user_id=user.get("id"),
            action="auth.login",
            resource_type=None,
            resource_id=None,
            request=request,
        )
        log_user_event(db, user_id=user.get("id"), event_type="login", document_id=None, meta=None)
    except Exception:
        pass

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


@router.post("/password/forgot", summary="请求重置密码")
def forgot_password(body: PasswordForgotRequest, db=Depends(get_db)):
    identifier = body.identifier
    user = get_user_by_email(db, identifier) if identifier else None
    if not user:
        user = get_user_by_username(db, identifier) if identifier else None
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    try:
        token = generate_password_reset_token(db, user_id=user["id"])
        return {"message": "重置链接已发送（模拟）", "token": token}
    except Exception as e:
        logger.error("生成重置令牌失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="无法生成重置令牌")


@router.post("/password/reset", summary="重置密码")
def reset_password(body: PasswordResetRequest, db=Depends(get_db), request: Request = None):
    record = get_password_reset_token(db, body.token)
    if not record:
        raise HTTPException(status_code=400, detail="无效的重置令牌")

    expires_at = record.get("expires_at")
    used_at = record.get("used_at")
    if used_at:
        raise HTTPException(status_code=400, detail="令牌已使用")
    if expires_at and isinstance(expires_at, datetime) and expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="令牌已过期")

    try:
        update_user_password(db, record["user_id"], body.new_password)
        mark_password_reset_used(db, body.token)
        try:
            log_action(
                db,
                user_id=record.get("user_id"),
                action="auth.password.reset",
                resource_type="user",
                resource_id=record.get("user_id"),
                request=request,
                meta={"token_id": record.get("id")},
            )
        except Exception:
            pass
        return {"message": "密码已重置"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("重置密码失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="重置失败")