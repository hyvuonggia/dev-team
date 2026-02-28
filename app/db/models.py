from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, List
from sqlmodel import SQLModel, Field


class Session(SQLModel, table=True):
    """Chat session model."""

    __tablename__ = "sessions"

    id: str = Field(primary_key=True, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Message(SQLModel, table=True):
    """Chat message model."""

    __tablename__ = "messages"

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="sessions.id", index=True)
    role: str = Field(index=True)  # "human", "ai", "system"
    content: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Task(SQLModel, table=True):
    """Task model for agent orchestration.

    Represents a unit of work assigned to agents with full context
    and metadata for tracking progress.
    """

    __tablename__ = "tasks"

    id: str = Field(primary_key=True, index=True)
    title: str = Field(..., description="Task title/summary")
    description: str = Field(..., description="Detailed task description")
    status: str = Field(
        default="pending",
        description="Task status: pending, in_progress, waiting_for_clarification, completed, failed",
    )
    assigned_agents: str = Field(
        default="",
        description="Comma-separated list of agents involved (ba,dev,tester)",
    )
    project_id: Optional[str] = Field(
        default=None, description="Project ID for workspace isolation"
    )
    artifacts: str = Field(
        default="", description="JSON-encoded list of file paths produced"
    )
    agent_messages: str = Field(
        default="", description="JSON-encoded agent conversation history"
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    error_message: Optional[str] = Field(None, description="Error if task failed")
    retry_count: int = Field(default=0, description="Number of retry attempts")
    max_retries: int = Field(default=3, description="Maximum retry attempts")
