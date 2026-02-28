from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional, List

from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    AIMessage,
    SystemMessage,
)
from sqlmodel import select

from app.db.database import get_session
from app.db.models import Session as DBSession, Message as DBMessage


def get_history(session_id: Optional[str] = None) -> BaseChatMessageHistory:
    """Get or create a ChatMessageHistory for a given session using SQLite storage."""
    if session_id is None:
        # Generate a new UUID-based session ID
        session_id = str(uuid.uuid4())

    return SQLiteChatMessageHistory(session_id)


def list_session_ids() -> List[str]:
    """Return a list of active session IDs from database."""
    with get_session() as session:
        statement = select(DBSession.id)
        results = session.exec(statement).all()
        return [str(result) for result in results]


def clear_session(session_id: str) -> None:
    """Clear the history for a specific session."""
    with get_session() as session:
        # Delete all messages for this session
        statement = select(DBMessage).where(DBMessage.session_id == session_id)
        messages = session.exec(statement).all()
        for message in messages:
            session.delete(message)

        # Delete the session itself
        db_session = session.get(DBSession, session_id)
        if db_session:
            session.delete(db_session)


def clear_all_sessions() -> None:
    """Clear all session histories."""
    with get_session() as session:
        # Delete all messages first (due to foreign key constraint)
        statement = select(DBMessage)
        messages = session.exec(statement).all()
        for message in messages:
            session.delete(message)

        # Delete all sessions
        statement = select(DBSession)
        sessions = session.exec(statement).all()
        for db_session in sessions:
            session.delete(db_session)


def get_session_history(session_id: str) -> List[dict]:
    """Get conversation history for a session as a list of message dicts."""
    with get_session() as session:
        statement = (
            select(DBMessage)
            .where(DBMessage.session_id == session_id)
            .order_by(DBMessage.created_at)
        )
        messages = session.exec(statement).all()
        return [
            {
                "role": msg.role,
                "content": msg.content,
                "created_at": msg.created_at.isoformat(),
            }
            for msg in messages
        ]


class SQLiteChatMessageHistory(BaseChatMessageHistory):
    """ChatMessageHistory backed by SQLite database."""

    def __init__(self, session_id: str):
        self._session_id = session_id
        self._ensure_session_exists()

    def _ensure_session_exists(self) -> None:
        """Ensure the session exists in the database."""
        with get_session() as session:
            db_session = session.get(DBSession, self._session_id)
            if not db_session:
                # Create new session
                db_session = DBSession(id=self._session_id)
                session.add(db_session)

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def messages(self) -> List[BaseMessage]:
        """Retrieve messages from database."""
        with get_session() as session:
            statement = (
                select(DBMessage)
                .where(DBMessage.session_id == self._session_id)
                .order_by(DBMessage.created_at)
            )
            db_messages = session.exec(statement).all()

            # Convert DB messages to LangChain message objects
            lc_messages = []
            for msg in db_messages:
                if msg.role == "human":
                    lc_messages.append(HumanMessage(content=msg.content))
                elif msg.role == "ai":
                    lc_messages.append(AIMessage(content=msg.content))
                elif msg.role == "system":
                    lc_messages.append(SystemMessage(content=msg.content))
            return lc_messages

    def add_message(self, message: BaseMessage) -> None:
        """Add a message to the database."""
        # Determine role from message type
        if isinstance(message, HumanMessage):
            role = "human"
        elif isinstance(message, AIMessage):
            role = "ai"
        elif isinstance(message, SystemMessage):
            role = "system"
        else:
            role = "unknown"

        with get_session() as session:
            db_message = DBMessage(
                session_id=self._session_id,
                role=role,
                content=str(message.content),
            )
            session.add(db_message)

            # Update session's updated_at timestamp
            db_session = session.get(DBSession, self._session_id)
            if db_session:
                db_session.updated_at = datetime.now(timezone.utc)

    def clear(self) -> None:
        """Clear all messages for this session."""
        with get_session() as session:
            statement = select(DBMessage).where(
                DBMessage.session_id == self._session_id
            )
            messages = session.exec(statement).all()
            for message in messages:
                session.delete(message)
