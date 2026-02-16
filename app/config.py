from __future__ import annotations

from dotenv import load_dotenv
import os
from pathlib import Path
from typing import Optional


# Load .env file if present (matches previous behavior using pydantic's env_file)
load_dotenv(dotenv_path=".env")

# Get the project root directory
PROJECT_ROOT = Path(__file__).parent.parent


class Settings:
    # API Keys
    OPENROUTER_API_KEY: Optional[str] = os.getenv("OPENROUTER_API_KEY")

    # OpenAI/OpenRouter Configuration
    OPENAI_API_BASE: str = (
        os.getenv("OPENAI_API_BASE") or "https://openrouter.ai/api/v1"
    )
    # model to use for ChatOpenAI
    OPENAI_MODEL: Optional[str] = os.getenv("OPENAI_MODEL")

    # Database URL for SQLite (default to local file with absolute path)
    DATABASE_URL: str = (
        os.getenv("DATABASE_URL") or f"sqlite:///{PROJECT_ROOT}/chat_history.db"
    )

    # Logging Configuration
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_DIR: str = os.getenv("LOG_DIR", "logs")

    # LangSmith Configuration (for tracing)
    LANGSMITH_API_KEY: Optional[str] = os.getenv("LANGSMITH_API_KEY")
    LANGSMITH_ENDPOINT: Optional[str] = os.getenv("LANGSMITH_ENDPOINT")
    LANGSMITH_PROJECT: str = os.getenv("LANGSMITH_PROJECT", "dev-team")
    # Enable LangSmith tracing
    LANGCHAIN_TRACING_V2: bool = (
        os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
    )


settings = Settings()
