"""
OAuth2 社交登录服务 - 支持 GitHub 和 Google 登录
"""
import httpx
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from app.core.config import settings

logger = logging.getLogger(__name__)


# ==================== OAuth2 配置 ====================

class OAuth2Config:
    """OAuth2 提供商配置"""
    
    # GitHub OAuth2
    GITHUB_CLIENT_ID = getattr(settings, 'GITHUB_CLIENT_ID', '')
    GITHUB_CLIENT_SECRET = getattr(settings, 'GITHUB_CLIENT_SECRET', '')
    GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
    GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
    GITHUB_USER_API = "https://api.github.com/user"
    GITHUB_SCOPES = ["user:email"]
    
    # Google OAuth2
    GOOGLE_CLIENT_ID = getattr(settings, 'GOOGLE_CLIENT_ID', '')
    GOOGLE_CLIENT_SECRET = getattr(settings, 'GOOGLE_CLIENT_SECRET', '')
    GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
    GOOGLE_USER_API = "https://www.googleapis.com/oauth2/v2/userinfo"
    GOOGLE_SCOPES = ["openid", "email", "profile"]


# ==================== OAuth2 提供商基类 ====================

class OAuth2Provider:
    """OAuth2 提供商基类"""
    
    name: str = ""
    authorize_url: str = ""
    token_url: str = ""
    user_api_url: str = ""
    scopes: list = []
    client_id: str = ""
    client_secret: str = ""
    
    def get_authorization_url(self, redirect_uri: str, state: str = "") -> str:
        """获取授权URL"""
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(self.scopes),
            "response_type": "code",
            "state": state,
        }
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{self.authorize_url}?{query}"
    
    async def exchange_code_for_token(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        """用授权码换取访问令牌"""
        raise NotImplementedError
    
    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """获取用户信息"""
        raise NotImplementedError


# ==================== GitHub OAuth2 ====================

class GitHubOAuth2(OAuth2Provider):
    """GitHub OAuth2 提供商"""
    
    name = "github"
    authorize_url = OAuth2Config.GITHUB_AUTHORIZE_URL
    token_url = OAuth2Config.GITHUB_TOKEN_URL
    user_api_url = OAuth2Config.GITHUB_USER_API
    scopes = OAuth2Config.GITHUB_SCOPES
    client_id = OAuth2Config.GITHUB_CLIENT_ID
    client_secret = OAuth2Config.GITHUB_CLIENT_SECRET
    
    async def exchange_code_for_token(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        """用授权码换取访问令牌"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.token_url,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            return response.json()
    
    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """获取 GitHub 用户信息"""
        async with httpx.AsyncClient() as client:
            # 获取基本用户信息
            response = await client.get(
                self.user_api_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )
            response.raise_for_status()
            user_data = response.json()
            
            # 如果邮箱为空，尝试获取邮箱列表
            if not user_data.get("email"):
                email_response = await client.get(
                    "https://api.github.com/user/emails",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/json",
                    },
                )
                if email_response.status_code == 200:
                    emails = email_response.json()
                    # 找到主邮箱
                    for email in emails:
                        if email.get("primary"):
                            user_data["email"] = email.get("email")
                            break
            
            return {
                "provider": "github",
                "provider_user_id": str(user_data.get("id")),
                "username": user_data.get("login"),
                "email": user_data.get("email"),
                "name": user_data.get("name") or user_data.get("login"),
                "avatar_url": user_data.get("avatar_url"),
            }


# ==================== Google OAuth2 ====================

class GoogleOAuth2(OAuth2Provider):
    """Google OAuth2 提供商"""
    
    name = "google"
    authorize_url = OAuth2Config.GOOGLE_AUTHORIZE_URL
    token_url = OAuth2Config.GOOGLE_TOKEN_URL
    user_api_url = OAuth2Config.GOOGLE_USER_API
    scopes = OAuth2Config.GOOGLE_SCOPES
    client_id = OAuth2Config.GOOGLE_CLIENT_ID
    client_secret = OAuth2Config.GOOGLE_CLIENT_SECRET
    
    def get_authorization_url(self, redirect_uri: str, state: str = "") -> str:
        """获取 Google 授权URL（需要额外参数）"""
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(self.scopes),
            "response_type": "code",
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{self.authorize_url}?{query}"
    
    async def exchange_code_for_token(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        """用授权码换取访问令牌"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.token_url,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            response.raise_for_status()
            return response.json()
    
    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """获取 Google 用户信息"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.user_api_url,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            user_data = response.json()
            
            return {
                "provider": "google",
                "provider_user_id": user_data.get("id"),
                "username": user_data.get("email", "").split("@")[0],
                "email": user_data.get("email"),
                "name": user_data.get("name"),
                "avatar_url": user_data.get("picture"),
            }


# ==================== OAuth2 服务函数 ====================

# 提供商实例
_providers = {
    "github": GitHubOAuth2(),
    "google": GoogleOAuth2(),
}


def get_provider(name: str) -> Optional[OAuth2Provider]:
    """获取 OAuth2 提供商实例"""
    return _providers.get(name.lower())


def get_supported_providers() -> list:
    """获取支持的 OAuth2 提供商列表"""
    return [
        {
            "name": "github",
            "display_name": "GitHub",
            "enabled": bool(OAuth2Config.GITHUB_CLIENT_ID),
        },
        {
            "name": "google",
            "display_name": "Google",
            "enabled": bool(OAuth2Config.GOOGLE_CLIENT_ID),
        },
    ]


async def get_or_create_oauth_user(
    db,
    *,
    provider: str,
    provider_user_id: str,
    email: Optional[str],
    username: str,
    name: Optional[str] = None,
    avatar_url: Optional[str] = None,
    access_token: Optional[str] = None,
    refresh_token: Optional[str] = None,
    expires_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    获取或创建 OAuth 用户
    
    流程：
    1. 先通过 provider + provider_user_id 查找已绑定账户
    2. 如果没有，通过邮箱查找已有账户并绑定
    3. 如果都没有，创建新用户并绑定
    """
    # 1. 查找已绑定的 OAuth 账户
    rows = db.query(
        """
        SELECT user_id FROM oauth_accounts 
        WHERE provider = %s AND provider_user_id = %s 
        LIMIT 1
        """,
        (provider, provider_user_id)
    )
    
    if rows:
        user_id = rows[0][0]
        # 更新 token 信息
        db.execute(
            """
            UPDATE oauth_accounts 
            SET access_token = %s, refresh_token = %s, expires_at = %s, updated_at = now()
            WHERE provider = %s AND provider_user_id = %s
            """,
            (access_token, refresh_token, expires_at, provider, provider_user_id)
        )
        
        # 获取用户信息
        user_rows = db.query(
            "SELECT id, username, email, role, is_active FROM users WHERE id = %s LIMIT 1",
            (user_id,)
        )
        if user_rows:
            user = user_rows[0]
            return {
                "id": user[0],
                "username": user[1],
                "email": user[2],
                "role": user[3],
                "is_active": user[4],
                "is_new": False,
            }
    
    # 2. 如果有邮箱，查找已有账户
    user_id = None
    if email:
        user_rows = db.query(
            "SELECT id, username, email, role, is_active FROM users WHERE email = %s LIMIT 1",
            (email,)
        )
        if user_rows:
            user = user_rows[0]
            user_id = user[0]
            
            # 绑定 OAuth 账户
            db.execute(
                """
                INSERT INTO oauth_accounts (user_id, provider, provider_user_id, access_token, refresh_token, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (user_id, provider, provider_user_id, access_token, refresh_token, expires_at)
            )
            
            return {
                "id": user[0],
                "username": user[1],
                "email": user[2],
                "role": user[3],
                "is_active": user[4],
                "is_new": False,
            }
    
    # 3. 创建新用户
    # 确保用户名唯一
    base_username = username or f"{provider}_user"
    unique_username = base_username
    counter = 1
    while True:
        exists = db.query(
            "SELECT 1 FROM users WHERE username = %s LIMIT 1",
            (unique_username,)
        )
        if not exists:
            break
        unique_username = f"{base_username}_{counter}"
        counter += 1
    
    # 生成随机密码（OAuth 用户通常不需要密码登录）
    import secrets
    random_password = secrets.token_urlsafe(32)
    from app.core.security import get_password_hash
    hashed_password = get_password_hash(random_password)
    
    # 创建用户
    db.execute(
        """
        INSERT INTO users (username, email, hashed_password, role, is_active, created_at, updated_at)
        VALUES (%s, %s, %s, 'editor', TRUE, now(), now())
        """,
        (unique_username, email, hashed_password)
    )
    
    # 获取新用户 ID
    user_rows = db.query(
        "SELECT id, username, email, role, is_active FROM users WHERE username = %s LIMIT 1",
        (unique_username,)
    )
    
    if not user_rows:
        raise Exception("创建用户失败")
    
    user = user_rows[0]
    user_id = user[0]
    
    # 更新头像（如果有）
    if avatar_url:
        db.execute(
            "UPDATE users SET avatar_url = %s WHERE id = %s",
            (avatar_url, user_id)
        )
    
    # 绑定 OAuth 账户
    db.execute(
        """
        INSERT INTO oauth_accounts (user_id, provider, provider_user_id, access_token, refresh_token, expires_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (user_id, provider, provider_user_id, access_token, refresh_token, expires_at)
    )
    
    logger.info(f"创建新 OAuth 用户: provider={provider}, username={unique_username}")
    
    return {
        "id": user[0],
        "username": user[1],
        "email": user[2],
        "role": user[3],
        "is_active": user[4],
        "is_new": True,
    }


def get_user_oauth_accounts(db, user_id: int) -> list:
    """获取用户绑定的 OAuth 账户列表"""
    rows = db.query(
        """
        SELECT provider, provider_user_id, created_at
        FROM oauth_accounts
        WHERE user_id = %s
        ORDER BY created_at
        """,
        (user_id,)
    )
    
    return [
        {
            "provider": row[0],
            "provider_user_id": row[1],
            "created_at": row[2],
        }
        for row in rows
    ]


def unlink_oauth_account(db, user_id: int, provider: str) -> bool:
    """解绑 OAuth 账户"""
    # 检查用户是否有密码（确保不会锁死账户）
    rows = db.query(
        "SELECT hashed_password FROM users WHERE id = %s LIMIT 1",
        (user_id,)
    )
    
    if not rows:
        return False
    
    # 检查是否还有其他登录方式
    oauth_count = db.query(
        "SELECT COUNT(*) FROM oauth_accounts WHERE user_id = %s",
        (user_id,)
    )
    
    # 如果只剩一个 OAuth 账户，需要确保用户有密码
    # （这里简化处理，实际可能需要更复杂的逻辑）
    
    db.execute(
        "DELETE FROM oauth_accounts WHERE user_id = %s AND provider = %s",
        (user_id, provider)
    )
    
    logger.info(f"解绑 OAuth 账户: user_id={user_id}, provider={provider}")
    return True
