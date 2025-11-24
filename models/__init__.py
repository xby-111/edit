"""
统一的数据库模型定义 - 已迁移至 SQL 操作
保留密码加密相关功能
"""
from passlib.context import CryptContext
from datetime import datetime

# 密码加密上下文（用于密码处理）
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """生成密码哈希"""
    return pwd_context.hash(password)