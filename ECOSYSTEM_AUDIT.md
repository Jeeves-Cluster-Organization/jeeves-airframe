# Jeeves Ecosystem: Augmented Assessment & Comparative Analysis

**Date:** 2026-02-23
**Scope:** Cross-repo ecosystem audit (jeeves-core + jeeves-airframe) with OSS comparative benchmarking
**Inputs:** Individual audits of jeeves-core (Rust) and jeeves-airframe (Python), OSS landscape research

---

## Part I: Augmented Ecosystem Assessment

### 1. Combined System Profile

| Metric | jeeves-core (Rust) | jeeves-airframe (Python) | Combined |
|--------|-------------------|-------------------------|----------|
| **Source LOC** | 7,700 | 18,962 | **26,662** |
| **Source Files** | 31 | 89 | **120** |
| **Tests** | 96 | 167 | **263** |
| **Coverage** | 81.36% | 31.1% | **~45%** (weighted) |
| **Dependencies** | 31 direct / 317 total | 5 core / 74 total | Separate supply chains |
| **Contributors** | 3 | 3 | **3** (same people) |
| **Total Commits** | 94 | 52 | **146** |
| **Age** | 19 days | 30 days | **30 days** |
| **CI/CD** | None | None | **None** |
| **Docker** | None | None | **None** |

The combined system is **~27,000 LOC** across two languages serving a complex multi-agent orchestration domain. This is remarkably lean for the feature set.

---

### 2. Systemic Findings (Cross-Repo)

#### 2.1 CRITICAL: Zero CI/CD Across the Entire Stack

Neither repository has `.github/workflows/`, Dockerfile, docker-compose, Makefile, or CI configuration of any kind. The combined system has 263 tests and **zero automated gates**. A developer can merge breaking changes to the IPC protocol in jeeves-core without any automated verification that jeeves-airframe still functions.

**Severity:** CRITICAL — The IPC boundary between Rust and Python (the single most important integration point) has zero automated validation.

#### 2.2 CRITICAL: No Shared Schema or Contract Definition

The wire protocol is defined twice, independently:
- **jeeves-core** defines 26 RPC methods, message types, and field names in Rust structs
- **jeeves-airframe** defines its understanding in Python dataclasses (`kernel_client.py`) and dict-deserialization helpers

There is no shared `.proto`, OpenAPI spec, JSON Schema, or machine-readable contract. The protocols/types.py explicitly states: `"No proto dependency — code is the contract."`

**Impact:** Contract drift is a certainty over time. Each side can independently change field names, add required fields, or alter semantics without the other side knowing.

#### 2.3 HIGH: Authentication Bypass Chains Across the Full Stack

The authentication gap is **worse in combination** than either audit reveals alone:

```
Internet → [Gateway: user_id from query param, no auth]
         → [IPC: user_id passed to kernel, trusted blindly]
         → [Kernel: rate limits by user_id — attacker-controlled]
         → [LLM: tokens consumed at attacker's will]
```

The rate limiting system — which exists across both repos with real implementation effort (Rust sliding-window enforcement + Python middleware) — is entirely bypassable because identity is never verified. And the rate limit middleware itself is **not even wired** into the gateway.

#### 2.4 HIGH: Observability is Declared but Hollow on Both Sides

| Repo | Tracing | Metrics | Correlation |
|------|---------|---------|-------------|
| **jeeves-core** | `init_tracing()` is an empty stub | `init_metrics()` is an empty stub | None |
| **jeeves-airframe** | Implemented but silently no-ops if OTLP package is missing | 14 Prometheus metrics defined | No Jaeger/Prometheus infrastructure |

**Impact:** In production, you would have partial Python-side metrics with no way to correlate them with Rust kernel internals. Distributed tracing across the IPC boundary is impossible. The system cannot be debugged in production.

#### 2.5 MEDIUM: Identical Development Velocity Pattern (Sprint-Then-Stall)

Both repos show intense burst activity with no subsequent maintenance cadence:
- jeeves-core: 94 commits in 19 days, then silence
- jeeves-airframe: 52 commits in 30 days, then silence
- Both underwent major architectural rewrites mid-stream

This pattern suggests a small team (1-2 people with AI assistance) building in rapid sprints. The architecture is stabilizing but has not been battle-tested under sustained development or production load.

#### 2.6 MEDIUM: No Deployment Story Whatsoever

Zero Dockerfiles, zero Helm charts, zero Terraform, zero docker-compose, zero systemd units across both repos. The system requires **two separate processes** (Rust binary + Python ASGI server) communicating over TCP, but there is no automation for starting either.

---

### 3. IPC Contract Analysis

#### 3.1 Wire Protocol Alignment: Tight

| Aspect | Core (Rust) | Airframe (Python) | Match? |
|--------|------------|-------------------|--------|
| Framing | 4-byte BE length + 1-byte type + msgpack | Same | YES |
| Message types | 0x01–0x04, 0xFF | Same | YES |
| Max frame | 50MB | 50MB | YES |
| Serialization | msgpack `use_bin_type=true` | Same | YES |
| Request envelope | `{id, service, method, body}` | Same | YES |

#### 3.2 Method Coverage

The Python client calls **21 of 26** RPC methods. The 5 server-only methods are acceptable if called by other clients or are internal.

| Service | Methods Called | Total Available |
|---------|--------------|----------------|
| `kernel` | 14 | ~12+ |
| `engine` | 2 | ~6 |
| `orchestration` | 4 | ~4 |
| `commbus` | 1 (Subscribe streaming) | ~4 |

#### 3.3 Schema Fragility at the Boundary

The Python client uses defensive `.get()` with defaults throughout (e.g., `d.get("state", "UNKNOWN")`). This is resilient against missing fields but **masks contract violations silently**. A field that the Rust side renamed would not produce an error; it would produce a silent default value.

#### 3.4 JSON-inside-msgpack Double-Encoding

At `kernel_client.py:538-539`, the `initialize_orchestration_session` method serializes dicts to JSON strings, then sends those strings inside msgpack. On the receive side, it must detect whether the received value is a string or a dict and parse accordingly. This double-encoding is fragile, creates unnecessary overhead, and is a contract smell.

#### 3.5 Enum Value Relic

The `InterruptKind` enum comment says "mirrors Go InterruptKind" — a vestigial reference to the Go→Rust rewrite. These enum values may not have been re-verified against the current Rust implementation.

---

### 4. Combined Coverage Gap Analysis

#### 4.1 The Inverted Risk Pyramid

| Layer | Coverage | Exposure | Risk |
|-------|----------|----------|------|
| Rust kernel internals | 81% | Internal only (behind IPC) | Low |
| Python IPC client | 57% | Internal (mocked transport) | Medium |
| Python protocol types | 77-88% | Internal | Low |
| **IPC boundary (real TCP+msgpack)** | **0%** | **Critical integration point** | **CRITICAL** |
| **Python gateway (HTTP/WS)** | **0%** | **Only externally-facing surface** | **CRITICAL** |
| Python LLM providers | 0% | External API calls | HIGH |
| Python orchestrator | 0% | Core business logic | HIGH |
| Python bootstrap/context | 0% | System initialization | HIGH |

The most-tested component (Rust kernel, 81%) is the least-exposed. The least-tested component (Python gateway, 0%) is the most-exposed. This is an **inverted risk pyramid**.

#### 4.2 The Untested IPC Chasm

Neither side tests actual TCP+msgpack serialization/deserialization against the other. The Rust kernel tests with mock connections. The Python client tests with `MagicMock(spec=IpcTransport)`. This means:
- A field name change in Rust would not be caught
- An enum value mismatch would silently produce wrong behavior
- The JSON-inside-msgpack double-encoding has never been validated end-to-end

---

### 5. Combined Security Posture

#### 5.1 End-to-End Attack Surface

```
Internet
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│  FastAPI Gateway                                          │
│  ● NO HTTP authentication (user_id from query param)      │
│  ● CORS: * with allow_credentials=True                    │
│  ● WebSocket accept() before auth validation              │
│  ● Hardcoded "local-dev-token" with auth disabled         │
│  ● Raw exception messages in HTTP responses               │
│  ● Rate limiting middleware EXISTS but NOT WIRED           │
│  ● No request body size limit                             │
│  ● No WebSocket per-message rate limiting                 │
└──────────────┬───────────────────────────────────────────┘
               │ TCP+msgpack (plaintext)
               ▼
┌──────────────────────────────────────────────────────────┐
│  Rust Kernel                                              │
│  ● No IPC authentication                                  │
│  ● No TLS on TCP transport                                │
│  ● Unbounded TCP connections (max_connections not enforced)│
│  ● No I/O timeouts (Slowloris-style DoS)                  │
│  ● Integer overflow in quota parsing (i64→i32 cast)       │
│  ● Negative usage values accepted                         │
│  ● Unbounded HashMap growth (OOM over time)               │
└──────────────────────────────────────────────────────────┘
```

#### 5.2 Defense-in-Depth: Absent

| Defense Layer | Status |
|--------------|--------|
| Network TLS (external) | Not configured |
| HTTP Authentication | Not implemented |
| API Authorization | user_id from query param (spoofable) |
| Rate Limiting | Implemented but NOT wired |
| IPC Authentication | Not implemented |
| IPC TLS (internal) | Not implemented |
| Input validation (API) | Partial (Pydantic min/max) |
| Input validation (IPC) | None (raw msgpack.unpackb) |
| Output sanitization | Raw `str(e)` in HTTP responses |

#### 5.3 Positive Security Properties

Despite the gaps, several design decisions are commendable:
- Zero `unsafe` in Rust kernel, zero `unwrap`/`panic` in production
- No `pickle`, `eval`, `exec`, `yaml.load`, or `os.system` in Python
- Parameterized SQL throughout
- Frozen `RequestContext` dataclass for async safety
- IPC frame size limit enforced (50MB)
- Pydantic validation on all API inputs
- Environment-based secrets management (no hardcoded API keys in source)
- Safe serialization formats only (msgpack, JSON)
- Panic isolation via `with_recovery()` wrapper
- Resource quota enforcement at kernel level

---

### 6. Architectural Coherence

#### 6.1 Three-Layer Design: Well-Conceived, Under-Integrated

```
Capability Layer  →  jeeves_infra (Airframe)  →  jeeves-core (Kernel)
```

Layer boundaries are enforced by code:
- Airframe never imports capabilities (verified by CONSTITUTION.md)
- Capabilities register via the 10-type plugin system
- Kernel is accessed only through `KernelClient`, not direct TCP

#### 6.2 Composition Root: Genuinely Good

`bootstrap.py` implements a proper composition root. All concrete implementations wired in one place. `AppContext` dataclass carries all dependencies. Textbook DI without a framework.

#### 6.3 Tension: Dual Orchestration

Both layers have orchestration concepts:
- **Rust kernel**: OrchestrationService with sessions, instructions, agent results (pull-based)
- **Python airframe**: `pipeline_worker.py` (519 LOC), `orchestrator/` (285 stmts), `runtime/agents.py` (599 LOC)

Where does orchestration actually live? Both places, incompletely. This dual-brain pattern is a coherence risk — bugs can emerge from disagreements about who is in control.

#### 6.4 Bug: Quota Sync Copy-Paste Error

At `bootstrap.py:326`, the `sync_quota_defaults_to_kernel` function passes `max_iterations=cfg.context_bounds.max_input_tokens` — a copy-paste error where `max_iterations` receives the value of `max_input_tokens`.

---

### 7. Maturity Alignment

| Dimension | Core (Rust) | Airframe (Python) | Delta |
|-----------|------------|-------------------|-------|
| Code quality | HIGH | HIGH | Aligned |
| Test coverage | 81% | 31% | **SEVERE MISMATCH** |
| Architecture | Clean microkernel | Clean layered | Aligned |
| Security | Basic gaps | Serious gaps | Python is worse |
| Observability | Stubs only | Implemented but unverified | Python is ahead |
| Deployment | Nothing | Nothing | Aligned (both zero) |
| Documentation | Audit docs | Audit + CONSTITUTION.md | Python slightly ahead |
| Stability | 2 language rewrites | 1 rename + 1 IPC migration | Both volatile |

**Overall Ecosystem Maturity: Early Development (2.4/5)**

---

### 8. Risk Amplification (Ecosystem-Level)

Risks that are **worse** when considering both repos together:

| Risk | Mechanism | Severity |
|------|-----------|----------|
| **Silent contract drift** | No shared schema; defensive `.get()` masks violations silently | CRITICAL |
| **Authentication bypass → quota bypass → resource exhaustion** | Untrusted user_id flows from gateway through IPC to kernel rate limiter | CRITICAL |
| **No deployment → no recovery** | Two-process system with zero automation, zero rollback | HIGH |
| **Observability gap → debugging impossibility** | Rust stubs + Python no-ops = zero cross-boundary tracing | HIGH |
| **Inverted test pyramid** | 81% on inner kernel, 0% on outer gateway = exposed surface untested | HIGH |

### 9. Strength Amplification (Ecosystem-Level)

Strengths that are **more impressive** in ecosystem context:

| Strength | Evidence |
|----------|----------|
| **Consistent architectural philosophy** | Protocol/trait-based interfaces in both languages (22 Protocols in Python, trait-based in Rust), composition over inheritance, explicit error handling — suggests genuine architectural discipline |
| **Aggressive simplification** | Combined ~27,000 LOC for a complex domain; both repos trend toward less code (20,000+ lines removed from airframe alone) |
| **Wire protocol simplicity** | Identical TCP+msgpack on both sides, no code generation, no proto compilation — fast iteration for small team |
| **Resource governance architecture** | 13 quota dimensions in Rust + usage tracking after every LLM/tool/agent call in Python + config sync from Python to Rust as single source of truth |
| **Capability registration system** | 10-type zero-coupling plugin architecture keeps infrastructure capability-agnostic |

---

## Part II: Comparative Assessment Against OSS Landscape

### 10. Framework Landscape Overview

| Framework | Language | Stars | Forks | Architecture | Maturity | Key Differentiator |
|-----------|---------|-------|-------|-------------|----------|-------------------|
| **Dify** | Python/TS | **130,000** | 20,300 | Visual workflow / microservices | Production | Low-code/no-code, visual pipeline builder |
| **AutoGen** | Python/.NET | **54,700** | 8,200 | Actor-model multi-agent | Production | Merging with Semantic Kernel; async messaging |
| **CrewAI** | Python | **44,500** | 6,000 | Role-based declarative | Production | Org-chart metaphor, sequential delegation |
| **Semantic Kernel** | C#/Python/Java | **27,300** | 4,500 | Plugin/middleware SDK | Production (1.0 GA) | Enterprise Microsoft ecosystem |
| **LangGraph** | Python | **25,000** | 4,400 | Compiled state graph (DAG) | Production | Cyclic graphs, checkpointing, LangSmith |
| **Haystack** | Python | **24,200** | 2,600 | Directed multigraph | Mature (v2.24) | Pipeline loops/cycles, SuperComponents |
| **Mastra** | TypeScript | **21,300** | — | Declarative, typed | Active (YC-backed) | TypeScript-native, eval primitives |
| **OpenAI Agents SDK** | Python | **~17,000** | — | Minimal primitives | Active | Handoffs, guardrails, built-in tracing |
| **Rig** | Rust | **6,100** | 665 | Trait-based modular SDK | Pre-1.0 (v0.31) | Leading Rust LLM framework, WASM + MCP |
| **Rivet** | TypeScript | **4,500** | 361 | Visual node graph | Active | Visual AI programming environment |
| **Agency Swarm** | Python | **3,900** | 1,000 | Org-chart metaphor | Active | OpenAI Agents SDK extension |
| **BeeAI** | Python/TS | **3,100** | 408 | Agent Communication Protocol | Active (Linux Foundation) | Framework-agnostic agent interop via ACP |
| **Kalosm** | Rust | **2,000** | 114 | Local inference | Pre-1.0 (v0.3) | Structured generation with parser-aware sampling |
| **llm-chain** | Rust | **1,600** | 142 | Chain pipeline | **Stagnant** (last release May 2023) | N/A (superseded by Rig) |
| **Jeeves** | **Rust + Python** | **Private** | — | **Microkernel** | **Early dev** | **Unix process model, kernel-driven orchestration** |

---

### 11. Architectural Paradigm Comparison

| Architecture | Representative | Strengths | Weaknesses |
|-------------|---------------|-----------|------------|
| **Pipeline/Chain** | LangChain, AutoGen | Simple mental model, linear workflows | Rigid; poor for dynamic branching |
| **Graph/State Machine** | LangGraph, Haystack | Explicit control flow, loops/branches, debuggable | More upfront complexity |
| **Role-based Declarative** | CrewAI, Agency Swarm | Intuitive org-chart metaphor | Sequential overhead, less flexible routing |
| **Plugin-based** | Semantic Kernel | Enterprise integration, modular | Heavier abstraction |
| **Minimal Primitives** | OpenAI Agents SDK | Low overhead, transparent | Requires DIY for state, memory, security |
| **Visual Workflow** | Dify | Low-code accessibility | Less programmatic control |
| **Microkernel** | **Jeeves**, Agent-Kernel (academic) | Decoupled core/plugins, independently updatable | Newer, less proven in production |

**Industry trend (2025-2026):** Moving from monolithic/chain architectures toward **graph-based** and **microkernel/plugin** patterns. MCP adoption became table-stakes in Q4 2025.

**Jeeves's position:** The microkernel approach is architecturally forward-looking but currently unproven. The closest comparable is Agent-Kernel (ZJU academic project, arXiv 2512.01610) which explicitly uses OS kernel terminology but is a simulation framework. No production framework currently implements a true Unix process model for agents.

---

### 12. Head-to-Head Feature Comparison

| Capability | LangGraph | CrewAI | AutoGen | Haystack | Semantic Kernel | Dify | **Jeeves** |
|-----------|-----------|--------|--------|----------|----------------|------|-----------|
| **Agent lifecycle** | Stateful graph nodes | Role assignment | Actor creation + messaging | Component pipeline | Plugin registry | Workflow nodes | **Unix process model (New→Ready→Running→Blocked→Terminated→Zombie)** |
| **State management** | Checkpointed state | Short/long-term/entity memory | Session state + distributed | Pipeline context | Thread-based session | PostgreSQL + Redis + vector DB | **Envelope (41 fields) + kernel PCBs + Redis** |
| **Human-in-the-loop** | First-class (inspect/modify state) | `human_input=True` (terminal) | In conversation flow | Not built-in | Planner approval | Workflow annotations | **7 interrupt types with TTL + auto-expire** |
| **Resource limits** | Token counting | Budget limits | Not built-in | Not built-in | Token limits | Rate limiting | **13 quota dimensions + kernel enforcement** |
| **IPC mechanism** | In-process | In-process | Async msg / gRPC (.NET↔Python) | In-process | In-process / MCP | HTTP REST + Celery/Redis | **TCP+msgpack (cross-process, cross-language)** |
| **Pipeline execution** | Compiled cyclic DAG | Sequential/hierarchical | Unbounded conversation loops | Directed multigraph | Planner-driven | Visual workflow | **Kernel-driven pull-based orchestration** |
| **LLM providers** | LangChain ecosystem (dozens) | LiteLLM (dozens) | OpenAI/.NET models | Modular (15+) | OpenAI/Azure/HF | 15+ built-in | **LiteLLM + OpenAI HTTP + Mock (3)** |
| **Streaming** | LangChain callbacks | Events | Async message streams | Pipeline streaming | Streaming chunks | SSE | **SSE + WebSocket event bridge** |
| **Observability** | LangSmith (commercial) | AgentOps | Tracing built-in | Haystack tracing | OTEL | Built-in monitoring | **OTEL + Prometheus (stubs/partial)** |
| **CI/CD** | GitHub Actions | GitHub Actions | GitHub Actions | GitHub Actions | Azure DevOps | GitHub Actions | **None** |
| **Test coverage** | Not published | CLI test runner | Not published | Not published | Extensive suites | Not published | **81% Rust / 31% Python** |
| **MCP support** | Yes | Yes | Yes | Via Hayhooks | Yes | Yes | **No** |
| **Security model** | LangSmith observability | Docker isolation | Docker sandbox + RBAC | N/A | Azure AI content filters | RBAC (4 roles) + SSO + DifySandbox | **Governance service + capability-based access** |
| **Multi-language** | Python only | Python only | Python + .NET | Python only | C#/Python/Java | Python + TypeScript | **Rust + Python** |

---

### 13. Quantitative Benchmarks

#### 13.1 Framework Overhead (from AIMultiple, 100 runs, 5-agent travel planning)

| Framework | Relative Latency | Token Efficiency | Overhead Source |
|-----------|-----------------|------------------|-----------------|
| **LangGraph** | **Lowest** | **Best** | State deltas only (no full history) |
| **OpenAI Swarm** | Low-Medium | Good | Lightweight stateless design |
| **CrewAI** | Medium-High | Moderate | 70% of response time is framework overhead (4-5s handoff vs 2s LLM) |
| **LangChain** | **Highest** | **Worst** | Full conversation history retention |
| **AutoGen** | Variable | Variable | Unbounded conversation loops (50+ rounds) |
| **Jeeves** | **Unknown** | **Unknown** | **No benchmarks exist** |

**Key insight:** Without tool calls, all frameworks converge to 6-8s latency and 650-744 tokens. Divergence comes from **tool invocation patterns and state management**.

#### 13.2 Scaling Limits (from industry reports)

| Framework | Known Limit |
|-----------|------------|
| LangGraph | Breaks at ~10,000 concurrent agents |
| CrewAI | 2-4x latency in multi-agent setups |
| AutoGen | Conversations loop endlessly without task completion |
| **Jeeves** | **Unknown — not benchmarked, but single Mutex is a theoretical bottleneck** |

#### 13.3 Codebase Size Comparison

| Framework | Estimated LOC | Languages |
|-----------|-------------|-----------|
| LangGraph | ~50,000+ | Python |
| CrewAI | ~30,000+ | Python |
| Haystack | ~80,000+ | Python |
| Semantic Kernel | ~200,000+ | C#/Python/Java |
| Dify | ~300,000+ | Python/TypeScript |
| Rig (Rust) | ~15,000 | Rust |
| **Jeeves (combined)** | **~27,000** | **Rust + Python** |

Jeeves is notably lean. At 27,000 LOC it delivers a comparable feature surface to frameworks 2-10x its size, though it lacks the polish, documentation, and ecosystem integration of mature frameworks.

---

### 14. Unique Differentiators: What Jeeves Has That Others Don't

#### 14.1 Unix Process Model for Agents

**No production framework** currently implements a true Unix-like process lifecycle for agents. Jeeves's `New→Ready→Running→Blocked→Terminated→Zombie` state machine with priority scheduling and GC is a genuinely novel approach. The closest analog is Microsoft's conceptual talk ("AI agents are just processes") but no framework has reified this into running code.

**Why it matters:** The process model provides natural primitives for preemption, resource accounting, zombie cleanup, and priority scheduling that other frameworks must reinvent ad hoc.

#### 14.2 Cross-Language Kernel Architecture

All major frameworks are single-language (Python). Jeeves is the only framework placing its orchestration kernel in Rust with a Python infrastructure layer, gaining:
- Memory-safe, zero-unsafe kernel with compile-time guarantees
- Async Rust performance for hot-path scheduling and quota enforcement
- Python flexibility for LLM integration and HTTP serving

**Trade-off:** The IPC boundary adds latency and contract-drift risk that in-process frameworks avoid entirely.

#### 14.3 Kernel-Enforced Resource Quotas (13 Dimensions)

Most frameworks offer basic token counting. Jeeves enforces 13 quota dimensions at the kernel level, making it impossible for the Python layer to bypass limits. This is a defense-in-depth pattern not seen in any OSS competitor.

#### 14.4 Seven Interrupt Types with TTL

Human-in-the-loop in most frameworks is binary (approve/reject). Jeeves offers 7 typed interrupts (Clarification, Confirmation, AgentReview, Checkpoint, ResourceExhausted, Timeout, SystemError) each with its own TTL and auto-expire behavior.

#### 14.5 MessagePack IPC

**No mainstream AI agent framework uses msgpack for IPC.** The industry has converged on JSON-RPC (MCP protocol) and HTTP+JSON (Google A2A). Jeeves's TCP+msgpack is differentiated on serialization performance but trades ecosystem compatibility.

---

### 14.6 Rust-Specific Competitive Landscape

| Framework | Stars | Architecture | MCP | Agent Orchestration | Comparable to Jeeves? |
|-----------|-------|-------------|-----|--------------------|-----------------------|
| **Rig** | 6,100 | Trait-based LLM SDK | Yes | Single-agent + tool calling | LLM SDK only, not a kernel |
| **llm-chain** | 1,600 | Chain pipeline | No | Sequential steps | **Stagnant**; superseded by Rig |
| **Kalosm** | 2,000 | Local inference (Candle) | No | Not built-in | Different niche (on-device) |
| **AutoAgents** (LiquidOS) | ~300 | Ractor actor framework | Yes | Multi-agent + typed pub/sub | **Closest Rust competitor** — but no kernel/user-space separation |
| **ADK-Rust** (Zavora) | New | Modular agent framework | Yes | Sequential/parallel/loop | Comprehensive but no microkernel |
| **rs-graph-llm** | Small | Graph-based (uses Rig) | No | Multi-agent graph workflows | Workflow engine only |

**Key finding:** No Rust framework combines a microkernel with a Python infrastructure layer. AutoAgents (LiquidOS) is the closest competitor with its actor-based model and typed pub/sub, but it lacks the Unix process lifecycle, the cross-language IPC boundary, and the kernel-enforced resource governance that distinguishes Jeeves.

---

### 15. What Jeeves Is Missing vs. The Field

| Capability | Industry Standard | Jeeves Status | Priority |
|-----------|------------------|--------------|----------|
| **CI/CD** | Universal (GitHub Actions) | None | CRITICAL |
| **MCP support** | Table-stakes since Q4 2025 | None | HIGH |
| **Authentication** | JWT/OAuth/API keys | None (user_id from query param) | CRITICAL |
| **Containerization** | Docker + compose standard | None | HIGH |
| **Observability** | OTEL + vendor integration | Stubs / partial | HIGH |
| **Benchmarks** | Common for frameworks >5k stars | None | MEDIUM |
| **Documentation site** | Standard (Docusaurus/MkDocs) | Markdown files only | MEDIUM |
| **Package registry** | PyPI / crates.io | Not published | MEDIUM |
| **Visual debugger** | LangSmith, AgentOps, Haystack tracing | None | LOW |
| **Cloud/managed offering** | LangSmith, Mastra Cloud, Dify Cloud | None (expected — early stage) | LOW |
| **Ecosystem integrations** | Dozens of LLM/vector/DB connectors | 3 LLM providers, Redis, Postgres | LOW |

---

### 16. Communication Protocol Landscape

| Protocol | Used By | Transport | Encoding | AI-Specific? |
|----------|---------|-----------|----------|-------------|
| **MCP** (Model Context Protocol) | LangGraph, CrewAI, Haystack, Mastra, etc. | STDIO (local) / HTTP+SSE (remote) | JSON-RPC 2.0 | Yes — tool/resource exposure |
| **A2A** (Agent-to-Agent, Google) | Emerging standard | HTTP | JSON | Yes — agent interop |
| **ACP** (Agent Communication Protocol, IBM) | BeeAI | Built on MCP | JSON-RPC 2.0 | Yes — agent discovery |
| **Jeeves IPC** | jeeves-core ↔ jeeves-airframe | TCP | msgpack (4-byte length prefix) | Custom |

Jeeves's custom TCP+msgpack protocol is performant but isolated. As MCP and A2A become industry standards, interoperability will require either:
1. An MCP adapter layer in jeeves-airframe
2. An A2A gateway for agent-to-agent communication
3. Accepting isolation as a deliberate trade-off

---

### 17. Maturity Radar: Jeeves vs. Field

```
                    Architecture
                         5
                        ╱│╲
                       ╱ │ ╲
                      ╱  │  ╲
            Security 1───┼───4 Code Quality
                     │╲  │  ╱│
                     │ ╲ │ ╱ │
                     │  ╲│╱  │
            DevOps   1───┼───3 Testing
                         │
                    Observability
                         1

Legend:  ● Jeeves (inner)  ○ Industry median (outer ring = 4)
```

| Dimension | Jeeves | Industry Median | Gap |
|-----------|--------|----------------|-----|
| Architecture | 4/5 | 3/5 | **+1 (ahead)** |
| Code Quality | 4/5 | 3/5 | **+1 (ahead)** |
| Testing | 3/5 | 4/5 | -1 (behind) |
| Security | 2/5 | 3/5 | -1 (behind) |
| DevOps | 1/5 | 4/5 | **-3 (far behind)** |
| Observability | 1/5 | 3/5 | **-2 (behind)** |

Jeeves has **architectural sophistication above the industry median** but is **severely behind on operational infrastructure**. The architecture is production-grade; everything around it is not.

---

## Part III: Recommendations

### 18. Ecosystem-Level Priority Recommendations

#### P0 — Do Before Any Production Use

| # | Recommendation | Rationale |
|---|---------------|-----------|
| 1 | **Add cross-repo integration test** (start Rust kernel + Python client, exercise every RPC over real TCP+msgpack) | Single highest-value test possible; validates the most critical boundary |
| 2 | **Add HTTP authentication middleware** (JWT/API key; derive user_id from token) | Current user_id from query params defeats the entire rate limiting architecture |
| 3 | **Wire rate limiting middleware** in `gateway/app.py` | Code exists, kernel supports it, just not connected |
| 4 | **Fix CORS defaults** (explicit origins, remove `allow_credentials=True`) | Wildcard + credentials is an active vulnerability |
| 5 | **Fix WebSocket security** (auth before accept, remove hardcoded dev token) | WebSocket is an open door |
| 6 | **Create CI pipeline** (both repos: build, test, lint; ideally cross-repo integration) | 263 tests, zero automation |
| 7 | **Enforce IPC connection limits and I/O timeouts** in Rust kernel | DDoS and Slowloris vectors |

#### P1 — High Priority

| # | Recommendation | Rationale |
|---|---------------|-----------|
| 8 | **Fix quota sync bug** at `bootstrap.py:326` (max_iterations gets max_input_tokens) | Silent misconfiguration |
| 9 | **Add integer bounds validation** in Rust quota parsing (i64→i32 cast) | Quota bypass via overflow |
| 10 | **Create docker-compose** (Rust kernel + Python gateway + health check) | Minimum viable deployment artifact |
| 11 | **Sanitize error responses** (generic messages to clients, full exceptions server-side) | Information leakage |
| 12 | **Add gateway integration tests** (916 untested statements in the only externally-facing surface) | Inverted risk pyramid |
| 13 | **Establish shared contract document** for IPC (even a markdown table of service/method/fields) | Prevent silent contract drift |

#### P2 — Medium Priority

| # | Recommendation | Rationale |
|---|---------------|-----------|
| 14 | **Add MCP support** | Industry table-stakes since Q4 2025 |
| 15 | **Implement observability** (wire tracing and metrics on both sides) | Cannot debug production issues |
| 16 | **Add request body size limits** and WebSocket per-message rate limiting | DoS vectors |
| 17 | **Add coverage enforcement** (fail_under thresholds in CI) | Prevent coverage regression |
| 18 | **Add IPC fuzz testing** (cargo-fuzz on msgpack codec) | Find parsing bugs |
| 19 | **Add graceful shutdown** (SIGTERM/SIGINT handler in Rust with connection draining) | Production safety |
| 20 | **Publish to PyPI and crates.io** | Ecosystem accessibility |

#### P3 — Lower Priority

| # | Recommendation | Rationale |
|---|---------------|-----------|
| 21 | **Add TLS for IPC** | Production deployments outside localhost |
| 22 | **Consider RwLock or sharding** for Rust kernel under high concurrency | Mutex bottleneck |
| 23 | **Add performance benchmarks** | Cannot compare against competitors without data |
| 24 | **Add architecture decision records** | Document Python→Go→Rust rationale |
| 25 | **Create documentation site** | Standard for frameworks seeking adoption |

---

### 19. Strategic Assessment

#### Where Jeeves Fits in the Landscape

Jeeves occupies a **unique and defensible niche**: kernel-driven, cross-language agent orchestration with Unix-like process semantics. No other production framework offers this combination.

**Strengths relative to the field:**
- Architectural novelty (microkernel + process model)
- Compile-time safety guarantees from Rust kernel
- 13-dimension resource governance that no competitor matches
- Remarkable code density (~27K LOC vs. 50K-300K for competitors)

**Weaknesses relative to the field:**
- Zero operational infrastructure (CI, Docker, observability)
- No ecosystem integrations (MCP, vector stores, dozens of LLM providers)
- Security hardening not started
- No community, no documentation site, no published packages

#### Competitive Positioning Options

1. **Internal infrastructure tool** — Ship for the Jeeves Cluster Organization's own use. Current state is sufficient for internal development if security and CI are addressed.

2. **Open-source framework** — Competing with LangGraph/CrewAI/Haystack requires: MCP support, documentation site, published packages, CI/CD, Docker, examples, and community building. This is a 3-6 month investment.

3. **Research contribution** — The microkernel + Unix process model is academically novel. A paper or technical blog post could establish thought leadership even without a polished framework.

---

---

### 20. Sources

**Framework Repositories:**
- [LangGraph](https://github.com/langchain-ai/langgraph) — 25K stars, MIT
- [CrewAI](https://github.com/crewAIInc/crewAI) — 44.5K stars, MIT
- [AutoGen](https://github.com/microsoft/autogen) — 54.7K stars, MIT
- [Semantic Kernel](https://github.com/microsoft/semantic-kernel) — 27.3K stars, MIT
- [Dify](https://github.com/langgenius/dify) — 130K stars, Apache 2.0 (modified)
- [Haystack](https://github.com/deepset-ai/haystack) — 24.2K stars, Apache 2.0
- [Rivet](https://github.com/Ironclad/rivet) — 4.5K stars, MIT
- [Mastra](https://github.com/mastra-ai/mastra) — 21.3K stars, Apache 2.0
- [OpenAI Swarm](https://github.com/openai/swarm) — 17K stars (replaced by Agents SDK)
- [Rig](https://github.com/0xPlaygrounds/rig) — 6.1K stars, MIT
- [llm-chain](https://github.com/sobelio/llm-chain) — 1.6K stars, MIT
- [Kalosm/Floneum](https://github.com/floneum/floneum) — 2K stars
- [Agency Swarm](https://github.com/VRSEN/agency-swarm) — 3.9K stars, MIT
- [BeeAI Framework](https://github.com/i-am-bee/beeai-framework) — 3.1K stars
- [Agent-Kernel (ZJU)](https://github.com/ZJU-LLMs/Agent-Kernel) — Academic, [arXiv:2512.01610](https://arxiv.org/abs/2512.01610)
- [AutoAgents (LiquidOS)](https://github.com/liquidos-ai/AutoAgents) — Rust, Ractor-based

**Industry Analysis:**
- [Top Agentic Orchestration Frameworks — AIMultiple](https://aimultiple.com/agentic-orchestration) (benchmark data)
- [AgentRace Benchmark — OpenReview](https://openreview.net/forum?id=eUuxWAQA5F) (framework efficiency)
- [Best AI Agent Frameworks 2026 — The AI Journal](https://theaijournal.co/2026/02/best-ai-agent-frameworks-2026/)
- [Top 10 Most Starred AI Agent Frameworks — Agentailor](https://blog.agentailor.com/posts/top-ai-agent-frameworks-github-2026)
- [State of Rust 2025 — JetBrains](https://blog.jetbrains.com/rust/2026/02/11/state-of-rust-2025/)
- [Rust Ecosystem for AI & LLMs — HackMD](https://hackmd.io/@Hamze/Hy5LiRV1gg)

**Protocol Standards:**
- [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) — JSON-RPC 2.0 over STDIO/HTTP+SSE
- [A2A (Agent-to-Agent, Google)](https://google.github.io/A2A/) — HTTP + JSON
- [ACP (Agent Communication Protocol, IBM)](https://agentcommunicationprotocol.dev/) — Built on MCP

---

*Generated: 2026-02-23 | Combines individual audits of jeeves-core and jeeves-airframe with OSS landscape research*
