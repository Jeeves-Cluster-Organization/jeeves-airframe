from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Optional

from .endpoints import EndpointSpec, HealthState, BackendKind

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None


class HealthProbe(ABC):
    @abstractmethod
    async def check(self, endpoint: EndpointSpec) -> HealthState:
        ...


class HttpHealthProbe(HealthProbe):
    """
    HTTP-based health probe for inference endpoints.

    Supports backend-specific health paths:
    - llama_server: GET /health
    - openai_chat: GET /v1/models (or /health if available)
    - anthropic_messages: GET /v1/messages (HEAD request)
    """

    def __init__(self, timeout: float = 5.0):
        self.timeout = timeout

    def _get_health_path(self, endpoint: EndpointSpec) -> str:
        """Return the health check path for a given backend kind."""
        if endpoint.backend_kind == BackendKind.LLAMA_SERVER:
            return "/health"
        elif endpoint.backend_kind == BackendKind.OPENAI_CHAT:
            return "/v1/models"
        elif endpoint.backend_kind == BackendKind.ANTHROPIC_MESSAGES:
            return "/v1/messages"
        return "/health"

    async def check(self, endpoint: EndpointSpec) -> HealthState:
        if httpx is None:
            return HealthState(
                status="unknown",
                checked_at=time.time(),
                detail="httpx not installed",
            )

        base_url = endpoint.base_url.rstrip("/")
        path = self._get_health_path(endpoint)
        url = f"{base_url}{path}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Use HEAD for anthropic to avoid auth requirements
                if endpoint.backend_kind == BackendKind.ANTHROPIC_MESSAGES:
                    resp = await client.head(url)
                else:
                    resp = await client.get(url)

                if resp.status_code < 400:
                    return HealthState(
                        status="healthy",
                        checked_at=time.time(),
                        detail=f"HTTP {resp.status_code}",
                    )
                elif resp.status_code < 500:
                    return HealthState(
                        status="degraded",
                        checked_at=time.time(),
                        detail=f"HTTP {resp.status_code}",
                    )
                else:
                    return HealthState(
                        status="unhealthy",
                        checked_at=time.time(),
                        detail=f"HTTP {resp.status_code}",
                    )

        except httpx.TimeoutException:
            return HealthState(
                status="unhealthy",
                checked_at=time.time(),
                detail="timeout",
            )
        except httpx.ConnectError as exc:
            return HealthState(
                status="unhealthy",
                checked_at=time.time(),
                detail=f"connection error: {exc}",
            )
        except Exception as exc:
            return HealthState(
                status="unknown",
                checked_at=time.time(),
                detail=f"probe error: {type(exc).__name__}: {exc}",
            )
