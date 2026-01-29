# Jeeves Mission System Constitution

**Updated:** 2026-01-30

---

## Overview

This constitution defines the rules for **mission_system**—the framework layer that provides generic orchestration mechanisms for capabilities.

**Architecture:**
- Re-exports centralized types from `core_engine` via `contracts_core.py`
- Provides generic config mechanisms (`ConfigRegistry`, `AgentProfile`)
- Capabilities OWN domain-specific configs (not mission_system)
- No concrete agent classes - agents defined via `AgentConfig` in capability layer

**Dependency:** This component depends on jeeves_infra and protocols. jeeves_infra delegates to **jeeves-core** (Go kernel) for process management and communication. All principles from the architectural contracts apply.

---

## Purpose

**Mission System responsibilities:**
- Generic orchestration framework (config registry, agent profiles)
- Re-export core types for capabilities (`contracts_core.py`)
- LangGraph orchestration infrastructure
- HTTP API server
- Generic application services

**NOT Mission System responsibilities (moved to capabilities):**
- Domain-specific configs (LanguageConfig, InferenceEndpoints, ToolAccess)
- Concrete agent implementations
- Domain-specific tools

**Mission System uses jeeves_infra:** Depends on jeeves_infra for infrastructure (LLM, database, memory). jeeves_infra delegates to jeeves-core (L0) for process management and CommBus.

---

## Core Principles (Inherited from Dependency Chain)

From the Architectural Contracts:
- **Evidence Chain Integrity** — Every claim traces to source code with `[file:line]` citations
- **Tool Boundary** — Capabilities define their own tools; runtime provides categories
- **Bounded Retry** — Max retries per step with graceful degradation

**All architectural contracts apply to this component.**

---

## Reference Pipeline Architecture

The following describes the **reference 7-agent pipeline** that capabilities can adopt. Capabilities may customize this pipeline or define their own agent configurations.

### Pipeline Definition (REINTENT Architecture)

```
                    ┌────────────────────────────────────────────────────────────────────┐
                    │        STAGE LOOP (goals-driven)                                   │
                    │                                                                    │
Perception → Intent → Planner → Traverser → Synthesizer → Critic ──┬──→ Integration → END
                ↑                                           │       │
                │                                           │       │
                └────────[reintent_transition]──────────────┘       │
                                                                    │
                └──────────[stage_transition]←[NEXT_STAGE]──────────┘
```

**Key Design Decision (REINTENT Architecture):**
- All feedback loops go through Intent agent
- Critic proposes hints (`refine_intent_hint`, `add_goals_hint`, `drop_goals_hint`)
- Intent decides how to use the hints
- No direct REPLAN loop from Critic to Planner

### Agent Responsibilities

| # | Agent | Type | Role | Output |
|---|-------|------|------|--------|
| 1 | **Perception** | Non-LLM | Load session state, normalize input | `PerceptionOutput` |
| 2 | **Intent** | LLM | Classify query, extract goals | `IntentOutput` |
| 3 | **Planner** | LLM | Select tools, create execution plan | `PlanOutput` |
| 4 | **Traverser** | Non-LLM | Execute tools, collect evidence | `ExecutionOutput` |
| 5 | **Synthesizer** | LLM | Aggregate findings, structure analysis | `SynthesizerOutput` |
| 6 | **Critic** | LLM | Validate goal satisfaction, decide next action | `CriticOutput` (verdict: APPROVED/REINTENT/NEXT_STAGE) |
| 7 | **Integration** | Non-LLM | Format response, persist state | `Response` |

### Component Rules

#### R1: Evidence Chain Integrity (P1 Enforcement)

**Every claim must trace to source code:**

```
Tool Execution → ExecutionOutput → SynthesizerOutput → Integration → Response
                      ↓
                [file:line] citations
```

**Rules:**
1. **Traverser** executes tools and captures raw output with citations
2. **Synthesizer** aggregates findings but does NOT add claims without citations
3. **Critic** validates completeness but does NOT generate response content
4. **Integration** builds response from `completed_stages` evidence only

**Violations:**
- Synthesizer inventing code without tool execution
- Critic adding recommendations not grounded in evidence
- Integration hallucinating file contents

**Enforcement:** `tests/contract/test_evidence_chain.py`

#### R2: Tool Boundary (P1 + P3)

**Capabilities define their own tool sets.** The runtime provides:

| Category | Description |
|----------|-------------|
| **Composite** | Multi-step tools with fallback strategies |
| **Resilient** | Wrapped base tools with graceful degradation |
| **Standalone** | Simple, single-operation tools |

**Tool Design Principles:**
- **Composability**: Higher-level tools wrap base operations
- **Transparency**: Return `attempt_history` showing all attempts
- **Bounded**: Respect `max_llm_calls_per_query` limits
- **Graceful degradation**: Partial results on failure

**Capabilities register their tools** via the `ToolRegistryProtocol`.

#### R3: Bounded Retry (P3 Enforcement)

**Traverser retry contract:**

| Failure | Strategy 1 | Strategy 2 | Max Attempts |
|---------|------------|------------|--------------|
| Empty grep | Broaden pattern | Try parent dir | 2 |
| File not found | Fuzzy match | Check index | 2 |
| Timeout | Reduce scope | Skip step | 2 |

**Rules:**
- Max 2 retries per step
- Return `attempt_history` for transparency
- Partial results acceptable with explanation
- No infinite loops

**Example:**
```python
async def execute_tool(tool: str, params: dict) -> ToolResult:
    for attempt in range(3):  # 1 initial + 2 retries
        try:
            return await tool_registry.execute(tool, params)
        except EmptyResultError:
            params = broaden_scope(params)  # Strategy 1
        except FileNotFoundError:
            params = fuzzy_match_path(params)  # Strategy 2

    # Return partial result after exhausting retries
    return ToolResult(status="partial", message="Retries exhausted")
```

#### R4: Composite Tool Determinism

**Composite tools follow:**

1. **Determinism** — Same inputs → same execution sequence
2. **Transparency** — Return `attempt_history` showing all attempts
3. **Bounds** — Stay within `max_llm_calls_per_query`
4. **Graceful degradation** — Partial results on failure

**Example: `locate` tool**
```python
async def locate(query: str, scope: str = None) -> LocateResult:
    attempts = []

    # Strategy 1: Symbol index (fast, exact)
    result = await find_symbol(query, scope)
    attempts.append(("find_symbol", result))
    if result.matches:
        return LocateResult(matches=result.matches, attempts=attempts)

    # Strategy 2: Grep search (medium, pattern)
    result = await grep_search(query, scope)
    attempts.append(("grep_search", result))
    if result.matches:
        return LocateResult(matches=result.matches, attempts=attempts)

    # Strategy 3: Semantic search (slow, fuzzy)
    result = await semantic_search(query, scope)
    attempts.append(("semantic_search", result))
    return LocateResult(matches=result.matches, attempts=attempts)
```

---

## Thresholds and Limits

Default values tuned for small-to-medium LLMs (~20K token context). Capabilities may override these via `ContextBounds`.

| Limit | Default | Purpose | Enforcement |
|-------|---------|---------|-------------|
| `max_tree_depth` | 15 | Prevent runaway recursion | Traverser |
| `max_grep_results` | 50 | Search result volume | Tools |
| `max_file_slice_tokens` | 4000 | Per-file code budget | Tools |
| `max_files_per_query` | 50 | Total file reads per query | Traverser |
| `max_total_code_tokens` | 12000 | Total code in context | Synthesizer |
| `max_retries_per_step` | 2 | Traverser retry limit | Traverser |
| `max_llm_calls_per_query` | 10 | LLM budget per query | Orchestrator |
| `max_stages` | 5 | Multi-stage execution limit | Orchestrator |
| `max_agent_hops` | 21 | Total pipeline iterations | Orchestrator |

**Override:** Via `ContextBounds` in core config.

**Location:** `mission_system/contracts.py`

---

## Orchestration

### LangGraph Pipeline

**Location:** `mission_system/orchestrator/`

**Responsibilities:**
- Define 7-agent graph with routing logic
- Handle critic decisions (REINTENT, NEXT_STAGE, COMPLETE)
- Manage multi-stage execution
- Emit agent events (telemetry)
- Integrate with checkpointing (optional)

**State:** `JeevesState` (LangGraph StateGraph)

**Routing (REINTENT Architecture):**
```python
def route_after_critic(state: JeevesState) -> str:
    """
    REINTENT Architecture - All feedback goes through Intent.

    Returns:
        "complete" - all goals satisfied → integration
        "complete_limit" - max_reintents reached → integration with explanation
        "next_stage" - more goals remain → stage_transition → planner
        "reintent" - needs re-analysis → reintent_transition → intent
    """
    verdict = state["critic"]["verdict"]

    if verdict == "reintent":
        if reintent_count >= bounds.max_reintents:
            return "complete_limit"
        return "reintent"  # → reintent_transition → intent
    elif verdict == "next_stage":
        return "next_stage"  # → stage_transition → planner
    else:  # approved
        return "complete"  # → integration
```

**Transition Nodes:**

| Node | Purpose | Next |
|------|---------|------|
| `reintent_transition` | Package critic hints for Intent, increment counter | → Intent |
| `stage_transition` | Save completed stage, advance counter | → Planner |

### REINTENT Constitutional Invariants

**R8: REINTENT Hint Requirement**

If `verdict == REINTENT`, the Critic **MUST** provide a substantive `refine_intent_hint` (minimum 10 characters).

```python
# INVARIANT: Enforced in reintent_transition_node
if verdict == CriticVerdict.REINTENT:
    assert refine_intent_hint and len(refine_intent_hint.strip()) >= 10, \
        "REINTENT requires substantive refine_intent_hint"
```

**Why?** Intent needs actionable guidance to refine its approach. Empty or vague hints cause infinite loops.

**R9: Single Feedback Edge**

The **only** feedback edge from Critic is to Intent (via `reintent_transition`).

- ❌ No `Critic → Planner` (removed REPLAN)
- ❌ No `Critic → Traverser`
- ✅ Only `Critic → reintent_transition → Intent`

**Why?** Centralizing feedback through Intent ensures consistent goal reassessment and prevents hidden loops.

**R10: Reintent Counter Bound**

Maximum reintents per query: `bounds.max_reintents` (default: 3).

When limit reached, route to `complete_limit` (graceful termination with explanation).

```python
if reintent_count >= bounds.max_reintents:
    return "complete_limit"  # Forces completion with available evidence
```

### Multi-Stage Execution

**Goals-driven pipeline:**
1. Intent extracts multiple goals from query
2. Each stage addresses remaining goals
3. Critic assesses progress after each stage
4. Loop until all goals satisfied OR max stages reached

**Example:**
```
Query: "How does authentication work and where is it configured?"

Stage 1:
  Goal 1: Understand authentication flow
  → Planner, Traverser, Synthesizer, Critic
  → Critic: "Goal 1 satisfied, Goal 2 remains"

Stage 2:
  Goal 2: Find configuration
  → Planner, Traverser, Synthesizer, Critic
  → Critic: "All goals satisfied, COMPLETE"

→ Integration → Response
```

### Clarification Workflow

If query is ambiguous:
1. **Intent** sets `clarification_required = True`
2. **Orchestrator** emits clarification question
3. **User** responds with clarification
4. **Resume** execution from Intent with updated context

**No looping:** One clarification per query maximum.

---

## Verticals Architecture

### Capability Registration

**Bootstrap process** (no import side-effects):

```python
# capability_bootstrap.py
from my_capability.agents.bootstrap import register_capability

# At startup
register_capability()
```

**Registry contract:**
```python
@dataclass
class Capability:
    id: str
    agents: Dict[str, Type[Agent]]
    tools: List[Callable]
    context_builders: Dict[str, Callable]

def register(capability: Capability) -> None: ...
def get_agent_class(capability_id: str, agent_name: str) -> Type[Agent]: ...
```

**Example capabilities:** `code_analysis`, `document_analysis`, `log_analysis`, etc.

### Capability Boundary Rules

**Capabilities may:**
- Implement agents (using core contracts)
- Provide tools (via registry)
- Use jeeves_infra services (LLM, database, memory)
- Define domain-specific configs

**Capabilities must NOT:**
- Import from other capabilities
- Modify core runtime
- Bypass jeeves_infra (which delegates to jeeves-core for backend implementations)

---

## API Layer

**Location:** `mission_system/api/`

**Endpoints:**

### Chat API
- `POST /api/v1/chat/messages` — Send message, trigger pipeline
- `GET /api/v1/chat/sessions` — List user sessions
- `GET /api/v1/chat/sessions/{id}` — Get session details
- `DELETE /api/v1/chat/sessions/{id}` — Delete session

### Governance API
- `GET /api/v1/governance/health` — System health summary
- `GET /api/v1/governance/tools/{tool_name}` — Tool health stats
- `GET /api/v1/governance/dashboard` — Web UI

### Health Checks
- `GET /health` — Liveness (is process alive?)
- `GET /ready` — Readiness (can accept traffic?)

**Protocol:** HTTP/REST with JSON

**Authentication:** (Future) Bearer token via header

---

## Testing Strategy

### Unit Tests

**Location:** `mission_system/tests/unit/`

**Coverage:**
- Individual agents (mock LLM, mock tools)
- Tool implementations (isolated execution)
- Orchestration routing logic
- Evidence chain validation

**Example:**
```python
async def test_synthesizer_preserves_citations():
    """Synthesizer must not add claims without citations."""
    execution_output = ExecutionOutput(
        steps=[ToolResult(file="auth.py", line=10, content="def login()")]
    )

    synthesizer = SynthesizerAgent(llm=mock_llm)
    result = await synthesizer.run(envelope, context)

    # All citations in output must exist in input
    assert all(
        citation in execution_output.citations
        for citation in result.output.citations
    )
```

### Integration Tests

**Location:** `mission_system/tests/integration/`

**Scenarios:**
- Full pipeline execution (with real LLM)
- Multi-stage execution
- Clarification workflow
- Checkpoint recovery

### Contract Tests

**Location:** `mission_system/tests/contract/`

**Validates:**
- Evidence chain integrity
- Import boundary rules
- Memory contracts (L1-L4)
- State conversion (envelope ↔ LangGraph state)

**Example:**
```python
def test_import_boundaries():
    """Core must not import from mission system."""
    core_imports = extract_imports("coreengine/")

    assert not any(
        "mission_system" in imp
        for imp in core_imports
    ), "Core imports from mission system (boundary violation)"
```

---

## Layer Contract

### Inputs

**What this layer imports:**
- `protocols` — Python protocols and type definitions
  - `AgentConfig`, `PipelineConfig`, `RoutingRule`, `ToolAccess`
  - `Agent`, `Runtime`
  - `Envelope`, `ProcessingRecord`
  - All protocols (`LLMProviderProtocol`, `ToolProtocol`, etc.)
  - `ContextBounds`, `WorkingMemory`
- `jeeves_infra` — Infrastructure layer (L1)
  - LLM providers
  - Memory service and repositories
  - Database clients and connection management
  - Settings and configuration
  - Cost tracking and telemetry enrichment
- External libraries — LangGraph, FastAPI, SQLAlchemy, etc.

### Outputs

**What this layer exports:**

1. **contracts_core.py** — Re-exports centralized types for capabilities
   - `AgentConfig`, `PipelineConfig`, `RoutingRule`, `ToolAccess`
   - `Agent`, `Runtime`, `create_pipeline_runner`
   - `Envelope`, `ProcessingRecord`, `create_envelope`
   - All protocols from protocols (LoggerProtocol, ToolExecutorProtocol, etc.)
   - `AgentProfile`, `LLMProfile`, `ThresholdProfile` (generic per-agent config)
   - **NOTE:** `ToolId` and `ToolCatalog` are NOT exported - these are capability-owned

2. **config/** — Generic config mechanisms
   - `ConfigRegistry`, `ConfigKeys` — Config injection pattern
   - `AgentProfile`, `LLMProfile`, `ThresholdProfile` — Generic agent config types
   - Operational constants (timeouts, retry limits, fuzzy match thresholds)

3. **adapters.py** — Wraps jeeves_infra for capabilities
   - Infrastructure access (LLM, memory, database)
   - LLM providers delegate to jeeves-core (L0) for process management

4. **orchestrator/** — LangGraph pipeline infrastructure
   - Pipeline routing and execution
   - Event context and emission

5. **API layer** — HTTP REST endpoints
   - Chat API (messages, sessions)
   - Governance API (health, tools)
   - Health checks (liveness, readiness)

### Type Contract

**Input Types (from core):**
```python
AgentConfig           # Declarative agent definition
PipelineConfig        # Pipeline with ordered agents
Agent          # Single agent class for all types
Envelope       # Dynamic output slots (outputs dict)
Runtime               # Executes pipelines from config
ContextBounds         # Resource limits
```

**Input Types (from jeeves_infra):**
```python
LLMProviderProtocol   # LLM interface
MemoryServiceProtocol # Memory interface
DatabaseClient        # Database interface
Settings              # Configuration
```

**Output Types (via contracts_core.py):**
```python
# Centralized agent types (re-exported from core)
AgentConfig, PipelineConfig, RoutingRule, ToolAccess
Agent, Runtime, create_pipeline_runner
Envelope, ProcessingRecord, create_envelope
TerminalReason, LoopVerdict, RiskApproval

# Generic config types (defined in mission_system)
AgentProfile, LLMProfile, ThresholdProfile
ConfigRegistry, ConfigKeys
```

**REMOVED Types:**
```python
# ❌ No longer exported - use AgentConfig instead
Agent, AgentResult, StateDelta, AgentStage
CoreEnvelope, EnvelopeStage
PerceptionOutput, IntentOutput, PlanOutput, etc.
```

### Enforcement

**Contract tests:**
- `tests/contract/test_import_boundaries.py` — Enforces layer rules
- `tests/contract/test_app_layer_boundaries.py` — Enforces app→mission contract
- `tests/integration/test_app_wiring.py` — Verifies sys.path wiring

**Boundary rules:**
- Apps MUST import from `mission_system.contracts` (not `core_engine`)
- Apps MUST use `mission_system.adapters` (not `jeeves_infra` directly)
- Mission system MAY import from core and jeeves_infra
- Core MUST NOT import from mission system

---

## Config Architecture

### Overview

The config architecture follows clear ownership boundaries:
- **Capability layer OWNS domain-specific configs** (language, tool access, deployment, identity)
- **Mission system provides generic mechanisms** (ConfigRegistry, AgentProfile)
- **Core engine defines protocols only**

### Domain Configs (OWNED by Capabilities)

**Located in each capability's `config/` directory:**

| Module | Content | Purpose |
|--------|---------|---------|
| `domain_config.py` | Domain-specific settings | Domain patterns |
| `tool_access.py` | AgentToolAccess, TOOL_CATEGORIES | Tool access matrix |
| `deployment.py` | InferenceEndpoint, PROFILES | Hardware deployment |
| `modes.py` | AGENT_MODES | Pipeline mode configuration |
| `identity.py` | PRODUCT_NAME, PRODUCT_VERSION | Product identity |

```python
# ✅ CORRECT - Import domain config from capability
from my_capability.config import (
    DomainConfig,
    AgentToolAccess,
    PROFILES,
)

# ❌ INCORRECT - Domain configs do not belong in mission_system
from mission_system.config.domain_config import DomainConfig  # WRONG
```

### Generic Config Mechanisms (Mission System)

**Located in `mission_system/config/`:**

| Module | Content | Purpose |
|--------|---------|---------|
| `registry.py` | ConfigRegistry, ConfigKeys | Generic config injection |
| `agent_profiles.py` | AgentProfile, LLMProfile, ThresholdProfile | Per-agent config types |
| `constants.py` | Operational constants | Timeouts, retry limits |

### AgentProfile (Canonical Per-Agent Config)

```python
from mission_system.config import AgentProfile, LLMProfile, ThresholdProfile

AGENT_PROFILES = {
    "planner": AgentProfile(
        role="planner",
        llm=LLMProfile(temperature=0.3, max_tokens=2500),
        thresholds=ThresholdProfile(clarification_threshold=0.7),
        latency_budget_ms=45000,
    ),
    # ... other agents
}
```

### ConfigRegistry (Injection Mechanism)

```python
from mission_system.config import ConfigRegistry, ConfigKeys

# At capability bootstrap
registry = ConfigRegistry()
registry.register(ConfigKeys.LANGUAGE_CONFIG, language_config)

# Tools access via registry
config = registry.get(ConfigKeys.LANGUAGE_CONFIG)
```

### Constitutional Layering

```
Capability Layer                  ← OWNS domain configs (tool_access, etc.)
         ↓ registers via
MissionRuntime.config_registry    ← Generic injection mechanism
         ↓ implements
ConfigRegistryProtocol            ← Defined in core_engine

Mission System                    ← OWNS generic config types (AgentProfile, etc.)
```

---

## Dependency Management

### Mission System Dependencies

**May import:**
- `protocols` — Runtime contracts and protocols
- `jeeves_infra` — Infrastructure layer (L1)
- External libraries (langgraph, fastapi, etc.)

**Must NOT import:**
- Nothing (top of dependency chain)

**Note:** jeeves_infra depends on `jeeves-core` for process management and CommBus. Mission system accesses these through jeeves_infra providers.

**Example:**
```python
# ALLOWED
from protocols import Envelope
from jeeves_infra.llm import LLMProvider
from jeeves_infra.memory import MemoryService

# All imports are allowed at mission system level
```

---

## Operational Rules

### R5: No Archive Directories

**Delete stale code, use git history:**

```bash
# BAD
mv agents/old_planner agents/archive/  # ❌

# GOOD
git rm -r agents/old_planner  # ✅
```

**Rationale:** Archives create confusion and import errors. Git provides history.

### R6: INDEX.md Per Directory

Every directory must have `INDEX.md` documenting:
- Purpose
- Files and their responsibilities
- Subdirectories with links to their INDEX.md
- Related components

**Enforcement:** Manual review (no CI check yet).

### R7: Single Responsibility Per Agent

Each agent has **one job**:

- Perception: Load state
- Intent: Extract goals
- Planner: Create plan
- Traverser: Execute plan
- Synthesizer: Aggregate findings
- Critic: Validate results
- Integration: Format response

**Do NOT:**
- Merge agents (e.g., Planner+Traverser)
- Add unrelated logic (e.g., Intent doing tool selection)

---

## Forbidden Patterns

**Do NOT:**
- Hallucinate code without tool execution
- Add claims in Synthesizer without citations
- Generate response content in Critic
- Store business logic in settings/feature flags
- Create archive/backup directories (use git)
- Implement agent logic in tools
- Bypass tool registry (direct tool imports)
- Exceed threshold limits without explicit override
- Define domain-specific configs in mission_system (they belong in capability layer)
- Use deprecated types (Agent, CoreEnvelope, AgentStage, etc.)

---

*This constitution inherits all principles from the dependency chain (Protocols → jeeves_infra → Mission System).*
