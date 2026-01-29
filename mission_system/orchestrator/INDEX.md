# Jeeves Mission System - Orchestrator Module

**Parent:** [Mission System Index](../INDEX.md)

---

## Overview

Pure Python workflow orchestration providing the foundation for capability pipelines with REINTENT loops and multi-stage processing.

---

## Files

| File | Description |
|------|-------------|
| `__init__.py` | Package exports |
| `agent_events.py` | `EventEmitter` - Agent lifecycle event emission |
| `event_context.py` | `EventContext` - Unified event emission facade |
| `flow_service.py` | `FlowService` - Main orchestration service |
| `governance_service.py` | `GovernanceService` - Tool access governance |
| `vertical_service.py` | Vertical registration and management |

## Subdirectories

| Directory | Description |
|-----------|-------------|
| `langgraph/` | State definitions (JeevesState TypedDict) - package name retained for import compatibility |

---

## Key Components

### FlowService (`flow_service.py`)
Main orchestration entry point:
```python
class FlowService:
    async def process_query(
        self, query: str, session_id: str, user_id: str, ...
    ) -> AsyncIterator[StreamEvent]
```

### Event Context (`event_context.py`)
Unified event emission (target for commbus migration):
```python
class EventContext:
    async def emit_agent_started(self, agent_name: str, **payload)
    async def emit_agent_completed(self, agent_name: str, status: str, ...)
    async def emit_tool_started(self, tool_name: str, ...)
    async def emit_tool_completed(self, tool_name: str, status: str, ...)
```

### Agent Events (`agent_events.py`)
Queue-based event broadcast to gRPC/WebSocket consumers.

---

## Pipeline Architecture

```
REINTENT Loop:
Perception → Intent → Planner → Traverser → Synthesizer → Critic
                ↑                                           │
                └─────────[reintent if not approved]────────┘

Multi-Stage: Critic can trigger stage_transition for complex queries
```

---

## Interrupt Integration

The orchestrator integrates with the unified interrupt system via `protocols.interrupts`:
- `InterruptKind.CLARIFICATION` - User clarification needed
- `InterruptKind.CONFIRMATION` - Approval required
- `InterruptKind.AGENT_REVIEW` - Agent review decision point
- `InterruptKind.CHECKPOINT` - Checkpoint save point

---

*Last updated: 2025-12-16*
