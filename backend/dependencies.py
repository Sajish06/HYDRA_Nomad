"""FastAPI dependency providers for Meetily Clean Room."""

from typing import Generator

from fastapi import Depends
from sqlalchemy.orm import Session

from backend.config import Settings, settings
from backend.storage.database import get_db
from backend.storage.repository import Repository


def get_app_settings() -> Settings:
    """Provides application settings."""
    return settings


def get_db_session() -> Generator[Session, None, None]:
    """Provides database session dependency."""
    yield from get_db()


def get_repo(db: Session = Depends(get_db_session)) -> Repository:
    """Provides a repository instance bound to the active DB session."""
    return Repository(db)
