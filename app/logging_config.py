"""Centralized logging configuration for the application.

Provides structured JSON logging to file and colored console output.
Follows security best practices - never logs API keys or sensitive data.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class JsonFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add extra fields if present
        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id
        if hasattr(record, "session_id"):
            log_data["session_id"] = record.session_id
        if hasattr(record, "duration_ms"):
            log_data["duration_ms"] = record.duration_ms
        if hasattr(record, "tokens"):
            log_data["tokens"] = record.tokens
        if hasattr(record, "cost_usd"):
            log_data["cost_usd"] = record.cost_usd
        if hasattr(record, "extra"):
            log_data.update(record.extra)

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, default=str)


class ColoredFormatter(logging.Formatter):
    """Colored formatter for console output."""

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        # Create a copy to avoid modifying the original record for other handlers
        import copy

        record_copy = copy.copy(record)
        color = self.COLORS.get(record_copy.levelname, self.RESET)
        record_copy.levelname = f"{color}{record_copy.levelname}{self.RESET}"
        return super(ColoredFormatter, self).format(record_copy)


def setup_logging(
    log_level: str | None = None,
    log_dir: str | Path = "logs",
    app_name: str = "dev-team",
) -> logging.Logger:
    """Configure application logging.

    Sets up both console (colored) and file (JSON) handlers.
    File handler rotates daily and keeps 7 days of logs.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR). Defaults to INFO.
        log_dir: Directory for log files. Defaults to "logs".
        app_name: Name of the application for logger.

    Returns:
        Configured root logger instance.
    """
    # Determine log level
    level = getattr(logging, (log_level or "INFO").upper(), logging.INFO)

    # Create logs directory
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(level)

    # Remove existing handlers to avoid duplicates
    logger.handlers = []

    # Console handler - colored output (uses a copy to avoid affecting file output)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_format = "%(levelname)s | %(asctime)s | %(name)s | %(message)s"
    console_handler.setFormatter(ColoredFormatter(console_format))
    logger.addHandler(console_handler)

    # File handler - JSON format with rotation (clean, no colors)
    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=log_path / f"{app_name}.log",
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(JsonFormatter())
    logger.addHandler(file_handler)

    # Separate file for LLM traces with JSON format
    llm_handler = logging.handlers.TimedRotatingFileHandler(
        filename=log_path / f"{app_name}-llm.log",
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
    )
    llm_handler.setLevel(level)
    llm_handler.setFormatter(JsonFormatter())

    # Create LLM-specific logger
    llm_logger = logging.getLogger("llm")
    llm_logger.handlers = []  # Clear any existing handlers
    llm_logger.addHandler(llm_handler)
    llm_logger.setLevel(level)
    llm_logger.propagate = False  # Don't send to root logger

    # Log startup message using a clean formatter to avoid color contamination
    startup_logger = logging.getLogger("startup")
    startup_logger.info(
        f"Logging configured | Level: {logging.getLevelName(level)} | "
        f"Log directory: {log_path.absolute()}"
    )

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the given name.

    Args:
        name: Logger name, typically __name__.

    Returns:
        Logger instance.
    """
    return logging.getLogger(name)


def sanitize_sensitive_data(data: dict[str, Any]) -> dict[str, Any]:
    """Remove sensitive fields from log data.

    Args:
        data: Dictionary potentially containing sensitive data.

    Returns:
        Sanitized dictionary with sensitive values redacted.
    """
    sensitive_keys = {
        "api_key",
        "apikey",
        "api-key",
        "token",
        "password",
        "secret",
        "authorization",
        "auth",
        "cookie",
        "session",
    }

    sanitized = {}
    for key, value in data.items():
        key_lower = key.lower()
        if any(sensitive in key_lower for sensitive in sensitive_keys):
            sanitized[key] = "[REDACTED]"
        elif isinstance(value, dict):
            sanitized[key] = sanitize_sensitive_data(value)
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_sensitive_data(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            sanitized[key] = value

    return sanitized
