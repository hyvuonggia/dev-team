from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


# Get the project root directory
PROJECT_ROOT = Path(__file__).parent.parent


class Settings(BaseSettings):
    """Application settings loaded from environment variables with validation.

    Uses pydantic-settings for automatic env var loading, type coercion,
    and .env file support. All fields are validated at startup.
    """

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # API Keys
    OPENROUTER_API_KEY: Optional[str] = Field(
        default=None, description="OpenRouter API key"
    )

    # OpenAI/OpenRouter Configuration
    OPENAI_API_BASE: str = Field(
        default="https://openrouter.ai/api/v1",
        description="Base URL for the OpenAI-compatible API",
    )
    OPENAI_MODEL: Optional[str] = Field(
        default=None, description="Default model to use for ChatOpenAI"
    )

    # Database URL for SQLite (default to local file with absolute path)
    DATABASE_URL: str = Field(
        default=f"sqlite:///{PROJECT_ROOT}/chat_history.db",
        description="SQLAlchemy database URL",
    )

    # Logging Configuration
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    LOG_DIR: str = Field(default="logs", description="Directory for log files")

    # LangSmith Configuration (for tracing)
    LANGSMITH_API_KEY: Optional[str] = Field(
        default=None, description="LangSmith API key for tracing"
    )
    LANGSMITH_ENDPOINT: Optional[str] = Field(
        default=None, description="LangSmith endpoint URL"
    )
    LANGSMITH_PROJECT: str = Field(
        default="dev-team", description="LangSmith project name"
    )
    LANGCHAIN_TRACING_V2: bool = Field(
        default=False, description="Enable LangSmith tracing"
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance.

    Uses lru_cache so the .env file is only read once per process.
    """
    return Settings()


# Module-level convenience alias for backward compatibility
settings = get_settings()
