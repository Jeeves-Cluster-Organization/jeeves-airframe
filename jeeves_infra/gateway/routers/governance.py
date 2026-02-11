"""Governance API router - L7 system introspection endpoints.

Provides REST endpoints for tool health and system observability:
- GET /api/v1/governance/health - System health summary
- GET /api/v1/governance/tools/{tool_name} - Tool health report
- GET /api/v1/governance/dashboard - Governance dashboard (HTML)

Constitutional Alignment:
- P5: Deterministic health checks with clear thresholds
- P6: Observable debugging and system metrics
- L7: Meta-memory system introspection
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from typing import Any, Dict

from jeeves_infra.memory.tool_health_service import ToolHealthService

router = APIRouter(prefix="/api/v1/governance", tags=["governance"])


def get_tool_health_service() -> ToolHealthService:
    """Dependency injection for ToolHealthService.

    Overridden by CapabilityResourceRegistry at startup to inject the real instance.
    """
    raise HTTPException(status_code=503, detail="Governance service not initialized")


@router.get("/health")
async def get_system_health(
    service: ToolHealthService = Depends(get_tool_health_service),
) -> Dict[str, Any]:
    """System health summary across all tools."""
    return await service.get_dashboard_summary()


@router.get("/tools/{tool_name}")
async def get_tool_health(
    tool_name: str,
    period_hours: int = Query(default=1, ge=1, le=168),
    service: ToolHealthService = Depends(get_tool_health_service),
) -> Dict[str, Any]:
    """Individual tool health report with performance metrics."""
    report = await service.check_tool_health(tool_name, period_hours=period_hours)
    return report.to_dict()


@router.get("/dashboard", response_class=HTMLResponse)
async def governance_dashboard(
    service: ToolHealthService = Depends(get_tool_health_service),
) -> str:
    """Governance dashboard - HTML view of system health."""
    summary = await service.get_dashboard_summary()

    status = summary.get("overall_status", "unknown")
    counts = summary.get("summary", {})
    tools = summary.get("tools_needing_attention", [])
    checked_at = summary.get("checked_at", "")

    tool_rows = ""
    for t in tools:
        tool_rows += f"<tr><td>{t.get('tool_name', '')}</td><td>{t.get('status', '')}</td><td>{t.get('issue', '')}</td></tr>\n"

    return f"""<!DOCTYPE html>
<html><head><title>Governance Dashboard</title></head>
<body>
<h1>Governance Dashboard</h1>
<h2>L7 System Introspection</h2>
<p>Overall Status: <strong>{status}</strong></p>
<p>System Status: healthy={counts.get('healthy', 0)} degraded={counts.get('degraded', 0)} unhealthy={counts.get('unhealthy', 0)}</p>
<p>Checked at: {checked_at}</p>
<h3>Tools Needing Attention</h3>
<table><tr><th>Tool</th><th>Status</th><th>Issue</th></tr>
{tool_rows}</table>
</body></html>"""
