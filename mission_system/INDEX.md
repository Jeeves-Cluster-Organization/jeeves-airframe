# Jeeves Mission System - Orchestration Layer Index

**Updated:** 2026-01-29

---

## Overview

This directory contains the **orchestration layer (L2)** of the Jeeves runtime. It implements API endpoints, services, and orchestration for capabilities.

**Position in Architecture:**
```
L3: Capability Layer          →  Domain-specific capabilities (mini-swe-agent, etc.)
        ↓
L2: mission_system/           →  Orchestration layer (THIS)
        ↓
L1: jeeves_infra/             →  Infrastructure (protocols, LLM, memory, database)
        ↓
L0: jeeves-core               →  Go kernel (process management, CommBus, scheduling)
```

**Key Principle:** This layer provides orchestration and the framework for capabilities to build on.

---

## Directory Structure

### Gateway (HTTP/gRPC)

| Directory | Description |
|-----------|-------------|
| [gateway/](gateway/) | HTTP→gRPC gateway (FastAPI, routers, WebSocket) |

### Orchestration

| Directory | Description |
|-----------|-------------|
| [orchestrator/](orchestrator/) | Flow orchestration (FlowService, events) |

### Services

| Directory | Description |
|-----------|-------------|
| [services/](services/) | ChatService, WorkerCoordinator |

### Configuration

| Directory | Description |
|-----------|-------------|
| [bootstrap.py](bootstrap.py) | Composition root, create_app_context() |
| [config/](config/) | Configuration and constants |

### Testing

| Directory | Description |
|-----------|-------------|
| [tests/](tests/) | Test suites (unit, integration, e2e) |

---

## Import Boundary Rules

**Mission System may import:**
- ✅ `jeeves_infra` - Infrastructure layer (protocols, LLM, memory, database)

**Mission System must NOT:**
- ❌ Be imported by `jeeves_infra` (one-way dependency)
- ❌ Import from capabilities (capabilities import from mission_system)

**Example:**
```python
# ALLOWED
from jeeves_infra.protocols import Envelope, InterruptKind, RequestContext
from jeeves_infra.llm import LLMProvider
from jeeves_infra.kernel_client import KernelClient
from jeeves_infra.database.client import create_database_client

# NOT ALLOWED
# jeeves_infra importing mission_system.*
```

---

## Gateway Architecture

```
HTTP Request                          gRPC Orchestrator
     │                                      │
     ▼                                      │
┌─────────┐    gRPC      ┌─────────────────┐
│ app.py  │─────────────►│  Go Kernel      │
│ (proxy) │              │  + Orchestrator │
└─────────┘              └─────────────────┘
```

- `app.py` is stateless - all state in kernel/orchestrator
- Health endpoints (`/health`, `/ready`) work without gRPC
- API endpoints (`/api/v1/*`) require running orchestrator

---

## Related

- [jeeves_infra/](../jeeves_infra/) - Infrastructure layer
- [ARCHITECTURE_TRACKER.md](../ARCHITECTURE_TRACKER.md) - Full architecture docs
- [CONSTITUTION.md](CONSTITUTION.md) - Mission System constitution
- [bootstrap.py](bootstrap.py) - Application bootstrap

---

*This directory represents the orchestration layer (L2) in the Agentic OS architecture.*
