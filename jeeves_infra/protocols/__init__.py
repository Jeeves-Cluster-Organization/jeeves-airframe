# Jeeves Protocol Types
#
# Code is the contract. Python dataclasses define the schema.
# No proto dependency.

# =============================================================================
# PYTHON DATACLASS TYPES (with methods - use these in application code)
# =============================================================================

from jeeves_infra.protocols.types import (
    # Enums (string-based)
    TerminalReason,
    InterruptKind,
    InterruptStatus,
    RiskLevel,
    ToolCategory,
    ToolAccess,
    HealthStatus,
    LoopVerdict,
    RiskApproval,
    OperationStatus,
    RunMode,
    JoinStrategy,
    AgentOutputMode,
    TokenStreamMode,
    AgentCapability,
    # Dataclass types with methods
    OperationResult,
    InterruptResponse,
    FlowInterrupt,
    RateLimitConfig,
    RateLimitResult,
    ProcessingRecord,
    PipelineEvent,
    RoutingRule,
    EdgeLimit,
    GenerationParams,
    AgentConfig,
    PipelineConfig,
    ContextBounds,
    ExecutionConfig,
    OrchestrationFlags,
    Envelope,
    # Protocols
    InterruptServiceProtocol,
    RateLimiterProtocol,
)

# =============================================================================
# PYTHON PROTOCOL INTERFACES
# =============================================================================

from jeeves_infra.protocols.interfaces import (
    RequestContext,
    LoggerProtocol,
    PersistenceProtocol,
    DatabaseClientProtocol,
    VectorStorageProtocol,
    LLMProviderProtocol,
    ToolProtocol,
    ToolDefinitionProtocol,
    ToolRegistryProtocol,
    SettingsProtocol,
    FeatureFlagsProtocol,
    ClockProtocol,
    AppContextProtocol,
    SearchResult,
    MemoryServiceProtocol,
    SemanticSearchProtocol,
    SessionStateProtocol,
    CheckpointRecord,
    CheckpointProtocol,
    DistributedTask,
    QueueStats,
    DistributedBusProtocol,
    IntentParsingProtocol,
    ClaimVerificationProtocol,
    EventBusProtocol,
    IdGeneratorProtocol,
    ToolExecutorProtocol,
    ConfigRegistryProtocol,
    LanguageConfigProtocol,
    InferenceEndpoint,
    InferenceEndpointsProtocol,
    AgentLLMConfig,
    DomainLLMRegistryProtocol,
    FeatureFlagsProviderProtocol,
    AgentToolAccessProtocol,
    GraphStorageProtocol,
    SkillStorageProtocol,
    WebSocketManagerProtocol,
    EmbeddingServiceProtocol,
    EventBridgeProtocol,
    ChunkServiceProtocol,
    SessionStateServiceProtocol,
)

# =============================================================================
# CAPABILITY REGISTRATION (moved from jeeves-core/protocols)
# =============================================================================

from jeeves_infra.protocols.capability import (
    get_capability_resource_registry,
    reset_capability_resource_registry,
    CapabilityResourceRegistry,
    CapabilityResourceRegistryProtocol,
    CapabilityToolCatalog,
    ToolCatalogEntry,
    ToolDefinition,
    DomainAgentConfig,
    CapabilityPromptConfig,
    CapabilityToolsConfig,
    CapabilityOrchestratorConfig,
    CapabilityContractsConfig,
    DomainServiceConfig,
    DomainModeConfig,
)

# =============================================================================
# RUNTIME COMPONENTS (Agent, PipelineRunner, etc.)
# =============================================================================

from jeeves_infra.runtime.agents import (
    Agent,
    PipelineRunner,
    create_pipeline_runner,
    create_envelope,
    OptionalCheckpoint,
)

# =============================================================================
# UTILITIES
# =============================================================================

from jeeves_infra.utils.json_repair import JSONRepairKit
from jeeves_infra.utils.strings import normalize_string_list

# =============================================================================
# WORKING MEMORY STUBS (for framework compatibility)
# =============================================================================

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class FocusType(str, Enum):
    """Focus type for session state."""
    GENERAL = "general"
    TASK = "task"
    EXPLORATION = "exploration"
    ENTITY = "entity"
    CLARIFICATION = "clarification"


@dataclass
class EntityRef:
    """Reference to a domain entity."""
    entity_id: str = ""
    entity_type: str = ""
    name: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ClarificationContext:
    """Context for clarification focus state."""
    original_query: str = ""
    clarification_type: str = ""
    options: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Finding:
    """A finding from agent processing."""
    id: str
    content: str
    source: str
    confidence: float = 0.8
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FocusState:
    """Focus state for working memory."""
    current_intent: Optional[str] = None
    current_topic: Optional[str] = None
    current_entities: List[str] = field(default_factory=list)
    last_tool_used: Optional[str] = None


@dataclass
class WorkingMemory:
    """Working memory for session state.

    Capabilities can extend or replace this with their own implementation.
    """
    session_id: str
    turn_count: int = 0
    findings: List[Finding] = field(default_factory=list)
    focus_state: FocusState = field(default_factory=FocusState)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def increment_turn(self) -> None:
        self.turn_count += 1

    def get_context_for_prompt(self) -> Dict[str, Any]:
        return {
            "turn_count": self.turn_count,
            "findings_count": len(self.findings),
            "current_intent": self.focus_state.current_intent,
            "current_topic": self.focus_state.current_topic,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "turn_count": self.turn_count,
            "findings": [{"id": f.id, "content": f.content, "source": f.source} for f in self.findings],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkingMemory":
        findings = [Finding(**f) for f in data.get("findings", [])]
        return cls(
            session_id=data["session_id"],
            turn_count=data.get("turn_count", 0),
            findings=findings,
            metadata=data.get("metadata", {}),
        )

__all__ = [
    # Enums
    "TerminalReason",
    "InterruptKind",
    "InterruptStatus",
    "RiskLevel",
    "ToolCategory",
    "ToolAccess",
    "HealthStatus",
    "LoopVerdict",
    "RiskApproval",
    "OperationStatus",
    "RunMode",
    "JoinStrategy",
    "AgentOutputMode",
    "TokenStreamMode",
    "AgentCapability",
    # Dataclass types
    "OperationResult",
    "InterruptResponse",
    "FlowInterrupt",
    "RateLimitConfig",
    "RateLimitResult",
    "ProcessingRecord",
    "PipelineEvent",
    "RoutingRule",
    "EdgeLimit",
    "GenerationParams",
    "AgentConfig",
    "PipelineConfig",
    "ContextBounds",
    "ExecutionConfig",
    "OrchestrationFlags",
    "Envelope",
    # Protocol interfaces
    "RequestContext",
    "LoggerProtocol",
    "PersistenceProtocol",
    "DatabaseClientProtocol",
    "VectorStorageProtocol",
    "LLMProviderProtocol",
    "ToolProtocol",
    "ToolDefinitionProtocol",
    "ToolRegistryProtocol",
    "SettingsProtocol",
    "FeatureFlagsProtocol",
    "ClockProtocol",
    "AppContextProtocol",
    "SearchResult",
    "MemoryServiceProtocol",
    "SemanticSearchProtocol",
    "SessionStateProtocol",
    "CheckpointRecord",
    "CheckpointProtocol",
    "DistributedTask",
    "QueueStats",
    "DistributedBusProtocol",
    "IntentParsingProtocol",
    "ClaimVerificationProtocol",
    "EventBusProtocol",
    "IdGeneratorProtocol",
    "ToolExecutorProtocol",
    "ConfigRegistryProtocol",
    "LanguageConfigProtocol",
    "InferenceEndpoint",
    "InferenceEndpointsProtocol",
    "AgentLLMConfig",
    "DomainLLMRegistryProtocol",
    "FeatureFlagsProviderProtocol",
    "AgentToolAccessProtocol",
    "GraphStorageProtocol",
    "SkillStorageProtocol",
    "WebSocketManagerProtocol",
    "EmbeddingServiceProtocol",
    "EventBridgeProtocol",
    "ChunkServiceProtocol",
    "SessionStateServiceProtocol",
    "InterruptServiceProtocol",
    "RateLimiterProtocol",
    # Capability registration
    "get_capability_resource_registry",
    "reset_capability_resource_registry",
    "CapabilityResourceRegistry",
    "CapabilityResourceRegistryProtocol",
    "CapabilityToolCatalog",
    "ToolCatalogEntry",
    "ToolDefinition",
    "DomainAgentConfig",
    "CapabilityPromptConfig",
    "CapabilityToolsConfig",
    "CapabilityOrchestratorConfig",
    "CapabilityContractsConfig",
    "DomainServiceConfig",
    "DomainModeConfig",
    # Runtime components
    "Agent",
    "PipelineRunner",
    "create_pipeline_runner",
    "create_envelope",
    "OptionalCheckpoint",
    # Utilities
    "JSONRepairKit",
    "normalize_string_list",
    # Working memory
    "WorkingMemory",
    "Finding",
    "FocusState",
    "FocusType",
    "EntityRef",
    "ClarificationContext",
]
