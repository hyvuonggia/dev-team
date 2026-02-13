from __future__ import annotations

from sqlmodel import SQLModel, create_engine, Session
from contextlib import contextmanager
from app.config import settings

# Create database engine
# Using aiosqlite for async support with SQLModel
DATABASE_URL = settings.DATABASE_URL or "sqlite:///./chat_history.db"

engine = create_engine(
    DATABASE_URL,
    echo=False,  # Set to True for SQL debugging
    connect_args={"check_same_thread": False}
    if DATABASE_URL.startswith("sqlite")
    else {},
)


def create_db_and_tables():
    """Create all database tables."""
    SQLModel.metadata.create_all(engine)


@contextmanager
def get_session():
    """Get a database session context manager."""
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db_session():
    """Get a database session (for dependency injection)."""
    with get_session() as session:
        yield session
