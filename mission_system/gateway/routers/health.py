"""
Governance router - System health and introspection endpoints (L7).

Provides read-only access to tool health metrics.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from mission_system.gateway.grpc_client import get_grpc_client
from jeeves_infra.logging import get_current_logger
from jeeves_infra.utils.serialization import ms_to_iso

try:
    from proto import jeeves_pb2
except ImportError:
    jeeves_pb2 = None

router = APIRouter()


# =============================================================================
# Response Models
# =============================================================================

class ToolHealthBrief(BaseModel):
    """Brief tool health status."""
    tool_name: str
    status: str  # healthy, degraded, unhealthy
    success_rate: float
    last_used: Optional[str] = None


class HealthSummaryResponse(BaseModel):
    """Overall system health summary."""
    overall_status: str  # healthy, degraded, unhealthy
    total_tools: int
    healthy_tools: int
    degraded_tools: int
    unhealthy_tools: int
    tools: List[ToolHealthBrief]


class ToolHealthResponse(BaseModel):
    """Detailed tool health information."""
    tool_name: str
    status: str
    total_calls: int
    successful_calls: int
    failed_calls: int
    success_rate: float
    avg_latency_ms: float
    last_success: Optional[str] = None
    last_failure: Optional[str] = None
    last_error: Optional[str] = None


class AgentInfo(BaseModel):
    """Agent information."""
    name: str
    description: str
    status: str
    layer: str


class MemoryLayerInfo(BaseModel):
    """Memory layer information."""
    name: str
    description: str
    status: str
    backend: str


class ConfigInfo(BaseModel):
    """Configuration info."""
    llm_provider: str
    database_backend: str
    log_level: str


class DashboardResponse(BaseModel):
    """Full governance dashboard data."""
    tools: List[ToolHealthBrief]
    agents: List[AgentInfo]
    memory_layers: List[MemoryLayerInfo]
    config: ConfigInfo


# =============================================================================
# Governance Endpoints
# =============================================================================

@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(request: Request):
    """
    Get full governance dashboard data.

    Returns tools health, agents, memory layers, and configuration.
    Per P2 (Fail loudly) - returns empty lists for data that can't be fetched,
    NOT fake/dummy data. Frontend should display "no data available" states.
    """
    _logger = get_current_logger()
    import os

    if jeeves_pb2 is None:
        raise HTTPException(
            status_code=503,
            detail="gRPC stubs not generated. Run proto compilation first."
        )

    # Get tools health from gRPC - this is required
    tools = []
    try:
        client = get_grpc_client()
        grpc_request = jeeves_pb2.GetHealthSummaryRequest()
        summary = await client.governance.GetHealthSummary(grpc_request)
        tools = [
            ToolHealthBrief(
                tool_name=t.tool_name,
                status=t.status,
                success_rate=t.success_rate,
                last_used=ms_to_iso(t.last_used_ms) if t.last_used_ms else None,
            )
            for t in summary.tools
        ]
    except Exception as e:
        _logger.error("Failed to get tools health from gRPC", error=str(e))
        raise HTTPException(
            status_code=503,
            detail=f"Backend unavailable: {str(e)}"
        )

    # Get agents from gRPC
    agents = []
    try:
        agents_request = jeeves_pb2.GetAgentsRequest()
        agents_response = await client.governance.GetAgents(agents_request)
        agents = [
            AgentInfo(
                name=a.name,
                description=a.description,
                status=a.status,
                layer=a.layer,
            )
            for a in agents_response.agents
        ]
    except Exception as e:
        _logger.error(
            "grpc_agents_fetch_failed",
            error=str(e),
            error_type=type(e).__name__,
        )
        # Return empty list per P2 (fail loudly, no dummy data)

    # Get memory layers from gRPC
    memory_layers = []
    try:
        layers_request = jeeves_pb2.GetMemoryLayersRequest()
        layers_response = await client.governance.GetMemoryLayers(layers_request)
        memory_layers = [
            MemoryLayerInfo(
                name=m.name,
                description=m.description,
                status=m.status,
                backend=m.backend,
            )
            for m in layers_response.layers
        ]
    except Exception as e:
        _logger.error(
            "grpc_memory_layers_fetch_failed",
            error=str(e),
            error_type=type(e).__name__,
        )
        # Return empty list per P2 (fail loudly, no dummy data)

    # Configuration from environment (this is real local config, not dummy data)
    config = ConfigInfo(
        llm_provider=os.environ.get("LLM_PROVIDER", "llamaserver"),
        database_backend=os.environ.get("DATABASE_BACKEND", "postgres"),
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
    )

    return DashboardResponse(
        tools=tools,
        agents=agents,
        memory_layers=memory_layers,
        config=config,
    )


@router.get("/health", response_model=HealthSummaryResponse)
async def get_health_summary(request: Request):
    """Get overall system health summary."""
    _logger = get_current_logger()
    if jeeves_pb2 is None:
        raise HTTPException(status_code=503, detail="gRPC stubs not generated")

    client = get_grpc_client()

    try:
        grpc_request = jeeves_pb2.GetHealthSummaryRequest()
        summary = await client.governance.GetHealthSummary(grpc_request)

        tools = [
            ToolHealthBrief(
                tool_name=t.tool_name,
                status=t.status,
                success_rate=t.success_rate,
                last_used=ms_to_iso(t.last_used_ms) if t.last_used_ms else None,
            )
            for t in summary.tools
        ]

        return HealthSummaryResponse(
            overall_status=summary.overall_status,
            total_tools=summary.total_tools,
            healthy_tools=summary.healthy_tools,
            degraded_tools=summary.degraded_tools,
            unhealthy_tools=summary.unhealthy_tools,
            tools=tools,
        )

    except Exception as e:
        _logger.error("get_health_summary_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tools/{tool_name}", response_model=ToolHealthResponse)
async def get_tool_health(request: Request, tool_name: str):
    """Get detailed health info for a specific tool."""
    _logger = get_current_logger()
    if jeeves_pb2 is None:
        raise HTTPException(status_code=503, detail="gRPC stubs not generated")

    client = get_grpc_client()

    try:
        grpc_request = jeeves_pb2.GetToolHealthRequest(tool_name=tool_name)
        health = await client.governance.GetToolHealth(grpc_request)

        return ToolHealthResponse(
            tool_name=health.tool_name,
            status=health.status,
            total_calls=health.total_calls,
            successful_calls=health.successful_calls,
            failed_calls=health.failed_calls,
            success_rate=health.success_rate,
            avg_latency_ms=health.avg_latency_ms,
            last_success=ms_to_iso(health.last_success_ms) if health.last_success_ms else None,
            last_failure=ms_to_iso(health.last_failure_ms) if health.last_failure_ms else None,
            last_error=health.last_error or None,
        )

    except Exception as e:
        _logger.error("get_tool_health_failed", error=str(e), tool_name=tool_name)
        raise HTTPException(status_code=404, detail=f"Tool not found: {tool_name}")


