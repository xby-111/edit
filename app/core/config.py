from pydantic_settings import BaseSettings

import os


class Settings(BaseSettings):
    PROJECT_NAME: str = "多人协作文档编辑后端 API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Database settings for openGauss
    DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "opengauss://appuser:GUAss000#@120.46.143.126:5432/editdb"
)


    
    # JWT settings
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    
    # Upload settings
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "uploads")
    
    # CORS settings
    BACKEND_CORS_ORIGINS: list[str] = ["http://localhost", "http://127.0.0.1", "http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:8000", "http://127.0.0.1:8000"]  # Configure appropriately for production
    
    # OAuth2 Settings - GitHub
    GITHUB_CLIENT_ID: str = os.getenv("GITHUB_CLIENT_ID", "")
    GITHUB_CLIENT_SECRET: str = os.getenv("GITHUB_CLIENT_SECRET", "")
    
    # OAuth2 Settings - Google
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    
    # Email Settings (SMTP)
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM_EMAIL: str = os.getenv("SMTP_FROM_EMAIL", "noreply@example.com")
    
    # SMS Settings (阿里云短信)
    SMS_ACCESS_KEY_ID: str = os.getenv("SMS_ACCESS_KEY_ID", "")
    SMS_ACCESS_KEY_SECRET: str = os.getenv("SMS_ACCESS_KEY_SECRET", "")
    SMS_SIGN_NAME: str = os.getenv("SMS_SIGN_NAME", "")
    SMS_TEMPLATE_CODE: str = os.getenv("SMS_TEMPLATE_CODE", "")

settings = Settings()