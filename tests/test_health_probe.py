"""Tests for HTTP health probe."""

import pytest

from airframe.endpoints import EndpointSpec, BackendKind, HealthState
from airframe.health import HttpHealthProbe


def test_health_path_llama_server():
    probe = HttpHealthProbe()
    endpoint = EndpointSpec(
        name="test",
        base_url="http://localhost:8080",
        backend_kind=BackendKind.LLAMA_SERVER,
    )
    path = probe._get_health_path(endpoint)
    assert path == "/health"


def test_health_path_openai():
    probe = HttpHealthProbe()
    endpoint = EndpointSpec(
        name="test",
        base_url="https://api.openai.com",
        backend_kind=BackendKind.OPENAI_CHAT,
    )
    path = probe._get_health_path(endpoint)
    assert path == "/v1/models"


def test_health_path_anthropic():
    probe = HttpHealthProbe()
    endpoint = EndpointSpec(
        name="test",
        base_url="https://api.anthropic.com",
        backend_kind=BackendKind.ANTHROPIC_MESSAGES,
    )
    path = probe._get_health_path(endpoint)
    assert path == "/v1/messages"


def test_probe_init_defaults():
    probe = HttpHealthProbe()
    assert probe.timeout == 5.0


def test_probe_init_custom_timeout():
    probe = HttpHealthProbe(timeout=10.0)
    assert probe.timeout == 10.0


@pytest.mark.asyncio
async def test_health_check_no_httpx(monkeypatch):
    """Test graceful handling when httpx is not available."""
    import airframe.health as health_module
    monkeypatch.setattr(health_module, "httpx", None)

    probe = HttpHealthProbe()
    endpoint = EndpointSpec(
        name="test",
        base_url="http://localhost:8080",
        backend_kind=BackendKind.LLAMA_SERVER,
    )
    state = await probe.check(endpoint)

    assert state.status == "unknown"
    assert "httpx not installed" in state.detail
    assert state.checked_at is not None
