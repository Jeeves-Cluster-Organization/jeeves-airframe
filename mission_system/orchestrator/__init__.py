"""
Capability Orchestrator - gRPC service layer.

This package provides the gRPC server that:
- Wraps capability-specific orchestration pipelines
- Exposes services for capability flow processing
- Runs as a separate container from the HTTP gateway

The orchestrator owns:
- Capability servicer delegation (via CapabilityServicerProtocol)
- Database connections
- LLM provider management
- Tool registry

Capabilities register their orchestrators via CapabilityResourceRegistry.
The FlowServicer delegates to registered capability servicers without
hardcoded knowledge of specific capabilities.

Unified Interrupt System (v4.0):
- ConfirmationOrchestrator has been REMOVED
- All interrupt handling now goes through control_tower.services.InterruptService
- EventOrchestrator remains for agent event emission
"""

__version__ = "0.1.0"

# Phase 7: Unified Event Orchestrator (retained)
from mission_system.orchestrator.events import (
    EventOrchestrator,
    create_event_orchestrator,
    AgentEventType,
    AgentEvent,
    EventEmitter,
    EventContext,
    create_agent_event_emitter,
    create_event_context,
)

__all__ = [
    # Events (Phase 7)
    "EventOrchestrator",
    "create_event_orchestrator",
    "AgentEventType",
    "AgentEvent",
    "EventEmitter",
    "EventContext",
    # Factory functions
    "create_agent_event_emitter",
    "create_event_context",
]
