"""LLM logging utilities for tracking token usage, pricing, and LangSmith traces.

Provides callbacks for LangChain to capture detailed LLM interaction metrics
and send traces to LangSmith.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from app.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)
llm_logger = logging.getLogger("llm")

# OpenRouter pricing per 1K tokens (input/output) in USD
# Update these rates as OpenRouter changes their pricing
MODEL_PRICING = {
    # Free models
    "nvidia/nemotron-3-nano-30b-a3b:free": {"input": 0.0, "output": 0.0},
    # Common paid models (update as needed)
    "gpt-4": {"input": 0.03, "output": 0.06},
    "gpt-4-turbo": {"input": 0.01, "output": 0.03},
    "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
    "claude-3-opus": {"input": 0.015, "output": 0.075},
    "claude-3-sonnet": {"input": 0.003, "output": 0.015},
    "claude-3-haiku": {"input": 0.00025, "output": 0.00125},
}


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate the cost of an LLM request.

    Args:
        model: Model identifier string.
        input_tokens: Number of input tokens.
        output_tokens: Number of output tokens.

    Returns:
        Total cost in USD.
    """
    pricing = MODEL_PRICING.get(model, {"input": 0.0, "output": 0.0})
    input_cost = (input_tokens / 1000) * pricing["input"]
    output_cost = (output_tokens / 1000) * pricing["output"]
    return round(input_cost + output_cost, 6)


class LLMLoggingCallback(BaseCallbackHandler):
    """Callback handler for logging LLM interactions with token usage and pricing.

    Captures:
    - Input/output tokens
    - Model used
    - Request duration
    - Cost calculation
    """

    def __init__(self, model: str | None = None, session_id: str | None = None):
        """Initialize the callback handler.

        Args:
            model: Model identifier for pricing calculation.
            session_id: Session ID for correlation.
        """
        super().__init__()
        self.model = model or settings.OPENAI_MODEL or "unknown"
        self.session_id = session_id
        self.input_tokens = 0
        self.output_tokens = 0

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        **kwargs: Any,
    ) -> None:
        """Called when LLM starts processing.

        Args:
            serialized: Serialized LLM information.
            prompts: List of prompts being sent.
            **kwargs: Additional arguments.
        """
        self.input_tokens = 0
        self.output_tokens = 0

        llm_logger.info(
            f"LLM Start | Model: {self.model} | Prompts: {len(prompts)}",
            extra={
                "event": "llm_start",
                "model": self.model,
                "prompt_count": len(prompts),
                "session_id": self.session_id,
            },
        )

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Called when LLM finishes processing.

        Args:
            response: LLM result containing generations and token usage.
            **kwargs: Additional arguments.
        """
        # Extract token usage from response
        if response.llm_output and "token_usage" in response.llm_output:
            token_usage = response.llm_output["token_usage"]
            self.input_tokens = token_usage.get("prompt_tokens", 0)
            self.output_tokens = token_usage.get("completion_tokens", 0)
        elif hasattr(response, "usage") and response.usage:
            self.input_tokens = getattr(response.usage, "prompt_tokens", 0)
            self.output_tokens = getattr(response.usage, "completion_tokens", 0)

        total_tokens = self.input_tokens + self.output_tokens
        cost_usd = calculate_cost(self.model, self.input_tokens, self.output_tokens)

        # Log to console
        logger.info(
            f"LLM Complete | {self.model} | "
            f"Tokens: {self.input_tokens}in/{self.output_tokens}out "
            f"({total_tokens} total) | Cost: ${cost_usd:.6f}"
        )

        # Log detailed info to LLM log file
        llm_logger.info(
            f"LLM Complete | Model: {self.model}",
            extra={
                "event": "llm_complete",
                "model": self.model,
                "session_id": self.session_id,
                "tokens": {
                    "input": self.input_tokens,
                    "output": self.output_tokens,
                    "total": total_tokens,
                },
                "cost_usd": cost_usd,
            },
        )

    def on_llm_error(
        self,
        error: BaseException,
        **kwargs: Any,
    ) -> None:
        """Called when LLM encounters an error.

        Args:
            error: Exception that occurred.
            **kwargs: Additional arguments.
        """
        logger.error(
            f"LLM Error | Model: {self.model} | Error: {error}",
            exc_info=True,
        )

        llm_logger.error(
            f"LLM Error | Model: {self.model} | Error: {str(error)}",
            extra={
                "event": "llm_error",
                "model": self.model,
                "session_id": self.session_id,
                "error": str(error),
                "error_type": type(error).__name__,
            },
        )


def create_llm_callback(
    model: str | None = None, session_id: str | None = None
) -> LLMLoggingCallback:
    """Factory function to create an LLM logging callback.

    Args:
        model: Model identifier for pricing calculation.
        session_id: Session ID for correlation.

    Returns:
        Configured LLMLoggingCallback instance.
    """
    return LLMLoggingCallback(model=model, session_id=session_id)


def get_langsmith_config() -> dict[str, Any] | None:
    """Get LangSmith configuration if available.

    Returns:
        Configuration dictionary for LangSmith tracing, or None if not configured.
    """
    if not settings.LANGSMITH_API_KEY:
        return None

    return {
        "api_key": settings.LANGSMITH_API_KEY,
        "endpoint": settings.LANGSMITH_ENDPOINT or "https://api.smith.langchain.com",
        "project": settings.LANGSMITH_PROJECT or "dev-team",
    }
