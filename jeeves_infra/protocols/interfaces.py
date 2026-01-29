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
# PERSISTENCE
# =============================================================================

@runtime_checkable
class PersistenceProtocol(Protocol):
    """Database persistence interface."""

    async def execute(self, query: str, params: Optional[Dict[str, Any]] = None) -> None: ...
    async def fetch_one(self, query: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]: ...
    async def fetch_all(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]: ...


@runtime_checkable
class DatabaseClientProtocol(Protocol):
    """Database client interface."""

    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def execute(self, query: str, params: Optional[Dict[str, Any]] = None) -> None: ...
    async def fetch_one(self, query: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]: ...
    async def fetch_all(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]: ...


@runtime_checkable
class VectorStorageProtocol(Protocol):
    """Unified vector storage interface for embeddings."""

    async def upsert(
        self,
        item_id: str,
        content: str,
        collection: str,
        metadata: Dict[str, Any]
    ) -> None: ...

    async def search(
        self,
        query: str,
        collections: List[str],
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]: ...

    async def delete(self, item_id: str, collection: str) -> None: ...

    def close(self) -> None: ...


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
class MemoryServiceProtocol(Protocol):
    """Memory service interface."""

    async def store(self, key: str, value: Any, ttl: Optional[int] = None) -> None: ...
    async def retrieve(self, key: str) -> Optional[Any]: ...
    async def delete(self, key: str) -> None: ...


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
# CHECKPOINT (Time-travel debugging)
# =============================================================================

@dataclass
class CheckpointRecord:
    """Checkpoint record for time-travel debugging."""
    checkpoint_id: str
    envelope_id: str
    agent_name: str
    stage_order: int
    created_at: datetime
    parent_checkpoint_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@runtime_checkable
class CheckpointProtocol(Protocol):
    """Checkpoint interface for time-travel debugging."""

    async def save_checkpoint(
        self,
        envelope_id: str,
        checkpoint_id: str,
        agent_name: str,
        state: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CheckpointRecord: ...

    async def load_checkpoint(self, checkpoint_id: str) -> Optional[Dict[str, Any]]: ...

    async def list_checkpoints(
        self,
        envelope_id: str,
        limit: int = 100,
    ) -> List[CheckpointRecord]: ...

    async def delete_checkpoints(
        self,
        envelope_id: str,
        before_checkpoint_id: Optional[str] = None,
    ) -> int: ...

    async def fork_from_checkpoint(
        self,
        checkpoint_id: str,
        new_envelope_id: str,
    ) -> str: ...


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
# NLI (Natural Language Interface)
# =============================================================================

@runtime_checkable
class IntentParsingProtocol(Protocol):
    """Intent parsing service for natural language understanding."""

    async def parse_intent(self, text: str) -> Dict[str, Any]: ...
    async def generate_response(self, intent: Dict[str, Any], context: Dict[str, Any]) -> str: ...


@runtime_checkable
class ClaimVerificationProtocol(Protocol):
    """Claim verification service using Natural Language Inference."""

    def verify_claim(self, claim: str, evidence: str) -> Any: ...
    def verify_claims_batch(self, claims: List[tuple]) -> List[Any]: ...


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
# ID GENERATOR
# =============================================================================

@runtime_checkable
class IdGeneratorProtocol(Protocol):
    """ID generator interface."""

    def generate(self) -> str: ...
    def generate_prefixed(self, prefix: str) -> str: ...


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
# LANGUAGE CONFIG
# =============================================================================

@runtime_checkable
class LanguageConfigProtocol(Protocol):
    """Language configuration for code analysis."""

    def get_extensions(self, language: str) -> List[str]: ...
    def get_comment_patterns(self, language: str) -> Dict[str, str]: ...
    def detect_language(self, filename: str) -> Optional[str]: ...


# =============================================================================
# DISTRIBUTED NODE PROFILES
# =============================================================================

@dataclass
class InferenceEndpoint:
    """Profile for a distributed LLM node."""
    name: str
    base_url: str
    agents: List[str] = field(default_factory=list)
    model: str = ""
    vram_gb: Optional[int] = None
    ram_gb: Optional[int] = None
    model_size_gb: Optional[float] = None
    max_parallel: int = 1
    gpu_id: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0

    def __post_init__(self):
        if self.model_size_gb is not None and self.vram_gb is not None:
            if self.model_size_gb > self.vram_gb:
                raise ValueError(
                    f"Model size ({self.model_size_gb}GB) exceeds "
                    f"VRAM capacity ({self.vram_gb}GB) for node {self.name}"
                )
        if self.max_parallel < 1:
            raise ValueError(f"max_parallel must be >= 1 for node {self.name}")

    @property
    def model_name(self) -> str:
        if not self.model:
            return ""
        return self.model.replace(".gguf", "").replace("-q4_k_m", "").replace("-q4_K_M", "")

    @property
    def vram_utilization(self) -> Optional[float]:
        if self.vram_gb is None or self.model_size_gb is None or self.vram_gb == 0:
            return None
        return (self.model_size_gb / self.vram_gb) * 100

    def can_handle_load(self, current_requests: int) -> bool:
        return current_requests < self.max_parallel


@runtime_checkable
class InferenceEndpointsProtocol(Protocol):
    """Node profiles interface for distributed LLM routing."""

    def get_profile_for_agent(self, agent_name: str) -> InferenceEndpoint: ...
    def list_profiles(self) -> List[InferenceEndpoint]: ...


# =============================================================================
# CAPABILITY LLM CONFIGURATION
# =============================================================================

@dataclass
class AgentLLMConfig:
    """LLM configuration for a specific agent.

    Note: Also available as a proto message in engine_pb2.AgentLLMConfig.
    This Python dataclass version provides validation and defaults.
    """
    agent_name: str
    model: str = "qwen2.5-7b-instruct-q4_k_m"
    temperature: Optional[float] = 0.3
    max_tokens: int = 2000
    server_url: Optional[str] = None
    provider: Optional[str] = None
    timeout_seconds: int = 120
    context_window: int = 16384


@runtime_checkable
class DomainLLMRegistryProtocol(Protocol):
    """Registry for capability-owned agent LLM configurations."""

    def register(
        self,
        capability_id: str,
        agent_name: str,
        config: AgentLLMConfig
    ) -> None: ...

    def get_agent_config(self, agent_name: str) -> Optional[AgentLLMConfig]: ...
    def list_agents(self) -> List[str]: ...
    def get_capability_agents(self, capability_id: str) -> List[AgentLLMConfig]: ...


@runtime_checkable
class FeatureFlagsProviderProtocol(Protocol):
    """Provider for feature flags at runtime."""

    def get_feature_flags(self) -> FeatureFlagsProtocol: ...


# =============================================================================
# AGENT TOOL ACCESS
# =============================================================================

@runtime_checkable
class AgentToolAccessProtocol(Protocol):
    """Agent tool access control interface."""

    def can_access(self, agent_name: str, tool_name: str) -> bool: ...
    def get_allowed_tools(self, agent_name: str) -> List[str]: ...


# =============================================================================
# MEMORY LAYER PROTOCOLS (L5-L6)
# =============================================================================

@runtime_checkable
class GraphStorageProtocol(Protocol):
    """L5 Entity Graph storage interface."""

    async def add_node(
        self,
        node_id: str,
        node_type: str,
        properties: Dict[str, Any],
        user_id: Optional[str] = None,
    ) -> bool: ...

    async def add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> bool: ...

    async def get_node(self, node_id: str) -> Optional[Dict[str, Any]]: ...

    async def get_neighbors(
        self,
        node_id: str,
        edge_type: Optional[str] = None,
        direction: str = "both",
        limit: int = 100,
    ) -> List[Dict[str, Any]]: ...

    async def find_path(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 5,
    ) -> Optional[List[Dict[str, Any]]]: ...

    async def query_subgraph(
        self,
        center_id: str,
        depth: int = 2,
        node_types: Optional[List[str]] = None,
        edge_types: Optional[List[str]] = None,
    ) -> Dict[str, Any]: ...

    async def delete_node(self, node_id: str) -> bool: ...


@runtime_checkable
class SkillStorageProtocol(Protocol):
    """L6 Skills/Patterns storage interface."""

    async def store_skill(
        self,
        skill_id: str,
        skill_type: str,
        pattern: Dict[str, Any],
        source_context: Optional[Dict[str, Any]] = None,
        confidence: float = 0.5,
        user_id: Optional[str] = None,
    ) -> str: ...

    async def get_skill(self, skill_id: str) -> Optional[Dict[str, Any]]: ...

    async def find_skills(
        self,
        skill_type: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        min_confidence: float = 0.0,
        limit: int = 10,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]: ...

    async def update_confidence(
        self,
        skill_id: str,
        delta: float,
        reason: Optional[str] = None,
    ) -> float: ...

    async def record_usage(
        self,
        skill_id: str,
        success: bool,
        context: Optional[Dict[str, Any]] = None,
    ) -> None: ...

    async def delete_skill(self, skill_id: str) -> bool: ...
    async def get_skill_stats(self, skill_id: str) -> Optional[Dict[str, Any]]: ...


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
class EmbeddingServiceProtocol(Protocol):
    """Embedding generation interface."""

    def embed(self, content: str) -> List[float]: ...
    def embed_batch(self, contents: List[str]) -> List[List[float]]: ...


@runtime_checkable
class EventBridgeProtocol(Protocol):
    """Bridge for kernel events to external systems."""

    async def emit(self, event_type: str, payload: Dict[str, Any]) -> None: ...


@runtime_checkable
class ChunkServiceProtocol(Protocol):
    """Document chunking interface."""

    async def chunk_document(
        self,
        content: str,
        metadata: Dict[str, Any],
    ) -> List[Dict[str, Any]]: ...


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
    # Persistence
    "PersistenceProtocol",
    "DatabaseClientProtocol",
    "VectorStorageProtocol",
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
    "MemoryServiceProtocol",
    "SemanticSearchProtocol",
    "SessionStateProtocol",
    # Checkpoint
    "CheckpointRecord",
    "CheckpointProtocol",
    # Distributed Bus
    "DistributedTask",
    "QueueStats",
    "DistributedBusProtocol",
    # NLI
    "IntentParsingProtocol",
    "ClaimVerificationProtocol",
    # Event Bus
    "EventBusProtocol",
    # ID Generator
    "IdGeneratorProtocol",
    # Tool Executor
    "ToolExecutorProtocol",
    # Config Registry
    "ConfigRegistryProtocol",
    # Language Config
    "LanguageConfigProtocol",
    # Distributed Node Profiles
    "InferenceEndpoint",
    "InferenceEndpointsProtocol",
    # Capability LLM Config
    "AgentLLMConfig",
    "DomainLLMRegistryProtocol",
    "FeatureFlagsProviderProtocol",
    # Agent Tool Access
    "AgentToolAccessProtocol",
    # Memory Layer Protocols
    "GraphStorageProtocol",
    "SkillStorageProtocol",
    # Infrastructure Protocols
    "WebSocketManagerProtocol",
    "EmbeddingServiceProtocol",
    "EventBridgeProtocol",
    "ChunkServiceProtocol",
    "SessionStateServiceProtocol",
]
