# Jeeves Protocol Types
#
# Session 10: Proto is the source of truth. Python types provide methods.
# Use Python dataclass types for code that needs methods (to_dict, from_dict, etc.)
# Use Proto types for gRPC communication.

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
# PROTO TYPES (for gRPC communication)
# =============================================================================

from jeeves_infra.protocols import engine_pb2 as proto
from jeeves_infra.protocols.engine_pb2_grpc import (
    EngineServiceStub,
    EngineServiceServicer,
    add_EngineServiceServicer_to_server,
)

# =============================================================================
# RUNTIME TYPES (Agent, PipelineRunner, etc.)
# =============================================================================

from jeeves_infra.runtime.agents import (
    Agent,
    PipelineRunner,
    create_pipeline_runner,
    create_envelope,
    OptionalCheckpoint,
)

# =============================================================================
# UTILITY TYPES
# =============================================================================

from jeeves_infra.utils.json_repair import JSONRepairKit
from jeeves_infra.utils.strings import normalize_string_list

# =============================================================================
# WORKING MEMORY TYPES
# =============================================================================

from jeeves_infra.protocols.working_memory import (
    Finding,
    WorkingMemory,
    WorkingMemoryProtocol,
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
# EVENT TYPES (for gateway event bus)
# =============================================================================

from jeeves_infra.protocols.events import (
    Event,
    EventCategory,
    EventSeverity,
    EventEmitterProtocol,
)

# =============================================================================
# VALIDATION TYPES (for meta-validation)
# =============================================================================

from jeeves_infra.protocols.validation import (
    MetaValidationIssue,
    VerificationReport,
)

__all__ = [
    # Runtime types
    "Agent",
    "PipelineRunner",
    "create_pipeline_runner",
    "create_envelope",
    "OptionalCheckpoint",
    # Utility types
    "JSONRepairKit",
    "normalize_string_list",
    # Working memory types
    "Finding",
    "WorkingMemory",
    "WorkingMemoryProtocol",
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
    # Proto module
    "proto",
    # gRPC
    "EngineServiceStub",
    "EngineServiceServicer",
    "add_EngineServiceServicer_to_server",
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
    # Event types
    "Event",
    "EventCategory",
    "EventSeverity",
    "EventEmitterProtocol",
    # Validation types
    "MetaValidationIssue",
    "VerificationReport",
]
