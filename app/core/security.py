from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt, ExpiredSignatureError, JWSError
from passlib.context import CryptContext
from app.core.config import settings
from fastapi import HTTPException, status, Depends
from app.db.session import get_db
from fastapi.security import OAuth2PasswordBearer
from app.schemas import User as UserSchema

# OAuth2 scheme for token authentication
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/token"
)
# Optional OAuth2 scheme
optional_oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/token",
    auto_error=False,
)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain password against its hashed version.
    """
    # bcrypt has a 72 byte limit for passwords
    if len(plain_password) > 72:
        plain_password = plain_password[:72]
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """
    Generate a hash for the given password.
    """
    # bcrypt has a 72 byte limit for passwords
    if len(password) > 72:
        password = password[:72]
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token with the given data and expiration time.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    """
    Decode a JWT access token and return the payload if valid.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None


async def get_current_user(token: str = Depends(oauth2_scheme), db = Depends(get_db)) -> UserSchema:
    """
    Get the current authenticated user from the JWT token.
    Returns a UserSchema object.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing username",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError as e:
        # 细分JWT错误类型
        error_msg = str(e)
        if "Invalid crypto padding" in error_msg or "Invalid base64-encoded string" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token format",
                headers={"WWW-Authenticate": "Bearer"},
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # Query user from database - 使用参数化查询避免SQL注入
    rows = db.query("SELECT id, username, email, phone, is_active, role, full_name, bio, avatar_url, created_at, updated_at FROM users WHERE username = %s LIMIT 1", (username,))

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = rows[0]  # 取第一行

    # Convert result to UserSchema
    return UserSchema(
        id=result[0],
        username=result[1],
        email=result[2],
        phone=result[3],
        is_active=result[4],
        role=result[5],
        full_name=result[6],
        bio=result[7],
        avatar_url=result[8],
        created_at=result[9],
        updated_at=result[10]
    )


async def get_current_user_optional(token: str = Depends(optional_oauth2_scheme), db = Depends(get_db)) -> Optional[UserSchema]:
    """获取可选用户，令牌缺失或无效时返回 None。"""
    if not token:
        return None

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
    except ExpiredSignatureError:
        return None
    except JWTError:
        return None

    rows = db.query("SELECT id, username, email, phone, is_active, role, full_name, bio, avatar_url, created_at, updated_at FROM users WHERE username = %s LIMIT 1", (username,))

    if not rows:
        return None

    result = rows[0]
    return UserSchema(
        id=result[0],
        username=result[1],
        email=result[2],
        phone=result[3],
        is_active=result[4],
        role=result[5],
        full_name=result[6],
        bio=result[7],
        avatar_url=result[8],
        created_at=result[9],
        updated_at=result[10]
    )
