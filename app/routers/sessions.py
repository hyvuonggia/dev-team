from __future__ import annotations

from fastapi import APIRouter

from app.chat_memory import list_session_ids, clear_session, get_session_history
from app.models.schemas import (
    SessionsResponse,
    SessionInfo,
    SessionHistoryResponse,
    MessageHistory,
    DeleteSessionResponse,
)

router = APIRouter()


@router.get("/sessions", response_model=SessionsResponse)
async def list_sessions():
    """List all active session IDs."""
    session_ids = list_session_ids()
    return SessionsResponse(
        sessions=[SessionInfo(session_id=sid) for sid in session_ids]
    )


@router.delete("/sessions/{session_id}", response_model=DeleteSessionResponse)
async def delete_session(session_id: str):
    """Clear a session and all its messages."""
    clear_session(session_id)
    return {"message": f"Session {session_id} cleared"}


@router.get("/sessions/{session_id}/history", response_model=SessionHistoryResponse)
async def get_history_endpoint(session_id: str):
    """Get conversation history for a session."""
    messages = get_session_history(session_id)
    return SessionHistoryResponse(
        session_id=session_id, messages=[MessageHistory(**msg) for msg in messages]
    )
