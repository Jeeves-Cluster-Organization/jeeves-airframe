"""
Governance router - System health and introspection endpoints (L7).

Provides read-only access to tool health metrics.
"""

from __future__ import annotations

import os
from typing import List, Optional

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from jeeves_infra.logging import get_current_logger
from jeeves_infra.utils.serialization import ms_to_iso

router = APIRouter()


# =============================================================================
# Response Models
# =============================================================================

class ToolHealthBrief(BaseModel):
    tool_name: str
    status: str
    success_rate: float
    last_used: Optional[str] = None


class HealthSummaryResponse(BaseModel):
    overall_status: str
    total_tools: int
    healthy_tools: int
    degraded_tools: int
    unhealthy_tools: int
    tools: List[ToolHealthBrief]


class ToolHealthResponse(BaseModel):
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
    name: str
    description: str
    status: str
    layer: str


class MemoryLayerInfo(BaseModel):
    name: str
    description: str
    status: str
    backend: str


class ConfigInfo(BaseModel):
    llm_provider: str
    database_backend: str
    log_level: str


class DashboardResponse(BaseModel):
    tools: List[ToolHealthBrief]
    agents: List[AgentInfo]
    memory_layers: List[MemoryLayerInfo]
    config: ConfigInfo


# =============================================================================
# Helpers
# =============================================================================

def _get_health_servicer(request: Request):
    servicer = getattr(request.app.state, "health_servicer", None)
    if servicer is None:
        raise HTTPException(status_code=503, detail="Health service not configured")
    return servicer


# =============================================================================
# Governance Endpoints
# =============================================================================

@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(request: Request):
    _logger = get_current_logger()
    servicer = _get_health_servicer(request)

    # Tools health
    tools = []
    try:
        summary = await servicer.get_health_summary()
        tools = [
            ToolHealthBrief(
                tool_name=t["tool_name"],
                status=t["status"],
                success_rate=t["success_rate"],
                last_used=ms_to_iso(t["last_used_ms"]) if t.get("last_used_ms") else None,
            )
            for t in summary.get("tools", [])
        ]
    except Exception as e:
        _logger.error("Failed to get tools health", error=str(e))
        raise HTTPException(status_code=503, detail=f"Backend unavailable: {str(e)}")

    # Agents
    agents = []
    try:
        agents_result = await servicer.get_agents()
        agents = [
            AgentInfo(
                name=a["name"],
                description=a["description"],
                status=a["status"],
                layer=a["layer"],
            )
            for a in agents_result.get("agents", [])
        ]
    except Exception as e:
        _logger.error("agents_fetch_failed", error=str(e))

    # Memory layers
    memory_layers = []
    try:
        layers_result = await servicer.get_memory_layers()
        memory_layers = [
            MemoryLayerInfo(
                name=m["name"],
                description=m["description"],
                status=m["status"],
                backend=m["backend"],
            )
            for m in layers_result.get("layers", [])
        ]
    except Exception as e:
        _logger.error("memory_layers_fetch_failed", error=str(e))

    config = ConfigInfo(
        llm_provider=os.environ.get("LLM_PROVIDER", "llamaserver"),
        database_backend=os.environ.get("DATABASE_BACKEND", "unknown"),
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
    _logger = get_current_logger()
    servicer = _get_health_servicer(request)

    try:
        summary = await servicer.get_health_summary()
        tools = [
            ToolHealthBrief(
                tool_name=t["tool_name"],
                status=t["status"],
                success_rate=t["success_rate"],
                last_used=ms_to_iso(t["last_used_ms"]) if t.get("last_used_ms") else None,
            )
            for t in summary.get("tools", [])
        ]
        return HealthSummaryResponse(
            overall_status=summary["overall_status"],
            total_tools=summary["total_tools"],
            healthy_tools=summary["healthy_tools"],
            degraded_tools=summary["degraded_tools"],
            unhealthy_tools=summary["unhealthy_tools"],
            tools=tools,
        )
    except Exception as e:
        _logger.error("get_health_summary_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tools/{tool_name}", response_model=ToolHealthResponse)
async def get_tool_health(request: Request, tool_name: str):
    _logger = get_current_logger()
    servicer = _get_health_servicer(request)

    try:
        health = await servicer.get_tool_health(tool_name)
        return ToolHealthResponse(
            tool_name=health["tool_name"],
            status=health["status"],
            total_calls=health["total_calls"],
            successful_calls=health["successful_calls"],
            failed_calls=health["failed_calls"],
            success_rate=health["success_rate"],
            avg_latency_ms=health["avg_latency_ms"],
            last_success=ms_to_iso(health["last_success_ms"]) if health.get("last_success_ms") else None,
            last_failure=ms_to_iso(health["last_failure_ms"]) if health.get("last_failure_ms") else None,
            last_error=health.get("last_error") or None,
        )
    except Exception as e:
        _logger.error("get_tool_health_failed", error=str(e), tool_name=tool_name)
        raise HTTPException(status_code=404, detail=f"Tool not found: {tool_name}")
