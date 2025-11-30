"""
应用配置模块

通过 pydantic-settings 管理所有配置项，支持从环境变量加载配置。
"""
import os
from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置类"""
    
    # ==================== 基础配置 ====================
    PROJECT_NAME: str = "多人协作文档编辑后端 API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    
    # ==================== 数据库配置 ====================
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "opengauss://appuser:GUAss000#@120.46.143.126:5432/editdb"
    )
    
    # ==================== JWT 配置 ====================
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    
    # ==================== 文件上传配置 ====================
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "uploads")
    MAX_UPLOAD_SIZE: int = int(os.getenv("MAX_UPLOAD_SIZE", str(10 * 1024 * 1024)))  # 10MB
    
    # ==================== CORS 配置 ====================
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost",
        "http://127.0.0.1",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]
    
    # ==================== OAuth2 配置 - GitHub ====================
    GITHUB_CLIENT_ID: str = os.getenv("GITHUB_CLIENT_ID", "")
    GITHUB_CLIENT_SECRET: str = os.getenv("GITHUB_CLIENT_SECRET", "")
    
    # ==================== OAuth2 配置 - Google ====================
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    
    # ==================== 邮件配置 (SMTP) ====================
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM_EMAIL: str = os.getenv("SMTP_FROM_EMAIL", "noreply@example.com")
    SMTP_USE_TLS: bool = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
    
    # ==================== 短信配置 (阿里云) ====================
    SMS_ACCESS_KEY_ID: str = os.getenv("SMS_ACCESS_KEY_ID", "")
    SMS_ACCESS_KEY_SECRET: str = os.getenv("SMS_ACCESS_KEY_SECRET", "")
    SMS_SIGN_NAME: str = os.getenv("SMS_SIGN_NAME", "")
    SMS_TEMPLATE_CODE: str = os.getenv("SMS_TEMPLATE_CODE", "")
    
    # ==================== 备份配置 ====================
    BACKUP_DIR: str = os.getenv("BACKUP_DIR", "backups")
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# 全局配置实例
settings = Settings()
