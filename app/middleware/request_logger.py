"""FastAPI middleware for request/response logging.

Captures HTTP request and response details including timing,
with sensitive data redaction for security.
"""

from __future__ import annotations

import time
import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.logging_config import get_logger, sanitize_sensitive_data

logger = get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log all HTTP requests and responses."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Response]
    ) -> Response:
        """Process request and log details.

        Args:
            request: Incoming HTTP request.
            call_next: Next middleware/endpoint in chain.

        Returns:
            HTTP response.
        """
        # Generate request ID for tracing
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id

        # Record start time
        start_time = time.time()

        # Extract request details
        method = request.method
        url = str(request.url)
        path = request.url.path
        query_params = dict(request.query_params)
        client_host = request.client.host if request.client else "unknown"

        # Get headers (sanitized)
        headers = dict(request.headers)
        safe_headers = sanitize_sensitive_data(headers)

        # Log request
        logger.info(
            f"→ Request | {method} {path} | ID: {request_id} | Client: {client_host}",
            extra={
                "request_id": request_id,
                "method": method,
                "path": path,
                "url": url,
                "query_params": query_params,
                "client_host": client_host,
                "headers": safe_headers,
            },
        )

        try:
            # Process request
            response = await call_next(request)

            # Calculate duration
            duration_ms = round((time.time() - start_time) * 1000, 2)

            # Extract response details
            status_code = response.status_code
            content_length = response.headers.get("content-length", "unknown")

            # Log response
            logger.info(
                f"← Response | {method} {path} | {status_code} | "
                f"{duration_ms}ms | ID: {request_id}",
                extra={
                    "request_id": request_id,
                    "method": method,
                    "path": path,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                    "content_length": content_length,
                },
            )

            # Add request ID to response headers for client-side tracing
            response.headers["X-Request-ID"] = request_id

            return response

        except Exception as e:
            # Calculate duration even on error
            duration_ms = round((time.time() - start_time) * 1000, 2)

            # Log error
            logger.error(
                f"✗ Error | {method} {path} | {type(e).__name__} | "
                f"{duration_ms}ms | ID: {request_id}",
                exc_info=True,
                extra={
                    "request_id": request_id,
                    "method": method,
                    "path": path,
                    "duration_ms": duration_ms,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            raise
