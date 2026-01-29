"""Memory repositories for data persistence.

Repositories:
- EventRepository: L2 append-only event log
- TraceRepository: Agent execution traces
- PgVectorRepository: L3 semantic vector storage
- ChunkRepository: L3 semantic chunks
- InMemoryGraphStorage: L5 graph stub for development
- SessionStateRepository: L4 working memory
- ToolMetricsRepository: L7 tool health metrics
- InMemorySkillStorage: L6 skills stub for development

For production graph storage, use PostgresGraphAdapter from jeeves_infra.postgres.

Constitutional Reference:
- Memory Module CONSTITUTION: L5 Graph, L6 Skills (extensible)
- Architecture: PostgreSQL-specific code lives in jeeves_infra.postgres
"""

from jeeves_infra.memory.repositories.event_repository import EventRepository, DomainEvent
from jeeves_infra.memory.repositories.trace_repository import TraceRepository, AgentTrace
from jeeves_infra.memory.repositories.pgvector_repository import PgVectorRepository
from jeeves_infra.memory.repositories.chunk_repository import ChunkRepository, Chunk
from jeeves_infra.memory.repositories.session_state_repository import SessionStateRepository, SessionState
from jeeves_infra.memory.repositories.tool_metrics_repository import ToolMetricsRepository, ToolMetric
# L5-L6 extensible stubs (in-memory implementations for development/testing)
from jeeves_infra.memory.repositories.graph_stub import InMemoryGraphStorage, GraphNode, GraphEdge
from jeeves_infra.memory.repositories.skill_stub import InMemorySkillStorage, Skill, SkillUsage

__all__ = [
    # L2 Events
    "EventRepository",
    "DomainEvent",
    # Traces
    "TraceRepository",
    "AgentTrace",
    # L3 Semantic
    "PgVectorRepository",
    "ChunkRepository",
    "Chunk",
    # L5 Graph (in-memory stub - for production use PostgresGraphAdapter)
    "InMemoryGraphStorage",
    "GraphNode",
    "GraphEdge",
    # L6 Skills (stub - extensible)
    "InMemorySkillStorage",
    "Skill",
    "SkillUsage",
    # L4 Session
    "SessionStateRepository",
    "SessionState",
    # L7 Metrics
    "ToolMetricsRepository",
    "ToolMetric",
]
