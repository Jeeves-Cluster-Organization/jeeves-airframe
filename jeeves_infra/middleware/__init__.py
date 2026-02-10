"""Middleware Module.

Provides middleware components for the API layer:
- RateLimitMiddleware: Request rate limiting
- AuthMiddleware: Authentication (future)
- CorsMiddleware: CORS handling (future)

Constitutional Reference: Infrastructure layer (jeeves_infra)
"""

from jeeves_infra.middleware.rate_limit import (
    RateLimitMiddleware,
    RateLimitError,
    create_rate_limit_middleware,
)

__all__ = [
    "RateLimitMiddleware",
    "RateLimitError",
    "create_rate_limit_middleware",
]
