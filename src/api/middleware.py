"""Request-level middleware: correlation IDs, structured access logging."""

from __future__ import annotations

import time
import uuid

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = structlog.get_logger(__name__)

_CORRELATION_HEADER = "X-Correlation-ID"
_REQUEST_ID_HEADER = "X-Request-ID"


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """Attach a correlation ID to every request.

    If the caller provides ``X-Correlation-ID`` the value is forwarded as-is.
    Otherwise a UUID4 is generated.  The ID is available via
    ``request.state.correlation_id`` and echoed in the response header.
    """

    async def dispatch(self, request: Request, call_next: "callable") -> Response:
        correlation_id = (
            request.headers.get(_CORRELATION_HEADER)
            or request.headers.get(_REQUEST_ID_HEADER)
            or uuid.uuid4().hex
        )
        request.state.correlation_id = correlation_id

        # Bind to structlog context so every log line in this request includes it
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            correlation_id=correlation_id,
            method=request.method,
            path=request.url.path,
        )

        t0 = time.monotonic()
        response = await call_next(request)
        elapsed = (time.monotonic() - t0) * 1000

        response.headers[_CORRELATION_HEADER] = correlation_id

        logger.info(
            "http.request",
            status_code=response.status_code,
            elapsed_ms=round(elapsed, 2),
        )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add basic security headers to all responses."""

    async def dispatch(self, request: Request, call_next: "callable") -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
        return response
