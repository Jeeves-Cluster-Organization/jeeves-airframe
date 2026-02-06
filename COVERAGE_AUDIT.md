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

### CRITICAL: Phantom packages (5 declared, 0 exist)

`mission_system/pyproject.toml` declares these as hard dependencies, but none
exist as installable packages or directories in the repository:

| Package | Files importing it | Impact |
|---------|-------------------|--------|
| `memory_module>=1.0.0` | 15+ files | Blocks all memory-related imports |
| `shared>=1.0.0` | 25 files | Blocks `get_component_logger` everywhere |
| `protocols>=1.0.0` | 0 runtime imports | Misleading dependency |
| `avionics>=1.0.0` | 0 runtime imports | Stale dependency |
| `control_tower>=1.0.0` | 0 runtime imports | Stale dependency |

**Root cause**: These appear to be sibling packages from a monorepo that were
partially migrated into `jeeves_infra/` but import paths were never updated.

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

Despite documentation referencing "jeeves-core Rust microkernel", there is no
`.gitmodules` file. The gRPC client communicates with it over the network, but
the proto files may drift without a submodule keeping them in sync.

---

## 4. Trackable Issues (scoped to this repository)

### P0 -- Blocking test execution

| # | Title | Type | Effort |
|---|-------|------|--------|
| 1 | Fix `memory_module` imports → `jeeves_infra.memory` | Bug | Medium |
| 2 | Fix `shared` imports → `jeeves_infra.utils.logging` (or create shim) | Bug | Medium |
| 3 | Resolve or remove `flow_service.py` reference + its test file | Bug | Small |
| 4 | Add `OptionalCheckpoint` to `protocols/__init__.py` exports | Bug | Trivial |
| 5 | Fix protobuf schema drift (`inference_requests`, `inference_input_chars`) | Bug | Small |
| 6 | Clean phantom deps from `mission_system/pyproject.toml` | Bug | Trivial |

### P1 -- Coverage gaps on critical paths

| # | Title | Type | Effort |
|---|-------|------|--------|
| 7 | Add unit tests for `kernel_client.py` resource management methods | Test | Medium |
| 8 | Add unit tests for `pipeline_worker.py` | Test | Medium |
| 9 | Add unit tests for `wiring.py` remaining DI paths | Test | Medium |
| 10 | Add unit tests for `feature_flags.py` | Test | Medium |
| 11 | Add unit tests for `gateway/` HTTP layer (FastAPI TestClient) | Test | Large |
| 12 | Add unit tests for `services/chat_service.py` | Test | Large |
| 13 | Add unit tests for `services/worker_coordinator.py` | Test | Large |
| 14 | Add unit tests for `postgres/client.py` (mock asyncpg) | Test | Medium |
| 15 | Add unit tests for `redis/client.py` + `connection_manager.py` | Test | Medium |
| 16 | Add unit tests for `mission_system/adapters.py` | Test | Medium |
| 17 | Add unit tests for `mission_system/orchestrator/` services | Test | Large |

### P2 -- Test infrastructure & quality

| # | Title | Type | Effort |
|---|-------|------|--------|
| 18 | Add CI pipeline (GitHub Actions) for pytest + coverage | Infra | Medium |
| 19 | Add coverage threshold enforcement (fail build below X%) | Infra | Small |
| 20 | Add `pydantic-settings` to root pyproject.toml dependencies | Bug | Trivial |
| 21 | Enable contract tests with testcontainers for PostgreSQL | Test | Medium |
| 22 | Add proto sync mechanism (submodule or CI step) for jeeves-core | Infra | Medium |

### P3 -- Coverage for utility/secondary modules

| # | Title | Type | Effort |
|---|-------|------|--------|
| 23 | Add tests for `utils/` modules (fuzzy_matcher, id_generator, uuid_utils, etc.) | Test | Medium |
| 24 | Add tests for `memory/` repositories and services | Test | Large |
| 25 | Add tests for `observability/` (metrics, tracing) | Test | Medium |
| 26 | Add tests for `webhooks/service.py` | Test | Medium |
| 27 | Add tests for `middleware/rate_limiter.py` | Test | Small |
| 28 | Add tests for `logging/` (setup, context) | Test | Small |

---

## 5. Recommendations

1. **Fix P0 items first.** The phantom package imports (`memory_module`, `shared`)
   prevent ~70+ tests from collecting and block coverage measurement on ~45 source
   modules. Fixing imports will likely raise measurable coverage by 5-10% with zero
   new test code.

2. **Set a coverage floor.** Current combined coverage is approximately 25%. After
   fixing P0 imports, target 40% as a near-term floor, 60% as a medium-term goal.

3. **Prioritize gateway and services testing.** The HTTP/WS/gRPC gateway and the
   chat/worker services are the system's API surface and have 0% coverage.

4. **Add CI immediately.** Without automated test runs, regressions like the proto
   drift and missing module issues accumulate silently.

5. **Consider testcontainers for integration tests.** The 36 skipped contract tests
   need PostgreSQL. `testcontainers-python` can provide ephemeral DB instances in CI.
