"""Request Body Size Limit Middleware.

Rejects requests whose Content-Length exceeds a configurable maximum.
For chunked transfers (no Content-Length), reads up to the limit and aborts.
"""

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

# 1 MB default — override via MAX_REQUEST_BODY_BYTES env var or constructor arg
DEFAULT_MAX_BYTES = 1 * 1024 * 1024


class BodyLimitMiddleware:
    """ASGI middleware that enforces a request body size ceiling."""

    def __init__(self, app: ASGIApp, max_bytes: int = DEFAULT_MAX_BYTES):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Fast path: check Content-Length header if present
        headers = dict(scope.get("headers", []))
        content_length_raw = headers.get(b"content-length")
        if content_length_raw is not None:
            try:
                content_length = int(content_length_raw)
            except (ValueError, TypeError):
                content_length = 0
            if content_length > self.max_bytes:
                response = JSONResponse(
                    status_code=413,
                    content={
                        "error": "request_too_large",
                        "detail": f"Request body exceeds {self.max_bytes} bytes",
                        "max_bytes": self.max_bytes,
                    },
                )
                await response(scope, receive, send)
                return

        # For chunked transfers: wrap receive to count bytes
        bytes_received = 0
        limit = self.max_bytes

        async def limited_receive() -> dict:
            nonlocal bytes_received
            message = await receive()
            if message.get("type") == "http.request":
                body = message.get("body", b"")
                bytes_received += len(body)
                if bytes_received > limit:
                    raise _BodyTooLarge()
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _BodyTooLarge:
            response = JSONResponse(
                status_code=413,
                content={
                    "error": "request_too_large",
                    "detail": f"Request body exceeds {self.max_bytes} bytes",
                    "max_bytes": self.max_bytes,
                },
            )
            await response(scope, receive, send)


class _BodyTooLarge(Exception):
    """Internal signal — not part of the public API."""
