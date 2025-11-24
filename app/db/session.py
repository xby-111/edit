from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# Create engine using PostgreSQL dialect for openGauss
engine = create_engine(
    settings.DATABASE_URL,
    echo=True,  # Set to False in production
    pool_pre_ping=True,  # Ensures connections are valid
    pool_size=10,
    max_overflow=20
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """
    Dependency to provide database sessions for FastAPI endpoints.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()