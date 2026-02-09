"""Unit tests for health check functionality.

Uses test_db fixture (in-memory SQLite).
Tests use test_db fixture from conftest.py.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from mission_system.health import (
    ComponentHealth,
    ComponentStatus,
    HealthChecker,
    HealthStatus,
    health_check_to_dict,
)
from mission_system.config.constants import PLATFORM_VERSION


@pytest.fixture
def health_checker(test_db):
    """Create health checker instance."""
    return HealthChecker(test_db)


@pytest.mark.asyncio
async def test_liveness_check(health_checker):
    """Test liveness check returns healthy status."""
    result = await health_checker.check_liveness()

    assert result.status == HealthStatus.HEALTHY
    assert result.uptime_seconds >= 0
    assert "api" in result.components
    assert result.components["api"].status == ComponentStatus.UP
    assert result.version == PLATFORM_VERSION


@pytest.mark.asyncio
async def test_readiness_check_healthy(health_checker):
    """Test readiness check with healthy database."""
    mock_models = ComponentHealth(
        status=ComponentStatus.UP,
        message="Mock LLM provider",
    )
    with patch.object(health_checker, "_check_models", return_value=mock_models):
        result = await health_checker.check_readiness()

    assert result.status == HealthStatus.HEALTHY
    assert result.uptime_seconds >= 0
    assert "database" in result.components

    db_health = result.components["database"]
    assert db_health.status == ComponentStatus.UP
    assert db_health.latency_ms is not None
    assert db_health.latency_ms < 1000  # Should be fast for in-memory


@pytest.mark.asyncio
async def test_readiness_check_database_timeout(health_checker):
    """Test readiness check when database times out."""
    async def mock_timeout(*args, **kwargs):
        import asyncio

        await asyncio.sleep(10)  # Exceed timeout

    mock_models = ComponentHealth(
        status=ComponentStatus.UP,
        message="Mock LLM provider",
    )
    with patch.object(health_checker.db, "fetch_one", side_effect=mock_timeout), \
         patch.object(health_checker, "_check_models", return_value=mock_models):
        result = await health_checker.check_readiness()

        assert result.status == HealthStatus.UNHEALTHY
        assert "database" in result.components
        assert result.components["database"].status == ComponentStatus.DOWN
        assert "timeout" in result.components["database"].message.lower()


@pytest.mark.asyncio
async def test_readiness_check_database_error(health_checker):
    """Test readiness check when database raises error."""
    mock_models = ComponentHealth(
        status=ComponentStatus.UP,
        message="Mock LLM provider",
    )
    with patch.object(
        health_checker.db, "fetch_one", side_effect=Exception("Connection failed")
    ), patch.object(health_checker, "_check_models", return_value=mock_models):
        result = await health_checker.check_readiness()

        assert result.status == HealthStatus.UNHEALTHY
        assert "database" in result.components
        assert result.components["database"].status == ComponentStatus.DOWN
        assert "Connection failed" in result.components["database"].message


@pytest.mark.asyncio
async def test_readiness_check_database_missing_schema(health_checker):
    """Test readiness check when database schema not initialized."""
    async def mock_missing_table(*args, **kwargs):
        raise Exception('relation "requests" does not exist')

    mock_models = ComponentHealth(
        status=ComponentStatus.UP,
        message="Mock LLM provider",
    )
    with patch.object(health_checker.db, "fetch_one", side_effect=mock_missing_table), \
         patch.object(health_checker, "_check_models", return_value=mock_models):
        result = await health_checker.check_readiness()

        assert result.status == HealthStatus.UNHEALTHY
        assert "database" in result.components
        assert result.components["database"].status == ComponentStatus.DOWN
        msg = result.components["database"].message.lower()
        assert "schema" in msg or "not" in msg or "table" in msg or "relation" in msg


@pytest.mark.asyncio
async def test_readiness_check_database_degraded(health_checker):
    """Test readiness check when database is slow but responding."""
    async def mock_slow(*args, **kwargs):
        import asyncio

        await asyncio.sleep(1.5)  # Slow but not timeout
        return ("requests",)

    mock_models = ComponentHealth(
        status=ComponentStatus.UP,
        message="Mock LLM provider",
    )
    with patch.object(health_checker.db, "fetch_one", side_effect=mock_slow), \
         patch.object(health_checker, "_check_models", return_value=mock_models):
        result = await health_checker.check_readiness()

        assert result.status == HealthStatus.DEGRADED
        assert "database" in result.components
        assert result.components["database"].status == ComponentStatus.DEGRADED
        assert "slowly" in result.components["database"].message.lower()


@pytest.mark.asyncio
async def test_check_models_mock_provider(health_checker):
    """Test that model check returns UP for mock provider."""
    mock_settings = AsyncMock()
    mock_settings.llm_provider = "mock"
    with patch("mission_system.adapters.get_settings", return_value=mock_settings):
        result = await health_checker._check_models()

    assert result.status == ComponentStatus.UP
    assert "mock" in result.message.lower()


def test_health_check_to_dict():
    """Test conversion of HealthCheckResult to dictionary."""
    now = datetime.now(timezone.utc)

    from mission_system.health import HealthCheckResult

    result = HealthCheckResult(
        status=HealthStatus.HEALTHY,
        timestamp=now,
        uptime_seconds=123.45,
        components={
            "database": ComponentHealth(
                status=ComponentStatus.UP,
                message="Operational",
                latency_ms=5.2,
                last_check=now,
            )
        },
    )

    data = health_check_to_dict(result)

    assert data["status"] == "healthy"
    assert data["uptime_seconds"] == 123.45
    assert data["version"] == PLATFORM_VERSION
    assert "database" in data["components"]
    assert data["components"]["database"]["status"] == "up"
    assert data["components"]["database"]["latency_ms"] == 5.2


def test_component_health_creation():
    """Test ComponentHealth dataclass creation."""
    now = datetime.now(timezone.utc)

    health = ComponentHealth(
        status=ComponentStatus.UP,
        message="Test message",
        latency_ms=10.5,
        last_check=now,
    )

    assert health.status == ComponentStatus.UP
    assert health.message == "Test message"
    assert health.latency_ms == 10.5
    assert health.last_check == now


def test_component_health_minimal():
    """Test ComponentHealth with minimal fields."""
    health = ComponentHealth(status=ComponentStatus.DOWN)

    assert health.status == ComponentStatus.DOWN
    assert health.message is None
    assert health.latency_ms is None
    assert health.last_check is None
