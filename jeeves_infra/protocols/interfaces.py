"""Protocol definitions - interfaces for dependency injection.

These are typing.Protocol classes for static type checking.
Implementations are in Go or Python adapters.

Moved from jeeves_core/protocols.py as part of Session 10
(Complete Python Removal from jeeves-core).
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable, ClassVar


# =============================================================================
# REQUEST CONTEXT
# =============================================================================

@dataclass(frozen=True)
class RequestContext:
    """Immutable request context for tracing and logging.

    Used with ContextVars for async-safe request tracking (ADR-001 Decision 5).

    Usage:
        ctx = RequestContext(
            request_id=str(uuid4()),
            capability="code_analysis",
            user_id="user-123",
        )
        with request_scope(ctx, logger):
            # All code in this scope has access to context
            ...
    """
    request_id: str
    capability: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    agent_role: Optional[str] = None
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    tags: Dict[str, str] = field(default_factory=dict)

    # Guardrails to prevent schema creep in tags
    MAX_TAGS: ClassVar[int] = 16
    MAX_TAG_KEY_LENGTH: ClassVar[int] = 64
    MAX_TAG_VALUE_LENGTH: ClassVar[int] = 256

    def __post_init__(self) -> None:
        if not isinstance(self.request_id, str) or not self.request_id.strip():
            raise ValueError("request_id is required and must be a non-empty string")
        if not isinstance(self.capability, str) or not self.capability.strip():
            raise ValueError("capability is required and must be a non-empty string")

        for field_name in ("session_id", "user_id", "agent_role", "trace_id", "span_id"):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string or None")

        if not isinstance(self.tags, dict):
            raise TypeError("tags must be a dict of string keys and values")
        if len(self.tags) > self.MAX_TAGS:
            raise ValueError(f"tags exceed max count ({self.MAX_TAGS})")
        for key, value in self.tags.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("tag keys must be non-empty strings")
            if not isinstance(value, str):
                raise ValueError("tag values must be strings")
            if len(key) > self.MAX_TAG_KEY_LENGTH:
                raise ValueError(f"tag key exceeds max length ({self.MAX_TAG_KEY_LENGTH})")
            if len(value) > self.MAX_TAG_VALUE_LENGTH:
                raise ValueError(f"tag value exceeds max length ({self.MAX_TAG_VALUE_LENGTH})")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a serializable dictionary."""
        return {
            "request_id": self.request_id,
            "capability": self.capability,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "agent_role": self.agent_role,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "tags": self.tags,
        }


# =============================================================================
# LOGGING
# =============================================================================

@runtime_checkable
class LoggerProtocol(Protocol):
    """Structured logging interface."""

    def info(self, message: str, **kwargs: Any) -> None: ...
    def debug(self, message: str, **kwargs: Any) -> None: ...
    def warning(self, message: str, **kwargs: Any) -> None: ...
    def error(self, message: str, **kwargs: Any) -> None: ...
    def bind(self, **kwargs: Any) -> "LoggerProtocol": ...


# =============================================================================
# DATABASE
# =============================================================================

@runtime_checkable
class DatabaseClientProtocol(Protocol):
    """Database client interface.

    Lifecycle: connect/disconnect
    Query: execute/fetch_one/fetch_all (raw SQL)
    Data: insert/update/upsert (structured), initialize_schema (DDL from file)
    Transaction: transaction() context manager (ACID)
    Identity: backend property
    """

    # Lifecycle
    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...

    # Query
    async def execute(self, query: str, params: Optional[Dict[str, Any]] = None) -> None: ...
    async def fetch_one(self, query: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]: ...
    async def fetch_all(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]: ...

    # Data
    async def insert(self, table: str, data: Dict[str, Any]) -> None: ...
    async def update(self, table: str, data: Dict[str, Any], where_clause: str, where_params: Optional[Any] = None) -> int: ...
    async def upsert(self, table: str, data: Dict[str, Any], key_columns: List[str]) -> None: ...
    async def initialize_schema(self, schema_path: str) -> None: ...

    # Transaction
    def transaction(self): ...

    # Identity
    @property
    def backend(self) -> str: ...


# =============================================================================
# LLM
# =============================================================================

@runtime_checkable
class LLMProviderProtocol(Protocol):
    """LLM provider interface."""

    async def generate(
        self,
        model: str,
        prompt: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> str: ...

    async def generate_stream(
        self,
        model: str,
        prompt: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> Any: ...  # AsyncIterator[TokenChunk]

    async def health_check(self) -> bool: ...


# =============================================================================
# TOOLS
# =============================================================================

@runtime_checkable
class ToolProtocol(Protocol):
    """Tool interface for individual tool implementations."""

    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]: ...


@runtime_checkable
class ToolDefinitionProtocol(Protocol):
    """Tool definition returned by registry lookups."""
    name: str
    function: Any  # Callable - using Any for protocol compatibility
    parameters: Dict[str, str]
    description: str


@runtime_checkable
class ToolRegistryProtocol(Protocol):
    """Tool registry interface for managing and accessing tools."""

    def has_tool(self, name: str) -> bool: ...
    def get_tool(self, name: str) -> Optional[ToolDefinitionProtocol]: ...


# =============================================================================
# APP CONTEXT
# =============================================================================

@runtime_checkable
class SettingsProtocol(Protocol):
    """Settings interface."""

    def get(self, key: str, default: Any = None) -> Any: ...
    def set(self, key: str, value: Any) -> None: ...


@runtime_checkable
class FeatureFlagsProtocol(Protocol):
    """Feature flags interface."""

    def is_enabled(self, flag: str) -> bool: ...
    def get_variant(self, flag: str) -> Optional[str]: ...


@runtime_checkable
class ClockProtocol(Protocol):
    """Clock interface for deterministic time."""

    def now(self) -> datetime: ...
    def utcnow(self) -> datetime: ...


@runtime_checkable
class AppContextProtocol(Protocol):
    """Application context interface."""

    @property
    def settings(self) -> SettingsProtocol: ...

    @property
    def feature_flags(self) -> FeatureFlagsProtocol: ...

    @property
    def logger(self) -> LoggerProtocol: ...


# =============================================================================
# MEMORY
# =============================================================================

@dataclass
class SearchResult:
    """Search result from semantic search."""
    id: str
    content: str
    score: float
    metadata: Dict[str, Any]


@runtime_checkable
class SemanticSearchProtocol(Protocol):
    """Semantic search interface."""

    async def search(
        self,
        query: str,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]: ...

    async def index(self, id: str, content: str, metadata: Dict[str, Any]) -> None: ...


@runtime_checkable
class SessionStateProtocol(Protocol):
    """Session state interface."""

    async def get(self, session_id: str) -> Optional[Dict[str, Any]]: ...
    async def set(self, session_id: str, state: Dict[str, Any]) -> None: ...
    async def delete(self, session_id: str) -> None: ...


# =============================================================================
# DISTRIBUTED BUS
# =============================================================================

@dataclass
class DistributedTask:
    """Task for distributed agent pipeline execution."""
    task_id: str
    envelope_state: Dict[str, Any]
    agent_name: str
    stage_order: int
    checkpoint_id: Optional[str] = None
    created_at: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    priority: int = 0


@dataclass
class QueueStats:
    """Queue statistics for monitoring."""
    queue_name: str
    pending_count: int
    in_progress_count: int
    completed_count: int
    failed_count: int
    avg_processing_time_ms: float = 0.0
    workers_active: int = 0


@runtime_checkable
class DistributedBusProtocol(Protocol):
    """Distributed message bus interface for horizontal scaling."""

    async def enqueue_task(self, queue_name: str, task: DistributedTask) -> str: ...

    async def dequeue_task(
        self,
        queue_name: str,
        worker_id: str,
        timeout_seconds: int = 30,
    ) -> Optional[DistributedTask]: ...

    async def complete_task(self, task_id: str, result: Dict[str, Any]) -> None: ...
    async def fail_task(self, task_id: str, error: str, retry: bool = True) -> None: ...
    async def register_worker(self, worker_id: str, capabilities: List[str]) -> None: ...
    async def deregister_worker(self, worker_id: str) -> None: ...
    async def heartbeat(self, worker_id: str) -> None: ...
    async def get_queue_stats(self, queue_name: str) -> QueueStats: ...
    async def list_queues(self) -> List[str]: ...
    async def stats(self, task_type: str) -> QueueStats: ...


# =============================================================================
# EVENT BUS
# =============================================================================

@runtime_checkable
class EventBusProtocol(Protocol):
    """Event bus interface for pub/sub messaging."""

    def publish(self, event_type: str, payload: Dict[str, Any]) -> None: ...
    def subscribe(self, event_type: str, handler: Any) -> None: ...
    def unsubscribe(self, event_type: str, handler: Any) -> None: ...


# =============================================================================
# TOOL EXECUTOR
# =============================================================================

@runtime_checkable
class ToolExecutorProtocol(Protocol):
    """Tool executor interface for running tools."""

    async def execute(
        self,
        tool_name: str,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]: ...

    def get_available_tools(self) -> List[str]: ...


# =============================================================================
# CONFIG REGISTRY
# =============================================================================

@runtime_checkable
class ConfigRegistryProtocol(Protocol):
    """Configuration registry for dependency injection."""

    def register(self, key: str, value: Any) -> None: ...
    def get(self, key: str, default: Any = None) -> Any: ...
    def has(self, key: str) -> bool: ...


# =============================================================================
# CAPABILITY LLM CONFIGURATION
# =============================================================================

@dataclass
class AgentLLMConfig:
    """LLM configuration for a specific agent.

    This Python dataclass is the canonical definition. Validation and defaults included.
    """
    agent_name: str
    model: str  # Required — capability must specify
    temperature: Optional[float] = 0.3
    max_tokens: int = 2000
    server_url: Optional[str] = None
    provider: Optional[str] = None
    timeout_seconds: int = 120
    context_window: int = 16384



# =============================================================================
# AGENT TOOL ACCESS
# =============================================================================

@runtime_checkable
class AgentToolAccessProtocol(Protocol):
    """Agent tool access control interface."""

    def can_access(self, agent_name: str, tool_name: str) -> bool: ...
    def get_allowed_tools(self, agent_name: str) -> List[str]: ...


# =============================================================================
# INFRASTRUCTURE PROTOCOLS
# =============================================================================

@runtime_checkable
class WebSocketManagerProtocol(Protocol):
    """WebSocket event streaming interface."""

    async def broadcast(self, event_type: str, payload: Dict[str, Any]) -> None: ...

    @property
    def connection_count(self) -> int: ...


@runtime_checkable
class EventBridgeProtocol(Protocol):
    """Bridge for kernel events to external systems."""

    async def emit(self, event_type: str, payload: Dict[str, Any]) -> None: ...


@runtime_checkable
class SessionStateServiceProtocol(Protocol):
    """Session state persistence interface."""

    async def get_state(self, session_id: str) -> Optional[Dict[str, Any]]: ...
    async def set_state(self, session_id: str, state: Dict[str, Any]) -> None: ...
    async def delete_state(self, session_id: str) -> bool: ...


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Request Context
    "RequestContext",
    # Logging
    "LoggerProtocol",
    # Database
    "DatabaseClientProtocol",
    # LLM
    "LLMProviderProtocol",
    # Tools
    "ToolProtocol",
    "ToolDefinitionProtocol",
    "ToolRegistryProtocol",
    # App Context
    "SettingsProtocol",
    "FeatureFlagsProtocol",
    "ClockProtocol",
    "AppContextProtocol",
    # Memory
    "SearchResult",
    "SemanticSearchProtocol",
    "SessionStateProtocol",
    # Distributed Bus (kept for Redis scaling)
    "DistributedTask",
    "QueueStats",
    "DistributedBusProtocol",
    # Event Bus
    "EventBusProtocol",
    # Tool Executor
    "ToolExecutorProtocol",
    # Config Registry
    "ConfigRegistryProtocol",
    # Capability LLM Config
    "AgentLLMConfig",
    # Agent Tool Access
    "AgentToolAccessProtocol",
    # Infrastructure Protocols
    "WebSocketManagerProtocol",
    "EventBridgeProtocol",
    "SessionStateServiceProtocol",
]
