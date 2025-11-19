"""Database initialization helpers."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import Document


def init_db() -> None:
    """Create tables and seed the default collaborative document."""

    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        _ensure_default_document(db)


def _ensure_default_document(db: Session) -> None:
    """Create the initial document if it does not exist."""

    document = db.get(Document, 1)
    if document:
        return

    document = Document(
        id=1,
        title="Welcome Document",
        content="",
        owner_id=None,
        created_at=datetime.utcnow(),
    )
    db.add(document)
    db.commit()
