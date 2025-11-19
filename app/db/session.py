"""Database session and engine configuration."""
from __future__ import annotations

from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

# Create a single global engine shared across the application.
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    future=True,
)

# Factory that creates new Session objects on demand.
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator:
    """FastAPI dependency that yields a transactional database session."""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
