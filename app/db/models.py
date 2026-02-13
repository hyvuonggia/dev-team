from __future__ import annotations

from datetime import datetime
from typing import Optional, List
from sqlmodel import SQLModel, Field


class Session(SQLModel, table=True):
    """Chat session model."""

    __tablename__ = "sessions"

    id: str = Field(primary_key=True, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Message(SQLModel, table=True):
    """Chat message model."""

    __tablename__ = "messages"

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="sessions.id", index=True)
    role: str = Field(index=True)  # "human", "ai", "system"
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
