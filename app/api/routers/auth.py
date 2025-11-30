from fastapi import APIRouter, Depends, HTTPException, Request, status
from typing import List, Optional
from pydantic import BaseModel, EmailStr, field_validator
from app.core.security import create_access_token, verify_password, get_password_hash, get_current_user
from app.db.session import get_db
from app.schemas import UserCreate, User as UserSchema, Token
from app.services.user_service import get_user_by_username, get_user_by_email, get_user_by_phone, create_user
from app.services.verification_service import (
    create_verification_code,
    verify_code,
    send_email_code,
    send_sms_code,
    CODE_TYPE_PASSWORD_RESET,
    CODE_TYPE_LOGIN,
)
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
from app.core.config import settings
import logging
import re
from app.services.audit_service import log_action

def _escape(value: str) -> str:
    """SQL字符串字面量转义"""
    if value is None:
        return "NULL"
    escaped_value = value.replace("'", "''")
    return f"'{escaped_value}'"

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
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db = Depends(get_db), request: Request = None):
    # 使用参数化查询，兼容层会处理占位符转换
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
    try:
        log_action(
            db,
            user_id=user.get("id"),
            action="auth.login",
            resource_type=None,
            resource_id=None,
            request=request,
        )
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


# ==================== 密码重置相关接口 ====================

class PasswordResetRequest(BaseModel):
    """密码重置请求 - 发送验证码"""
    email: Optional[EmailStr] = None
    phone: Optional[str] = None

    @field_validator('phone')
    @classmethod
    def validate_phone(cls, v):
        if v and not re.match(r'^1[3-9]\d{9}$', v):
            raise ValueError('手机号格式不正确')
        return v


class PasswordResetVerify(BaseModel):
    """密码重置验证 - 验证验证码并重置密码"""
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    code: str
    new_password: str

    @field_validator('new_password')
    @classmethod
    def validate_password(cls, v):
        if len(v) < 6:
            raise ValueError('密码长度至少6位')
        return v


@router.post("/password-reset/request", summary="请求密码重置", description="发送密码重置验证码到邮箱或手机")
async def request_password_reset(data: PasswordResetRequest, db=Depends(get_db)):
    """
    发送密码重置验证码
    - 必须提供邮箱或手机号之一
    - 验证码10分钟内有效
    """
    if not data.email and not data.phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请提供邮箱或手机号"
        )

    # 查找用户
    user = None
    if data.email:
        user = get_user_by_email(db, email=data.email)
    elif data.phone:
        user = get_user_by_phone(db, phone=data.phone)

    if not user:
        # 为防止用户枚举攻击，即使用户不存在也返回成功
        return {"message": "如果账户存在，验证码已发送"}

    user_id = user.get('id') if isinstance(user, dict) else user.id

    # 生成并发送验证码
    try:
        code = create_verification_code(
            db,
            user_id=user_id,
            email=data.email,
            phone=data.phone,
            code_type=CODE_TYPE_PASSWORD_RESET,
        )

        # 发送验证码
        if data.email:
            send_email_code(data.email, code, CODE_TYPE_PASSWORD_RESET)
        elif data.phone:
            send_sms_code(data.phone, code, CODE_TYPE_PASSWORD_RESET)

        return {"message": "验证码已发送，请查收"}
    except Exception as e:
        logger.error(f"发送验证码失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="发送验证码失败，请稍后重试"
        )


@router.post("/password-reset/verify", summary="验证并重置密码", description="验证验证码并设置新密码")
async def verify_password_reset(data: PasswordResetVerify, db=Depends(get_db), request: Request = None):
    """
    验证验证码并重置密码
    - 验证码正确后将设置新密码
    - 验证码使用后立即失效
    """
    if not data.email and not data.phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请提供邮箱或手机号"
        )

    # 验证验证码
    result = verify_code(
        db,
        email=data.email,
        phone=data.phone,
        code=data.code,
        code_type=CODE_TYPE_PASSWORD_RESET,
        consume=True,
    )

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["message"]
        )

    user_id = result.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户不存在"
        )

    # 更新密码
    try:
        new_hashed_password = get_password_hash(data.new_password)
        db.execute(
            "UPDATE users SET hashed_password = %s, updated_at = now() WHERE id = %s",
            (new_hashed_password, user_id)
        )

        # 记录审计日志
        try:
            log_action(
                db,
                user_id=user_id,
                action="auth.password_reset",
                resource_type=None,
                resource_id=None,
                request=request,
            )
        except Exception:
            pass

        return {"message": "密码重置成功，请使用新密码登录"}
    except Exception as e:
        logger.error(f"密码重置失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="密码重置失败，请稍后重试"
        )


# ==================== 验证码登录相关接口 ====================

class CodeLoginRequest(BaseModel):
    """验证码登录请求 - 发送验证码"""
    email: Optional[EmailStr] = None
    phone: Optional[str] = None

    @field_validator('phone')
    @classmethod
    def validate_phone(cls, v):
        if v and not re.match(r'^1[3-9]\d{9}$', v):
            raise ValueError('手机号格式不正确')
        return v


class CodeLoginVerify(BaseModel):
    """验证码登录验证"""
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    code: str


@router.post("/login/code/request", summary="请求验证码登录", description="发送登录验证码到邮箱或手机")
async def request_code_login(data: CodeLoginRequest, db=Depends(get_db)):
    """
    发送登录验证码
    - 必须提供邮箱或手机号之一
    - 验证码10分钟内有效
    """
    if not data.email and not data.phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请提供邮箱或手机号"
        )

    # 查找用户
    user = None
    if data.email:
        user = get_user_by_email(db, email=data.email)
    elif data.phone:
        user = get_user_by_phone(db, phone=data.phone)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在，请先注册"
        )

    user_id = user.get('id') if isinstance(user, dict) else user.id

    # 生成并发送验证码
    try:
        code = create_verification_code(
            db,
            user_id=user_id,
            email=data.email,
            phone=data.phone,
            code_type=CODE_TYPE_LOGIN,
        )

        # 发送验证码
        if data.email:
            send_email_code(data.email, code, CODE_TYPE_LOGIN)
        elif data.phone:
            send_sms_code(data.phone, code, CODE_TYPE_LOGIN)

        return {"message": "验证码已发送，请查收"}
    except Exception as e:
        logger.error(f"发送验证码失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="发送验证码失败，请稍后重试"
        )


@router.post("/login/code/verify", response_model=Token, summary="验证码登录", description="使用验证码登录并返回Token")
async def verify_code_login(data: CodeLoginVerify, db=Depends(get_db), request: Request = None):
    """
    使用验证码登录
    - 验证码正确后返回JWT Token
    - 验证码使用后立即失效
    """
    if not data.email and not data.phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请提供邮箱或手机号"
        )

    # 验证验证码
    result = verify_code(
        db,
        email=data.email,
        phone=data.phone,
        code=data.code,
        code_type=CODE_TYPE_LOGIN,
        consume=True,
    )

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=result["message"],
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = result.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 获取用户名
    rows = db.query("SELECT username FROM users WHERE id = %s LIMIT 1", (user_id,))
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )

    username = rows[0][0]

    # 生成访问令牌
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": username}, expires_delta=access_token_expires
    )

    try:
        log_action(
            db,
            user_id=user_id,
            action="auth.code_login",
            resource_type=None,
            resource_id=None,
            request=request,
        )
    except Exception:
        pass

    return {"access_token": access_token, "token_type": "bearer"}


# ==================== OAuth2 社交登录相关接口 ====================

from app.services.oauth_service import (
    get_provider,
    get_supported_providers,
    get_or_create_oauth_user,
    get_user_oauth_accounts,
    unlink_oauth_account,
)
import secrets


class OAuth2CallbackData(BaseModel):
    """OAuth2 回调数据"""
    code: str
    state: Optional[str] = None


@router.get("/oauth/providers", summary="获取支持的OAuth2提供商", description="返回系统支持的第三方登录提供商列表")
async def list_oauth_providers():
    """获取支持的 OAuth2 提供商列表"""
    return {"providers": get_supported_providers()}


@router.get("/oauth/{provider}/authorize", summary="获取OAuth2授权URL", description="获取第三方登录的授权URL")
async def oauth_authorize(provider: str, redirect_uri: str):
    """
    获取 OAuth2 授权 URL
    
    - provider: 提供商名称 (github, google)
    - redirect_uri: 回调地址
    """
    oauth_provider = get_provider(provider)
    if not oauth_provider:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的 OAuth2 提供商: {provider}"
        )
    
    # 检查是否已配置
    if not oauth_provider.client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{provider} 登录未配置"
        )
    
    # 生成 state 防止 CSRF
    state = secrets.token_urlsafe(32)
    
    auth_url = oauth_provider.get_authorization_url(redirect_uri, state)
    
    return {
        "authorization_url": auth_url,
        "state": state,
    }


@router.post("/oauth/{provider}/callback", response_model=Token, summary="OAuth2回调处理", description="处理OAuth2授权回调并返回Token")
async def oauth_callback(
    provider: str,
    data: OAuth2CallbackData,
    redirect_uri: str,
    db=Depends(get_db),
    request: Request = None,
):
    """
    处理 OAuth2 回调
    
    - 用授权码换取访问令牌
    - 获取用户信息
    - 创建或关联用户
    - 返回 JWT Token
    """
    oauth_provider = get_provider(provider)
    if not oauth_provider:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的 OAuth2 提供商: {provider}"
        )
    
    try:
        # 换取 token
        token_data = await oauth_provider.exchange_code_for_token(data.code, redirect_uri)
        access_token = token_data.get("access_token")
        
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="获取访问令牌失败"
            )
        
        # 获取用户信息
        user_info = await oauth_provider.get_user_info(access_token)
        
        # 计算 token 过期时间
        expires_in = token_data.get("expires_in")
        expires_at = None
        if expires_in:
            from datetime import datetime, timedelta
            expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        
        # 获取或创建用户
        user = await get_or_create_oauth_user(
            db,
            provider=user_info["provider"],
            provider_user_id=user_info["provider_user_id"],
            email=user_info.get("email"),
            username=user_info.get("username", ""),
            name=user_info.get("name"),
            avatar_url=user_info.get("avatar_url"),
            access_token=access_token,
            refresh_token=token_data.get("refresh_token"),
            expires_at=expires_at,
        )
        
        # 生成 JWT Token
        jwt_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        jwt_token = create_access_token(
            data={"sub": user["username"]}, expires_delta=jwt_expires
        )
        
        # 记录审计日志
        try:
            log_action(
                db,
                user_id=user["id"],
                action=f"auth.oauth_login.{provider}",
                resource_type=None,
                resource_id=None,
                request=request,
                meta={"is_new_user": user.get("is_new", False)},
            )
        except Exception:
            pass
        
        return {"access_token": jwt_token, "token_type": "bearer"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OAuth2 登录失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="第三方登录失败，请稍后重试"
        )


@router.get("/oauth/accounts", summary="获取已绑定的OAuth账户", description="获取当前用户绑定的第三方账户列表")
async def list_oauth_accounts(
    current_user: UserSchema = Depends(get_current_user),
    db=Depends(get_db),
):
    """获取当前用户绑定的 OAuth 账户列表"""
    accounts = get_user_oauth_accounts(db, current_user.id)
    return {"accounts": accounts}


@router.delete("/oauth/{provider}", summary="解绑OAuth账户", description="解绑指定的第三方账户")
async def unlink_oauth(
    provider: str,
    current_user: UserSchema = Depends(get_current_user),
    db=Depends(get_db),
):
    """解绑 OAuth 账户"""
    result = unlink_oauth_account(db, current_user.id, provider)
    if result:
        return {"message": f"已解绑 {provider} 账户"}
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="解绑失败"
        )


# ==================== 双因素认证 (2FA/TOTP) 相关接口 ====================

from app.services.totp_service import (
    setup_2fa,
    enable_2fa,
    disable_2fa,
    verify_2fa,
    is_2fa_enabled,
    get_2fa_status,
    regenerate_backup_codes,
)


class TwoFactorSetupResponse(BaseModel):
    """2FA 设置响应"""
    secret: str
    uri: str  # 用于生成二维码
    backup_codes: List[str]


class TwoFactorVerifyRequest(BaseModel):
    """2FA 验证请求"""
    code: str


class TwoFactorLoginRequest(BaseModel):
    """带 2FA 的登录请求"""
    username: str
    password: str
    totp_code: Optional[str] = None


@router.get("/2fa/status", summary="获取2FA状态", description="获取当前用户的双因素认证状态")
async def get_2fa_status_endpoint(
    current_user: UserSchema = Depends(get_current_user),
    db=Depends(get_db),
):
    """获取 2FA 状态"""
    status_info = get_2fa_status(db, current_user.id)
    return status_info


@router.post("/2fa/setup", summary="设置2FA", description="生成2FA密钥和二维码URI")
async def setup_2fa_endpoint(
    current_user: UserSchema = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    设置 2FA
    - 返回密钥和二维码 URI
    - 用户需要用验证器 App 扫描二维码
    - 设置后需要调用 /2fa/enable 接口启用
    """
    try:
        result = setup_2fa(db, current_user.id)
        return TwoFactorSetupResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"设置 2FA 失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="设置 2FA 失败"
        )


@router.post("/2fa/enable", summary="启用2FA", description="验证TOTP后启用双因素认证")
async def enable_2fa_endpoint(
    data: TwoFactorVerifyRequest,
    current_user: UserSchema = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    启用 2FA
    - 需要先调用 /2fa/setup 获取密钥
    - 用验证器 App 生成的验证码来验证
    """
    try:
        success = enable_2fa(db, current_user.id, data.code)
        if success:
            return {"message": "2FA 已启用"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="验证码错误，请重试"
            )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/2fa/disable", summary="禁用2FA", description="验证后禁用双因素认证")
async def disable_2fa_endpoint(
    data: TwoFactorVerifyRequest,
    current_user: UserSchema = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    禁用 2FA
    - 需要提供 TOTP 验证码或备用码
    """
    try:
        success = disable_2fa(db, current_user.id, data.code)
        if success:
            return {"message": "2FA 已禁用"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="验证码错误"
            )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/2fa/backup-codes/regenerate", summary="重新生成备用码", description="生成新的备用恢复码")
async def regenerate_backup_codes_endpoint(
    data: TwoFactorVerifyRequest,
    current_user: UserSchema = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    重新生成备用码
    - 需要提供 TOTP 验证码
    - 旧的备用码将全部失效
    """
    try:
        new_codes = regenerate_backup_codes(db, current_user.id, data.code)
        return {"backup_codes": new_codes}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/token/2fa", response_model=Token, summary="带2FA的登录", description="用户名密码+可选TOTP验证登录")
async def login_with_2fa(
    data: TwoFactorLoginRequest,
    db=Depends(get_db),
    request: Request = None,
):
    """
    带 2FA 的登录
    - 如果用户启用了 2FA，必须提供 totp_code
    - 如果用户未启用 2FA，totp_code 可选
    """
    # 验证用户名密码
    rows = db.query(
        "SELECT id, username, hashed_password FROM users WHERE username = %s LIMIT 1",
        (data.username,)
    )
    
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    result = rows[0]
    user_id = result[0]
    username = result[1]
    hashed_password = result[2]
    
    if not verify_password(data.password, hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 检查 2FA
    if is_2fa_enabled(db, user_id):
        if not data.totp_code:
            # 返回特殊状态码，前端需要弹出 2FA 输入框
            raise HTTPException(
                status_code=status.HTTP_428_PRECONDITION_REQUIRED,
                detail="需要双因素认证验证码",
            )
        
        if not verify_2fa(db, user_id, data.totp_code):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="双因素认证验证码错误",
                headers={"WWW-Authenticate": "Bearer"},
            )
    
    # 生成 Token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": username}, expires_delta=access_token_expires
    )
    
    try:
        log_action(
            db,
            user_id=user_id,
            action="auth.login_2fa",
            resource_type=None,
            resource_id=None,
            request=request,
        )
    except Exception:
        pass
    
    return {"access_token": access_token, "token_type": "bearer"}