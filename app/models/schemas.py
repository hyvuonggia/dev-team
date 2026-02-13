from __future__ import annotations

from pydantic import BaseModel
from typing import Optional, List


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
