"""Global error handler middleware.

Catches unhandled exceptions and returns consistent JSON error responses
instead of raw 500 errors. Handles HTTPException, ValidationError, and
generic exceptions with appropriate status codes and messages.
"""

from __future__ import annotations

import logging
from typing import Callable

from fastapi import Request, Response
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


def _build_error_body(
    error_type: str,
    message: str,
    request_id: str | None = None,
    status_code: int = 500,
) -> dict:
    """Build a consistent error response body.

    Args:
        error_type: Machine-readable error classification.
        message: Human-readable error description.
        request_id: Optional request ID for tracing.
        status_code: HTTP status code.

    Returns:
        Structured error dict.
    """
    body: dict = {
        "error": {
            "type": error_type,
            "message": message,
            "status_code": status_code,
        }
    }
    if request_id:
        body["error"]["request_id"] = request_id
    return body


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Middleware that converts unhandled exceptions to JSON error responses."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Response]
    ) -> Response:
        """Process request and catch unhandled exceptions.

        Args:
            request: Incoming HTTP request.
            call_next: Next middleware/endpoint in chain.

        Returns:
            HTTP response (normal or error JSON).
        """
        request_id: str | None = getattr(request.state, "request_id", None)

        try:
            return await call_next(request)

        except HTTPException as exc:
            # FastAPI HTTPExceptions — preserve status code and detail
            logger.warning(
                f"HTTPException {exc.status_code}: {exc.detail} | "
                f"path={request.url.path} request_id={request_id}",
            )
            return JSONResponse(
                status_code=exc.status_code,
                content=_build_error_body(
                    error_type="http_error",
                    message=str(exc.detail),
                    request_id=request_id,
                    status_code=exc.status_code,
                ),
            )

        except ValidationError as exc:
            # Pydantic validation errors — 422 Unprocessable Entity
            error_count = exc.error_count()
            logger.warning(
                f"ValidationError ({error_count} errors): {exc.title} | "
                f"path={request.url.path} request_id={request_id}",
            )
            return JSONResponse(
                status_code=422,
                content=_build_error_body(
                    error_type="validation_error",
                    message=f"Validation failed with {error_count} error(s)",
                    request_id=request_id,
                    status_code=422,
                ),
            )

        except Exception as exc:
            # Catch-all for unexpected errors — 500 Internal Server Error
            logger.error(
                f"Unhandled {type(exc).__name__}: {exc} | "
                f"path={request.url.path} request_id={request_id}",
                exc_info=True,
            )
            return JSONResponse(
                status_code=500,
                content=_build_error_body(
                    error_type="internal_error",
                    message="An unexpected error occurred",
                    request_id=request_id,
                    status_code=500,
                ),
            )
