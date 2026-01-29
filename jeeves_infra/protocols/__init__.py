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
]
