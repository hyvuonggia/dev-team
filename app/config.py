from __future__ import annotations

from dotenv import load_dotenv
import os
from typing import Optional


# Load .env file if present (matches previous behavior using pydantic's env_file)
load_dotenv(dotenv_path=".env")


class Settings:
    OPENROUTER_API_KEY: Optional[str] = os.getenv("OPENROUTER_API_KEY")
    OPENAI_API_BASE: str = os.getenv("OPENAI_API_BASE", "https://openrouter.ai/api/v1")
    OPENAI_API_TYPE: Optional[str] = os.getenv("OPENAI_API_TYPE")
    OPENAI_API_VERSION: Optional[str] = os.getenv("OPENAI_API_VERSION")


settings = Settings()
