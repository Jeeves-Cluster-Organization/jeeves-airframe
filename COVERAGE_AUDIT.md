# jeeves-airframe Python Coverage & Test Audit

**Date**: 2026-02-06
**Scope**: jeeves_infra + mission_system Python packages
**Branch**: `claude/audit-python-coverage-MCxV0`

---

## Executive Summary

| Metric | Value |
|--------|-------|
| Source lines (jeeves_infra) | 41,104 |
| Source lines (mission_system) | 8,616 |
| Source lines (total) | 49,720 |
| Test lines (total) | 18,763 |
| Test-to-source ratio | 0.38:1 |
| Test functions (total) | 518 (177 root + 341 mission) |
| Source modules | 175 (129 infra + 46 mission) |
| **jeeves_infra coverage** | **17%** |
| **mission_system coverage** | **50%** |
| Tests passing | 295 / 340 collected |
| Tests failing | 9 |
| Tests skipped | 36 |
| Tests uncollectable (import errors) | 5 test files (~70+ tests) |

The codebase has significant structural issues that prevent full test execution.
The `memory_module` and `shared` phantom packages block imports across ~45 source
files, and multiple declared dependencies do not exist. Coverage is critically low
on jeeves_infra (17%) and moderate on mission_system (50%).

---

## 1. Test Execution Results

### Root tests (`tests/`)

```
173 collected | 168 passed | 5 failed | 0 skipped
```

**5 Failures** -- all in `tests/unit/test_kernel_client.py`, caused by a protobuf
schema drift: `kernel_client.py` passes `inference_requests` and
`inference_input_chars` fields to `RecordUsageRequest`, but the generated
`jeeves_pb2` does not define those fields.

Affected tests:
- `TestResourceManagement::test_record_usage`
- `TestConvenienceMethods::test_record_llm_call`
- `TestConvenienceMethods::test_record_llm_call_quota_exceeded`
- `TestConvenienceMethods::test_record_tool_call`
- `TestConvenienceMethods::test_record_agent_hop`

### Mission system tests (`mission_system/tests/`)

```
167 collected | 127 passed | 4 failed | 36 skipped | 5 files uncollectable
```

**4 Failures:**
- `test_pytest_imports::test_memory_imports` -- asserts `memory_module` importable (it isn't)
- `test_bootstrap::test_creates_app_context` -- imports `memory_module.manager`
- `test_bootstrap::test_set_and_get_pid` -- same root cause
- `test_bootstrap::test_creates_manager_with_dependencies` -- same root cause

**36 Skipped:** All contract tests (P2 reliability, M1 canonical, M2 events) --
require a live PostgreSQL database.

**5 Uncollectable files (import errors):**

| File | Root cause |
|------|-----------|
| `unit/orchestrator/test_flow_service.py` | `flow_service.py` does not exist |
| `unit/orchestrator/test_governance_service.py` | `GovernanceServiceServicer` NoneType (proto import issue) |
| `unit/services/test_chat_service.py` | `OptionalCheckpoint` not exported from `protocols` |
| `unit/test_l2_event_dedup.py` | `memory_module` not found |
| `unit/test_nli_service.py` | `memory_module` not found |

---

## 2. Coverage Analysis

### jeeves_infra: 17% (2,010 / 11,649 statements)

#### Modules at 0% coverage (never tested)

| Module | Statements | Description |
|--------|-----------|-------------|
| `database/factory.py` | 50 | DB connection factory |
| `database/registry.py` | 114 | Schema/migration registry |
| `database/schema_init.py` | 41 | Schema initializer |
| `feature_flags.py` | 146 | Feature flag system |
| `gateway/chat.py` | 83 | Chat endpoint |
| `gateway/health.py` | 63 | Health endpoints |
| `gateway/main.py` | 54 | FastAPI app factory |
| `gateway/routers.py` | 94 | Route registration |
| `gateway/sse.py` | 97 | Server-sent events |
| `gateway/websocket.py` | 143 | WebSocket handler |
| `gateway/websocket_manager.py` | 75 | WS connection manager |
| `logging/context.py` | 67 | Log context propagation |
| `logging/setup.py` | 107 | Logging configuration |
| `memory/handlers.py` | 257 | Memory event handlers |
| `memory/intent_classifier.py` | 67 | Intent classification |
| `memory/manager.py` | 131 | Memory manager |
| `memory/messages/*` | 276 | Message types (events, queries, commands) |
| `memory/repositories/*` | 511 | All 7 repositories |
| `memory/services/*` | 834 | All 8 services |
| `memory/sql_adapter.py` | 157 | SQL adapter |
| `middleware/rate_limiter.py` | 100 | Rate limiting |
| `observability/*` | 242 | Metrics, tracing, middleware |
| `pipeline_worker.py` | 94 | Pipeline worker |
| `postgres/client.py` | 204 | PostgreSQL client |
| `postgres/graph.py` | 85 | Graph operations |
| `postgres/checkpoints.py` | 65 | Checkpoint storage |
| `redis/client.py` | 116 | Redis client |
| `redis/connection_manager.py` | 106 | Redis connection mgr |
| `services/chat_service.py` | 217 | Chat service |
| `services/debug_api.py` | 101 | Debug API |
| `services/worker_coordinator.py` | 188 | Worker coordination |
| `utils/cot_proxy.py` | 63 | CoT extraction |
| `utils/formatting/*` | 164 | Prompt/response formatting |
| `utils/fuzzy_matcher.py` | 52 | Fuzzy string matching |
| `utils/id_generator.py` | 48 | ID generation |
| `utils/plan_triage.py` | 57 | Plan triage logic |
| `utils/prompt_compression.py` | 60 | Prompt compression |
| `utils/uuid_utils.py` | 49 | UUID utilities |
| `webhooks/service.py` | 218 | Webhook dispatch |

**~4,800 statements at 0% coverage** (41% of jeeves_infra).

#### Modules with partial coverage

| Module | Coverage | Notes |
|--------|---------|-------|
| `kernel_client.py` | 31% | Only process lifecycle tested, not resource/inference |
| `wiring.py` | 59% | DI container partially tested |
| `tools/catalog.py` | 56% | Registration tested, lookup/execution gaps |
| `settings.py` | 81% | Good but missing edge cases |
| `protocols/types.py` | 78% | Type definitions mostly covered |
| `protocols/interfaces.py` | 82% | Good |

### mission_system: 50% (1,978 / 3,935 statements)

#### Modules at 0% coverage

| Module | Statements | Description |
|--------|-----------|-------------|
| `adapters.py` | 147 | Infrastructure adapters |
| `capability_wiring.py` | 69 | Capability wiring |
| `contracts_core.py` | 47 | Contract definitions |
| `orchestrator/agent_events.py` | 103 | Agent event handling |
| `orchestrator/events.py` | 47 | Event types |
| `orchestrator/governance_service.py` | 122 | Governance gRPC service |
| `orchestrator/vertical_service.py` | 88 | Vertical routing |
| `services/chat_service.py` | 173 | Chat orchestration |
| `services/debug_api.py` | 94 | Debug endpoints |
| `services/worker_coordinator.py` | 159 | Worker management |
| `verticals/registry.py` | 24 | Vertical registry |

#### Modules with good coverage (>80%)

| Module | Coverage |
|--------|---------|
| `common/cot_proxy.py` | 93% |
| `common/prompt_compression.py` | 90% |
| `config/agent_profiles.py` | 100% |
| `config/constants.py` | 100% |
| `prompts/core/*` | 96-100% |

---

## 3. Structural / Dependency Issues

### jeeves-core submodule: NOT a solution for phantom packages

jeeves-core is a **pure Rust gRPC server** (confirmed by `protocols/interfaces.py:6`:
*"Moved from jeeves_core/protocols.py as part of Session 10 (Complete Python Removal
from jeeves-core)"*). No `.gitmodules` exists. Cloning it would only provide `.proto`
source files for sync -- it contains **zero Python packages**. The phantom packages
originate from an earlier multi-package Python architecture that was partially
consolidated into `jeeves_infra` but never fully wired up.

### CRITICAL: Phantom packages -- diagnosis and fix-forward strategy

`mission_system/pyproject.toml` declares 5 phantom dependencies. Each has a
distinct root cause and fix path:

#### (a) `memory_module` -- ALREADY MIGRATED, needs path fix

All code lives at `jeeves_infra/memory/`. Mechanical find-and-replace only.

| File (line) | Phantom import | Correct import |
|-------------|---------------|----------------|
| `jeeves_infra/memory/__init__.py` (14) | `from memory_module.handlers import register_memory_handlers, reset_cached_services` | `from jeeves_infra.memory.handlers import register_memory_handlers, reset_cached_services` |
| `jeeves_infra/memory/handlers.py` (56) | `from memory_module.messages import GetSessionState, SearchMemory, ...` | `from jeeves_infra.memory.messages import GetSessionState, SearchMemory, ...` |
| `jeeves_infra/memory/messages/__init__.py` (12,23,30) | `from memory_module.messages.events/queries/commands import ...` | `from jeeves_infra.memory.messages.events/queries/commands import ...` |
| `jeeves_infra/memory/services/event_emitter.py` (382) | `from memory_module.messages import MemoryStored` | `from jeeves_infra.memory.messages import MemoryStored` |
| `mission_system/bootstrap.py` (576) | `from memory_module.manager import MemoryManager` | `from jeeves_infra.memory.manager import MemoryManager` |
| `mission_system/adapters.py` (111) | `from memory_module.manager import MemoryManager` | `from jeeves_infra.memory.manager import MemoryManager` |
| `mission_system/tests/acceptance/test_pytest_imports.py` (49,62) | `from memory_module.manager/intent_classifier import ...` | `from jeeves_infra.memory.manager/intent_classifier import ...` |

#### (b) `shared` -- ALREADY MIGRATED, needs path fix

Was a flat utility package split into three locations. `get_component_logger` is
defined at `jeeves_infra/utils/logging/__init__.py:288`.

| Phantom symbol | Correct import path |
|---------------|-------------------|
| `get_component_logger` | `jeeves_infra.utils.logging` |
| `convert_uuids_to_strings`, `uuid_str`, `uuid_read` | `jeeves_infra.utils.uuid_utils` |
| `parse_datetime` | `jeeves_infra.utils.serialization` |

**25 files** need this fix, all under `jeeves_infra/memory/` and `jeeves_infra/postgres/`.

#### (c) `avionics` -- ALREADY MIGRATED (old name for jeeves_infra)

`avionics` was the former package name. Evidence: `jeeves_infra/memory/manager.py:15`
says *"Moved from avionics/memory/manager.py"*. All code-level imports are in 2 test
files (`test_distributed_mode.py`, `test_unwired_audit_phase2.py`). ~20 docstrings
in `jeeves_infra/` also reference the old name.

Fix: `s/avionics/jeeves_infra/` in test files + docstring updates.

#### (d) `protocols` (bare package) -- PARTIALLY MIGRATED + GENUINELY MISSING TYPES

**Path fix needed** for `RequestContext`: exists at `jeeves_infra.protocols.interfaces.RequestContext`.

**Genuinely missing types** (must be written):

| Missing type | Referenced in | Proposed location |
|-------------|--------------|-------------------|
| `Event` | `gateway/event_bus.py:44`, `gateway/websocket.py:23`, `gateway/routers/chat.py:109` | `jeeves_infra/protocols/events.py` |
| `EventCategory` | `gateway/routers/chat.py:135` | `jeeves_infra/protocols/events.py` |
| `EventSeverity` | `gateway/routers/chat.py:140` | `jeeves_infra/protocols/events.py` |
| `EventEmitterProtocol` | `gateway/event_bus.py:44` | `jeeves_infra/protocols/events.py` |
| `MetaValidationIssue` | `utils/models.py:11`, `mission_system/common/models.py:11` | `jeeves_infra/protocols/validation.py` |
| `VerificationReport` | `utils/models.py:11`, `observability/metrics.py:39` | `jeeves_infra/protocols/validation.py` |

#### (e) `control_tower` -- REPLACED BY `kernel_client.py` + Rust kernel

Confirmed deleted by `mission_system/events/bridge.py:22`: *"control_tower deleted -
Session 14"*. The Rust kernel now provides the same functionality via gRPC, accessed
through `jeeves_infra/kernel_client.py`. Runtime code already degrades gracefully
(try/except guards).

**Type mapping (control_tower → kernel_client/protobuf):**

| control_tower type | kernel_client equivalent | Notes |
|-------------------|------------------------|-------|
| `SchedulingPriority` enum | String `"HIGH"/"NORMAL"/"LOW"` | `kernel_client.create_process()` uses `priority_map` dict (line 232) |
| `ProcessState` enum | String `"RUNNING"/"TERMINATED"/etc.` | `ProcessInfo.state` is a plain `str` (line 78) |
| `ResourceQuota` dataclass | kwargs to `kernel_client.create_process()` | Quota set at process creation (line 240) |
| `ResourceUsage` dataclass | `ProcessInfo` fields (llm_calls, tool_calls, etc.) | Inlined into ProcessInfo, not a separate object |
| `ResourceTracker` class | `kernel_client` methods directly | `record_usage()`, `check_quota()`, `get_process()` |
| `ControlTower` class | `KernelClient` itself | `.lifecycle.*` + `.resources.*` → flat async methods |
| `get_commbus()` | `CommBusServiceStub` (exists in pb2_grpc, not yet wired) | Need to add stub to KernelClient |

**Consumer rewiring plan:**

| Consumer | What it needs | Fix |
|----------|--------------|-----|
| `services/worker_coordinator.py` (both copies) | Enum values + lifecycle/resource calls | Replace enums with strings, calls with `await kernel_client.*()` |
| `gateway/server.py` | Process CRUD + orchestration + service registry | Direct rewire for CRUD; orchestration loop needed for `submit_request()`/`resume_request()` |
| `memory/services/event_emitter.py:229` | `get_commbus()` (try/except) | Wire `CommBusServiceStub` into `KernelClient` |
| Test files (3) | Full `control_tower` surface | Rewrite against `KernelClient` mock |

**What can be directly rewired (no new code):**
- `lifecycle.get_process()` → `kernel_client.get_process()`
- `lifecycle.transition_state()` → `kernel_client.transition_state()`
- `lifecycle.terminate()` → `kernel_client.terminate_process()`
- `lifecycle.list_processes()` → `kernel_client.list_processes()`
- `resources.record_usage()` → `kernel_client.record_usage()`
- `resources.check_quota()` → `kernel_client.check_quota()`
- `resources.get_system_usage()` → `kernel_client.get_process_counts()`
- `lifecycle.submit() + resources.allocate()` → single `kernel_client.create_process()`

**What needs new code:**
- `submit_request()` / `resume_request()` → orchestration loop using `initialize_orchestration_session()` + `get_next_instruction()` + `report_agent_result()`
- `register_service()` → Python-side service registry (not a kernel concern)
- `events` (EventAggregator) → Wire `CommBusServiceStub` or Python-side event bus
- `get_commbus()` → Add `CommBusServiceStub` to KernelClient (stub already in pb2_grpc)

### CRITICAL: Missing source file referenced by tests

`mission_system/orchestrator/flow_service.py` does not exist, but
`test_flow_service.py` (630+ lines, ~20 tests) imports from it.

### MEDIUM: Protobuf schema drift

`kernel_client.py` references `inference_requests` and `inference_input_chars`
fields on `RecordUsageRequest`, but the generated protobuf does not define them.
The `.proto` source needs to be re-synced with the Rust kernel's proto definitions.

### MEDIUM: Missing re-export

`OptionalCheckpoint` is defined in `jeeves_infra/runtime/agents.py:648` but
imported from `jeeves_infra.protocols` in two `debug_api.py` files. The
`protocols/__init__.py` does not re-export it.

### LOW: No CI/CD configuration

No GitHub Actions, GitLab CI, or any CI pipeline exists. Tests are not
automatically run on commits or PRs.

### LOW: No git submodule for jeeves-core

jeeves-core is pure Rust, communicates via gRPC only. A submodule would be useful
**only** for keeping `engine.proto` in sync (preventing the proto drift issue above).
No `.gitmodules` exists. The generated `_pb2.py` files embed a Go package path
(`github.com/jeeves-cluster-organization/codeanalysis/coreengine/proto`) suggesting
the proto source lives in a separate `codeanalysis` repository.

---

## 4. Trackable Issues (scoped to this repository)

### P0 -- Blocking test execution (fix-forward wiring)

| # | Title | Category | Effort | Files |
|---|-------|----------|--------|-------|
| 1 | Fix `memory_module` → `jeeves_infra.memory` imports | Path fix (a) | Small | ~8 files, mechanical |
| 2 | Fix `shared` → `jeeves_infra.utils.{logging,uuid_utils,serialization}` | Path fix (a) | Medium | 25 files, 3-way split |
| 3 | Fix `avionics` → `jeeves_infra` in test files | Path fix (a) | Small | 2 test files + docstrings |
| 4 | Write `jeeves_infra/protocols/events.py` (Event, EventCategory, EventSeverity, EventEmitterProtocol) | New code (b) | Medium | 4 types, 3 consumers |
| 5 | Write `jeeves_infra/protocols/validation.py` (MetaValidationIssue, VerificationReport) | New code (b) | Small | 2 types, 3 consumers |
| 6 | Rewire `control_tower` consumers → `kernel_client` (direct rewire for 8 methods, new code for orchestration loop + CommBus) | Rewire | Large | ~6 source files, 3 test files |
| 7 | Resolve or remove `flow_service.py` reference + its test file | Bug | Small | 1 test file |
| 8 | Add `OptionalCheckpoint` to `protocols/__init__.py` exports | Bug | Trivial | 1 line |
| 9 | Fix protobuf schema drift (`inference_requests`, `inference_input_chars`) | Bug | Small | kernel_client.py |
| 10 | Clean phantom deps from `mission_system/pyproject.toml` | Bug | Trivial | 5 lines |
| 11 | Add `pydantic-settings` to root `pyproject.toml` dependencies | Bug | Trivial | 1 line |

### P1 -- Coverage gaps on critical paths

| # | Title | Type | Effort |
|---|-------|------|--------|
| 12 | Add unit tests for `kernel_client.py` resource management methods | Test | Medium |
| 13 | Add unit tests for `pipeline_worker.py` | Test | Medium |
| 14 | Add unit tests for `wiring.py` remaining DI paths | Test | Medium |
| 15 | Add unit tests for `feature_flags.py` | Test | Medium |
| 16 | Add unit tests for `gateway/` HTTP layer (FastAPI TestClient) | Test | Large |
| 17 | Add unit tests for `services/chat_service.py` | Test | Large |
| 18 | Add unit tests for `services/worker_coordinator.py` | Test | Large |
| 19 | Add unit tests for `postgres/client.py` (mock asyncpg) | Test | Medium |
| 20 | Add unit tests for `redis/client.py` + `connection_manager.py` | Test | Medium |
| 21 | Add unit tests for `mission_system/adapters.py` | Test | Medium |
| 22 | Add unit tests for `mission_system/orchestrator/` services | Test | Large |

### P2 -- Test infrastructure & quality

| # | Title | Type | Effort |
|---|-------|------|--------|
| 23 | Add CI pipeline (GitHub Actions) for pytest + coverage | Infra | Medium |
| 24 | Add coverage threshold enforcement (fail build below X%) | Infra | Small |
| 25 | Enable contract tests with testcontainers for PostgreSQL | Test | Medium |
| 26 | Add proto sync mechanism (submodule or CI step) for jeeves-core | Infra | Medium |

### P3 -- Coverage for utility/secondary modules

| # | Title | Type | Effort |
|---|-------|------|--------|
| 27 | Add tests for `utils/` modules (fuzzy_matcher, id_generator, uuid_utils, etc.) | Test | Medium |
| 28 | Add tests for `memory/` repositories and services | Test | Large |
| 29 | Add tests for `observability/` (metrics, tracing) | Test | Medium |
| 30 | Add tests for `webhooks/service.py` | Test | Medium |
| 31 | Add tests for `middleware/rate_limiter.py` | Test | Small |
| 32 | Add tests for `logging/` (setup, context) | Test | Small |

---

## 5. Recommendations

### Fall-forward wiring order

The fix-forward approach for the phantom packages follows a clear dependency chain:

```
Step 1: Mechanical path fixes (P0 #1-3)
  memory_module → jeeves_infra.memory   (~8 files)
  shared → jeeves_infra.utils.*         (~25 files)
  avionics → jeeves_infra              (~2 test files)
  ↓
Step 2: Write missing types (P0 #4-5)
  jeeves_infra/protocols/events.py      (4 types)
  jeeves_infra/protocols/validation.py  (2 types)
  ↓
Step 3: Rewire control_tower → kernel_client (P0 #6)
  Direct: 8 methods map 1:1 (enum→string, sync→async)
  New:    Orchestration loop, CommBusServiceStub, service registry
  ↓
Step 4: Trivial fixes (P0 #7-11)
  OptionalCheckpoint re-export, proto drift, dep cleanup
```

Steps 1 & 4 are mechanical -- no design decisions needed. Step 2 requires reading
the consumers to understand the type contracts. Step 3 is the largest piece: the
8 direct-rewire methods are straightforward (enum→string, sync→async), but the
orchestration loop (`submit_request`/`resume_request`) and CommBus wiring require
new code. The Rust kernel already provides all the gRPC services -- this is purely
a Python client-side wiring task.

### Post-wiring impact

After completing P0:
- ~7 currently-uncollectable test files will become runnable (~70+ additional tests)
- ~45 source modules that fail at import will become testable/measurable
- Estimated coverage increase: **+5-10% with zero new test code**

### Coverage targets

| Milestone | Target | When |
|-----------|--------|------|
| After P0 wiring | ~30% combined | Immediate |
| After P1 critical path tests | ~50% combined | Near-term |
| After P2 infrastructure + P3 utilities | ~65% combined | Medium-term |

### Other recommendations

1. **Add CI immediately** (P2 #23). Without automated test runs, regressions like
   the proto drift and missing module issues accumulate silently.

2. **Prioritize gateway and services testing** (P1 #16-18). The HTTP/WS/gRPC
   gateway and the chat/worker services are the system's API surface and have 0%
   coverage.

3. **Add proto sync for jeeves-core** (P2 #26). The generated `_pb2.py` files embed
   a Go package path (`github.com/jeeves-cluster-organization/codeanalysis/coreengine/proto`)
   suggesting the proto source lives in a separate `codeanalysis` repo. A submodule
   or CI step to regenerate Python stubs would prevent future drift.

---

## Appendix A: P0 Implementation Plan (line-level)

### Guiding principles

- **No backward-compatibility shims.** Delete old paths, don't alias them.
- **No duplicate files.** Where infra and mission_system have identical copies,
  one is canonical and the other imports from it.
- **Forward only.** If code references a deleted subsystem, rewire it to the
  replacement or delete the consumer.

### Additional issues discovered during investigation

| Issue | Details |
|-------|---------|
| `governance_service.py` proto import path wrong | Uses `from proto import jeeves_pb2_grpc` (bare); should be `from jeeves_infra.gateway.proto import jeeves_pb2_grpc`. The bare import only works inside `gateway/` due to relative paths. |
| Duplicate `worker_coordinator.py` | `jeeves_infra/services/worker_coordinator.py` and `mission_system/services/worker_coordinator.py` are byte-identical (604 lines). |
| Duplicate `debug_api.py` | `jeeves_infra/services/debug_api.py` and `mission_system/services/debug_api.py` are byte-identical (388 lines). |
| `control_tower` calls in `worker_coordinator.py` are sync | All `self._control_tower.lifecycle.*` calls are NOT awaited, but `KernelClient` methods are all `async`. The calling methods are already `async def`, so adding `await` is safe. |
| `bootstrap.py` resource callback is sync | `track_resources()` callback (line 338) calls `control_tower.record_llm_call()` synchronously. `KernelClient.record_llm_call()` is async. Callback must become async. |
| Newer proto exists but is not used | `protocols/coreengine/proto/engine_pb2.py` has inference fields; `protocols/engine_pb2.py` (active) does not. |

---

### Step 1: Mechanical path fixes

#### 1a. `memory_module` → `jeeves_infra.memory` (P0 #1)

| File | Line | Old | New |
|------|------|-----|-----|
| `jeeves_infra/memory/__init__.py` | 14 | `from memory_module.handlers import register_memory_handlers, reset_cached_services` | `from jeeves_infra.memory.handlers import register_memory_handlers, reset_cached_services` |
| `jeeves_infra/memory/handlers.py` | 56 | `from memory_module.messages import (...)` | `from jeeves_infra.memory.messages import (...)` |
| `jeeves_infra/memory/messages/__init__.py` | 12 | `from memory_module.messages.events import (...)` | `from jeeves_infra.memory.messages.events import (...)` |
| `jeeves_infra/memory/messages/__init__.py` | 23 | `from memory_module.messages.queries import (...)` | `from jeeves_infra.memory.messages.queries import (...)` |
| `jeeves_infra/memory/messages/__init__.py` | 30 | `from memory_module.messages.commands import (...)` | `from jeeves_infra.memory.messages.commands import (...)` |
| `jeeves_infra/memory/services/event_emitter.py` | 382 | `from memory_module.messages import MemoryStored` | `from jeeves_infra.memory.messages import MemoryStored` |
| `mission_system/bootstrap.py` | 576 | `from memory_module.manager import MemoryManager` | `from jeeves_infra.memory.manager import MemoryManager` |
| `mission_system/adapters.py` | 111 | `from memory_module.manager import MemoryManager` | `from jeeves_infra.memory.manager import MemoryManager` |
| `mission_system/tests/acceptance/test_pytest_imports.py` | 49 | `from memory_module.manager import MemoryManager` | `from jeeves_infra.memory.manager import MemoryManager` |
| `mission_system/tests/acceptance/test_pytest_imports.py` | 62 | `from memory_module.intent_classifier import IntentClassifier` | `from jeeves_infra.memory.intent_classifier import IntentClassifier` |

#### 1b. `shared` → `jeeves_infra.utils.*` (P0 #2)

**Import mapping:**

| Old import | New import |
|-----------|-----------|
| `from shared import get_component_logger` | `from jeeves_infra.utils.logging import get_component_logger` |
| `from shared import get_component_logger, parse_datetime` | Split into 2 imports: `from jeeves_infra.utils.logging import get_component_logger` + `from jeeves_infra.utils.serialization import parse_datetime` |
| `from shared import get_component_logger, convert_uuids_to_strings` | Split: `...logging import get_component_logger` + `...uuid_utils import convert_uuids_to_strings` |
| `from shared import uuid_str, uuid_read, get_component_logger, parse_datetime` | Split: `...logging import get_component_logger` + `...uuid_utils import uuid_str, uuid_read` + `...serialization import parse_datetime` |

**Files (25):** All under `jeeves_infra/memory/` (managers, services, repositories),
`jeeves_infra/capability_registry.py`, and `jeeves_infra/postgres/graph.py`.

#### 1c. `avionics` → `jeeves_infra` (P0 #3)

**Code-level imports (2 test files):**
- `mission_system/tests/e2e/test_distributed_mode.py`: Replace all `from avionics.X import Y` with `from jeeves_infra.X import Y`
- `mission_system/tests/integration/test_unwired_audit_phase2.py`: Same replacement

**Docstrings (~20 files in jeeves_infra/):** Update `from avionics.X import Y` to
`from jeeves_infra.X import Y` in Usage/Example docstring blocks. Not blocking but
prevents confusion.

---

### Step 2: Write missing protocol types

#### 2a. Create `jeeves_infra/protocols/events.py` (P0 #4)

```python
"""Unified event types for the gateway event bus."""
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, Optional
import uuid

from jeeves_infra.protocols.interfaces import RequestContext


class EventCategory(str, Enum):
    AGENT_LIFECYCLE = "agent_lifecycle"
    CRITIC_DECISION = "critic_decision"
    TOOL_EXECUTION = "tool_execution"
    PIPELINE_FLOW = "pipeline_flow"
    STAGE_TRANSITION = "stage_transition"
    DOMAIN_EVENT = "domain_event"


class EventSeverity(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class Event:
    event_id: str
    event_type: str
    category: EventCategory
    timestamp_iso: str
    timestamp_ms: int
    request_context: RequestContext
    request_id: str
    session_id: str
    user_id: Optional[str]
    payload: Dict[str, Any]
    severity: EventSeverity
    source: str
    version: str = "1.0"

    @classmethod
    def create_now(cls, event_type, category, request_context,
                   payload=None, severity=EventSeverity.INFO,
                   source="", version="1.0"):
        now = datetime.now(timezone.utc)
        return cls(
            event_id=str(uuid.uuid4()), event_type=event_type,
            category=category, timestamp_iso=now.isoformat(),
            timestamp_ms=int(now.timestamp() * 1000),
            request_context=request_context,
            request_id=request_context.request_id,
            session_id=request_context.session_id or "",
            user_id=request_context.user_id,
            payload=payload or {}, severity=severity,
            source=source, version=version,
        )


class EventEmitterProtocol:
    async def emit(self, event: Event) -> None:
        raise NotImplementedError
    async def subscribe(self, pattern: str,
                        handler: Callable[[Event], Awaitable[None]]) -> str:
        raise NotImplementedError
    async def unsubscribe(self, subscription_id: str) -> None:
        raise NotImplementedError
```

**Then fix consumer imports (3 files):**

| File | Old | New |
|------|-----|-----|
| `gateway/event_bus.py:44` | `from protocols.events import Event, EventCategory, EventSeverity, EventEmitterProtocol` | `from jeeves_infra.protocols.events import Event, EventCategory, EventSeverity, EventEmitterProtocol` |
| `gateway/websocket.py:23` | `from protocols.events import Event` | `from jeeves_infra.protocols.events import Event` |
| `gateway/routers/chat.py:109` | `from protocols.events import EventCategory` | `from jeeves_infra.protocols.events import EventCategory` |
| `gateway/routers/chat.py:135-139` | `from protocols.events import Event, EventCategory, EventSeverity` | `from jeeves_infra.protocols.events import Event, EventCategory, EventSeverity` |

#### 2b. Create `jeeves_infra/protocols/validation.py` (P0 #5)

```python
"""Meta-validation types for the verification layer."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List

@dataclass
class MetaValidationIssue:
    type: str = ""
    message: str = ""
    severity: str = "warning"

@dataclass
class VerificationReport:
    approved: bool = False
    issues_found: List[MetaValidationIssue] = field(default_factory=list)
```

**Then fix consumer imports (3 files):**

| File | Old | New |
|------|-----|-----|
| `jeeves_infra/utils/models.py:11` | `from protocols.validation import MetaValidationIssue, VerificationReport` | `from jeeves_infra.protocols.validation import MetaValidationIssue, VerificationReport` |
| `mission_system/common/models.py:11` | same | same fix |
| `jeeves_infra/observability/metrics.py:39` | `from protocols.validation import VerificationReport` | `from jeeves_infra.protocols.validation import VerificationReport` |

---

### Step 3: Rewire control_tower → kernel_client (P0 #6)

This is the largest step. Broken into sub-tasks by file.

#### 3a. `jeeves_infra/services/worker_coordinator.py`

All methods are already `async def`. Changes:

1. **Line 104**: Constructor param `control_tower: Optional["ControlTowerProtocol"]` → `kernel_client: Optional["KernelClient"] = None`
2. **Line 119**: `self._control_tower = control_tower` → `self._kernel_client = kernel_client`
3. **Lines 152-181** (submit_envelope block): Replace:
   ```python
   if self._kernel_client:
       priority_str = "HIGH" if priority >= 10 else ("LOW" if priority <= -10 else "NORMAL")
       await self._kernel_client.create_process(
           pid=pid, request_id=envelope.request_id or pid,
           priority=priority_str,
           max_llm_calls=100, max_tool_calls=50, max_agent_hops=20,
       )
   ```
4. **Lines 363-395** (process execution): Replace:
   ```python
   if self._kernel_client:
       await self._kernel_client.transition_state(pid, "RUNNING", "task_started")
       await self._kernel_client.record_usage(pid=pid, agent_hops=1)
       quota = await self._kernel_client.check_quota(pid)
       if not quota.within_bounds:
           await self._kernel_client.terminate_process(pid, quota.exceeded_reason)
   ```
5. **Lines 409-435** (post-execution usage): Replace with `await self._kernel_client.record_usage(...)` + `await self._kernel_client.check_quota(pid)`
6. **Lines 477-482** (failure): Replace with `await self._kernel_client.terminate_process(pid, str(e))`
7. **Delete `mission_system/services/worker_coordinator.py`** (byte-identical duplicate). Update `mission_system/bootstrap.py:449` to import from `jeeves_infra.services.worker_coordinator`.

#### 3b. `jeeves_infra/gateway/server.py`

All endpoint handlers are already `async def`. Changes:

1. **Line 121**: `self.control_tower: Optional[ControlTower]` → `self.kernel_client: Optional[KernelClient]`
2. **Line 250**: `control_tower = app_context.control_tower` → `kernel_client = app_context.kernel_client`
3. **Lines 302-320**: `control_tower.register_service(...)` → Delete. Service registration was a control_tower concept. The orchestrator factory should handle service dispatch internally, or a lightweight `ServiceRegistry` dict replaces it (in-process only).
4. **Line 327**: `event_aggregator=control_tower.events` → Create a local `EventAggregator` class (simple pub/sub dict of handlers). ~30 lines. Pass it as `event_aggregator=event_aggregator`.
5. **Line 352**: `app_state.control_tower = control_tower` → `app_state.kernel_client = kernel_client`
6. **Lines 544, 775, 934, 988**: All guard `if not app_state.control_tower:` → change to `if not app_state.kernel_client:`
7. **Lines 687-689** (`submit_request`): Replace with:
   ```python
   pid = str(uuid.uuid4())
   await app_state.kernel_client.create_process(pid, request_id=..., priority="NORMAL")
   await app_state.kernel_client.initialize_orchestration_session(pid, ...)
   # Kick off orchestration loop (get_next_instruction / report_agent_result)
   ```
   This requires a new `_run_orchestration_loop(kernel_client, pid)` async helper.
8. **Lines 781-783** (`resume_request`): Replace with `await kernel_client.transition_state(pid, "RUNNING")` + resume orchestration loop.
9. **Lines 938-944** (get process/usage/quota): Replace sync calls with `await`:
   ```python
   process = await app_state.kernel_client.get_process(pid)
   quota = await app_state.kernel_client.check_quota(pid)
   ```
10. **Lines 992-999** (system metrics): Replace with `await kernel_client.get_process_counts()` + `await kernel_client.list_processes(state=state)`.
11. **Line 995**: Delete `from control_tower.types import ProcessState`. Use `PROCESS_STATES = ["NEW", "READY", "RUNNING", "WAITING", "BLOCKED", "TERMINATED", "ZOMBIE"]`.

#### 3c. `jeeves_infra/memory/services/event_emitter.py`

1. **Lines 229-233**: Delete the `from control_tower.ipc.commbus import get_commbus` lazy import. Simplify the `commbus` property to just return `self._commbus` (which is `None` unless injected via constructor at line 206).

#### 3d. `jeeves_infra/context.py`

1. **Line 114**: Delete `control_tower: Optional[Any] = None` field.
2. **Line 151**: Delete `control_tower=self.control_tower,` from `with_request()`.
3. The `kernel_client: Optional["KernelClient"] = None` field at line 110 already exists.

#### 3e. `mission_system/bootstrap.py`

1. **Lines 325-353**: Resource callback. Replace `app_context.control_tower` with `app_context.kernel_client`. The callback `track_resources()` must become async:
   ```python
   async def track_resources(tokens_in, tokens_out):
       await kernel_client.record_llm_call(pid, tokens_in, tokens_out)
   ```
   Verify that `LLMGateway.set_resource_callback()` accepts async callables (if not, wrap with `asyncio.create_task()`).
2. **Line 518**: `control_tower=app_context.control_tower` → `kernel_client=app_context.kernel_client`

#### 3f. New code: `EventAggregator` (~30 lines)

A minimal local pub/sub for `server.py` line 327. Replaces `control_tower.events`:

```python
class EventAggregator:
    def __init__(self):
        self._handlers: Dict[str, List[Callable]] = {}
    def subscribe(self, pattern: str, callback):
        self._handlers.setdefault(pattern, []).append(callback)
    def unsubscribe(self, pattern: str, callback):
        self._handlers.get(pattern, []).remove(callback)
    async def emit(self, event_type: str, data: Any):
        for pattern, handlers in self._handlers.items():
            if fnmatch.fnmatch(event_type, pattern):
                for handler in handlers:
                    await handler(data)
```

Can live in `jeeves_infra/gateway/event_aggregator.py` or inline in `server.py`.

#### 3g. New code: orchestration loop

A helper that composes kernel_client primitives into `submit_request`/`resume_request` equivalents:

```python
async def run_orchestration(kernel_client, pid, agent_registry, event_aggregator):
    session = await kernel_client.initialize_orchestration_session(pid, ...)
    while not session.terminated:
        instruction = await kernel_client.get_next_instruction(pid)
        if instruction.kind == "EXECUTE_AGENT":
            agent = agent_registry.get(instruction.agent_name)
            result = await agent.execute(instruction.envelope)
            metrics = AgentExecutionMetrics(...)
            await kernel_client.report_agent_result(pid, metrics, result)
        elif instruction.kind == "TERMINATE":
            break
        session = await kernel_client.get_orchestration_session_state(pid)
```

Can live in `jeeves_infra/services/orchestrator.py` or `jeeves_infra/gateway/orchestration.py`.

---

### Step 4: Remaining fixes

#### 4a. `OptionalCheckpoint` re-export (P0 #8)

In `jeeves_infra/protocols/__init__.py`:
- **Line 135-140**: Add `OptionalCheckpoint` to the `from jeeves_infra.runtime.agents import (...)` block.
- **Line 317-321**: Add `"OptionalCheckpoint"` to the `__all__` list in the Runtime components section.

#### 4b. Proto drift fix (P0 #9)

**Option B (minimal, recommended):** Remove drifted fields from `kernel_client.py`:
- **Lines 67-68**: Delete `inference_requests: int = 0` and `inference_input_chars: int = 0` from `QuotaCheckResult`.
- **Lines 397-398**: Delete params from `record_usage()` signature.
- **Lines 409-410**: Delete from docstring.
- **Lines 422-423**: Delete from `pb2.RecordUsageRequest()` constructor.
- **Lines 434-435**: Delete from `QuotaCheckResult()` constructor.
- **Lines 900-922**: Delete `record_inference_usage()` method entirely (dead code, nothing calls it).

Note: A newer proto at `protocols/coreengine/proto/engine_pb2.py` HAS these fields.
If inference tracking is wanted later, promote that proto to be the active one.

#### 4c. `flow_service.py` (P0 #7)

The test file (630 lines) contains enough detail to reconstruct the module: 6 gRPC
methods + 2 helpers, SQL patterns, constructor signatures. The proto stubs already
exist in `jeeves_pb2_grpc.JeevesFlowServiceServicer`. **Recommended:** Reconstruct
`mission_system/orchestrator/flow_service.py` from the test contracts. This unblocks
~20 tests immediately.

#### 4d. `governance_service.py` proto import fix

- **Line 29-33**: Change `from proto import jeeves_pb2, jeeves_pb2_grpc` to
  `from jeeves_infra.gateway.proto import jeeves_pb2, jeeves_pb2_grpc` (the bare
  `proto` package only works inside `gateway/` where it's a sibling).

#### 4e. Clean phantom deps (P0 #10)

In `mission_system/pyproject.toml`, delete lines 25-29:
```
    "protocols>=1.0.0",
    "shared>=1.0.0",
    "avionics>=1.0.0",
    "control_tower>=1.0.0",
    "memory_module>=1.0.0",
```
Replace with:
```
    "jeeves-infra>=1.0.0",
```

#### 4f. Add `pydantic-settings` (P0 #11)

In root `pyproject.toml`, add to `dependencies` (line 35):
```
    "pydantic-settings>=2.0.0",
```

---

### Execution order (dependency-aware)

```
Phase 1 -- Unblock imports (no new code, all mechanical)
  1a. memory_module path fixes          (~10 edits)
  1b. shared path fixes                 (~25 files, ~40 edits)
  1c. avionics path fixes               (~2 test files)
  4e. Clean phantom deps                (1 file, 5 deletions + 1 addition)
  4f. Add pydantic-settings             (1 line)
  → Run tests. Expect: memory/ modules now importable, ~2 more test files collectable.

Phase 2 -- Write missing types (small new files)
  2a. Create protocols/events.py        (1 new file, ~80 lines)
      Fix 3 consumer imports            (4 edits)
  2b. Create protocols/validation.py    (1 new file, ~15 lines)
      Fix 3 consumer imports            (3 edits)
  4a. OptionalCheckpoint re-export      (2 edits)
  4d. governance_service proto fix      (1 edit)
  → Run tests. Expect: gateway modules importable, debug_api importable, ~3 more test files collectable.

Phase 3 -- Proto drift fix (small, isolated)
  4b. Remove inference fields           (6 edits in kernel_client.py)
  → Run tests. Expect: 5 kernel_client tests now pass.

Phase 4 -- control_tower rewire (largest, most edits)
  3c. event_emitter.py commbus cleanup  (1 edit)
  3a. worker_coordinator.py rewire      (~15 edits + delete duplicate)
  3e. bootstrap.py rewire               (~5 edits)
  3d. context.py cleanup                (2 edits)
  3f. EventAggregator (~30 lines)       (1 new file or inline)
  3b. server.py rewire                  (~20 edits)
  3g. Orchestration loop (~40 lines)    (1 new file or inline)
  → Run tests. Expect: all control_tower guard paths now active.

Phase 5 -- flow_service reconstruction (optional, unblocks 20 tests)
  4c. Write flow_service.py from test contracts (~250 lines)
  → Run tests. Expect: test_flow_service.py collectable, ~20 more tests.
```

### Expected outcome

| Metric | Before P0 | After P0 |
|--------|----------|---------|
| Tests collectable | 340 | ~430 |
| Tests passing | 295 | ~380+ |
| Tests failing | 9 | ~4 (contract test infra) |
| jeeves_infra coverage | 17% | ~25% (more modules importable) |
| mission_system coverage | 50% | ~55% |
| Import errors at collection | 7 files | 0 |
