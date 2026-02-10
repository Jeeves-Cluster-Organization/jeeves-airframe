# Jeeves Mission System - Application Layer Index

**Parent:** [Airframe Constitution](../CONSTITUTION.md)
**Updated:** 2026-02-10

---

## Overview

This directory contains the **application layer** of the Jeeves runtime. It implements orchestration, API endpoints, and provides the framework for capabilities to build upon.

**Position in Architecture:**
```
Capability Layer (external)       →  Domain-specific capabilities (e.g., hello-world)
        ↓
mission_system/            →  Application layer (THIS)
        ↓
jeeves_infra/              →  Infrastructure (LLM adapters, protocols, gateway)
        ↓
jeeves-core-rs/            →  Rust microkernel (gRPC)
```

**Key Principle:** This layer provides application-specific orchestration and the framework for capabilities to build on.

---

## Directory Structure

### Orchestration

| Directory | Description |
|-----------|-------------|
| [orchestrator/](orchestrator/) | Flow orchestration (FlowService, VerticalService, events) |

### Verticals

| Directory | Description |
|-----------|-------------|
| [verticals/](verticals/) | Vertical registry and base classes |

**Note:** Domain-specific agent pipelines belong in capability layers, not here.

### API & Services

| Directory | Description |
|-----------|-------------|
| [api/](api/) | HTTP API endpoints (chat, health, governance) |
| [services/](services/) | ChatService, WorkerCoordinator |
| [contracts/](contracts/) | Contract definitions |
| [prompts/](prompts/) | Core prompts |

### Configuration

| Directory | Description |
|-----------|-------------|
| [bootstrap.py](bootstrap.py) | Composition root, create_app_context() |

### Operations

| Directory | Description |
|-----------|-------------|
| [scripts/](scripts/) | Operational scripts (import boundary checks, etc.) |
| [tests/](tests/) | Test suites (unit, contract, integration) |

---

## Files

| File | Purpose |
|------|---------|
| `__init__.py` | Package exports, version info |

---

## Import Boundary Rules

**Mission System may import:**
- ✅ `jeeves_infra.protocols` - Protocol definitions, types
- ✅ `jeeves_infra` - Infrastructure layer (LLM, gateway, database, observability)

**Mission System must NOT:**
- ❌ Be imported by `jeeves_infra` (one-way dependency)
- ❌ Import from capability layers (capabilities import from mission_system)

**Example:**
```python
# ALLOWED
from jeeves_infra.protocols import Envelope, InterruptKind
from jeeves_infra.llm import LLMClient
from jeeves_infra.database import DatabaseClient

# NOT ALLOWED
# jeeves_infra importing mission_system.*
# mission_system importing jeeves_capability_*
```

---

## Deployment

The mission system provides framework primitives for capabilities:

**Mission System Framework:**
- Provides: Stable API via `mission_system.api`
- Exports: `MissionRuntime`, `create_mission_runtime()`
- Role: Framework that capabilities build on (NOT an application)

**Capabilities (Applications):**
- Capability entry points are defined in external capability repositories
- Protocol: gRPC on port 50051 (configurable)
- Capabilities import FROM mission system API (constitutional)

**API Gateway:**
- Contains: Minimal web layer (handled by `jeeves_infra.gateway`)
- Protocol: HTTP/REST on port 8000

---

## Related

- [jeeves_infra/](../jeeves_infra/) - Infrastructure layer (LLM, gateway, protocols)
- [CONSTITUTION.md](../CONSTITUTION.md) - Airframe constitution
- [bootstrap.py](bootstrap.py) - Application bootstrap

---

*This directory represents the application layer in the two-package split (`jeeves_infra` + `mission_system`).*
