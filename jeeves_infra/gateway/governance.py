"""Governance API router for L7 System Introspection (v0.13).

Provides endpoints for monitoring tool health and system governance:
- GET /api/v1/governance/health - System health summary
- GET /api/v1/governance/tools/{tool_name} - Individual tool health
- GET /api/v1/governance/dashboard - Web UI for governance metrics

v0.13 Updates (Constitution v3.0 Compliance):
- Removed OpenLoopService (deleted feature)
- Memory layer health overview
- Circuit breaker status

Constitutional Alignment:
- P5: Deterministic health reporting with clear thresholds
- P6: Observable system state for debugging
- L7: System introspection and meta-memory
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Depends, status, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from jeeves_infra.feature_flags import get_feature_flags
from jeeves_infra.memory.services.tool_health_service import ToolHealthService
from jeeves_infra.protocols import get_capability_resource_registry
from mission_system.config.constants import PLATFORM_NAME, PLATFORM_VERSION


def _get_service_display_name() -> str:
    """Get the display name for the current capability from registry.

    Returns:
        Service name from registry, or platform name as fallback.
    """
    registry = get_capability_resource_registry()
    default_service = registry.get_default_service()
    if default_service:
        service_config = registry.get_service_config(default_service)
        if service_config:
            return service_config.service_id
    return PLATFORM_NAME

router = APIRouter(prefix="/api/v1/governance", tags=["governance"])


# =============================================================================
# Response Models
# =============================================================================


class HealthSummaryResponse(BaseModel):
    """Response model for system health summary."""

    overall_status: str
    summary: Dict[str, int]  # healthy, degraded, unhealthy, unknown counts
    tools_needing_attention: list
    slow_executions: list
    checked_at: str


class ToolHealthResponse(BaseModel):
    """Response model for individual tool health."""

    tool_name: str
    status: str
    success_rate: float
    avg_latency_ms: float
    total_calls: int
    recent_errors: int
    issues: list
    recommendations: list
    checked_at: str


# =============================================================================
# Dependency Injection
# =============================================================================


def get_tool_health_service() -> ToolHealthService:
    """Dependency injection for ToolHealthService.

    This will be overridden by the app startup to inject the actual service.
    """
    # This is a placeholder - actual service injected via app.dependency_overrides
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="ToolHealthService not initialized"
    )


# =============================================================================
# API Endpoints
# =============================================================================


@router.get("/health", response_model=HealthSummaryResponse)
async def get_system_health(
    tool_health_service: ToolHealthService = Depends(get_tool_health_service),
) -> Dict[str, Any]:
    """Get system health summary for all tools.

    Returns:
        System health summary with:
        - Overall status (healthy, degraded, unhealthy, unknown)
        - Summary counts by status
        - Tools needing attention
        - Recent slow executions
        - Timestamp

    Raises:
        500 Internal Server Error: If health check fails
    """
    try:
        summary = await tool_health_service.get_dashboard_summary()
        return summary

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve system health: {str(e)}",
        )


@router.get("/tools/{tool_name}", response_model=ToolHealthResponse)
async def get_tool_health(
    tool_name: str,
    period_hours: int = 1,
    tool_health_service: ToolHealthService = Depends(get_tool_health_service),
) -> Dict[str, Any]:
    """Get health report for a specific tool.

    Args:
        tool_name: Name of the tool to check
        period_hours: Time period for analysis (default: 1 hour)

    Returns:
        Tool health report with:
        - Health status (healthy, degraded, unhealthy, unknown)
        - Success rate
        - Average latency
        - Total calls
        - Recent error count
        - Issues identified
        - Recommendations
        - Timestamp

    Raises:
        500 Internal Server Error: If health check fails
    """
    try:
        report = await tool_health_service.check_tool_health(
            tool_name=tool_name,
            period_hours=period_hours
        )
        return report.to_dict()

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve tool health: {str(e)}",
        )


# =============================================================================
# Web UI Endpoint
# =============================================================================


@router.get("/dashboard", response_class=HTMLResponse)
async def governance_dashboard(
    user_id: str = Query(default="system", description="User ID for open loop context"),
    tool_health_service: ToolHealthService = Depends(get_tool_health_service),
) -> str:
    """Render the governance dashboard web UI.

    v0.12 Updates:
    - Open loop detection section (L4 Working Memory)
    - Memory layer health overview
    - Circuit breaker status display

    Returns:
        HTML page with interactive governance dashboard showing:
        - System health status
        - Tool health cards
        - Latency metrics
        - Error patterns
        - Recommendations
        - Open loops summary (v0.12)
        - Memory layer status (v0.12)

    Raises:
        500 Internal Server Error: If rendering fails
    """
    try:
        # Get dashboard data
        summary = await tool_health_service.get_dashboard_summary()
        system_report = await tool_health_service.check_all_tools_health(period_hours=24)

        # Prepare data for template
        overall_status = summary["overall_status"]
        status_counts = summary["summary"]
        tools_needing_attention = summary["tools_needing_attention"]
        slow_executions = summary["slow_executions"]
        all_tools = [r.to_dict() for r in system_report.tool_reports]

        # v0.12: Get feature flags for circuit breaker status
        feature_flags = get_feature_flags()
        circuit_breaker_enabled = feature_flags.memory_tool_quarantine
        governance_mode = feature_flags.memory_governance_mode

        # v0.12: Get memory layer status
        memory_layers = _get_memory_layer_status(feature_flags)

        # Render HTML template
        html_content = _render_governance_html(
            overall_status=overall_status,
            status_counts=status_counts,
            all_tools=all_tools,
            tools_needing_attention=tools_needing_attention,
            slow_executions=slow_executions,
            checked_at=summary["checked_at"],
            circuit_breaker_enabled=circuit_breaker_enabled,
            governance_mode=governance_mode,
            memory_layers=memory_layers,
            user_id=user_id
        )

        return html_content

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to render governance dashboard: {str(e)}",
        )


def _get_memory_layer_status(feature_flags) -> List[Dict[str, Any]]:
    """Get status of all memory layers.

    Returns a list of memory layer status dictionaries for dashboard display.
    """
    return [
        {
            "layer": "L1",
            "name": "Canonical",
            "status": "Production",
            "description": "Tasks, journal, sessions, messages",
            "color": "#10b981"  # green
        },
        {
            "layer": "L2",
            "name": "Events",
            "status": "Wired" if feature_flags.memory_event_sourcing_mode != "disabled" else "Available",
            "description": "Audit trail, domain events",
            "color": "#10b981" if feature_flags.memory_event_sourcing_mode != "disabled" else "#6b7280"
        },
        {
            "layer": "L3",
            "name": "Semantic",
            "status": "Wired" if feature_flags.memory_semantic_mode != "disabled" else "Available",
            "description": "Chunk-based context for planner",
            "color": "#10b981" if feature_flags.memory_semantic_mode != "disabled" else "#6b7280"
        },
        {
            "layer": "L4",
            "name": "Working",
            "status": "Production",
            "description": "Session state, working context",
            "color": "#10b981"  # green
        },
        {
            "layer": "L5",
            "name": "Graph",
            "status": "Wired" if feature_flags.memory_graph_mode == "enabled" else "Available",
            "description": "Entity relationships, dependencies",
            "color": "#10b981" if feature_flags.memory_graph_mode == "enabled" else "#6b7280"
        },
        {
            "layer": "L7",
            "name": "Meta",
            "status": "Production",
            "description": "Tool metrics, circuit breaking",
            "color": "#10b981"  # green
        },
    ]


# =============================================================================
# HTML Rendering
# =============================================================================


def _render_governance_html(
    overall_status: str,
    status_counts: Dict[str, int],
    all_tools: list,
    tools_needing_attention: list,
    slow_executions: list,
    checked_at: str,
    circuit_breaker_enabled: bool = False,
    governance_mode: str = "disabled",
    memory_layers: Optional[List[Dict[str, Any]]] = None,
    user_id: str = "system"
) -> str:
    """Render governance dashboard HTML.

    v0.12 Updates: Added memory layer status and circuit breaker info.

    Args:
        overall_status: Overall system health status
        status_counts: Counts by status category
        all_tools: All tool health reports
        tools_needing_attention: Tools that are degraded/unhealthy
        slow_executions: Recent slow tool executions
        checked_at: Timestamp of health check
        circuit_breaker_enabled: Whether circuit breaker is enabled (v0.12)
        governance_mode: Current governance mode (v0.12)
        memory_layers: Memory layer status list (v0.12)
        user_id: User ID for open loops context (v0.12)

    Returns:
        HTML string
    """
    # Status badge styling
    status_colors = {
        "healthy": "#10b981",  # green
        "degraded": "#f59e0b",  # amber
        "unhealthy": "#ef4444",  # red
        "unknown": "#6b7280"   # gray
    }

    overall_color = status_colors.get(overall_status, "#6b7280")

    # Build tool cards HTML
    tool_cards_html = ""
    for tool in all_tools:
        tool_status = tool["status"]
        tool_color = status_colors.get(tool_status, "#6b7280")

        # Issues and recommendations
        issues_html = "".join([f"<li class='text-sm text-red-600'>{issue}</li>" for issue in tool["issues"]])
        recs_html = "".join([f"<li class='text-sm text-blue-600'>{rec}</li>" for rec in tool["recommendations"]])

        tool_cards_html += f"""
        <div class="border rounded-lg p-4 bg-white shadow-sm">
            <div class="flex justify-between items-start mb-2">
                <h3 class="font-semibold text-lg">{tool["tool_name"]}</h3>
                <span class="px-3 py-1 rounded-full text-xs font-semibold text-white" style="background-color: {tool_color}">
                    {tool_status.upper()}
                </span>
            </div>
            <div class="grid grid-cols-2 gap-2 text-sm mb-2">
                <div>
                    <span class="text-gray-600">Success Rate:</span>
                    <span class="font-medium">{tool["success_rate"]*100:.1f}%</span>
                </div>
                <div>
                    <span class="text-gray-600">Avg Latency:</span>
                    <span class="font-medium">{tool["avg_latency_ms"]:.0f}ms</span>
                </div>
                <div>
                    <span class="text-gray-600">Total Calls:</span>
                    <span class="font-medium">{tool["total_calls"]}</span>
                </div>
                <div>
                    <span class="text-gray-600">Recent Errors:</span>
                    <span class="font-medium">{tool["recent_errors"]}</span>
                </div>
            </div>
            {f'<div class="mt-2"><strong class="text-sm">Issues:</strong><ul class="list-disc pl-5">{issues_html}</ul></div>' if issues_html else ''}
            {f'<div class="mt-2"><strong class="text-sm">Recommendations:</strong><ul class="list-disc pl-5">{recs_html}</ul></div>' if recs_html else ''}
        </div>
        """

    # Build slow executions table
    slow_exec_rows = ""
    for exec in slow_executions:
        slow_exec_rows += f"""
        <tr>
            <td class="px-4 py-2 border-b">{exec["tool_name"]}</td>
            <td class="px-4 py-2 border-b">{exec["execution_time_ms"]}ms</td>
            <td class="px-4 py-2 border-b">{exec.get("recorded_at", "N/A")}</td>
        </tr>
        """

    # Get dynamic service name from registry
    service_name = _get_service_display_name()

    # Full HTML
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{service_name} - Governance Dashboard</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-50">
        <div class="container mx-auto px-4 py-8">
            <!-- Header -->
            <div class="mb-8">
                <h1 class="text-3xl font-bold text-gray-900 mb-2">Governance Dashboard</h1>
                <p class="text-gray-600">L7 System Introspection - Tool Health Monitoring</p>
                <p class="text-sm text-gray-500 mt-1">Last updated: {checked_at}</p>
            </div>

            <!-- Overall Status Card -->
            <div class="mb-6 p-6 rounded-lg shadow-md" style="background-color: {overall_color}; color: white;">
                <h2 class="text-2xl font-semibold mb-2">System Status: {overall_status.upper()}</h2>
                <div class="grid grid-cols-4 gap-4 mt-4">
                    <div class="text-center">
                        <div class="text-3xl font-bold">{status_counts.get('healthy', 0)}</div>
                        <div class="text-sm opacity-90">Healthy</div>
                    </div>
                    <div class="text-center">
                        <div class="text-3xl font-bold">{status_counts.get('degraded', 0)}</div>
                        <div class="text-sm opacity-90">Degraded</div>
                    </div>
                    <div class="text-center">
                        <div class="text-3xl font-bold">{status_counts.get('unhealthy', 0)}</div>
                        <div class="text-sm opacity-90">Unhealthy</div>
                    </div>
                    <div class="text-center">
                        <div class="text-3xl font-bold">{status_counts.get('unknown', 0)}</div>
                        <div class="text-sm opacity-90">Unknown</div>
                    </div>
                </div>
            </div>

            <!-- v0.12: Memory Layer Status & Safety Controls Grid -->
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
                <!-- Memory Layer Status -->
                <div class="p-6 bg-white rounded-lg shadow-md">
                    <h2 class="text-xl font-semibold text-gray-900 mb-4">Memory Layer Status</h2>
                    <div class="space-y-2">
                        {"".join([f'''
                        <div class="flex items-center justify-between p-2 rounded" style="background-color: {layer["color"]}10; border-left: 4px solid {layer["color"]}">
                            <div>
                                <span class="font-semibold">{layer["layer"]}: {layer["name"]}</span>
                                <span class="text-sm text-gray-600 ml-2">- {layer["description"]}</span>
                            </div>
                            <span class="px-2 py-1 text-xs font-semibold rounded" style="background-color: {layer["color"]}; color: white;">
                                {layer["status"]}
                            </span>
                        </div>
                        ''' for layer in (memory_layers or [])])}
                    </div>
                </div>

                <!-- Safety Controls (Circuit Breaker) -->
                <div class="p-6 bg-white rounded-lg shadow-md">
                    <h2 class="text-xl font-semibold text-gray-900 mb-4">Safety Controls</h2>
                    <div class="space-y-4">
                        <div class="flex items-center justify-between p-3 bg-gray-50 rounded">
                            <div>
                                <span class="font-semibold">Circuit Breaker</span>
                                <p class="text-sm text-gray-600">Auto-quarantine failing tools</p>
                            </div>
                            <span class="px-3 py-1 text-xs font-semibold rounded {'bg-green-500 text-white' if circuit_breaker_enabled else 'bg-gray-400 text-white'}">
                                {'ENABLED' if circuit_breaker_enabled else 'DISABLED'}
                            </span>
                        </div>
                        <div class="flex items-center justify-between p-3 bg-gray-50 rounded">
                            <div>
                                <span class="font-semibold">Governance Mode</span>
                                <p class="text-sm text-gray-600">L7 policy enforcement level</p>
                            </div>
                            <span class="px-3 py-1 text-xs font-semibold rounded {'bg-green-500 text-white' if governance_mode == 'log_and_enforce' else 'bg-yellow-500 text-white' if governance_mode == 'log_only' else 'bg-gray-400 text-white'}">
                                {governance_mode.upper().replace('_', ' ')}
                            </span>
                        </div>
                        <div class="mt-4 p-3 bg-blue-50 rounded border border-blue-200">
                            <p class="text-sm text-blue-800">
                                <strong>{service_name} v{PLATFORM_VERSION}</strong> - PostgreSQL + pgvector
                            </p>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Tools Needing Attention -->
            {f'''
            <div class="mb-6 p-6 bg-yellow-50 border border-yellow-200 rounded-lg">
                <h2 class="text-xl font-semibold text-yellow-900 mb-4">Tools Needing Attention</h2>
                <div class="space-y-3">
                    {"".join([f'<div class="bg-white p-3 rounded border border-yellow-300"><strong>{t["tool_name"]}</strong>: {t["status"]} (Success: {t["success_rate"]*100:.1f}%, Latency: {t["avg_latency_ms"]:.0f}ms)</div>' for t in tools_needing_attention])}
                </div>
            </div>
            ''' if tools_needing_attention else ''}

            <!-- All Tools Grid -->
            <div class="mb-6">
                <h2 class="text-2xl font-semibold text-gray-900 mb-4">All Tools</h2>
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {tool_cards_html}
                </div>
            </div>

            <!-- Slow Executions Table -->
            {f'''
            <div class="mb-6">
                <h2 class="text-2xl font-semibold text-gray-900 mb-4">Recent Slow Executions</h2>
                <div class="bg-white rounded-lg shadow overflow-hidden">
                    <table class="min-w-full">
                        <thead class="bg-gray-100">
                            <tr>
                                <th class="px-4 py-2 text-left text-sm font-semibold text-gray-700">Tool Name</th>
                                <th class="px-4 py-2 text-left text-sm font-semibold text-gray-700">Execution Time</th>
                                <th class="px-4 py-2 text-left text-sm font-semibold text-gray-700">Recorded At</th>
                            </tr>
                        </thead>
                        <tbody>
                            {slow_exec_rows}
                        </tbody>
                    </table>
                </div>
            </div>
            ''' if slow_executions else '<div class="mb-6 p-4 bg-green-50 border border-green-200 rounded-lg text-green-700">✅ No slow executions detected</div>'}

            <!-- Constitutional Alignment Note -->
            <div class="mt-8 p-4 bg-blue-50 border border-blue-200 rounded-lg">
                <h3 class="font-semibold text-blue-900 mb-2">Constitutional Alignment (v3.0)</h3>
                <ul class="text-sm text-blue-800 space-y-1">
                    <li>✓ <strong>P5 (Deterministic Spine):</strong> Health thresholds clearly defined (≥95% success = healthy, ≥80% = degraded)</li>
                    <li>✓ <strong>P6 (Testable/Observable):</strong> All tool metrics and memory layer status exposed</li>
                    <li>✓ <strong>L4 (Working Memory):</strong> Session state for capability context</li>
                    <li>✓ <strong>L7 (Meta-Memory):</strong> System introspection with circuit breaker enforcement</li>
                </ul>
            </div>

            <!-- Refresh Notice -->
            <div class="mt-6 text-center text-sm text-gray-500">
                <p>Dashboard auto-refreshes every 30 seconds</p>
                <button onclick="location.reload()" class="mt-2 px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600">
                    Refresh Now
                </button>
            </div>
        </div>

        <script>
            // Auto-refresh every 30 seconds
            setTimeout(function() {{
                location.reload();
            }}, 30000);
        </script>
    </body>
    </html>
    """
