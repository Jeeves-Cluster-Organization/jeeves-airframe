"""Health check endpoints for production monitoring.

Provides /health and /ready endpoints following Kubernetes conventions:
- /health: Liveness check (is the service running?)
- /ready: Readiness check (can the service accept requests?)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from time import monotonic
from typing import Any, Dict, Optional

from jeeves_infra.protocols import DatabaseClientProtocol, HealthStatus
from mission_system.config.constants import PLATFORM_VERSION


class ComponentStatus(str, Enum):
    """Individual component status values."""

    UP = "up"
    DOWN = "down"
    DEGRADED = "degraded"


@dataclass
class ComponentHealth:
    """Health status for an individual component."""

    status: ComponentStatus
    message: Optional[str] = None
    latency_ms: Optional[float] = None
    last_check: Optional[datetime] = None


@dataclass
class HealthCheckResult:
    """Complete health check result."""

    status: HealthStatus
    timestamp: datetime
    uptime_seconds: float
    components: Dict[str, ComponentHealth]
    version: str = PLATFORM_VERSION


class HealthChecker:
    """Performs health checks on system components."""

    def __init__(
        self,
        db: DatabaseClientProtocol,
        *,
        database_timeout: float = 2.0,
        model_timeout: float = 5.0,
    ) -> None:
        """Initialize health checker.

        Args:
            db: Database client for persistence checks
            database_timeout: Timeout for database health checks (seconds)
            model_timeout: Timeout for model health checks (seconds)
        """
        self.db = db
        self.database_timeout = database_timeout
        self.model_timeout = model_timeout
        self._start_time = monotonic()

    async def check_liveness(self) -> HealthCheckResult:
        """Perform liveness check (basic service availability).

        This is a lightweight check that only verifies the service is running.
        Kubernetes uses this to determine if the pod should be restarted.
        """
        now = datetime.now(timezone.utc)
        uptime = monotonic() - self._start_time

        return HealthCheckResult(
            status=HealthStatus.HEALTHY,
            timestamp=now,
            uptime_seconds=uptime,
            components={
                "api": ComponentHealth(
                    status=ComponentStatus.UP,
                    message="Service is running",
                    last_check=now,
                )
            },
        )

    async def check_readiness(self) -> HealthCheckResult:
        """Perform readiness check (can accept traffic).

        This checks all critical dependencies (database, models, etc.).
        Kubernetes uses this to determine if the pod should receive traffic.
        """
        now = datetime.now(timezone.utc)
        uptime = monotonic() - self._start_time

        components: Dict[str, ComponentHealth] = {}

        # Check database connectivity
        db_health = await self._check_database()
        components["database"] = db_health

        # Check LLM model availability
        model_health = await self._check_models()
        components["models"] = model_health

        # Determine overall status
        statuses = [comp.status for comp in components.values()]
        if any(s == ComponentStatus.DOWN for s in statuses):
            overall_status = HealthStatus.UNHEALTHY
        elif any(s == ComponentStatus.DEGRADED for s in statuses):
            overall_status = HealthStatus.DEGRADED
        else:
            overall_status = HealthStatus.HEALTHY

        return HealthCheckResult(
            status=overall_status,
            timestamp=now,
            uptime_seconds=uptime,
            components=components,
        )

    async def _check_database(self) -> ComponentHealth:
        """Check database connectivity and responsiveness."""
        start = monotonic()

        try:
            # Simple query to verify database is responsive
            async with asyncio.timeout(self.database_timeout):
                # Test a basic query - check if requests table exists
                # Use PostgreSQL-compatible query (information_schema)
                result = await self.db.fetch_one(
                    """SELECT table_name FROM information_schema.tables
                       WHERE table_schema = 'public' AND table_name = 'requests'"""
                )

                if result is None:
                    return ComponentHealth(
                        status=ComponentStatus.DOWN,
                        message="Database schema not initialized",
                        latency_ms=(monotonic() - start) * 1000,
                        last_check=datetime.now(timezone.utc),
                    )

                latency_ms = (monotonic() - start) * 1000

                # Check if latency is concerning
                if latency_ms > 1000:  # >1s is degraded
                    status = ComponentStatus.DEGRADED
                    message = f"Database responding slowly ({latency_ms:.1f}ms)"
                else:
                    status = ComponentStatus.UP
                    message = "Database operational"

                return ComponentHealth(
                    status=status,
                    message=message,
                    latency_ms=latency_ms,
                    last_check=datetime.now(timezone.utc),
                )

        except asyncio.TimeoutError:
            return ComponentHealth(
                status=ComponentStatus.DOWN,
                message=f"Database timeout (>{self.database_timeout}s)",
                latency_ms=(monotonic() - start) * 1000,
                last_check=datetime.now(timezone.utc),
            )
        except Exception as exc:
            return ComponentHealth(
                status=ComponentStatus.DOWN,
                message=f"Database error: {str(exc)}",
                latency_ms=(monotonic() - start) * 1000,
                last_check=datetime.now(timezone.utc),
            )

    async def _check_models(self) -> ComponentHealth:
        """Check if LLM models are available and responsive.

        Checks the configured LLM provider for availability:
        - llamaserver: HTTP health check to llama.cpp server
        - openai/anthropic/azure: API key presence check
        - mock: Always returns UP
        - llamacpp: Model file existence check
        """
        import os

        start = monotonic()

        try:
            from mission_system.adapters import get_settings
            settings = get_settings()
            provider = settings.llm_provider.lower()

            if provider == "mock":
                # Mock mode is always healthy
                return ComponentHealth(
                    status=ComponentStatus.UP,
                    message="Mock LLM provider (no external dependency)",
                    latency_ms=(monotonic() - start) * 1000,
                    last_check=datetime.now(timezone.utc),
                )

            elif provider == "llamaserver":
                # Check llama.cpp server health endpoint
                import aiohttp

                base_url = settings.llamaserver_host.rstrip('/')
                health_url = f"{base_url}/health"

                try:
                    async with asyncio.timeout(self.model_timeout):
                        async with aiohttp.ClientSession() as session:
                            async with session.get(health_url) as response:
                                latency_ms = (monotonic() - start) * 1000

                                if response.status == 200:
                                    data = await response.json()
                                    status_str = data.get("status", "unknown")
                                    if status_str == "ok":
                                        return ComponentHealth(
                                            status=ComponentStatus.UP,
                                            message=f"llama-server healthy at {settings.llamaserver_host}",
                                            latency_ms=latency_ms,
                                            last_check=datetime.now(timezone.utc),
                                        )
                                    else:
                                        return ComponentHealth(
                                            status=ComponentStatus.DEGRADED,
                                            message=f"llama-server status: {status_str}",
                                            latency_ms=latency_ms,
                                            last_check=datetime.now(timezone.utc),
                                        )
                                else:
                                    return ComponentHealth(
                                        status=ComponentStatus.DOWN,
                                        message=f"llama-server returned HTTP {response.status}",
                                        latency_ms=latency_ms,
                                        last_check=datetime.now(timezone.utc),
                                    )
                except aiohttp.ClientError as e:
                    return ComponentHealth(
                        status=ComponentStatus.DOWN,
                        message=f"llama-server unreachable: {str(e)[:80]}",
                        latency_ms=(monotonic() - start) * 1000,
                        last_check=datetime.now(timezone.utc),
                    )

            elif provider == "openai":
                # Check OpenAI API key is configured
                if not settings.openai_api_key:
                    return ComponentHealth(
                        status=ComponentStatus.DOWN,
                        message="OpenAI API key not configured (OPENAI_API_KEY)",
                        latency_ms=(monotonic() - start) * 1000,
                        last_check=datetime.now(timezone.utc),
                    )
                return ComponentHealth(
                    status=ComponentStatus.UP,
                    message="OpenAI API key configured",
                    latency_ms=(monotonic() - start) * 1000,
                    last_check=datetime.now(timezone.utc),
                )

            elif provider == "anthropic":
                # Check Anthropic API key is configured
                if not settings.anthropic_api_key:
                    return ComponentHealth(
                        status=ComponentStatus.DOWN,
                        message="Anthropic API key not configured (ANTHROPIC_API_KEY)",
                        latency_ms=(monotonic() - start) * 1000,
                        last_check=datetime.now(timezone.utc),
                    )
                return ComponentHealth(
                    status=ComponentStatus.UP,
                    message="Anthropic API key configured",
                    latency_ms=(monotonic() - start) * 1000,
                    last_check=datetime.now(timezone.utc),
                )

            elif provider == "azure":
                # Check Azure configuration is complete
                if not all([settings.azure_endpoint, settings.azure_api_key, settings.azure_deployment_name]):
                    missing = []
                    if not settings.azure_endpoint:
                        missing.append("AZURE_ENDPOINT")
                    if not settings.azure_api_key:
                        missing.append("AZURE_API_KEY")
                    if not settings.azure_deployment_name:
                        missing.append("AZURE_DEPLOYMENT_NAME")
                    return ComponentHealth(
                        status=ComponentStatus.DOWN,
                        message=f"Azure config incomplete: missing {', '.join(missing)}",
                        latency_ms=(monotonic() - start) * 1000,
                        last_check=datetime.now(timezone.utc),
                    )
                return ComponentHealth(
                    status=ComponentStatus.UP,
                    message=f"Azure configured for deployment: {settings.azure_deployment_name}",
                    latency_ms=(monotonic() - start) * 1000,
                    last_check=datetime.now(timezone.utc),
                )

            elif provider == "llamacpp":
                # Check model file exists
                model_path = settings.llamacpp_model_path
                if not os.path.exists(model_path):
                    return ComponentHealth(
                        status=ComponentStatus.DOWN,
                        message=f"Model file not found: {model_path}",
                        latency_ms=(monotonic() - start) * 1000,
                        last_check=datetime.now(timezone.utc),
                    )
                return ComponentHealth(
                    status=ComponentStatus.UP,
                    message=f"llama.cpp model available: {os.path.basename(model_path)}",
                    latency_ms=(monotonic() - start) * 1000,
                    last_check=datetime.now(timezone.utc),
                )

            else:
                return ComponentHealth(
                    status=ComponentStatus.DEGRADED,
                    message=f"Unknown LLM provider: {provider}",
                    latency_ms=(monotonic() - start) * 1000,
                    last_check=datetime.now(timezone.utc),
                )

        except asyncio.TimeoutError:
            return ComponentHealth(
                status=ComponentStatus.DOWN,
                message=f"LLM provider timeout (>{self.model_timeout}s)",
                latency_ms=(monotonic() - start) * 1000,
                last_check=datetime.now(timezone.utc),
            )
        except ImportError as e:
            # avionics might not be available in all contexts
            return ComponentHealth(
                status=ComponentStatus.DEGRADED,
                message=f"Settings unavailable: {str(e)[:50]}",
                latency_ms=(monotonic() - start) * 1000,
                last_check=datetime.now(timezone.utc),
            )
        except Exception as exc:
            return ComponentHealth(
                status=ComponentStatus.DOWN,
                message=f"LLM provider error: {str(exc)[:80]}",
                latency_ms=(monotonic() - start) * 1000,
                last_check=datetime.now(timezone.utc),
            )


def health_check_to_dict(result: HealthCheckResult) -> Dict[str, Any]:
    """Convert HealthCheckResult to dictionary for API response."""
    return {
        "status": result.status.value,
        "timestamp": result.timestamp.isoformat(),
        "uptime_seconds": result.uptime_seconds,
        "version": result.version,
        "components": {
            name: {
                "status": comp.status.value,
                "message": comp.message,
                "latency_ms": comp.latency_ms,
                "last_check": comp.last_check.isoformat() if comp.last_check else None,
            }
            for name, comp in result.components.items()
        },
    }
