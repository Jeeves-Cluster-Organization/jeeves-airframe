"""Unit tests for health check functionality.

PostgreSQL-only as of 2025-11-27 (Amendment V).
Tests use pg_test_db fixture from conftest.py.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from jeeves_infra.gateway.health import (
    ComponentHealth,
    ComponentStatus,
    HealthChecker,
    HealthStatus,
    health_check_to_dict,
)
from mission_system.config.constants import PLATFORM_VERSION

# Requires PostgreSQL database
pytestmark = pytest.mark.requires_postgres


@pytest.fixture
def health_checker(pg_test_db):
    """Create health checker instance."""
    return HealthChecker(pg_test_db)


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
    # Mock database query to timeout
    async def mock_timeout(*args, **kwargs):
        import asyncio

        await asyncio.sleep(10)  # Exceed timeout

    with patch.object(health_checker.db, "fetch_one", side_effect=mock_timeout):
        result = await health_checker.check_readiness()

        assert result.status == HealthStatus.UNHEALTHY
        assert "database" in result.components
        assert result.components["database"].status == ComponentStatus.DOWN
        assert "timeout" in result.components["database"].message.lower()


@pytest.mark.asyncio
async def test_readiness_check_database_error(health_checker):
    """Test readiness check when database raises error."""
    # Mock database query to raise error
    with patch.object(
        health_checker.db, "fetch_one", side_effect=Exception("Connection failed")
    ):
        result = await health_checker.check_readiness()

        assert result.status == HealthStatus.UNHEALTHY
        assert "database" in result.components
        assert result.components["database"].status == ComponentStatus.DOWN
        assert "Connection failed" in result.components["database"].message


@pytest.mark.asyncio
async def test_readiness_check_database_missing_schema(postgres_container):
    """Test readiness check when database schema not initialized.

    Creates a fresh PostgreSQL database without schema to test health checker
    detection of missing schema. Uses the session-scoped postgres_container
    to create a temporary database.

    Import Boundary Note: Mission system tests can access avionics
    directly for database infrastructure (mission_system IS the wiring layer).
    """
    # Mission system is the wiring layer - avionics imports acceptable
    from jeeves_infra.postgres.client import PostgreSQLClient
    import urllib.parse
    import uuid

    # Create unique database name for this test
    db_name = f"test_no_schema_{uuid.uuid4().hex[:8]}"
    admin_url = postgres_container.get_connection_url()

    # Create empty database (no schema) using AUTOCOMMIT
    # (CREATE DATABASE cannot run inside a transaction block)
    from sqlalchemy import text

    admin_client = PostgreSQLClient(admin_url)
    await admin_client.connect()

    try:
        async with admin_client.engine.connect() as conn:
            # AsyncConnection.execution_options() is async in SQLAlchemy 2.0
            conn_with_autocommit = await conn.execution_options(isolation_level="AUTOCOMMIT")
            await conn_with_autocommit.execute(text(f"CREATE DATABASE {db_name}"))
    finally:
        await admin_client.disconnect()

    # Connect to empty database
    # Replace database name in URL - handle any database name by replacing last path segment
    parsed = urllib.parse.urlparse(admin_url)
    new_path = parsed.path.rsplit('/', 1)[0] + f'/{db_name}'
    test_url = parsed._replace(path=new_path).geturl()
    db_empty = PostgreSQLClient(test_url)
    await db_empty.connect()  # Connected but no schema initialized

    # Create health checker with database that lacks schema
    health_checker = HealthChecker(db_empty)

    try:
        result = await health_checker.check_readiness()

        assert result.status == HealthStatus.UNHEALTHY
        assert "database" in result.components
        assert result.components["database"].status == ComponentStatus.DOWN
        # The error message should indicate schema/table issue
        msg = result.components["database"].message.lower()
        assert "schema" in msg or "not" in msg or "table" in msg or "relation" in msg
    finally:
        # Cleanup
        await db_empty.disconnect()

        # Drop test database using AUTOCOMMIT
        # (DROP DATABASE cannot run inside a transaction block)
        admin_client = PostgreSQLClient(admin_url)
        await admin_client.connect()
        try:
            async with admin_client.engine.connect() as conn:
                # AsyncConnection.execution_options() is async in SQLAlchemy 2.0
                conn_with_autocommit = await conn.execution_options(isolation_level="AUTOCOMMIT")
                await conn_with_autocommit.execute(
                    text(f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{db_name}'")
                )
                await conn_with_autocommit.execute(text(f"DROP DATABASE IF EXISTS {db_name}"))
        finally:
            await admin_client.disconnect()


@pytest.mark.asyncio
async def test_readiness_check_database_degraded(health_checker):
    """Test readiness check when database is slow but responding."""
    # Mock database query to be slow
    async def mock_slow(*args, **kwargs):
        import asyncio

        await asyncio.sleep(1.5)  # Slow but not timeout
        return ("requests",)

    with patch.object(health_checker.db, "fetch_one", side_effect=mock_slow):
        result = await health_checker.check_readiness()

        assert result.status == HealthStatus.DEGRADED
        assert "database" in result.components
        assert result.components["database"].status == ComponentStatus.DEGRADED
        assert "slowly" in result.components["database"].message.lower()


@pytest.mark.asyncio
async def test_check_models_mock_provider(health_checker):
    """Test that model check returns UP for mock provider."""
    result = await health_checker._check_models()

    # Mock provider returns UP status
    assert result.status == ComponentStatus.UP
    assert "mock" in result.message.lower()


def test_health_check_to_dict():
    """Test conversion of HealthCheckResult to dictionary."""
    now = datetime.now(timezone.utc)

    from jeeves_infra.gateway.health import HealthCheckResult

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
