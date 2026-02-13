from __future__ import annotations

from dotenv import load_dotenv
import os
from typing import Optional


# Load .env file if present (matches previous behavior using pydantic's env_file)
load_dotenv(dotenv_path=".env")


class Settings:
    OPENROUTER_API_KEY: Optional[str] = os.getenv("OPENROUTER_API_KEY")
    OPENAI_API_BASE: str = (
        os.getenv("OPENAI_API_BASE") or "https://openrouter.ai/api/v1"
    )
    # model to use for ChatOpenAI
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL")


settings = Settings()
