# Jeeves-Airframe: Comprehensive Repository Audit

**Date:** 2026-02-23
**Scope:** Full codebase, git history, architecture, security, testing, capabilities

---

## 1. Executive Summary

**jeeves-airframe** (`jeeves_infra`) is a Python 3.11+ infrastructure and orchestration framework for the Jeeves microkernel ecosystem. It serves as the middleware layer between a Rust micro-kernel (`jeeves-core`) and a capability layer, providing: LLM provider abstraction, HTTP/WebSocket gateway, pipeline execution, IPC transport, database abstraction, event orchestration, and observability.

| Metric | Value |
|--------|-------|
| **Language** | Python 3.11+ |
| **Package Name** | `jeeves-infra` |
| **Source Files** | 89 Python files |
| **Test Files** | 31 Python files |
| **Source LOC** | 18,962 |
| **Test LOC** | 6,560 |
| **Total Dependencies** | 74 packages (5 core + optional groups) |
| **Total Commits** | 52 |
| **Contributors** | 3 (Emper0r: 33, Claude: 15, Shahbaz Shaik: 4) |
| **Repo Age** | 30 days (Jan 24 – Feb 12, 2026) |
| **License** | Apache-2.0 |
| **Test Status** | 167 passed, 0 failed (as of audit date) |

---

## 2. Repository Evolution & Git History

### 2.1 Timeline (52 commits over 30 days)

```
Jan 24  ████                        Initial commit, package structure
Jan 25  ████████                    Tests moved, adapters fix, restructure
Jan 26  ██                          LlamaServer adapter fix
Jan 29  ████                        jeeves-infra integration (PR #2)
Jan 30  ██                          Export changes
Feb 01  ████                        Kernel hardening, inference tracking
Feb 02  ██                          Mock renames
Feb 05  ██                          Kernel client config update
Feb 06  ████████████████████████████ Major audit + 6-phase remediation (14 commits)
Feb 07  ██████                      PR merge, coverage audit cleanup
Feb 09  ██████████████████          Postgres decoupling, debloating (9 commits)
Feb 10  ██████████████              mission_system merge, bootstrap refactor (7 commits)
Feb 11  ████████                    IPC migration gRPC→TCP+msgpack (4 commits)
Feb 12  ████                        Database rewrite, EventBridge wiring (2 commits)
```

### 2.2 Key Evolutionary Phases

| Phase | Date Range | Description | Impact |
|-------|-----------|-------------|--------|
| **Genesis** | Jan 24-25 | Initial standalone package extraction from parent repo | Foundation |
| **Integration** | Jan 26-30 | Replace airframe with jeeves-infra, adapter fixes | PR #1, #2 |
| **Hardening** | Feb 1-5 | Kernel client force parameter, gRPC status codes, inference tracking | Stability |
| **Major Audit** | Feb 6-7 | Claude-driven 6-phase audit: phantom imports, dead code, type fixes, layer separation | -1,800 LOC dead code, 75 import fixes across 35 files |
| **Debloating** | Feb 9 | Remove postgres-specific code, push domain logic to capabilities | -568 LOC, protocol-based DB |
| **Consolidation** | Feb 10 | Merge mission_system into jeeves_infra, eliminate globals, K8s bootstrap | -11,557 LOC (massive), single package |
| **IPC Migration** | Feb 11 | gRPC/protobuf → TCP+msgpack, delete generated code | -4,000+ LOC generated proto code |
| **Final Polish** | Feb 12 | Database protocol rewrite, EventBridge end-to-end | -7,743 insertions, +3,516 deletions in single commit |

### 2.3 Contributor Analysis

| Author | Commits | Role |
|--------|---------|------|
| **Emper0r** | 33 (63%) | Primary developer — architecture, refactoring, features |
| **Claude** | 15 (29%) | AI-assisted audit — import fixes, dead code removal, type corrections |
| **Shahbaz Shaik** | 4 (8%) | PR merges, cleanup |

### 2.4 Code Trajectory

The repository has undergone significant **net reduction**:
- The mission_system merge alone removed ~11,500 lines
- gRPC→msgpack migration deleted ~4,000 lines of generated code
- Final database rewrite removed another ~7,700 net lines
- Overall trend: **aggressive simplification** from a larger, more complex ancestor

---

## 3. Architecture

### 3.1 Three-Layer Model

```
┌─────────────────────────────────────────────┐
│         Capability Layer (User Space)        │
│   Agents, Prompts, Tools, Domain DB, etc.    │
│         imports from jeeves_infra ↓          │
├─────────────────────────────────────────────┤
│       jeeves_infra (THIS PACKAGE)            │
│   Gateway, LLM, Pipeline, IPC, Events,       │
│   Orchestration, Database, Observability     │
│         IPC (TCP+msgpack) ↓                  │
├─────────────────────────────────────────────┤
│       jeeves-core (Rust Microkernel)         │
│   Rate limiting, routing, state management   │
└─────────────────────────────────────────────┘
```

### 3.2 Package Structure

```
jeeves_infra/                    (89 files, 18,962 LOC)
├── __init__.py                  Package init
├── bootstrap.py          (352)  Composition root — AppContext creation
├── capability_registry.py (266)  Capability registration
├── capability_wiring.py         Discovery and routing
├── context.py                   Request context (frozen dataclass)
├── feature_flags.py       (396)  Runtime toggles
├── health.py              (372)  K8s liveness/readiness probes
├── kernel_client.py       (823)  TCP+msgpack IPC bridge to Rust kernel
├── pipeline_worker.py     (519)  Agent execution worker
├── settings.py            (292)  Pydantic-based configuration
├── thresholds.py                Configuration thresholds
├── wiring.py              (304)  Tool executor framework, DB client factory
│
├── config/                      Configuration and constants
├── database/                    Database abstraction (factory, registry)
├── distributed/                 Redis-based distributed infrastructure
├── events/                      Kernel ↔ gateway event bridge
├── gateway/                     FastAPI HTTP/WS/SSE server
│   └── routers/                 API route handlers (chat, governance, interrupts)
├── ipc/                         TCP+msgpack protocol & transport
├── llm/                         LLM provider abstraction
│   └── providers/               LiteLLM, OpenAI HTTP, Mock providers
├── logging/                     Structlog infrastructure
├── memory/                      CommBus message handling
│   └── messages/                Message type definitions
├── middleware/                   Rate limiting middleware
├── observability/               Metrics (Prometheus) & tracing (OTEL/Jaeger)
├── orchestrator/                Event orchestration, governance, flow
├── protocols/                   Type definitions & interfaces (75 types)
├── redis/                       Redis client & connection management
├── runtime/                     Agent execution, persistence
├── tools/                       Tool catalog & executor framework
└── utils/                       Logging utilities, JSON repair, testing helpers
```

### 3.3 Largest Files (complexity indicators)

| File | LOC | Purpose |
|------|-----|---------|
| `protocols/capability.py` | 897 | Capability registration system |
| `kernel_client.py` | 823 | IPC bridge to Rust kernel |
| `protocols/types.py` | 812 | Core domain types & enums |
| `gateway/routers/chat.py` | 605 | Chat API endpoints |
| `runtime/agents.py` | 599 | Agent execution runtime |
| `orchestrator/event_context.py` | 534 | Event context management |
| `memory/tool_health_service.py` | 533 | Tool health monitoring |
| `pipeline_worker.py` | 519 | Pipeline execution worker |
| `protocols/interfaces.py` | 482 | Protocol interfaces (22 protocols) |

---

## 4. Type System & Domain Model

### 4.1 Protocol Architecture (75 public types)

| Category | Count | Examples |
|----------|-------|---------|
| **Enums** | 17 | TerminalReason, InterruptKind, RiskLevel, ToolCategory, HealthStatus |
| **Dataclasses** | 31 | Envelope (41 fields), AgentConfig, PipelineConfig, FlowInterrupt |
| **Protocols** | 22 | LoggerProtocol, DatabaseClientProtocol, LLMProviderProtocol, ToolProtocol |
| **Other Classes** | 5 | CapabilityResourceRegistry, CapabilityToolCatalog, ToolCatalogEntry |

### 4.2 Core Entity: Envelope

The `Envelope` is the master state container flowing through the pipeline:
- **Identity:** envelope_id, request_id, user_id, session_id
- **Execution State:** current_stage, stage_order, iteration, terminated, terminal_reason
- **Resource Tracking:** llm_call_count, agent_hop_count, loop feedback
- **Output Storage:** outputs (Dict[stage_name → Dict[field_name → value]])
- **Interrupts:** interrupt (FlowInterrupt), interrupt_pending
- **Goals:** all_goals, remaining_goals, goal_completion_status
- **Limits:** max_iterations (3), max_llm_calls (10), max_agent_hops (21)

### 4.3 Key Design Patterns

1. **Structural Typing (Protocols):** 22 Protocol interfaces enable duck typing with type safety — no inheritance required
2. **Frozen Context:** `RequestContext` is immutable (frozen dataclass) for async safety
3. **Capability Isolation:** Each capability owns its `CapabilityToolCatalog` — no global tool state
4. **Envelope Pattern:** Single mutable container flows through immutable pipeline stages
5. **Resource Guards:** llm_call_count, agent_hop_count, iteration counters prevent runaway execution

---

## 5. Core Capabilities Assessment

### 5.1 What This System Does

| Capability | Implementation | Status |
|------------|---------------|--------|
| **LLM Inference** | Multi-provider (LiteLLM, OpenAI HTTP, Mock) with streaming | Functional |
| **HTTP Gateway** | FastAPI REST/SSE/WebSocket server | Functional |
| **Pipeline Execution** | DAG-based agent orchestration with interrupts | Functional |
| **IPC Transport** | TCP+msgpack to Rust kernel | Functional |
| **Rate Limiting** | Kernel-delegated per-user/endpoint limiting | Functional |
| **Event Bridge** | Kernel → Gateway event streaming via WebSocket | Functional |
| **Database Abstraction** | Protocol-based with factory pattern | Functional |
| **Distributed Processing** | Redis-backed task queue with worker heartbeats | Functional |
| **Observability** | Prometheus metrics + OpenTelemetry/Jaeger tracing | Functional |
| **Health Checks** | K8s liveness/readiness probes | Functional |
| **Feature Flags** | Runtime toggles with in-memory backend | Functional |
| **Capability Registration** | Zero-coupling plugin system (10 registration types) | Functional |

### 5.2 External Integrations

| System | Protocol | Purpose |
|--------|----------|---------|
| **jeeves-core (Rust)** | TCP+msgpack | Kernel IPC — routing, state, rate limiting |
| **LLM Providers** | HTTP/REST | OpenAI, Anthropic, Azure, LiteLLM, llama.cpp |
| **Redis** | redis:// | Distributed state, task queues |
| **PostgreSQL** | Protocol-based | Primary database (via capability layer) |
| **Jaeger** | gRPC (OTLP) | Distributed tracing |
| **Prometheus** | HTTP /metrics | Metrics collection |

### 5.3 API Surface

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Liveness probe |
| `/ready` | GET | Readiness probe |
| `/api/v1/chat/*` | Various | Chat API (submit, stream, history) |
| `/api/v1/governance/*` | Various | Governance API (approvals, policies) |
| `/api/v1/interrupts/*` | Various | Interrupt management (create, resolve) |
| `/ws` | WebSocket | Real-time event streaming |
| `/metrics` | GET | Prometheus metrics |
| `/docs` | GET | OpenAPI documentation |

---

## 6. Technology Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| **Language** | Python | 3.11+ |
| **Package Manager** | uv | Latest |
| **Build System** | Hatchling | PEP 517 |
| **Web Framework** | FastAPI | 0.128.8 |
| **ASGI Server** | Uvicorn | 0.27+ |
| **Data Validation** | Pydantic | 2.x |
| **HTTP Client** | httpx | 0.28.1 |
| **IPC Serialization** | msgpack | 1.0+ |
| **LLM Abstraction** | LiteLLM | 1.0+ |
| **Async Runtime** | asyncio | stdlib |
| **WebSockets** | websockets | 12.0+ |
| **SSE** | sse-starlette | 1.6+ |
| **Structured Logging** | structlog | 23.0+ |
| **Configuration** | pydantic-settings | 2.0+ |
| **Metrics** | prometheus-client | (via OTEL) |
| **Tracing** | OpenTelemetry | (OTLP/Jaeger) |
| **Testing** | pytest + pytest-asyncio | 7.x + 0.21+ |
| **Formatting** | Black | 100-char line |
| **Linting** | Ruff | E, F, I, UP rules |
| **Type Checking** | mypy | 1.0+ |

---

## 7. Testing Assessment

### 7.1 Test Suite Summary

| Metric | Value |
|--------|-------|
| **Total Tests** | 167 |
| **Pass Rate** | 100% (167/167) |
| **Execution Time** | ~1.1s |
| **Framework** | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| **Async Mode** | auto |
| **Test Database** | In-memory SQLite |

### 7.2 Test Distribution

| Test File | Tests | Coverage Area |
|-----------|-------|--------------|
| `test_event_bridge.py` | 17 | Event bridge kernel↔gateway |
| `unit/distributed/test_redis_bus.py` | 24 | Redis distributed bus |
| `unit/test_kernel_client.py` | 31 | IPC client to Rust kernel |
| `unit/test_persistence.py` | 9 | Database persistence layer |
| `unit/test_pipeline_worker.py` | 8 | Pipeline execution worker |
| `unit/test_protocols.py` | 34 | Protocol types and enums |
| `unit/test_thresholds.py` | 6 | Configuration thresholds |
| `unit/test_tool_executor.py` | 22 | Tool execution framework |
| `unit/test_utils.py` | 16 | Utility functions |

### 7.3 Test Quality Assessment

**Strengths:**
- All tests pass with zero failures
- Good coverage of core infrastructure (kernel client, protocols, tools)
- Proper async test support with `asyncio_mode = "auto"`
- Well-organized fixture system with mocks for kernel, LLM, and database
- In-memory SQLite for fast, isolated database tests
- Custom markers for unit/integration/slow test categorization

**Gaps & Concerns:**
- **No integration tests present** — only unit tests exist in the current suite
- **No gateway/API endpoint tests** — the FastAPI app, routers (chat, governance, interrupts) lack tests
- **No WebSocket tests** — the `/ws` endpoint is untested
- **No LLM provider tests** — LiteLLM, OpenAI HTTP providers lack dedicated tests
- **No middleware tests** — rate limiting middleware is untested
- **No observability tests** — metrics and tracing are untested
- **No settings/config validation tests** — Pydantic validators are untested
- **No CI/CD pipeline** — no `.github/workflows/` or any CI configuration
- **No coverage reporting** — no coverage thresholds or reports configured
- **Test-to-code ratio:** 6,560 / 18,962 = 34.6% (test LOC / source LOC)

---

## 8. Security Assessment

### 8.1 Findings

| ID | Severity | Finding | Location |
|----|----------|---------|----------|
| **S1** | **CRITICAL** | Hardcoded default WebSocket auth token (`"local-dev-token"`) with auth disabled | `settings.py:139-140` |
| **S2** | **HIGH** | CORS allows all origins (`"*"`) with `allow_credentials=True` | `gateway/app.py:63,215-221` |
| **S3** | **HIGH** | No HTTP authentication on any API endpoint — `user_id` from query param | `gateway/routers/chat.py:343` |
| **S4** | **HIGH** | WebSocket `accept()` called before any token validation | `gateway/app.py:360-369` |
| **S5** | **MEDIUM** | Raw exception messages exposed to HTTP clients via `detail=str(e)` | `gateway/routers/chat.py:384,489,525`, `governance.py:116,190,214` |
| **S6** | **MEDIUM** | Rate limiting middleware exists but is NOT wired into the gateway | `middleware/rate_limit.py` (unused), `gateway/app.py` (not referenced) |
| **S7** | **MEDIUM** | No request body size limit at framework level | `gateway/app.py` |
| **S8** | **MEDIUM** | WebSocket has no per-message rate limiting (unbounded `while True` loop) | `gateway/app.py:379-408` |
| **S9** | **MEDIUM** | No WebSocket Origin header validation during upgrade | `gateway/app.py:360` |
| **S10** | **MEDIUM** | f-string table name interpolation in SQL query | `orchestrator/governance_service.py:274` |
| **S11** | **MEDIUM** | Redis URL potentially logged with credentials | `redis/client.py:63` |
| **S12** | **MEDIUM** | Dependencies use only lower version bounds (`>=`) — no upper bounds | `pyproject.toml` |
| **S13** | **LOW** | Dynamic `__import__` from `JEEVES_CAPABILITIES` env var without validation | `capability_wiring.py:111` |
| **S14** | **LOW** | No secrets file patterns (`.pem`, `.key`, `.cert`) in `.gitignore` | `.gitignore` |
| **S15** | **LOW** | No schema validation on deserialized IPC msgpack payloads | `ipc/protocol.py:71` |

### 8.2 Positive Security Findings

- No hardcoded API keys, tokens, or passwords in source code
- No `.env` or key files ever committed to git history
- No usage of `pickle`, `eval()`, `exec()`, `yaml.load`, or `os.system`
- Parameterized SQL queries (`?` placeholders) used consistently in repositories
- Pydantic models enforce input validation on API endpoints (min/max length, range bounds)
- IPC frame size limit enforced (50MB max) in transport layer
- WebSocketEventManager has idle timeout and heartbeat mechanisms
- Tool executor validates parameters against schemas before execution
- Settings loaded from environment via pydantic-settings (not hardcoded)
- Interrupt endpoints verify user ownership before allowing access

### 8.3 Security Architecture

- **Authentication:** Not implemented at the infrastructure level — `user_id` is a trusted query parameter with no identity verification
- **Authorization:** Tool access controls via `ToolAccess` enum (NONE/READ/WRITE/ALL) and `AgentToolAccessProtocol`; interrupt endpoints verify user ownership
- **Rate Limiting:** `RateLimitMiddleware` exists and delegates to Rust kernel, but is **not wired** into the FastAPI middleware stack
- **Input Validation:** Pydantic models for API inputs (message max 10,000 chars, user_id max 255 chars); tool parameter schema validation
- **Secrets Management:** Environment variables via pydantic-settings (`.env` file support); no secrets in code
- **Transport Security:** No TLS configuration for IPC (TCP+msgpack) — assumes trusted network
- **CORS:** Configurable via `CORS_ORIGINS` env var, but defaults to wildcard `*` with credentials enabled
- **Serialization:** Safe formats only (JSON, msgpack) — no pickle/eval/yaml.load

### 8.4 Recommendations (Priority Order)

1. **Wire rate limiting middleware** — `RateLimitMiddleware` exists but is not added to the FastAPI app
2. **Add HTTP authentication middleware** — implement JWT/API key validation; derive `user_id` from token, not query param
3. **Fix CORS defaults** — change from `"*"` to explicit origins; remove `allow_credentials=True` unless needed
4. **Fix WebSocket auth** — validate token BEFORE `accept()`; enable `websocket_auth_required` by default; remove hardcoded dev token
5. **Sanitize error responses** — return generic messages to clients; log full exceptions server-side only
6. **Add request size limits** — configure uvicorn `--limit-max-request-line` or add ASGI middleware
7. **Add WebSocket protections** — per-message rate limiting, Origin header validation, max message size
8. **Sanitize logged URLs** — strip credentials from Redis URLs before logging
9. **Validate dynamic imports** — allowlist module paths in `capability_wiring.py`
10. **Add dependency upper bounds** — pin versions to prevent unvetted major upgrades; run `pip-audit` regularly
11. **Add TLS for IPC** — consider TLS for TCP+msgpack transport in production
12. **Add secrets file patterns to .gitignore** — `.pem`, `.key`, `.cert`, `credentials.json`

---

## 9. Infrastructure & DevOps

### 9.1 What Exists

- **Package management:** `uv` with `pyproject.toml` (Hatchling build backend)
- **Lock file:** `uv.lock` (538 KB, 74 packages pinned)
- **Code quality:** Black, Ruff, mypy configured in `pyproject.toml`
- **Test framework:** pytest with markers and fixtures
- **K8s readiness:** Health/readiness probes built-in

### 9.2 What's Missing

| Category | Status | Notes |
|----------|--------|-------|
| **CI/CD** | Missing | No `.github/workflows/`, no CI config of any kind |
| **Dockerfile** | Missing | No containerization defined |
| **docker-compose** | Missing | No local development orchestration |
| **Makefile** | Missing | No task runner |
| **Coverage config** | Missing | No coverage thresholds |
| **Pre-commit hooks** | Missing | No `.pre-commit-config.yaml` |
| **CHANGELOG** | Missing | No change tracking |
| **Contribution guide** | Missing | No CONTRIBUTING.md |
| **Release process** | Missing | No tags, no versioning strategy |

---

## 10. Code Quality Assessment

### 10.1 Architecture Quality: HIGH

- **CONSTITUTION.md** provides clear ownership boundaries and acceptance criteria
- **Protocol-driven design** with 22 interfaces enables clean dependency injection
- **Clean layer separation** — infra never imports capabilities
- **Composition root pattern** (bootstrap.py) eliminates global state
- **Single responsibility** — each module has a focused purpose

### 10.2 Code Health Indicators

| Indicator | Status | Notes |
|-----------|--------|-------|
| Circular imports | None found | Clean dependency graph |
| Dead code | Minimal | Aggressive cleanup in Feb 9-12 refactors |
| Type safety | Good | mypy configured, Protocol-based typing |
| Error handling | Good | Structured errors, no silent failures (post-Feb 11 refactor) |
| Logging | Excellent | structlog throughout with context binding |
| Documentation | Adequate | Docstrings on public APIs, CONSTITUTION.md as architectural guide |
| Naming conventions | Consistent | snake_case throughout, clear module names |

### 10.3 Technical Debt

| Item | Impact | Effort |
|------|--------|--------|
| No CI/CD pipeline | High — no automated quality gates | Medium |
| No integration tests | High — API layer untested | High |
| CORS wildcard default | Medium — security risk in production | Low |
| WebSocket auth disabled | Medium — open WebSocket in production | Low |
| No Dockerfile | Medium — manual deployment | Low |
| Global `_settings` singleton | Low — partially mitigated by bootstrap pattern | Low |
| Module-level `config = GatewayConfig()` in app.py | Low — eager initialization at import time | Low |

---

## 11. Dependency Health

### 11.1 Core Dependencies (Minimal, Well-Chosen)

| Package | Version | Risk | Notes |
|---------|---------|------|-------|
| msgpack | >=1.0.0 | Low | Mature, stable IPC serialization |
| httpx | >=0.25.0 | Low | Modern async HTTP client |
| pydantic | >=2.0.0 | Low | Industry standard validation |
| pydantic-settings | >=2.0.0 | Low | Config management |
| structlog | >=23.0.0 | Low | Structured logging standard |

### 11.2 Optional Dependencies

| Group | Key Packages | Risk |
|-------|-------------|------|
| **gateway** | FastAPI 0.109+, Uvicorn 0.27+, websockets 12+ | Low |
| **redis** | redis 5.0+ | Low |
| **llm** | litellm 1.0+, tiktoken 0.5+ | Medium — litellm has fast release cycles |
| **dev** | pytest 7+, black 23+, ruff 0.1+, mypy 1.0+ | Low |

### 11.3 Supply Chain

- **74 total packages** in lock file — reasonable for the feature set
- **No known CVEs** identified in pinned versions (manual check recommended)
- **uv lock file** provides deterministic builds
- No dependency scanning (Dependabot, Snyk, etc.) configured

---

## 12. Capability Registration System

The capability registration system enables zero-coupling between infrastructure and domain logic:

| Registration Type | Purpose |
|-------------------|---------|
| **Schemas** | Database DDL files |
| **Modes** | Gateway request handling modes |
| **Services** | Control Tower service definitions |
| **Agents** | Agent definitions for governance |
| **Prompts** | LLM prompt templates with factory functions |
| **Tools** | Tool catalogs (capability-scoped) |
| **Orchestrators** | Service factory functions |
| **Contracts** | Tool result schemas & validators |
| **API Routers** | FastAPI routers with dependency injection |
| **Memory Layers** | Multi-layer memory definitions |

This is a well-designed plugin architecture that keeps the infrastructure layer capability-agnostic.

---

## 13. Branch & PR History

| PR | Title | Status |
|----|-------|--------|
| #1 | Fix missing adapters and k8s subpackages in wheel | Merged |
| #2 | feat: Replace airframe with jeeves-infra infrastructure layer | Merged |
| #3 | Claude audit: Python coverage | Merged (audit deleted after) |

**Current branches:**
- `master` — main development branch
- `main` (remote) — remote default
- `claude/repo-audit-assessment-5yAzu` — this audit branch

**Tags:** None — no versioning/release process established.

---

## 14. Summary of Strengths

1. **Clean architecture** with clear constitutional boundaries and ownership rules
2. **Aggressive simplification** — 20,000+ lines removed through debloating over 30 days
3. **Protocol-driven design** — 22 protocols enable proper dependency injection
4. **Modern stack** — Python 3.11+, FastAPI, Pydantic 2, asyncio, structlog
5. **100% test pass rate** — all 167 tests pass in ~1 second
6. **IPC modernization** — migrated from gRPC/protobuf to simpler TCP+msgpack
7. **Capability isolation** — infrastructure never imports domain logic
8. **Comprehensive observability** — Prometheus metrics + OpenTelemetry tracing built-in
9. **K8s-ready** — health probes, graceful shutdown, environment-based config

---

## 15. Summary of Risks & Recommendations

### Critical (Address Before Production)
1. **Wire rate limiting middleware** — `RateLimitMiddleware` exists but is not added to the gateway
2. **Add HTTP authentication middleware** — endpoints accept arbitrary `user_id` from query params
3. **Fix CORS default** — wildcard `*` with `allow_credentials=True` is unsafe
4. **Fix WebSocket security** — auth before `accept()`, remove hardcoded dev token, validate Origin
5. **Add CI/CD pipeline** — no automated tests, linting, or type checking on push

### High Priority
6. **Sanitize error responses** — raw exception messages leak internal details to clients
7. **Add integration tests** — gateway, routers, WebSocket endpoints are untested
8. **Add Dockerfile** — no containerization for deployment
9. **Add coverage thresholds** — establish and enforce minimum coverage
10. **Add dependency scanning** — no Dependabot/Snyk/safety checks; run `pip-audit`

### Medium Priority
11. **Add request body size limits** — no max body size on API endpoints
12. **Add WebSocket protections** — per-message rate limiting, max message size
13. **Add pre-commit hooks** — automate Black/Ruff/mypy on commit
14. **Pin dependency upper bounds** — only lower bounds (`>=`) currently specified
15. **Sanitize logged URLs** — Redis URLs may contain credentials
16. **Establish release process** — no tags, no CHANGELOG, no versioning strategy
17. **Add IPC transport security** — TCP+msgpack has no TLS

### Low Priority
18. **Validate dynamic imports** — allowlist module paths in `capability_wiring.py`
19. **Add secrets file patterns to .gitignore** — `.pem`, `.key`, `.cert`
20. **Add CONTRIBUTING.md** — development workflow documentation
21. **Consider removing global settings singleton** — prefer full DI via AppContext
