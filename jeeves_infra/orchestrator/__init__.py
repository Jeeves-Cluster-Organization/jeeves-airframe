"""Orchestrator — event emission and lifecycle management.

Provides EventOrchestrator for agent/tool lifecycle events.
Capabilities register their orchestrators via CapabilityResourceRegistry.
"""

__version__ = "0.1.0"

# Phase 7: Unified Event Orchestrator (retained)
from jeeves_infra.orchestrator.events import (
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
