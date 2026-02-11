"""GovernanceService implementation.

Provides interface for system health, tool metrics, agent status,
and memory layer introspection (L7).

Per JEEVES_CORE_CONSTITUTION.md Amendment X (Agent Boundaries):
- Reports on agent pipeline status (agents discovered via registry)
- Single responsibility per agent; prompts externalized

Per MEMORY_INFRASTRUCTURE_CONTRACT.md:
- Reports on L1-L7 memory layer statuses

Layer Extraction Compliant:
- Agent definitions are dynamically discovered via CapabilityResourceRegistry
- No hardcoded capability-specific agent names
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from jeeves_infra.logging import get_current_logger as get_logger
from jeeves_infra.utils.serialization import datetime_to_ms
from jeeves_infra.protocols import LoggerProtocol, get_capability_resource_registry


class ServiceError(Exception):
    """Service-level error with a code."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


def get_agent_definitions() -> List[dict]:
    """Get agent definitions from the CapabilityResourceRegistry.

    Layer Extraction Compliant: No hardcoded capability-specific agents.
    Queries the registry for dynamically registered agents.

    Returns:
        List of agent definitions with name, description, layer, and tools.
    """
    registry = get_capability_resource_registry()
    agent_configs = registry.get_agents()

    if agent_configs:
        return [
            {
                "name": agent.name,
                "description": agent.description,
                "layer": agent.layer,
                "tools": agent.tools,
            }
            for agent in agent_configs
        ]

    return []


class HealthServicer:
    """Governance service for health, agents, and memory layer introspection."""

    def __init__(self, tool_health_service, db=None, logger: Optional[LoggerProtocol] = None, kernel_client=None):
        self._logger = logger or get_logger()
        self.tool_health_service = tool_health_service
        self.db = db
        self._kernel_client = kernel_client

    async def get_health_summary(self) -> Dict[str, Any]:
        """Get overall system health summary.

        Returns:
            Dict with overall_status, tool counts, and per-tool briefs.

        Raises:
            ServiceError: On internal failure.
        """
        try:
            summary = await self.tool_health_service.get_health_summary()

            tools = []
            for tool_name, health in summary.get("tools", {}).items():
                tools.append({
                    "tool_name": tool_name,
                    "status": health.get("status", "unknown"),
                    "success_rate": health.get("success_rate", 0.0),
                    "last_used_ms": datetime_to_ms(health.get("last_used")),
                })

            healthy = sum(1 for t in tools if t["status"] == "healthy")
            degraded = sum(1 for t in tools if t["status"] == "degraded")
            unhealthy = sum(1 for t in tools if t["status"] == "unhealthy")

            if unhealthy > 0:
                overall = "unhealthy"
            elif degraded > 0:
                overall = "degraded"
            else:
                overall = "healthy"

            return {
                "overall_status": overall,
                "total_tools": len(tools),
                "healthy_tools": healthy,
                "degraded_tools": degraded,
                "unhealthy_tools": unhealthy,
                "tools": tools,
            }

        except Exception as e:
            self._logger.error("get_health_summary_error", error=str(e))
            raise ServiceError("INTERNAL", str(e))

    async def get_system_status(self) -> Dict[str, Any]:
        """Get system-level status from the kernel.

        Delegates to kernel.GetSystemStatus for process counts,
        service health, orchestration state, and commbus stats.

        Returns:
            Dict with processes, services, orchestration, commbus sections.

        Raises:
            ServiceError: If kernel_client is not available or call fails.
        """
        if not self._kernel_client:
            raise ServiceError("UNAVAILABLE", "kernel_client not configured")
        try:
            status = await self._kernel_client.get_system_status()
            return {
                "processes": {
                    "total": status.processes_total,
                    "by_state": status.processes_by_state,
                },
                "services": {
                    "healthy": status.services_healthy,
                    "degraded": status.services_degraded,
                    "unhealthy": status.services_unhealthy,
                },
                "orchestration": {
                    "active_sessions": status.active_orchestration_sessions,
                },
                "commbus": {
                    "events_published": status.commbus_events_published,
                    "commands_sent": status.commbus_commands_sent,
                    "queries_executed": status.commbus_queries_executed,
                    "active_subscribers": status.commbus_active_subscribers,
                },
            }
        except Exception as e:
            self._logger.error("get_system_status_error", error=str(e))
            raise ServiceError("INTERNAL", str(e))

    async def get_tool_health(self, tool_name: str) -> Dict[str, Any]:
        """Get detailed health info for a specific tool.

        Args:
            tool_name: Name of the tool to query.

        Returns:
            Dict with tool health details.

        Raises:
            ServiceError: NOT_FOUND if tool doesn't exist, INTERNAL on failure.
        """
        try:
            health = await self.tool_health_service.get_tool_health(tool_name)

            if not health:
                raise ServiceError("NOT_FOUND", f"Tool not found: {tool_name}")

            return {
                "tool_name": tool_name,
                "status": health.get("status", "unknown"),
                "total_calls": health.get("total_calls", 0),
                "successful_calls": health.get("successful_calls", 0),
                "failed_calls": health.get("failed_calls", 0),
                "success_rate": health.get("success_rate", 0.0),
                "avg_latency_ms": health.get("avg_latency_ms", 0.0),
                "last_success_ms": datetime_to_ms(health.get("last_success")),
                "last_failure_ms": datetime_to_ms(health.get("last_failure")),
                "last_error": health.get("last_error") or "",
            }

        except ServiceError:
            raise
        except Exception as e:
            self._logger.error("get_tool_health_error", error=str(e))
            raise ServiceError("INTERNAL", str(e))

    async def get_agents(self) -> Dict[str, Any]:
        """Get list of all agents in the pipeline.

        Layer Extraction Compliant: Queries CapabilityResourceRegistry
        for dynamically registered agents instead of hardcoded definitions.

        Returns:
            Dict with agents list.

        Raises:
            ServiceError: On internal failure.
        """
        try:
            agents = []
            agent_definitions = get_agent_definitions()

            for agent_def in agent_definitions:
                agents.append({
                    "name": agent_def["name"],
                    "description": agent_def["description"],
                    "status": "active",
                    "layer": agent_def["layer"],
                    "tools": agent_def["tools"],
                })

            self._logger.info("get_agents_completed", agent_count=len(agents))
            return {"agents": agents}

        except Exception as e:
            self._logger.error("get_agents_error", error=str(e))
            raise ServiceError("INTERNAL", str(e))

    async def get_memory_layers(self) -> Dict[str, Any]:
        """Get status of all memory layers.

        Returns:
            Dict with layers list.

        Raises:
            ServiceError: On internal failure.
        """
        try:
            from jeeves_infra.protocols.capability import get_capability_resource_registry
            registry = get_capability_resource_registry()
            memory_layer_defs = registry.get_memory_layers()

            layers = []
            for layer_def in memory_layer_defs:
                status = await self._check_layer_status(layer_def)

                layers.append({
                    "name": layer_def["name"],
                    "description": layer_def["description"],
                    "status": status,
                    "backend": layer_def["backend"],
                    "layer_id": layer_def["layer_id"],
                })

            self._logger.info("get_memory_layers_completed", layer_count=len(layers))
            return {"layers": layers}

        except Exception as e:
            self._logger.error("get_memory_layers_error", error=str(e))
            raise ServiceError("INTERNAL", str(e))

    async def _check_layer_status(self, layer_def: dict) -> str:
        """Check if a memory layer is operational by probing its tables."""
        if layer_def["layer_id"] == "L6":
            return "inactive"

        if self.db is None:
            return "unknown"

        if not layer_def["tables"]:
            return "active"

        tables_ok = 0
        tables_total = len(layer_def["tables"])

        for table in layer_def["tables"]:
            try:
                await self.db.fetch_one(f"SELECT 1 FROM {table} LIMIT 1")
                tables_ok += 1
            except Exception:
                pass

        if tables_ok == tables_total:
            return "active"
        elif tables_ok > 0:
            return "degraded"
        else:
            return "inactive"
