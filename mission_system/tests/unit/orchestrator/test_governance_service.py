"""Unit tests for HealthServicer (GovernanceService).

Clean, modern async/await tests using mocked dependencies.
All external dependencies (gRPC, database, tool health service) are mocked.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

# Import the servicer
from mission_system.orchestrator import governance_service


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_logger():
    """Create a mock logger."""
    logger = MagicMock()
    logger.bind.return_value = logger
    return logger


@pytest.fixture
def mock_db():
    """Mock DatabaseClientProtocol."""
    db = AsyncMock()
    db.fetch_one = AsyncMock()
    return db


@pytest.fixture
def mock_tool_health_service():
    """Mock ToolHealthService."""
    service = AsyncMock()
    service.get_health_summary = AsyncMock()
    service.get_tool_health = AsyncMock()
    return service


@pytest.fixture
def mock_grpc_context():
    """Mock grpc.aio.ServicerContext."""
    context = AsyncMock()
    context.abort = AsyncMock()
    return context


@pytest.fixture
def mock_registry(monkeypatch):
    """Mock CapabilityResourceRegistry."""
    registry = MagicMock()

    # Mock agent configs
    agent1 = MagicMock()
    agent1.name = "Perception"
    agent1.description = "Analyzes user request"
    agent1.layer = "L1"
    agent1.tools = ["grep_search", "file_read"]

    agent2 = MagicMock()
    agent2.name = "Planner"
    agent2.description = "Creates execution plan"
    agent2.layer = "L2"
    agent2.tools = ["task_create", "task_list"]

    registry.get_agents.return_value = [agent1, agent2]

    monkeypatch.setattr(
        "mission_system.orchestrator.governance_service.get_capability_resource_registry",
        lambda: registry
    )
    return registry


@pytest.fixture
def health_servicer(mock_tool_health_service, mock_db, mock_logger):
    """HealthServicer instance with mocked dependencies."""
    return governance_service.HealthServicer(
        tool_health_service=mock_tool_health_service,
        db=mock_db,
        logger=mock_logger
    )


# =============================================================================
# GETHEALTHSUMMARY TESTS
# =============================================================================


@pytest.mark.asyncio
async def test_get_health_summary_all_healthy(health_servicer, mock_tool_health_service, mock_grpc_context):
    """Test health summary when all tools healthy."""
    # Mock health service response
    mock_tool_health_service.get_health_summary.return_value = {
        "tools": {
            "grep_search": {
                "status": "healthy",
                "success_rate": 1.0,
                "last_used": datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
            },
            "file_read": {
                "status": "healthy",
                "success_rate": 0.98,
                "last_used": datetime(2024, 1, 15, 10, 5, 0, tzinfo=timezone.utc)
            }
        }
    }

    request = MagicMock()

    # Execute
    summary = await health_servicer.GetHealthSummary(request, mock_grpc_context)

    # Verify summary
    assert summary.overall_status == "healthy"
    assert summary.total_tools == 2
    assert summary.healthy_tools == 2
    assert summary.degraded_tools == 0
    assert summary.unhealthy_tools == 0
    assert len(summary.tools) == 2

    # Verify tool details
    assert summary.tools[0].tool_name == "grep_search"
    assert summary.tools[0].status == "healthy"
    assert summary.tools[0].success_rate == 1.0


@pytest.mark.asyncio
async def test_get_health_summary_degraded(health_servicer, mock_tool_health_service, mock_grpc_context):
    """Test health summary with some degraded tools."""
    mock_tool_health_service.get_health_summary.return_value = {
        "tools": {
            "tool1": {"status": "healthy", "success_rate": 1.0, "last_used": None},
            "tool2": {"status": "degraded", "success_rate": 0.75, "last_used": None},
            "tool3": {"status": "healthy", "success_rate": 0.95, "last_used": None}
        }
    }

    request = MagicMock()

    # Execute
    summary = await health_servicer.GetHealthSummary(request, mock_grpc_context)

    # Verify overall status is degraded
    assert summary.overall_status == "degraded"
    assert summary.total_tools == 3
    assert summary.healthy_tools == 2
    assert summary.degraded_tools == 1
    assert summary.unhealthy_tools == 0


@pytest.mark.asyncio
async def test_get_health_summary_unhealthy(health_servicer, mock_tool_health_service, mock_grpc_context):
    """Test health summary with unhealthy tools."""
    mock_tool_health_service.get_health_summary.return_value = {
        "tools": {
            "tool1": {"status": "healthy", "success_rate": 1.0, "last_used": None},
            "tool2": {"status": "unhealthy", "success_rate": 0.2, "last_used": None},
            "tool3": {"status": "degraded", "success_rate": 0.75, "last_used": None}
        }
    }

    request = MagicMock()

    # Execute
    summary = await health_servicer.GetHealthSummary(request, mock_grpc_context)

    # Verify overall status is unhealthy
    assert summary.overall_status == "unhealthy"
    assert summary.total_tools == 3
    assert summary.healthy_tools == 1
    assert summary.degraded_tools == 1
    assert summary.unhealthy_tools == 1


@pytest.mark.asyncio
async def test_get_health_summary_error_handling(health_servicer, mock_tool_health_service, mock_grpc_context):
    """Test error handling in GetHealthSummary."""
    # Mock health service raises exception
    mock_tool_health_service.get_health_summary.side_effect = Exception("Database connection failed")

    request = MagicMock()

    # Execute
    await health_servicer.GetHealthSummary(request, mock_grpc_context)

    # Verify abort was called
    mock_grpc_context.abort.assert_called_once()
    assert mock_grpc_context.abort.call_args[0][0].name == "INTERNAL"


# =============================================================================
# GETTOOLHEALTH TESTS
# =============================================================================


@pytest.mark.asyncio
async def test_get_tool_health_success(health_servicer, mock_tool_health_service, mock_grpc_context):
    """Test retrieving tool health details."""
    request = MagicMock()
    request.tool_name = "grep_search"

    # Mock tool health response
    mock_tool_health_service.get_tool_health.return_value = {
        "status": "healthy",
        "total_calls": 100,
        "successful_calls": 95,
        "failed_calls": 5,
        "success_rate": 0.95,
        "avg_latency_ms": 150.5,
        "last_success": datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
        "last_failure": datetime(2024, 1, 14, 9, 30, 0, tzinfo=timezone.utc),
        "last_error": "File not found"
    }

    # Execute
    health = await health_servicer.GetToolHealth(request, mock_grpc_context)

    # Verify response
    assert health.tool_name == "grep_search"
    assert health.status == "healthy"
    assert health.total_calls == 100
    assert health.successful_calls == 95
    assert health.failed_calls == 5
    assert health.success_rate == 0.95
    assert health.avg_latency_ms == 150.5
    assert health.last_error == "File not found"
    assert health.last_success_ms > 0
    assert health.last_failure_ms > 0

    # Verify service was called
    mock_tool_health_service.get_tool_health.assert_called_once_with("grep_search")


@pytest.mark.asyncio
async def test_get_tool_health_not_found(health_servicer, mock_tool_health_service, mock_grpc_context):
    """Test tool not found returns NOT_FOUND status."""
    request = MagicMock()
    request.tool_name = "nonexistent_tool"

    # Mock tool health returns None
    mock_tool_health_service.get_tool_health.return_value = None

    # Execute
    await health_servicer.GetToolHealth(request, mock_grpc_context)

    # Verify abort was called with NOT_FOUND
    mock_grpc_context.abort.assert_called_once()
    assert mock_grpc_context.abort.call_args[0][0].name == "NOT_FOUND"
    assert "not found" in mock_grpc_context.abort.call_args[0][1].lower()


@pytest.mark.asyncio
async def test_get_tool_health_metrics(health_servicer, mock_tool_health_service, mock_grpc_context):
    """Test tool health includes all metrics."""
    request = MagicMock()
    request.tool_name = "file_read"

    # Mock tool health with minimal data
    mock_tool_health_service.get_tool_health.return_value = {
        "status": "degraded",
        "total_calls": 50,
        "successful_calls": 40,
        "failed_calls": 10,
        "success_rate": 0.8,
        "avg_latency_ms": 200.0,
        "last_success": None,
        "last_failure": None,
        "last_error": None
    }

    # Execute
    health = await health_servicer.GetToolHealth(request, mock_grpc_context)

    # Verify all metrics present
    assert health.tool_name == "file_read"
    assert health.status == "degraded"
    assert health.total_calls == 50
    assert health.successful_calls == 40
    assert health.failed_calls == 10
    assert health.success_rate == 0.8
    assert health.last_error == ""  # None converted to empty string


# =============================================================================
# GETAGENTS TESTS
# =============================================================================


@pytest.mark.asyncio
async def test_get_agents_from_registry(health_servicer, mock_grpc_context, mock_registry):
    """Test agents retrieved from capability registry."""
    request = MagicMock()

    # Execute
    response = await health_servicer.GetAgents(request, mock_grpc_context)

    # Verify response
    assert len(response.agents) == 2

    # Verify first agent
    assert response.agents[0].name == "Perception"
    assert response.agents[0].description == "Analyzes user request"
    assert response.agents[0].status == "active"
    assert response.agents[0].layer == "L1"
    assert list(response.agents[0].tools) == ["grep_search", "file_read"]

    # Verify second agent
    assert response.agents[1].name == "Planner"
    assert response.agents[1].description == "Creates execution plan"
    assert response.agents[1].layer == "L2"
    assert list(response.agents[1].tools) == ["task_create", "task_list"]

    # Verify logger was called
    health_servicer._logger.info.assert_called_once()


@pytest.mark.asyncio
async def test_get_agents_empty_registry(health_servicer, mock_grpc_context, monkeypatch):
    """Test empty agent list when registry has no agents."""
    # Mock registry with no agents
    registry = MagicMock()
    registry.get_agents.return_value = []

    monkeypatch.setattr(
        "mission_system.orchestrator.governance_service.get_capability_resource_registry",
        lambda: registry
    )

    request = MagicMock()

    # Execute
    response = await health_servicer.GetAgents(request, mock_grpc_context)

    # Verify empty response
    assert len(response.agents) == 0


@pytest.mark.asyncio
async def test_get_agents_includes_metadata(health_servicer, mock_grpc_context, mock_registry):
    """Test agent info includes layer and tools."""
    request = MagicMock()

    # Execute
    response = await health_servicer.GetAgents(request, mock_grpc_context)

    # Verify metadata included
    for agent in response.agents:
        assert agent.name is not None
        assert agent.description is not None
        assert agent.status == "active"
        assert agent.layer is not None
        assert agent.tools is not None


# =============================================================================
# GETMEMORYLAYERS TESTS
# =============================================================================


@pytest.mark.asyncio
async def test_get_memory_layers_all_active(health_servicer, mock_db, mock_grpc_context):
    """Test all memory layers active."""
    # Mock all database queries succeed
    mock_db.fetch_one.return_value = {"count": 1}

    request = MagicMock()

    # Execute
    response = await health_servicer.GetMemoryLayers(request, mock_grpc_context)

    # Verify response
    assert len(response.layers) == 7  # L1-L7

    # Verify layer structure
    layer_ids = [layer.layer_id for layer in response.layers]
    assert "L1" in layer_ids
    assert "L2" in layer_ids
    assert "L3" in layer_ids
    assert "L4" in layer_ids
    assert "L5" in layer_ids
    assert "L6" in layer_ids
    assert "L7" in layer_ids

    # Verify each layer has required fields
    for layer in response.layers:
        assert layer.name is not None
        assert layer.description is not None
        assert layer.backend is not None
        assert layer.layer_id is not None


@pytest.mark.asyncio
async def test_get_memory_layers_l6_inactive(health_servicer, mock_db, mock_grpc_context):
    """Test L6 always returns inactive (deferred)."""
    # Mock database queries succeed
    mock_db.fetch_one.return_value = {"count": 1}

    request = MagicMock()

    # Execute
    response = await health_servicer.GetMemoryLayers(request, mock_grpc_context)

    # Find L6 layer
    l6_layer = next(layer for layer in response.layers if layer.layer_id == "L6")

    # Verify L6 is inactive (deferred feature)
    assert l6_layer.status == "inactive"
    assert l6_layer.backend == "none"


@pytest.mark.asyncio
async def test_get_memory_layers_degraded(health_servicer, mock_db, mock_grpc_context):
    """Test degraded layer when some tables inaccessible."""
    # Mock some queries succeed, some fail
    call_count = [0]

    async def mock_fetch_one(query):
        call_count[0] += 1
        if call_count[0] % 2 == 0:  # Every other query fails
            raise Exception("Table not accessible")
        return {"count": 1}

    mock_db.fetch_one = mock_fetch_one

    request = MagicMock()

    # Execute
    response = await health_servicer.GetMemoryLayers(request, mock_grpc_context)

    # Verify some layers are degraded
    statuses = [layer.status for layer in response.layers]
    assert "degraded" in statuses or "inactive" in statuses


@pytest.mark.asyncio
async def test_get_memory_layers_no_db(mock_tool_health_service, mock_logger, mock_grpc_context):
    """Test unknown status when no db connection."""
    # Create servicer without database
    servicer = governance_service.HealthServicer(
        tool_health_service=mock_tool_health_service,
        db=None,  # No database
        logger=mock_logger
    )

    request = MagicMock()

    # Execute
    response = await servicer.GetMemoryLayers(request, mock_grpc_context)

    # Verify layers have unknown status (except L6 which is inactive)
    for layer in response.layers:
        if layer.layer_id == "L6":
            assert layer.status == "inactive"
        else:
            assert layer.status == "unknown"


# =============================================================================
# _CHECK_LAYER_STATUS TESTS
# =============================================================================


@pytest.mark.asyncio
async def test_check_layer_status_active(health_servicer, mock_db):
    """Test layer status active when all tables accessible."""
    # Mock all database queries succeed
    mock_db.fetch_one.return_value = {"count": 1}

    layer_def = {
        "layer_id": "L1",
        "name": "Canonical State Store",
        "tables": ["sessions", "messages", "tasks"]
    }

    # Execute
    status = await health_servicer._check_layer_status(layer_def)

    # Verify active status
    assert status == "active"

    # Verify all tables were checked
    assert mock_db.fetch_one.call_count == 3


@pytest.mark.asyncio
async def test_check_layer_status_degraded(health_servicer, mock_db):
    """Test degraded status when some tables missing."""
    # Mock some queries succeed, some fail
    call_count = [0]

    async def mock_fetch_one(query):
        call_count[0] += 1
        if call_count[0] == 2:  # Second query fails
            raise Exception("Table not found")
        return {"count": 1}

    mock_db.fetch_one = mock_fetch_one

    layer_def = {
        "layer_id": "L2",
        "name": "Event Log",
        "tables": ["domain_events", "agent_traces"]
    }

    # Execute
    status = await health_servicer._check_layer_status(layer_def)

    # Verify degraded status (1 out of 2 tables accessible)
    assert status == "degraded"


@pytest.mark.asyncio
async def test_check_layer_status_inactive(health_servicer, mock_db):
    """Test inactive status when no tables accessible."""
    # Mock all database queries fail
    async def mock_fetch_one(query):
        raise Exception("Database error")

    mock_db.fetch_one = mock_fetch_one

    layer_def = {
        "layer_id": "L3",
        "name": "Semantic Memory",
        "tables": ["semantic_chunks"]
    }

    # Execute
    status = await health_servicer._check_layer_status(layer_def)

    # Verify inactive status
    assert status == "inactive"


@pytest.mark.asyncio
async def test_check_layer_status_l6_always_inactive(health_servicer, mock_db):
    """Test L6 always returns inactive regardless of db state."""
    # Even if db would succeed
    mock_db.fetch_one.return_value = {"count": 1}

    layer_def = {
        "layer_id": "L6",
        "name": "Skills & Patterns",
        "tables": []
    }

    # Execute
    status = await health_servicer._check_layer_status(layer_def)

    # Verify L6 is always inactive
    assert status == "inactive"

    # Verify no db queries were made
    mock_db.fetch_one.assert_not_called()


@pytest.mark.asyncio
async def test_check_layer_status_no_tables(health_servicer, mock_db):
    """Test layer with no tables is considered active."""
    layer_def = {
        "layer_id": "L7",
        "name": "Meta-Memory",
        "tables": []
    }

    # Execute
    status = await health_servicer._check_layer_status(layer_def)

    # Verify active status when no tables to check
    assert status == "active"


# =============================================================================
# GET_AGENT_DEFINITIONS TESTS
# =============================================================================


def test_get_agent_definitions_with_agents(mock_registry):
    """Test get_agent_definitions returns agents from registry."""
    agent_defs = governance_service.get_agent_definitions()

    # Verify agents returned
    assert len(agent_defs) == 2
    assert agent_defs[0]["name"] == "Perception"
    assert agent_defs[0]["layer"] == "L1"
    assert agent_defs[0]["tools"] == ["grep_search", "file_read"]
    assert agent_defs[1]["name"] == "Planner"
    assert agent_defs[1]["layer"] == "L2"


def test_get_agent_definitions_empty_registry(monkeypatch):
    """Test get_agent_definitions returns empty list when no agents."""
    registry = MagicMock()
    registry.get_agents.return_value = None

    monkeypatch.setattr(
        "mission_system.orchestrator.governance_service.get_capability_resource_registry",
        lambda: registry
    )

    agent_defs = governance_service.get_agent_definitions()

    # Verify empty list returned
    assert agent_defs == []
