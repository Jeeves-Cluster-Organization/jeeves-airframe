import asyncio

import pytest

from airframe.endpoints import EndpointSpec, BackendKind, HealthState
from airframe.registry import StaticRegistry


@pytest.mark.asyncio
async def test_static_registry_watch_once():
    ep = EndpointSpec(
        name="local",
        base_url="http://localhost:8080",
        backend_kind=BackendKind.LLAMA_SERVER,
    )
    registry = StaticRegistry([ep])

    called = asyncio.Event()

    async def cb(snapshot):
        assert snapshot[0].name == "local"
        called.set()

    handle = registry.watch(cb)
    await asyncio.wait_for(called.wait(), timeout=1.0)
    handle.cancel()


def test_static_registry_list_endpoints():
    ep1 = EndpointSpec(name="ep1", base_url="http://a", backend_kind=BackendKind.LLAMA_SERVER)
    ep2 = EndpointSpec(name="ep2", base_url="http://b", backend_kind=BackendKind.OPENAI_CHAT)
    registry = StaticRegistry([ep1, ep2])

    endpoints = registry.list_endpoints()
    assert len(endpoints) == 2
    assert endpoints[0].name == "ep1"
    assert endpoints[1].name == "ep2"


def test_static_registry_get_health_unknown():
    ep = EndpointSpec(name="test", base_url="http://x", backend_kind=BackendKind.LLAMA_SERVER)
    registry = StaticRegistry([ep])

    health = registry.get_health("test")
    assert health is not None
    assert health.status == "unknown"


def test_static_registry_get_health_missing():
    ep = EndpointSpec(name="test", base_url="http://x", backend_kind=BackendKind.LLAMA_SERVER)
    registry = StaticRegistry([ep])

    health = registry.get_health("nonexistent")
    assert health is None


def test_static_registry_set_health():
    ep = EndpointSpec(name="test", base_url="http://x", backend_kind=BackendKind.LLAMA_SERVER)
    registry = StaticRegistry([ep])

    registry.set_health("test", HealthState(status="healthy", detail="ok"))
    health = registry.get_health("test")

    assert health.status == "healthy"
    assert health.detail == "ok"


def test_static_registry_set_health_nonexistent():
    ep = EndpointSpec(name="test", base_url="http://x", backend_kind=BackendKind.LLAMA_SERVER)
    registry = StaticRegistry([ep])

    # Should not raise, just silently ignore
    registry.set_health("nonexistent", HealthState(status="healthy"))
    assert registry.get_health("nonexistent") is None


def test_static_registry_list_healthy_endpoints():
    ep1 = EndpointSpec(name="ep1", base_url="http://a", backend_kind=BackendKind.LLAMA_SERVER)
    ep2 = EndpointSpec(name="ep2", base_url="http://b", backend_kind=BackendKind.LLAMA_SERVER)
    ep3 = EndpointSpec(name="ep3", base_url="http://c", backend_kind=BackendKind.LLAMA_SERVER)
    registry = StaticRegistry([ep1, ep2, ep3])

    # Mark ep1 as healthy, ep2 as unhealthy, ep3 stays unknown
    registry.set_health("ep1", HealthState(status="healthy"))
    registry.set_health("ep2", HealthState(status="unhealthy"))

    healthy = registry.list_healthy_endpoints()
    assert len(healthy) == 1
    assert healthy[0].name == "ep1"


def test_static_registry_with_probe_none():
    ep = EndpointSpec(name="test", base_url="http://x", backend_kind=BackendKind.LLAMA_SERVER)
    registry = StaticRegistry([ep], health_probe=None)

    # Should work fine without probe
    assert registry.list_endpoints()[0].name == "test"


class MockHealthProbe:
    """Mock health probe for testing."""

    def __init__(self, return_status="healthy"):
        self.return_status = return_status
        self.check_count = 0

    async def check(self, endpoint):
        self.check_count += 1
        return HealthState(status=self.return_status, detail=f"checked {endpoint.name}")


@pytest.mark.asyncio
async def test_static_registry_check_health():
    ep1 = EndpointSpec(name="ep1", base_url="http://a", backend_kind=BackendKind.LLAMA_SERVER)
    ep2 = EndpointSpec(name="ep2", base_url="http://b", backend_kind=BackendKind.LLAMA_SERVER)

    probe = MockHealthProbe(return_status="healthy")
    registry = StaticRegistry([ep1, ep2], health_probe=probe)

    await registry.check_health()

    assert probe.check_count == 2
    assert registry.get_health("ep1").status == "healthy"
    assert registry.get_health("ep2").status == "healthy"


@pytest.mark.asyncio
async def test_static_registry_check_health_no_probe():
    ep = EndpointSpec(name="test", base_url="http://x", backend_kind=BackendKind.LLAMA_SERVER)
    registry = StaticRegistry([ep])

    # Should not raise, just return early
    await registry.check_health()
    assert registry.get_health("test").status == "unknown"


@pytest.mark.asyncio
async def test_static_registry_check_health_for():
    ep1 = EndpointSpec(name="ep1", base_url="http://a", backend_kind=BackendKind.LLAMA_SERVER)
    ep2 = EndpointSpec(name="ep2", base_url="http://b", backend_kind=BackendKind.LLAMA_SERVER)

    probe = MockHealthProbe(return_status="degraded")
    registry = StaticRegistry([ep1, ep2], health_probe=probe)

    result = await registry.check_health_for("ep1")

    assert probe.check_count == 1
    assert result.status == "degraded"
    assert registry.get_health("ep1").status == "degraded"
    assert registry.get_health("ep2").status == "unknown"  # Not checked


@pytest.mark.asyncio
async def test_static_registry_check_health_for_nonexistent():
    ep = EndpointSpec(name="test", base_url="http://x", backend_kind=BackendKind.LLAMA_SERVER)
    probe = MockHealthProbe()
    registry = StaticRegistry([ep], health_probe=probe)

    result = await registry.check_health_for("nonexistent")

    assert result is None
    assert probe.check_count == 0


@pytest.mark.asyncio
async def test_static_registry_health_monitor():
    ep = EndpointSpec(name="test", base_url="http://x", backend_kind=BackendKind.LLAMA_SERVER)
    probe = MockHealthProbe()
    registry = StaticRegistry([ep], health_probe=probe)

    handle = registry.start_health_monitor(interval=0.1)

    # Wait for a few check cycles
    await asyncio.sleep(0.35)
    registry.stop_health_monitor()

    # Should have checked multiple times
    assert probe.check_count >= 2


def test_static_registry_stop_health_monitor_not_started():
    ep = EndpointSpec(name="test", base_url="http://x", backend_kind=BackendKind.LLAMA_SERVER)
    registry = StaticRegistry([ep])

    # Should not raise
    registry.stop_health_monitor()
