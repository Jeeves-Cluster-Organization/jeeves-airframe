from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Awaitable, Callable, Iterable, List, Optional

from .endpoints import EndpointSpec, HealthState

if TYPE_CHECKING:
    from .health import HealthProbe


class WatchHandle:
    def __init__(self, task: Optional[asyncio.Task] = None):
        self._task = task

    def cancel(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()


class EndpointRegistry(ABC):
    @abstractmethod
    def list_endpoints(self) -> List[EndpointSpec]:
        ...

    @abstractmethod
    def get_health(self, name: str) -> Optional[HealthState]:
        ...

    @abstractmethod
    def watch(
        self, callback: Callable[[List[EndpointSpec]], Awaitable[None]]
    ) -> WatchHandle:
        """
        Callback receives the full snapshot when changes occur.
        """
        ...


class StaticRegistry(EndpointRegistry):
    """
    Static endpoint registry with optional health probing.

    Usage:
        # Basic (no health checking)
        registry = StaticRegistry([endpoint1, endpoint2])

        # With health checking
        from airframe.health import HttpHealthProbe
        registry = StaticRegistry([endpoint1], health_probe=HttpHealthProbe())
        await registry.check_health()  # One-time check
        registry.start_health_monitor(interval=30.0)  # Background monitoring
    """

    def __init__(
        self,
        endpoints: Iterable[EndpointSpec],
        health_probe: Optional["HealthProbe"] = None,
    ):
        self._endpoints = list(endpoints)
        self._health = {e.name: HealthState(status="unknown") for e in self._endpoints}
        self._health_probe = health_probe
        self._health_monitor_handle: Optional[WatchHandle] = None

    def list_endpoints(self) -> List[EndpointSpec]:
        return list(self._endpoints)

    def get_health(self, name: str) -> Optional[HealthState]:
        return self._health.get(name)

    def set_health(self, name: str, state: HealthState) -> None:
        """Manually update health state for an endpoint."""
        if name in self._health:
            self._health[name] = state

    def list_healthy_endpoints(self) -> List[EndpointSpec]:
        """Return only endpoints with healthy status."""
        return [
            e for e in self._endpoints
            if self._health.get(e.name, HealthState(status="unknown")).status == "healthy"
        ]

    async def check_health(self) -> None:
        """Check health of all endpoints using the configured probe."""
        if self._health_probe is None:
            return

        for endpoint in self._endpoints:
            state = await self._health_probe.check(endpoint)
            self._health[endpoint.name] = state

    async def check_health_for(self, name: str) -> Optional[HealthState]:
        """Check health of a specific endpoint by name."""
        if self._health_probe is None:
            return None

        for endpoint in self._endpoints:
            if endpoint.name == name:
                state = await self._health_probe.check(endpoint)
                self._health[name] = state
                return state
        return None

    def start_health_monitor(self, interval: float = 30.0) -> WatchHandle:
        """
        Start background health monitoring.

        Args:
            interval: Seconds between health checks (default 30s)

        Returns:
            WatchHandle that can be used to cancel monitoring
        """
        if self._health_probe is None:
            return WatchHandle()

        async def monitor():
            while True:
                try:
                    await self.check_health()
                except asyncio.CancelledError:
                    break
                except Exception:
                    # Swallow errors to keep monitoring alive
                    pass
                await asyncio.sleep(interval)

        task = asyncio.create_task(monitor())
        self._health_monitor_handle = WatchHandle(task)
        return self._health_monitor_handle

    def stop_health_monitor(self) -> None:
        """Stop background health monitoring if running."""
        if self._health_monitor_handle:
            self._health_monitor_handle.cancel()
            self._health_monitor_handle = None

    def watch(
        self, callback: Callable[[List[EndpointSpec]], Awaitable[None]]
    ) -> WatchHandle:
        async def fire_once():
            await callback(self.list_endpoints())

        task = asyncio.create_task(fire_once())
        return WatchHandle(task)
