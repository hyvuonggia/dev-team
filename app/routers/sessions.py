from __future__ import annotations

from fastapi import APIRouter, Request

from app.chat_memory import list_session_ids, clear_session, get_session_history
from app.models.schemas import (
    SessionsResponse,
    SessionInfo,
    SessionHistoryResponse,
    MessageHistory,
    DeleteSessionResponse,
)
from app.logging_config import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.get("/sessions", response_model=SessionsResponse)
async def list_sessions(request: Request):
    """List all active session IDs."""
    request_id = getattr(request.state, "request_id", "unknown")
    session_ids = list_session_ids()

    logger.info(
        f"List sessions | Count: {len(session_ids)} | RequestID: {request_id}",
        extra={
            "request_id": request_id,
            "session_count": len(session_ids),
            "endpoint": "/sessions",
        },
    )

    return SessionsResponse(
        sessions=[SessionInfo(session_id=sid) for sid in session_ids]
    )


@router.delete("/sessions/{session_id}", response_model=DeleteSessionResponse)
async def delete_session(session_id: str, request: Request):
    """Clear a session and all its messages."""
    request_id = getattr(request.state, "request_id", "unknown")

    logger.info(
        f"Delete session | Session: {session_id} | RequestID: {request_id}",
        extra={
            "request_id": request_id,
            "session_id": session_id,
            "endpoint": "/sessions/{session_id}",
        },
    )

    try:
        clear_session(session_id)

        logger.info(
            f"Session deleted | Session: {session_id} | RequestID: {request_id}",
            extra={
                "request_id": request_id,
                "session_id": session_id,
                "endpoint": "/sessions/{session_id}",
            },
        )

        return {"message": f"Session {session_id} cleared"}

    except Exception as e:
        logger.error(
            f"Session deletion failed | Session: {session_id} | "
            f"Error: {e} | RequestID: {request_id}",
            exc_info=True,
            extra={
                "request_id": request_id,
                "session_id": session_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "endpoint": "/sessions/{session_id}",
            },
        )
        raise


@router.get("/sessions/{session_id}/history", response_model=SessionHistoryResponse)
async def get_history_endpoint(session_id: str, request: Request):
    """Get conversation history for a session."""
    request_id = getattr(request.state, "request_id", "unknown")

    logger.info(
        f"Get session history | Session: {session_id} | RequestID: {request_id}",
        extra={
            "request_id": request_id,
            "session_id": session_id,
            "endpoint": "/sessions/{session_id}/history",
        },
    )

    try:
        messages = get_session_history(session_id)
        message_count = len(messages)

        logger.info(
            f"Session history retrieved | Session: {session_id} | "
            f"Messages: {message_count} | RequestID: {request_id}",
            extra={
                "request_id": request_id,
                "session_id": session_id,
                "message_count": message_count,
                "endpoint": "/sessions/{session_id}/history",
            },
        )

        return SessionHistoryResponse(
            session_id=session_id, messages=[MessageHistory(**msg) for msg in messages]
        )

    except Exception as e:
        logger.error(
            f"Session history retrieval failed | Session: {session_id} | "
            f"Error: {e} | RequestID: {request_id}",
            exc_info=True,
            extra={
                "request_id": request_id,
                "session_id": session_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "endpoint": "/sessions/{session_id}/history",
            },
        )
        raise
