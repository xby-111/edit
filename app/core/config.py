from pydantic_settings import BaseSettings
import os

class Settings(BaseSettings):
    PROJECT_NAME: str = "Collaborative Editor API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Database settings - using PostgreSQL dialect for openGauss
    DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://appuser:YH030500!@120.46.143.126:5432/editdb"
)

    
    # JWT settings
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    
    # Upload settings
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "uploads")
    
    # CORS settings
    BACKEND_CORS_ORIGINS: list[str] = ["http://localhost", "http://127.0.0.1", "http://localhost:3000", "http://127.0.0.1:3000"]  # Configure appropriately for production

settings = Settings()