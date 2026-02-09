"""Memory repositories for data persistence.

Repositories:
- EventRepository: L2 append-only event log
- TraceRepository: Agent execution traces
- ChunkRepository: L3 semantic chunks
- InMemoryGraphStorage: L5 graph stub for development
- SessionStateRepository: L4 working memory
- ToolMetricsRepository: L7 tool health metrics

Concrete vector storage is owned by capabilities.
"""

from mission_system.memory.repositories.event_repository import EventRepository, DomainEvent
from mission_system.memory.repositories.trace_repository import TraceRepository, AgentTrace
from mission_system.memory.repositories.chunk_repository import ChunkRepository, Chunk
from mission_system.memory.repositories.session_state_repository import SessionStateRepository, SessionState
from mission_system.memory.repositories.tool_metrics_repository import ToolMetricsRepository, ToolMetric
# L5 extensible stub (in-memory implementation for development/testing)
from mission_system.memory.repositories.graph_stub import InMemoryGraphStorage, GraphNode, GraphEdge

__all__ = [
    # L2 Events
    "EventRepository",
    "DomainEvent",
    # Traces
    "TraceRepository",
    "AgentTrace",
    # L3 Semantic
    "ChunkRepository",
    "Chunk",
    # L5 Graph (in-memory stub)
    "InMemoryGraphStorage",
    "GraphNode",
    "GraphEdge",
    # L4 Session
    "SessionStateRepository",
    "SessionState",
    # L7 Metrics
    "ToolMetricsRepository",
    "ToolMetric",
]
