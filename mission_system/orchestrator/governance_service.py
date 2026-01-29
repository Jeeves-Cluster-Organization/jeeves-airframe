"""
GovernanceService implementation.

Provides gRPC interface for system health, tool metrics, agent status,
and memory layer introspection (L7).

Per JEEVES_CORE_CONSTITUTION.md Amendment X (Agent Boundaries):
- Reports on the 7-agent pipeline status
- Single responsibility per agent; prompts externalized

Per MEMORY_INFRASTRUCTURE_CONTRACT.md:
- Reports on L1-L7 memory layer statuses

Layer Extraction Compliant:
- Agent definitions are dynamically discovered via CapabilityResourceRegistry
- No hardcoded capability-specific agent names
"""

from __future__ import annotations

from typing import List, Optional

import grpc

from mission_system.adapters import get_logger
from jeeves_infra.utils.serialization import datetime_to_ms
from jeeves_infra.protocols import LoggerProtocol, get_capability_resource_registry

try:
    from proto import jeeves_pb2, jeeves_pb2_grpc
except ImportError:
    jeeves_pb2 = None
    jeeves_pb2_grpc = None


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
        # Convert CapabilityAgentConfig to dict format
        return [
            {
                "name": agent.name,
                "description": agent.description,
                "layer": agent.layer,
                "tools": agent.tools,
            }
            for agent in agent_configs
        ]

    # Fallback: return empty list if no agents registered
    return []

# Memory Layer Definitions (from MEMORY_INFRASTRUCTURE_CONTRACT.md)
MEMORY_LAYER_DEFINITIONS = [
    {
        "layer_id": "L1",
        "name": "Canonical State Store",
        "description": "Single source of truth - tasks, journal_entries, sessions, messages",
        "backend": "postgres",
        "tables": ["tasks", "journal_entries", "sessions", "messages", "kv_store"],
    },
    {
        "layer_id": "L2",
        "name": "Event Log & Trace Store",
        "description": "Immutable record of state changes and agent decisions",
        "backend": "postgres",
        "tables": ["domain_events", "agent_traces"],
    },
    {
        "layer_id": "L3",
        "name": "Semantic Memory",
        "description": "Semantic search with pgvector embeddings",
        "backend": "pgvector",
        "tables": ["semantic_chunks"],
    },
    {
        "layer_id": "L4",
        "name": "Working Memory",
        "description": "Bounded context for conversations, open loops, flow interrupts",
        "backend": "postgres",
        "tables": ["session_state", "open_loops", "flow_interrupts"],
    },
    {
        "layer_id": "L5",
        "name": "State Graph",
        "description": "Entity relationships and dependencies",
        "backend": "postgres",
        "tables": ["graph_nodes", "graph_edges"],
    },
    {
        "layer_id": "L6",
        "name": "Skills & Patterns",
        "description": "Reusable workflow patterns (deferred to v3.x)",
        "backend": "none",
        "tables": [],
    },
    {
        "layer_id": "L7",
        "name": "Meta-Memory & Governance",
        "description": "System behavior tracking, tool metrics, prompt versions",
        "backend": "postgres",
        "tables": ["tool_metrics", "prompt_versions", "agent_evaluations"],
    },
]


class HealthServicer(jeeves_pb2_grpc.GovernanceServiceServicer):
    """gRPC implementation of GovernanceService."""

    def __init__(self, tool_health_service, db=None, logger: Optional[LoggerProtocol] = None):
        self._logger = logger or get_logger()
        self.tool_health_service = tool_health_service
        self.db = db  # Database client for layer status checks

    async def GetHealthSummary(
        self,
        request: jeeves_pb2.GetHealthSummaryRequest,
        context: grpc.aio.ServicerContext,
    ) -> jeeves_pb2.HealthSummary:
        """Get overall system health summary."""
        try:
            summary = await self.tool_health_service.get_health_summary()

            tools = []
            for tool_name, health in summary.get("tools", {}).items():
                tools.append(jeeves_pb2.ToolHealthBrief(
                    tool_name=tool_name,
                    status=health.get("status", "unknown"),
                    success_rate=health.get("success_rate", 0.0),
                    last_used_ms=datetime_to_ms(health.get("last_used")),
                ))

            # Calculate counts
            healthy = sum(1 for t in tools if t.status == "healthy")
            degraded = sum(1 for t in tools if t.status == "degraded")
            unhealthy = sum(1 for t in tools if t.status == "unhealthy")

            # Determine overall status
            if unhealthy > 0:
                overall = "unhealthy"
            elif degraded > 0:
                overall = "degraded"
            else:
                overall = "healthy"

            return jeeves_pb2.HealthSummary(
                overall_status=overall,
                total_tools=len(tools),
                healthy_tools=healthy,
                degraded_tools=degraded,
                unhealthy_tools=unhealthy,
                tools=tools,
            )

        except Exception as e:
            self._logger.error("get_health_summary_error", error=str(e))
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

    async def GetToolHealth(
        self,
        request: jeeves_pb2.GetToolHealthRequest,
        context: grpc.aio.ServicerContext,
    ) -> jeeves_pb2.ToolHealth:
        """Get detailed health info for a specific tool."""
        try:
            health = await self.tool_health_service.get_tool_health(request.tool_name)

            if not health:
                await context.abort(grpc.StatusCode.NOT_FOUND, f"Tool not found: {request.tool_name}")
                return  # Never reached, but satisfies type checker

            return jeeves_pb2.ToolHealth(
                tool_name=request.tool_name,
                status=health.get("status", "unknown"),
                total_calls=health.get("total_calls", 0),
                successful_calls=health.get("successful_calls", 0),
                failed_calls=health.get("failed_calls", 0),
                success_rate=health.get("success_rate", 0.0),
                avg_latency_ms=health.get("avg_latency_ms", 0.0),
                last_success_ms=datetime_to_ms(health.get("last_success")),
                last_failure_ms=datetime_to_ms(health.get("last_failure")),
                last_error=health.get("last_error") or "",
            )

        except grpc.RpcError:
            raise
        except Exception as e:
            self._logger.error("get_tool_health_error", error=str(e))
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

    async def GetAgents(
        self,
        request: jeeves_pb2.GetAgentsRequest,
        context: grpc.aio.ServicerContext,
    ) -> jeeves_pb2.GetAgentsResponse:
        """Get list of all agents in the pipeline.

        Layer Extraction Compliant: Queries CapabilityResourceRegistry
        for dynamically registered agents instead of hardcoded definitions.
        """
        try:
            agents = []
            agent_definitions = get_agent_definitions()

            for agent_def in agent_definitions:
                agents.append(jeeves_pb2.AgentInfo(
                    name=agent_def["name"],
                    description=agent_def["description"],
                    status="active",  # All agents are active when orchestrator is running
                    layer=agent_def["layer"],
                    tools=agent_def["tools"],
                ))

            self._logger.info("get_agents_completed", agent_count=len(agents))
            return jeeves_pb2.GetAgentsResponse(agents=agents)

        except Exception as e:
            self._logger.error("get_agents_error", error=str(e))
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

    async def GetMemoryLayers(
        self,
        request: jeeves_pb2.GetMemoryLayersRequest,
        context: grpc.aio.ServicerContext,
    ) -> jeeves_pb2.GetMemoryLayersResponse:
        """Get status of all memory layers (L1-L7)."""
        try:
            layers = []
            for layer_def in MEMORY_LAYER_DEFINITIONS:
                # Determine layer status by checking if tables exist and are accessible
                status = await self._check_layer_status(layer_def)

                layers.append(jeeves_pb2.MemoryLayerInfo(
                    name=layer_def["name"],
                    description=layer_def["description"],
                    status=status,
                    backend=layer_def["backend"],
                    layer_id=layer_def["layer_id"],
                ))

            self._logger.info("get_memory_layers_completed", layer_count=len(layers))
            return jeeves_pb2.GetMemoryLayersResponse(layers=layers)

        except Exception as e:
            self._logger.error("get_memory_layers_error", error=str(e))
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

    async def _check_layer_status(self, layer_def: dict) -> str:
        """Check if a memory layer is operational by probing its tables."""
        # L6 is deferred - always inactive
        if layer_def["layer_id"] == "L6":
            return "inactive"

        # If no db connection, can't check
        if self.db is None:
            return "unknown"

        # If no tables defined, assume active
        if not layer_def["tables"]:
            return "active"

        # Check if at least one table is accessible
        tables_ok = 0
        tables_total = len(layer_def["tables"])

        for table in layer_def["tables"]:
            try:
                # Try a simple query to verify table exists and is accessible
                await self.db.fetch_one(f"SELECT 1 FROM {table} LIMIT 1")
                tables_ok += 1
            except Exception:
                # Table doesn't exist or isn't accessible
                pass

        # Determine status based on table accessibility
        if tables_ok == tables_total:
            return "active"
        elif tables_ok > 0:
            return "degraded"
        else:
            return "inactive"
