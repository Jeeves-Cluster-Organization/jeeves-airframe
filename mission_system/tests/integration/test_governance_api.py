"""Integration tests for Governance API (v0.9).

Tests L7 System Introspection endpoints for tool health monitoring.

Constitutional Alignment:
- P5: Tests deterministic health reporting
- P6: Tests observability and debugging capabilities
- L7: Tests meta-memory and system introspection
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from jeeves_infra.utils.testing import parse_postgres_url
from jeeves_infra.gateway.server import app, app_state
from jeeves_infra.memory.services.tool_health_service import ToolHealthService, HealthStatus
from jeeves_infra.memory.repositories.tool_metrics_repository import ToolMetric


@pytest.fixture
async def db(pg_test_db):
    """PostgreSQL test database with schema.

    Uses pg_test_db fixture from conftest.py for PostgreSQL-only testing.
    All tests now use PostgreSQL instead of SQLite (as of 2025-11-27).
    """
    return pg_test_db


@pytest.fixture
async def tool_health_service(db):
    """Create ToolHealthService with test database."""
    service = ToolHealthService(db)
    await service.ensure_initialized()
    return service


@pytest.fixture
def governance_client(pg_test_db):
    """Create test client with properly configured PostgreSQL connection.

    For sync tests (TestClient), we set the database URL in environment
    and let the lifespan create its own connection in the correct event loop.
    """
    import os
    from jeeves_infra.settings import reload_settings, get_settings
    from jeeves_infra.database.factory import reset_factory

    # Parse the test database URL into environment variables
    db_env = parse_postgres_url(pg_test_db.database_url)

    # Save original environment values for cleanup
    original_env = {
        "DATABASE_BACKEND": os.environ.get("DATABASE_BACKEND"),
        "MOCK_MODE": os.environ.get("MOCK_MODE"),
        "LLM_PROVIDER": os.environ.get("LLM_PROVIDER"),
        "POSTGRES_HOST": os.environ.get("POSTGRES_HOST"),
        "POSTGRES_PORT": os.environ.get("POSTGRES_PORT"),
        "POSTGRES_DATABASE": os.environ.get("POSTGRES_DATABASE"),
        "POSTGRES_USER": os.environ.get("POSTGRES_USER"),
        "POSTGRES_PASSWORD": os.environ.get("POSTGRES_PASSWORD"),
    }

    # Reset factory state
    reset_factory()

    # Configure environment for PostgreSQL testing
    os.environ["DATABASE_BACKEND"] = "postgres"
    os.environ["MOCK_MODE"] = "true"
    os.environ["LLM_PROVIDER"] = "mock"

    # Set database connection details from test database
    for key, value in db_env.items():
        os.environ[key] = value

    # Reload settings to pick up new environment
    reload_settings()
    settings = get_settings()
    settings.llm_provider = "mock"
    settings.memory_enabled = False

    try:
        with TestClient(app) as client:
            yield client
    finally:
        # Cleanup - restore original environment variables
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

        app_state.shutdown_event.clear()
        app_state.db = None


class TestGovernanceHealthEndpoint:
    """Test suite for /api/v1/governance/health endpoint."""

    @pytest.mark.asyncio
    async def test_health_endpoint_returns_system_summary(self, db, tool_health_service):
        """Test that health endpoint returns system health summary."""

        # Setup: Record some tool executions
        await tool_health_service.record_execution(
            tool_name="add_task",
            user_id="test-user",
            status="success",
            execution_time_ms=150
        )
        await tool_health_service.record_execution(
            tool_name="add_task",
            user_id="test-user",
            status="success",
            execution_time_ms=200
        )
        await tool_health_service.record_execution(
            tool_name="get_tasks",
            user_id="test-user",
            status="error",
            execution_time_ms=50,
            error_type="ValidationError"
        )

        # Execute: Get dashboard summary
        summary = await tool_health_service.get_dashboard_summary()

        # Verify: Summary structure
        assert "overall_status" in summary
        assert "summary" in summary
        assert "tools_needing_attention" in summary
        assert "slow_executions" in summary
        assert "checked_at" in summary

        # Verify: Status counts
        assert isinstance(summary["summary"], dict)
        assert "healthy" in summary["summary"]
        assert "degraded" in summary["summary"]
        assert "unhealthy" in summary["summary"]
        assert "unknown" in summary["summary"]

    @pytest.mark.asyncio
    async def test_health_endpoint_with_healthy_tools(self, db, tool_health_service):
        """Test health endpoint when all tools are healthy."""

        # Setup: Record healthy executions
        for i in range(10):
            await tool_health_service.record_execution(
                tool_name="add_task",
                user_id="test-user",
                status="success",
                execution_time_ms=100 + i * 10
            )

        # Execute
        summary = await tool_health_service.get_dashboard_summary()

        # Verify: Should have healthy status
        # Note: With only 10 calls, might be "unknown" if threshold not met
        assert summary["overall_status"] in ["healthy", "unknown"]

    @pytest.mark.asyncio
    async def test_health_endpoint_with_unhealthy_tools(self, db, tool_health_service):
        """Test health endpoint when tools are unhealthy."""

        # Setup: Record mostly failed executions
        for i in range(10):
            await tool_health_service.record_execution(
                tool_name="failing_tool",
                user_id="test-user",
                status="error" if i < 8 else "success",  # 80% failure rate
                execution_time_ms=100,
                error_type="RuntimeError" if i < 8 else None
            )

        # Execute
        report = await tool_health_service.check_tool_health("failing_tool", period_hours=24)

        # Verify: Should be unhealthy
        assert report.status == HealthStatus.UNHEALTHY
        assert report.success_rate < 0.3  # Less than 30% success
        assert len(report.issues) > 0
        assert len(report.recommendations) > 0


class TestGovernanceToolEndpoint:
    """Test suite for /api/v1/governance/tools/{tool_name} endpoint."""

    @pytest.mark.asyncio
    async def test_tool_endpoint_returns_health_report(self, db, tool_health_service):
        """Test that tool endpoint returns individual tool health report."""

        # Setup: Record executions for specific tool
        for i in range(6):
            await tool_health_service.record_execution(
                tool_name="update_task",
                user_id="test-user",
                status="success",
                execution_time_ms=120 + i * 5
            )

        # Execute
        report = await tool_health_service.check_tool_health("update_task", period_hours=1)

        # Verify: Report structure
        report_dict = report.to_dict()
        assert report_dict["tool_name"] == "update_task"
        assert "status" in report_dict
        assert "success_rate" in report_dict
        assert "avg_latency_ms" in report_dict
        assert "total_calls" in report_dict
        assert "recent_errors" in report_dict
        assert "issues" in report_dict
        assert "recommendations" in report_dict
        assert "checked_at" in report_dict

        # Verify: Metrics
        assert report_dict["total_calls"] == 6
        assert report_dict["success_rate"] == 1.0  # 100% success
        assert report_dict["recent_errors"] == 0

    @pytest.mark.asyncio
    async def test_tool_endpoint_with_degraded_performance(self, db, tool_health_service):
        """Test tool endpoint with degraded performance (high latency)."""

        # Setup: Record slow executions
        for i in range(10):
            await tool_health_service.record_execution(
                tool_name="slow_search",
                user_id="test-user",
                status="success",
                execution_time_ms=3000 + i * 100  # 3-4 seconds (degraded)
            )

        # Execute
        report = await tool_health_service.check_tool_health("slow_search", period_hours=1)

        # Verify: Should be degraded due to latency
        assert report.status in [HealthStatus.DEGRADED, HealthStatus.UNHEALTHY]
        assert report.avg_latency_ms > 2000  # Above healthy threshold
        assert any("latency" in issue.lower() for issue in report.issues)


class TestGovernanceDashboard:
    """Test suite for /api/v1/governance/dashboard web UI.

    These tests use the governance_client fixture which properly sets up
    the database connection for TestClient's separate event loop.
    """

    @pytest.mark.requires_full_app
    @pytest.mark.requires_services
    def test_dashboard_renders_html(self, governance_client):
        """Test that dashboard endpoint renders HTML."""
        response = governance_client.get("/api/v1/governance/dashboard")

        # Verify: Returns HTML
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Governance Dashboard" in response.text
        assert "L7 System Introspection" in response.text

    @pytest.mark.requires_full_app
    @pytest.mark.requires_services
    def test_dashboard_shows_tool_status(self, governance_client):
        """Test that dashboard displays tool health status."""
        response = governance_client.get("/api/v1/governance/dashboard")

        # Verify: Dashboard renders with proper structure
        assert response.status_code == 200
        # Check for dashboard structure
        assert "System Status:" in response.text or "Overall Status" in response.text


class TestGovernanceConstitutionalAlignment:
    """Test constitutional compliance of governance features."""

    @pytest.mark.asyncio
    async def test_p5_deterministic_health_checks(self, db, tool_health_service):
        """Test P5: Deterministic health check thresholds."""

        # Setup: Record exactly at thresholds
        # Healthy threshold: >= 95% success
        for i in range(20):
            await tool_health_service.record_execution(
                tool_name="threshold_test",
                user_id="test-user",
                status="success" if i < 19 else "error",  # 95% success
                execution_time_ms=100
            )

        # Execute
        report = await tool_health_service.check_tool_health("threshold_test", period_hours=1)

        # Verify: Deterministic threshold behavior
        assert report.total_calls == 20
        assert 0.94 <= report.success_rate <= 0.96  # Approximately 95%

        # Should be at healthy/degraded boundary
        assert report.status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED]

    @pytest.mark.asyncio
    async def test_p6_observable_metrics(self, db, tool_health_service):
        """Test P6: All metrics are observable for debugging."""

        # Setup
        await tool_health_service.record_execution(
            tool_name="observable_tool",
            user_id="test-user",
            status="error",
            execution_time_ms=500,
            error_type="ValueError",
            error_message="Invalid input",
            metadata={"context": "test"}
        )

        # Execute: Get error patterns
        error_patterns = await tool_health_service.get_error_patterns("observable_tool", limit=10)

        # Verify: All error details are observable
        assert error_patterns["tool_name"] == "observable_tool"
        assert error_patterns["total_errors"] >= 1
        assert len(error_patterns["patterns"]) > 0
        assert error_patterns["patterns"][0]["error_type"] == "ValueError"
        assert len(error_patterns["recent_messages"]) > 0
        assert "Invalid input" in error_patterns["recent_messages"][0]

    @pytest.mark.asyncio
    async def test_l7_meta_memory_introspection(self, db, tool_health_service):
        """Test L7: System can introspect on its own behavior."""

        # Setup: Create a pattern of degrading performance
        for i in range(10):
            await tool_health_service.record_execution(
                tool_name="degrading_tool",
                user_id="test-user",
                status="success",
                execution_time_ms=1000 + i * 200  # Getting slower
            )

        # Execute: System should detect degradation
        report = await tool_health_service.check_tool_health("degrading_tool", period_hours=1)

        # Verify: System is self-aware of degradation
        assert report.avg_latency_ms > 1000  # Detected slowness
        if report.avg_latency_ms > 2000:
            # If slow enough to trigger threshold
            assert report.status in [HealthStatus.DEGRADED, HealthStatus.UNHEALTHY]
            assert len(report.recommendations) > 0  # Provides self-improvement suggestions


class TestGovernanceFeatureFlags:
    """Test feature flag compliance for v0.9."""

    @pytest.mark.asyncio
    async def test_governance_enabled_by_default(self):
        """Test that governance endpoints are always enabled (no feature flag)."""

        # Governance is a core P6 feature and should always be available
        # This is verified by the fact that the router is mounted unconditionally
        # in server.py (not behind a feature flag like kanban/chat)

        # Execute: Check that endpoints are registered
        routes = [route.path for route in app.routes]

        # Verify: Governance routes exist
        assert any("/governance/health" in route for route in routes)
        assert any("/governance/tools" in route for route in routes)
        assert any("/governance/dashboard" in route for route in routes)
