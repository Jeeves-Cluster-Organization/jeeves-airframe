"""Rate Limit Middleware — thin HTTP wrapper around kernel CheckRateLimit.

Extracts user identity from the request, calls kernel_client.check_rate_limit(),
and returns HTTP 429 with Retry-After when the kernel says "exceeded".
"""

import time
from typing import Any, Callable, Dict, Optional

from jeeves_infra.protocols import LoggerProtocol


class RateLimitError(Exception):
    """Raised when the kernel reports rate limit exceeded."""

    def __init__(self, user_id: str, endpoint: str, result: Dict[str, Any]):
        self.user_id = user_id
        self.endpoint = endpoint
        self.result = result
        retry = result.get("retry_after_seconds", 0)
        super().__init__(f"Rate limit exceeded for {user_id} on {endpoint} (retry in {retry}s)")

    def to_response_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {
            "X-RateLimit-Limit": str(self.result.get("limit", 0)),
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(int(time.time() + self.result.get("retry_after_seconds", 0))),
        }
        retry = self.result.get("retry_after_seconds", 0)
        if retry > 0:
            headers["Retry-After"] = str(int(retry))
        return headers


SKIP_ENDPOINTS = ("/health", "/ready", "/metrics")


class RateLimitMiddleware:
    """ASGI middleware that delegates rate limiting to the Rust kernel."""

    def __init__(self, kernel_client, logger: Optional[LoggerProtocol] = None):
        self._kernel_client = kernel_client
        self._logger = logger

    async def __call__(self, request: Any, call_next: Callable) -> Any:
        endpoint = getattr(getattr(request, "url", None), "path", "default")
        if endpoint in SKIP_ENDPOINTS:
            return await call_next(request)

        user_id = self._extract_user_id(request)

        try:
            result = await self._kernel_client.check_rate_limit(user_id, endpoint)
        except Exception as exc:
            if self._logger:
                self._logger.error("rate_limit_check_failed", user_id=user_id, endpoint=endpoint, error=str(exc))
            try:
                from starlette.responses import JSONResponse
                return JSONResponse(
                    status_code=503,
                    content={"error": "rate_limit_unavailable", "detail": "Rate limiting service is unavailable"},
                )
            except ImportError:
                return {"status_code": 503, "error": "rate_limit_unavailable"}

        if result.get("exceeded", False):
            if self._logger:
                self._logger.warning("rate_limit_exceeded", user_id=user_id, endpoint=endpoint)
            error = RateLimitError(user_id, endpoint, result)
            try:
                from starlette.responses import JSONResponse
                return JSONResponse(
                    status_code=429,
                    content={"error": "rate_limit_exceeded", "retry_after_seconds": result.get("retry_after_seconds", 0)},
                    headers=error.to_response_headers(),
                )
            except ImportError:
                return {"status_code": 429, "error": "rate_limit_exceeded", "headers": error.to_response_headers()}

        return await call_next(request)

    @staticmethod
    def _extract_user_id(request: Any) -> str:
        if hasattr(request, "state") and hasattr(request.state, "user"):
            user = request.state.user
            if hasattr(user, "id"):
                return str(user.id)
        if hasattr(request, "headers") and "X-User-ID" in request.headers:
            return request.headers["X-User-ID"]
        if hasattr(request, "client") and request.client:
            return request.client.host
        return "anonymous"
