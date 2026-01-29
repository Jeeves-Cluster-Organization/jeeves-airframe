"""Rate Limit Middleware for API layer.

Provides middleware for rate limiting API requests. Integrates with
the ResourceTracker and RateLimiter.

Architecture:
- RateLimiter defines and tracks limits
- This middleware enforces at the API boundary
- Returns standard HTTP 429 responses with Retry-After header

Usage with FastAPI:
    from jeeves_infra.middleware import RateLimitMiddleware

    app = FastAPI()
    rate_limiter = RateLimiter(logger)
    middleware = RateLimitMiddleware(rate_limiter)

    @app.middleware("http")
    async def rate_limit(request, call_next):
        return await middleware(request, call_next)

Usage with generic ASGI:
    middleware = create_rate_limit_middleware(rate_limiter)
    app = middleware(app)

Constitutional Reference: API layer integration with ResourceTracker
"""

import functools
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, TypeVar

from jeeves_infra.protocols import (
    LoggerProtocol,
    RateLimitResult,
    RateLimitConfig,
    RateLimiterProtocol,
)


class RateLimitError(Exception):
    """Exception raised when rate limit is exceeded.

    Attributes:
        result: The rate limit check result
        user_id: User who exceeded the limit
        endpoint: Endpoint that was rate limited
    """

    def __init__(
        self,
        result: RateLimitResult,
        user_id: str,
        endpoint: str,
    ):
        self.result = result
        self.user_id = user_id
        self.endpoint = endpoint
        super().__init__(result.reason or "Rate limit exceeded")

    def to_response_headers(self) -> Dict[str, str]:
        """Generate HTTP headers for rate limit response.

        Returns:
            Headers including Retry-After and rate limit info
        """
        headers = {
            "X-RateLimit-Limit": str(self.result.limit),
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(int(time.time() + self.result.retry_after_seconds)),
        }

        if self.result.retry_after_seconds > 0:
            headers["Retry-After"] = str(int(self.result.retry_after_seconds))

        return headers


@dataclass
class RateLimitMiddlewareConfig:
    """Configuration for rate limit middleware.

    Attributes:
        enabled: Whether rate limiting is enabled
        user_id_extractor: Function to extract user ID from request
        endpoint_extractor: Function to extract endpoint from request
        skip_endpoints: Endpoints to skip rate limiting (e.g., health checks)
        include_headers: Whether to include rate limit headers in responses
    """
    enabled: bool = True
    skip_endpoints: tuple = ("/health", "/ready", "/metrics")
    include_headers: bool = True


class RateLimitMiddleware:
    """Middleware for API rate limiting.

    Enforces rate limits at the API layer using Control Tower's RateLimiter.
    Works with any ASGI-compatible framework.

    Response Headers (when include_headers=True):
    - X-RateLimit-Limit: Maximum requests allowed
    - X-RateLimit-Remaining: Requests remaining in current window
    - X-RateLimit-Reset: Unix timestamp when limit resets
    - Retry-After: Seconds until request would be allowed (on 429)
    """

    def __init__(
        self,
        rate_limiter: RateLimiterProtocol,
        config: Optional[RateLimitMiddlewareConfig] = None,
        logger: Optional[LoggerProtocol] = None,
    ):
        """Initialize rate limit middleware.

        Args:
            rate_limiter: RateLimiter implementing RateLimiterProtocol
            config: Middleware configuration
            logger: Optional logger
        """
        self._rate_limiter = rate_limiter
        self._config = config or RateLimitMiddlewareConfig()
        self._logger = logger

    def check_rate_limit(
        self,
        user_id: str,
        endpoint: str,
    ) -> RateLimitResult:
        """Check if a request is within rate limits.

        Args:
            user_id: User making the request
            endpoint: Endpoint being accessed

        Returns:
            RateLimitResult

        Raises:
            RateLimitError: If rate limit is exceeded
        """
        if not self._config.enabled:
            return RateLimitResult.ok()

        # Skip certain endpoints
        if endpoint in self._config.skip_endpoints:
            return RateLimitResult.ok()

        result = self._rate_limiter.check_rate_limit(user_id, endpoint)

        if result.exceeded:
            if self._logger:
                self._logger.warning(
                    "rate_limit_exceeded_api",
                    user_id=user_id,
                    endpoint=endpoint,
                    limit_type=result.limit_type,
                    retry_after=result.retry_after_seconds,
                )
            raise RateLimitError(result, user_id, endpoint)

        return result

    def get_response_headers(self, result: RateLimitResult) -> Dict[str, str]:
        """Generate rate limit response headers.

        Args:
            result: Rate limit check result

        Returns:
            Headers to include in response
        """
        if not self._config.include_headers:
            return {}

        return {
            "X-RateLimit-Remaining": str(result.remaining),
        }

    async def __call__(
        self,
        request: Any,
        call_next: Callable,
        user_id: Optional[str] = None,
        endpoint: Optional[str] = None,
    ) -> Any:
        """Process a request through the middleware.

        Generic interface that can be adapted to different frameworks.

        Args:
            request: The incoming request
            call_next: Function to call the next handler
            user_id: User ID (extracted from request if not provided)
            endpoint: Endpoint (extracted from request if not provided)

        Returns:
            Response from the next handler or error response
        """
        # Extract user_id if not provided
        if user_id is None:
            user_id = self._extract_user_id(request)

        # Extract endpoint if not provided
        if endpoint is None:
            endpoint = self._extract_endpoint(request)

        try:
            result = self.check_rate_limit(user_id, endpoint)

            # Call next handler
            response = await call_next(request)

            # Add rate limit headers to response
            headers = self.get_response_headers(result)
            if headers and hasattr(response, "headers"):
                for key, value in headers.items():
                    response.headers[key] = value

            return response

        except RateLimitError as e:
            return self._create_rate_limit_response(e, request)

    def _extract_user_id(self, request: Any) -> str:
        """Extract user ID from request.

        Override this method for custom extraction logic.
        Default: looks for user in request state or returns IP.
        """
        # Try common patterns
        if hasattr(request, "state") and hasattr(request.state, "user"):
            user = request.state.user
            if hasattr(user, "id"):
                return str(user.id)
            if isinstance(user, dict) and "id" in user:
                return str(user["id"])

        # Try headers
        if hasattr(request, "headers"):
            if "X-User-ID" in request.headers:
                return request.headers["X-User-ID"]
            if "Authorization" in request.headers:
                # Hash the auth header as a user identifier
                import hashlib
                auth = request.headers["Authorization"]
                return hashlib.md5(auth.encode()).hexdigest()[:16]

        # Fall back to client IP
        if hasattr(request, "client") and request.client:
            return request.client.host

        return "anonymous"

    def _extract_endpoint(self, request: Any) -> str:
        """Extract endpoint from request.

        Override this method for custom extraction logic.
        """
        if hasattr(request, "url") and hasattr(request.url, "path"):
            return request.url.path
        if hasattr(request, "path"):
            return request.path
        return "default"

    def _create_rate_limit_response(
        self,
        error: RateLimitError,
        request: Any,
    ) -> Any:
        """Create a rate limit error response.

        Override this method for framework-specific responses.
        Default returns a dict that can be converted to JSON.
        """
        # Try to use framework-specific response
        try:
            from starlette.responses import JSONResponse
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "message": error.result.reason,
                    "retry_after_seconds": error.result.retry_after_seconds,
                },
                headers=error.to_response_headers(),
            )
        except ImportError:
            pass

        # Generic response dict
        return {
            "status_code": 429,
            "error": "rate_limit_exceeded",
            "message": error.result.reason,
            "headers": error.to_response_headers(),
        }


def create_rate_limit_middleware(
    rate_limiter: RateLimiterProtocol,
    config: Optional[RateLimitMiddlewareConfig] = None,
    logger: Optional[LoggerProtocol] = None,
) -> RateLimitMiddleware:
    """Factory function to create rate limit middleware.

    Args:
        rate_limiter: RateLimiter implementing RateLimiterProtocol
        config: Optional configuration
        logger: Optional logger

    Returns:
        Configured RateLimitMiddleware instance
    """
    return RateLimitMiddleware(rate_limiter, config, logger)


def rate_limit(
    rate_limiter: RateLimiterProtocol,
    user_id_param: str = "user_id",
    endpoint: Optional[str] = None,
) -> Callable:
    """Decorator for rate limiting individual functions.

    Args:
        rate_limiter: RateLimiter instance
        user_id_param: Name of the parameter containing user ID
        endpoint: Optional endpoint name (defaults to function name)

    Returns:
        Decorator function

    Example:
        @rate_limit(limiter, user_id_param="user_id")
        async def my_endpoint(user_id: str):
            ...
    """
    def decorator(func: Callable) -> Callable:
        func_endpoint = endpoint or func.__name__

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Extract user_id
            user_id = kwargs.get(user_id_param, "anonymous")

            # Check rate limit
            result = rate_limiter.check_rate_limit(user_id, func_endpoint)
            if result.exceeded:
                raise RateLimitError(result, user_id, func_endpoint)

            return await func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            user_id = kwargs.get(user_id_param, "anonymous")

            result = rate_limiter.check_rate_limit(user_id, func_endpoint)
            if result.exceeded:
                raise RateLimitError(result, user_id, func_endpoint)

            return func(*args, **kwargs)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator
