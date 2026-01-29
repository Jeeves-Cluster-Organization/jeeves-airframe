# ARCHITECTURE_TRACKER.md

> Last Updated: 2026-01-30 (Session 26)
> Tests: 238+ passed (jeeves_tests)
> Architecture: Agentic OS (Hexagonal Ports & Adapters)

---

## 1. Agentic OS Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  AGENTIC OS ARCHITECTURE                                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  L3: USER SPACE (Capabilities)                                              │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                           │
│  │mini-swe-    │ │ calendar-   │ │  research-  │  ... more capabilities     │
│  │agent        │ │ agent       │ │  agent      │                           │
│  └─────────────┘ └─────────────┘ └─────────────┘                           │
│                                                                              │
│  L2: ORCHESTRATION (mission_system)                                         │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌───────────────┐      │
│  │ gateway/     │ │ orchestrator │ │  services/   │ │   prompts/    │      │
│  │ (HTTP→gRPC)  │ │ (scheduling) │ │  (business)  │ │   (templates) │      │
│  └──────────────┘ └──────────────┘ └──────────────┘ └───────────────┘      │
│                                                                              │
│  L1: INFRASTRUCTURE (jeeves_infra)                                          │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌───────────────┐      │
│  │ protocols/   │ │ memory/      │ │ postgres/    │ │ llm/          │      │
│  │ (45 ports)   │ │ (storage)    │ │ (drivers)    │ │ (providers)   │      │
│  └──────────────┘ └──────────────┘ └──────────────┘ └───────────────┘      │
│  + kernel_client/ (gRPC client to Go kernel)                                │
│                                                                              │
│  L0: KERNEL (jeeves-core / Go)                                              │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌───────────────┐      │
│  │  Lifecycle   │ │   CommBus    │ │   Memory     │ │  Scheduler    │      │
│  │(process mgmt)│ │   (IPC)      │ │ (primitives) │ │  (execution)  │      │
│  └──────────────┘ └──────────────┘ └──────────────┘ └───────────────┘      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Key Principle**: Dependencies flow DOWN only (L3 → L2 → L1 → L0)

---

## 2. Package Structure

### jeeves_infra/ (L1: Library)

```
jeeves_infra/                        # pip install jeeves-infra
├── protocols/                       # 45 Protocol interfaces
├── memory/                          # Memory adapters
├── postgres/                        # Database driver
├── llm/                             # LLM providers
├── redis/                           # Cache driver
├── runtime/                         # Process management
├── kernel_client.py                 # gRPC client to Go kernel
│   ├── KernelClient                 # Process lifecycle
│   └── CommBusClient                # Pub/sub
└── NO imports from mission_system ✅
```

### mission_system/ (L2: Framework)

```
mission_system/                      # pip install mission-system
├── gateway/                         # HTTP→gRPC gateway
│   ├── app.py                      # FastAPI app (gRPC proxy)
│   ├── routers/                    # REST endpoints
│   │   ├── chat.py                 # /api/v1/chat/*
│   │   ├── governance.py           # /api/v1/governance/*
│   │   └── interrupts.py           # /api/v1/interrupts/*
│   ├── grpc_client.py              # gRPC client manager
│   ├── websocket.py                # WebSocket handlers
│   └── proto/                      # gRPC definitions
├── services/                        # Business services
├── orchestrator/                    # Orchestration logic
├── bootstrap.py                     # Composition root
└── depends on: jeeves_infra ✅
```

---

## 3. Gateway Architecture (Session 25 Cleanup)

### What Changed (Session 25-26)

**Deleted** (broken/duplicate/stale):
- `server.py` (1046 lines) - broken imports
- `chat.py` (548 lines) - duplicate of `routers/chat.py`
- `governance.py` (552 lines) - duplicate of `routers/governance.py`
- `test_unwired_audit_phase2.py` (905 lines) - tested deleted infra
- `test_distributed_mode.py` (578 lines) - tested deleted infra

**Kept** (clean gRPC architecture):
- `app.py` - FastAPI gateway (HTTP→gRPC proxy)
- `routers/*.py` - REST endpoints via gRPC
- `grpc_client.py` - gRPC client manager
- Supporting files (websocket, sse, health, etc.)

### Gateway Pattern

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

## 4. Test Status

### Integration Tests

| Test File | Status | Notes |
|-----------|--------|-------|
| `test_api.py` | ✅ Passing | Health endpoints only |
| `test_api_ci.py` | ✅ Passing | Health endpoints only |
| `test_governance_api.py` | ⏭️ Skipped | Needs gRPC orchestrator |

### Coverage

| Module | Coverage | Priority |
|--------|----------|----------|
| `kernel_client.py` | 98% | ✅ Done |
| `gateway/` | ~10% | P2 |
| `postgres/` | 0% | P2 |

---

## 5. Next Steps

### P1: Library/Framework Completion

| Task | Status |
|------|--------|
| Fix circular dependencies | ✅ Done (Session 23) |
| Delete broken gateway files | ✅ Done (Session 25) |
| Create `ResourceTracker` class | ❌ Pending |
| Create config dataclasses | ❌ Pending |
| Add CI boundary checks | ❌ Pending |

### P2: Production Readiness

| Task | Status |
|------|--------|
| Wire LLMGateway to ResourceTracker | ❌ Pending |
| Add gRPC test infrastructure | ❌ Pending |
| Integration tests with real kernel | ❌ Pending |

### P3: Test Coverage

| Task | Target |
|------|--------|
| Go tests for CommBusServer | 80% |
| Gateway integration tests | 40% |

---

## 6. Session History (Recent)

### Session 26 (2026-01-30)
- **Documentation Audit**: Removed all `avionics` and `control_tower` references
- **Deleted**: `test_unwired_audit_phase2.py`, `test_distributed_mode.py` (1,483 lines)
- **Renamed**: `avionics_mocks.py` → `infra_mocks.py` (both test directories)
- **Updated**: 20+ files with stale docstrings/comments
- **Added**: Protocol exports for `Event`, `EventCategory`, `MetaValidationIssue`, etc.
- **Result**: Clean codebase with no stale references

### Session 25 (2026-01-29)
- **Deleted**: `server.py`, `chat.py`, `governance.py` (2,146 lines removed)
- **Updated**: Integration tests to use gRPC-based `app.py`
- **Result**: Clean gateway with single architecture pattern

### Session 24 (2026-01-29)
- Added gRPC auth metadata to kernel_client
- Clarified SDK design (jeeves_infra = library)
- Added 39 KernelClient tests (98% coverage)

### Session 23 (2026-01-29)
- Fixed P0 circular dependencies
- Moved `gateway/` from jeeves_infra to mission_system
- Added CommBusClient to kernel_client.py

---

## 7. Quick Reference

### Run Tests

```bash
# All tests
pytest jeeves-infra/ -v

# Skip PostgreSQL tests
pytest jeeves-infra/ -v -m "not requires_postgres"
```

### Check Dependencies

```bash
# Verify no circular imports
grep -r "^from mission_system" jeeves_infra/
# Should return nothing

# Verify no stale imports
grep -r "avionics" jeeves_infra/ --include="*.py" | grep -v "# " | head -5
# Should return nothing (only comments allowed)
```

### Gateway Endpoints

| Endpoint | Requires gRPC |
|----------|---------------|
| `/health` | No |
| `/ready` | No (returns status) |
| `/` | No |
| `/api/v1/chat/*` | Yes |
| `/api/v1/governance/*` | Yes |
| `/api/v1/interrupts/*` | Yes |
