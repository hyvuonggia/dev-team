from __future__ import annotations

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
