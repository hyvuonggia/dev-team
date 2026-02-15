from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional, List


# ============================================================================
# Chat Models
# ============================================================================


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str


class SessionInfo(BaseModel):
    session_id: str


class SessionsResponse(BaseModel):
    sessions: List[SessionInfo]


class MessageHistory(BaseModel):
    role: str
    content: str
    created_at: str


class SessionHistoryResponse(BaseModel):
    session_id: str
    messages: List[MessageHistory]


class DeleteSessionResponse(BaseModel):
    """Response model for session deletion."""

    message: str = Field(..., description="Status message")


# ============================================================================
# Business Analyst (BA) Agent Models
# ============================================================================


class BARequest(BaseModel):
    """Request model for BA analysis."""

    text: str = Field(..., description="The user request text to analyze")
    project_id: Optional[str] = Field(
        None, description="Optional project ID for context retrieval"
    )


class UserStory(BaseModel):
    """A single user story with acceptance criteria."""

    id: str = Field(..., description="Unique identifier for the user story")
    title: str = Field(..., description="Short title of the user story")
    description: str = Field(..., description="Detailed description of the user story")
    acceptance_criteria: List[str] = Field(
        default_factory=list, description="List of acceptance criteria"
    )


class BAResponse(BaseModel):
    """Response model from BA analysis."""

    title: str = Field(..., description="Title of the analyzed requirement")
    description: str = Field(..., description="Detailed description of the requirement")
    user_stories: List[UserStory] = Field(
        default_factory=list, description="List of user stories"
    )
    questions: List[str] = Field(
        default_factory=list,
        description="Clarifying questions if requirements are ambiguous",
    )
    priority: Optional[str] = Field(
        None, description="Priority level (high/medium/low)"
    )


# ============================================================================
# Developer (Dev) Agent Models
# ============================================================================


class FilePlan(BaseModel):
    """A planned file with summary before writing."""

    path: str = Field(..., description="Relative path to the file")
    summary: str = Field(
        ..., description="Brief description of what this file contains"
    )


class GeneratedFile(BaseModel):
    """A generated file with content."""

    path: str = Field(..., description="Relative path to the file")
    content: str = Field(..., description="File content")


class DevRequest(BaseModel):
    """Request model for Dev code generation."""

    task_description: str = Field(
        ..., description="Description of the task to implement"
    )
    user_stories: Optional[List[UserStory]] = Field(
        None, description="User stories from BA analysis"
    )
    project_id: Optional[str] = Field(
        None, description="Optional project ID for workspace isolation"
    )
    context: Optional[List[str]] = Field(
        None, description="Additional context (code snippets, requirements, etc.)"
    )
    dry_run: bool = Field(
        False, description="If True, return plan without writing files"
    )
    explain_changes: bool = Field(
        True, description="Include explanations for each file"
    )


class DevGenerateRequest(BaseModel):
    """Request model for Dev code generation endpoint.

    Can accept either:
    - A task_id (if task is already created and tracked)
    - Direct requirements (task_description, user_stories) for standalone generation
    """

    task_id: Optional[str] = Field(
        None,
        description="Existing task ID to use (optional - if provided, other fields ignored)",
    )
    task_description: Optional[str] = Field(
        None, description="Description of what to implement (required if no task_id)"
    )
    user_stories: Optional[List[UserStory]] = Field(
        None, description="User stories from BA analysis (optional)"
    )
    project_id: Optional[str] = Field(
        None, description="Project ID for workspace isolation"
    )
    context: Optional[List[str]] = Field(
        None, description="Additional context (code snippets, docs, etc.)"
    )
    dry_run: bool = Field(
        False, description="If True, return plan without writing files"
    )
    explain_changes: bool = Field(
        True, description="Include explanations for each file"
    )


class DevResponse(BaseModel):
    """Response model from Dev code generation."""

    plan: List[FilePlan] = Field(
        default_factory=list, description="Planned files before writing"
    )
    files: List[GeneratedFile] = Field(
        default_factory=list, description="Generated files with content"
    )
    explanations: dict = Field(
        default_factory=dict,
        description="Explanations for each file (path -> explanation)",
    )
    static_check_results: Optional[dict] = Field(
        None, description="Results from static analysis (linting/formatting)"
    )
    created_files: List[str] = Field(
        default_factory=list, description="List of paths that were actually written"
    )


class ImplementationResult(BaseModel):
    """Full implementation result with metadata."""

    success: bool = Field(..., description="Whether the implementation succeeded")
    plan: List[FilePlan] = Field(default_factory=list, description="Planned files")
    files: List[GeneratedFile] = Field(
        default_factory=list, description="Generated files"
    )
    explanations: dict = Field(default_factory=dict, description="File explanations")
    created_files: List[str] = Field(
        default_factory=list, description="Actually written files"
    )
    static_check_results: Optional[dict] = Field(
        None, description="Lint/format results"
    )
    error: Optional[str] = Field(None, description="Error message if failed")
    diffs: Optional[dict] = Field(None, description="Diffs for modified files")


# ============================================================================
# Task Models
# ============================================================================


class Task(BaseModel):
    """Task model for agent orchestration.

    Represents a unit of work assigned to an agent with full context
    and metadata for tracking progress.
    """

    id: str = Field(..., description="Unique task identifier")
    title: str = Field(..., description="Task title/summary")
    description: str = Field(..., description="Detailed task description")
    status: str = Field(
        default="pending",
        description="Task status: pending, in_progress, completed, failed",
    )
    assigned_to: Optional[str] = Field(
        None, description="Agent role assigned to this task (ba, dev, tester, manager)"
    )
    project_id: Optional[str] = Field(
        None, description="Project ID for workspace isolation"
    )
    user_stories: Optional[List[UserStory]] = Field(
        None, description="User stories from BA analysis"
    )
    context: Optional[List[str]] = Field(
        None, description="Additional context (code snippets, docs, etc.)"
    )
    artifacts: List[str] = Field(
        default_factory=list, description="File paths produced by this task"
    )
    agent_messages: List[dict] = Field(
        default_factory=list, description="Agent conversation history"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    error_message: Optional[str] = Field(None, description="Error if task failed")
