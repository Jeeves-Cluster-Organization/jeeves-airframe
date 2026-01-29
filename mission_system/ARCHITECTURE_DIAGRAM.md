# Jeeves Mission System Architecture Diagram

**Companion to:** [CONSTITUTION.md](CONSTITUTION.md)
**Version:** 2.2
**Last Updated:** 2025-12-16

---

## Overview

This document provides architectural views for **Jeeves Mission System**—the application layer that provides orchestration framework, API endpoints, and the foundation for capabilities.

**Key Principle:** Mission System provides **orchestration infrastructure** using services from Avionics and abstractions from Core Engine. Domain-specific logic belongs in capability layers.

**Control Tower Integration:** Mission System services register with Control Tower at startup and receive requests via `control_tower.submit_request()`. All requests flow through the Control Tower kernel for lifecycle management, resource tracking, and event aggregation.

---

## Intra-Level: Mission System Internal Architecture

### Module Organization

```
mission_system/
│
├─ verticals/                    # Capability registration (domain logic in external repos)
│  └─ registry.py                # Capability registry
│
├─ orchestrator/                 # LangGraph orchestration
│  ├─ langgraph/
│  │  ├─ state.py               # JeevesState definition
│  │  ├─ routing.py             # Routing logic
│  │  ├─ vertical_nodes.py      # Agent wrapper nodes
│  │  └─ checkpointer.py        # Optional checkpointing
│  ├─ flow_service.py           # Pipeline execution
│  ├─ governance_service.py     # Tool health monitoring
│  ├─ agent_events.py           # Event emission
│  └─ server.py                 # gRPC server (orchestrator service)
│
├─ api/                          # HTTP API layer
│  ├─ main.py                   # FastAPI app
│  ├─ routers/
│  │  ├─ chat.py                # Chat endpoints
│  │  ├─ health.py          # Governance dashboard
│  │  └─ health.py              # Health checks
│  └─ templates/                # Jinja2 templates
│
├─ services/                     # Application services
│  ├─ tool_registry.py          # Tool discovery and execution
│  └─ evidence_validator.py     # Citation validation
│
├─ config/                       # Configuration
│  ├─ agent_modes.py            # Agent mode definitions
│  ├─ agent_tool_access.py      # Tool access control
│  ├─ node_profiles.py          # LangGraph node profiles
│  └─ constants.py              # Application constants
│
├─ common/                       # Shared utilities
│  └─ formatting/               # Output formatting
│
├─ scripts/                      # Operational scripts
│  ├─ run/                      # Server startup
│  ├─ database/                 # DB initialization
│  ├─ deployment/               # Deployment scripts
│  └─ testing/                  # Test utilities
│
└─ tests/                        # Test suites
   ├─ unit/                     # Unit tests
   ├─ integration/              # Integration tests
   ├─ contract/                 # Contract tests
   └─ e2e/                      # End-to-end tests
```

---

## Reference Pipeline Architecture

The following describes the **reference 7-agent pipeline** that capabilities can adopt. Capabilities may customize this pipeline or define their own agent configurations.

### Reference Pipeline Diagram

```
┌───────────────────────────────────────────────────────────────┐
│  USER QUERY: "How does authentication work?"                  │
└───────────────────────────┬───────────────────────────────────┘
                            │
                            ↓
┌───────────────────────────────────────────────────────────────┐
│  1. PERCEPTION (Non-LLM)                                      │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  • Load session state from L3 memory                     │ │
│  │  • Normalize user input                                  │ │
│  │  • Check for previous context                            │ │
│  │  • Output: PerceptionOutput                              │ │
│  │    - normalized_query                                    │ │
│  │    - session_context                                     │ │
│  └─────────────────────────────────────────────────────────┘ │
└───────────────────────────┬───────────────────────────────────┘
                            │
                            ↓
┌───────────────────────────────────────────────────────────────┐
│  2. INTENT (LLM)                                              │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  • Classify query intent                                 │ │
│  │  • Extract goals: ["understand_auth_flow", "find_config"]│ │
│  │  • Determine if clarification needed                     │ │
│  │  • Output: IntentOutput                                  │ │
│  │    - goals: List[str]                                    │ │
│  │    - intent_type: "trace_flow"                           │ │
│  │    - clarification_required: bool                        │ │
│  └─────────────────────────────────────────────────────────┘ │
└───────────────────────────┬───────────────────────────────────┘
                            │
                            ↓
┌───────────────────────────────────────────────────────────────┐
│  MULTI-STAGE LOOP (Repeat until all goals satisfied)         │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  3. PLANNER (LLM)                                        │ │
│  │  ┌───────────────────────────────────────────────────┐  │ │
│  │  │  • Review remaining goals                          │  │ │
│  │  │  • Select tools from registry (9 exposed tools)    │  │ │
│  │  │  • Create execution plan                           │  │ │
│  │  │  • Output: PlanOutput                              │  │ │
│  │  │    - steps: List[PlanStep]                         │  │ │
│  │  │    - reasoning: str                                │  │ │
│  │  └───────────────────────────────────────────────────┘  │ │
│  └─────────────────────────────────────────────────────────┘ │
│                            │                                  │
│                            ↓                                  │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  4. TRAVERSER (Non-LLM)                                 │ │
│  │  ┌───────────────────────────────────────────────────┐  │ │
│  │  │  • Execute plan steps sequentially                 │  │ │
│  │  │  • Call tools from registry                        │  │ │
│  │  │  • Collect evidence with [file:line] citations     │  │ │
│  │  │  • Retry on failures (max 2 retries per step)      │  │ │
│  │  │  • Output: ExecutionOutput                         │  │ │
│  │  │    - results: List[ToolExecutionResult]            │  │ │
│  │  │    - citations: List[Citation]                     │  │ │
│  │  │    - attempt_history: List[AttemptRecord]          │  │ │
│  │  └───────────────────────────────────────────────────┘  │ │
│  └─────────────────────────────────────────────────────────┘ │
│                            │                                  │
│                            ↓                                  │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  5. SYNTHESIZER (LLM)                                   │ │
│  │  ┌───────────────────────────────────────────────────┐  │ │
│  │  │  • Aggregate findings from execution               │  │ │
│  │  │  • Structure analysis (preserve citations)         │  │ │
│  │  │  • Identify gaps                                   │  │ │
│  │  │  • Output: SynthesizerOutput                       │  │ │
│  │  │    - summary: str                                  │  │ │
│  │  │    - findings: List[Finding]                       │  │ │
│  │  │    - gaps: List[str]                               │  │ │
│  │  │    - citations: List[Citation] (preserved)         │  │ │
│  │  └───────────────────────────────────────────────────┘  │ │
│  └─────────────────────────────────────────────────────────┘ │
│                            │                                  │
│                            ↓                                  │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  6. CRITIC (LLM)                                        │ │
│  │  ┌───────────────────────────────────────────────────┐  │ │
│  │  │  • Validate goal satisfaction                      │  │ │
│  │  │  • Check completeness against original goals       │  │ │
│  │  │  • Decide next action:                             │  │ │
│  │  │    - REPLAN: Plan was insufficient, try again      │  │ │
│  │  │    - NEXT_STAGE: Goal satisfied, move to next      │  │ │
│  │  │    - COMPLETE: All goals satisfied                 │  │ │
│  │  │  • Output: CriticOutput                            │  │ │
│  │  │    - decision: CriticDecision                      │  │ │
│  │  │    - verdict: str                                  │  │ │
│  │  │    - remaining_goals: List[str]                    │  │ │
│  │  └───────────────────────────────────────────────────┘  │ │
│  └─────────────────────────────────────────────────────────┘ │
│                            │                                  │
│                   ┌────────┴────────┐                         │
│                   │                 │                         │
│          [REPLAN] │      [NEXT_STAGE]│      [COMPLETE]        │
│                   │                 │            │            │
│                   ↓                 ↓            │            │
│            Back to PLANNER   Back to PLANNER    │            │
│            (same stage)      (new stage)        │            │
│                                                  │            │
└──────────────────────────────────────────────────┼────────────┘
                                                   │
                                                   ↓
┌───────────────────────────────────────────────────────────────┐
│  7. INTEGRATION (Non-LLM)                                     │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  • Format final response                                 │ │
│  │  • Add [file:line] citations                             │ │
│  │  • Save session state to L3 memory                       │ │
│  │  • Log events to L2 (event log)                          │ │
│  │  • Output: Response                                      │ │
│  │    - answer: str (with citations)                        │ │
│  │    - evidence: List[Evidence]                            │ │
│  │    - metadata: ResponseMetadata                          │ │
│  └─────────────────────────────────────────────────────────┘ │
└───────────────────────────┬───────────────────────────────────┘
                            │
                            ↓
┌───────────────────────────────────────────────────────────────┐
│  RESPONSE: "Authentication flow starts in auth.py:42..."     │
│  [auth.py:42] [middleware.py:15] [config.yaml:8]             │
└───────────────────────────────────────────────────────────────┘
```

---

## Tool Registry Architecture

Capabilities define and register their own tools. The runtime provides a `ToolRegistry` pattern:

### Tool Categories

```
┌───────────────────────────────────────────────────────────────┐
│  COMPOSITE TOOLS                                              │
│  Multi-step workflows with fallback strategies               │
│                                                               │
│  Example pattern:                                             │
│  - Strategy 1: Fast, exact lookup                             │
│  - Strategy 2: Pattern-based search                           │
│  - Strategy 3: Semantic/fuzzy fallback                        │
└───────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│  RESILIENT TOOLS                                              │
│  Wrapped base tools with retry and graceful degradation      │
│                                                               │
│  Features:                                                    │
│  - Fuzzy matching on NotFoundError                            │
│  - Fallback strategies                                        │
│  - Token/size-based slicing                                   │
└───────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│  STANDALONE TOOLS                                             │
│  Simple, single-operation tools                               │
│                                                               │
│  Examples:                                                    │
│  - System status tools                                        │
│  - Registry introspection (list_tools)                        │
└───────────────────────────────────────────────────────────────┘
```

### Tool Registry

```
┌───────────────────────────────────────────────────────────────┐
│  ToolRegistry                                                 │
│                                                               │
│  class ToolRegistry:                                          │
│      def __init__(self):                                      │
│          self._tools: Dict[str, Callable] = {}                │
│          self._metadata: Dict[str, ToolInfo] = {}             │
│                                                               │
│      def register(                                            │
│          self,                                                │
│          name: str,                                           │
│          func: Callable,                                      │
│          info: ToolInfo                                       │
│      ) -> None:                                               │
│          """Register a tool."""                               │
│          self._tools[name] = func                             │
│          self._metadata[name] = info                          │
│                                                               │
│      async def execute(                                       │
│          self,                                                │
│          name: str,                                           │
│          params: dict                                         │
│      ) -> ToolResult:                                         │
│          """Execute a tool by name."""                        │
│          if name not in self._tools:                          │
│              return ToolResult(                               │
│                  status="not_found",                          │
│                  error=f"Tool '{name}' not found"             │
│              )                                                │
│                                                               │
│          try:                                                 │
│              result = await self._tools[name](**params)       │
│              return ToolResult(status="success", data=result) │
│          except Exception as e:                               │
│              return ToolResult(status="error", error=str(e))  │
│                                                               │
│      def list_tools(self) -> List[ToolInfo]:                  │
│          """Return metadata for all tools."""                 │
│          return list(self._metadata.values())                 │
└───────────────────────────────────────────────────────────────┘
```

---

## Intra-Level: Orchestration Layer

### LangGraph State Definition

```
┌───────────────────────────────────────────────────────────────┐
│  JeevesState (LangGraph StateGraph)                           │
│                                                               │
│  class JeevesState(TypedDict):                                │
│      # Core envelope (converted from CoreEnvelope)            │
│      envelope_id: str                                         │
│      user_input: str                                          │
│      user_id: str                                             │
│      session_id: str                                          │
│      stage: str                                               │
│                                                               │
│      # Agent outputs (accumulated)                            │
│      perception_output: Optional[PerceptionOutput]            │
│      intent_output: Optional[IntentOutput]                    │
│      plan_output: Optional[PlanOutput]                        │
│      execution_output: Optional[ExecutionOutput]              │
│      synthesizer_output: Optional[SynthesizerOutput]          │
│      critic_output: Optional[CriticOutput]                    │
│      integration_output: Optional[Response]                   │
│                                                               │
│      # Multi-stage tracking                                   │
│      current_stage_index: int                                 │
│      completed_stages: List[StageResult]                      │
│      remaining_goals: List[str]                               │
│                                                               │
│      # Routing                                                │
│      next_node: Optional[str]                                 │
│      critic_decision: Optional[CriticDecision]                │
│                                                               │
│      # Error tracking                                         │
│      errors: List[ErrorRecord]                                │
└───────────────────────────────────────────────────────────────┘
```

### LangGraph Pipeline Definition

```
┌───────────────────────────────────────────────────────────────┐
│  Pipeline Graph                                               │
│                                                               │
│  graph = StateGraph(JeevesState)                              │
│                                                               │
│  # Add nodes                                                  │
│  graph.add_node("perception", perception_node)                │
│  graph.add_node("intent", intent_node)                        │
│  graph.add_node("planner", planner_node)                      │
│  graph.add_node("traverser", traverser_node)                  │
│  graph.add_node("synthesizer", synthesizer_node)              │
│  graph.add_node("critic", critic_node)                        │
│  graph.add_node("integration", integration_node)              │
│                                                               │
│  # Add edges                                                  │
│  graph.set_entry_point("perception")                          │
│  graph.add_edge("perception", "intent")                       │
│  graph.add_edge("intent", "planner")                          │
│  graph.add_edge("planner", "traverser")                       │
│  graph.add_edge("traverser", "synthesizer")                   │
│  graph.add_edge("synthesizer", "critic")                      │
│                                                               │
│  # Conditional routing after critic                           │
│  graph.add_conditional_edges(                                 │
│      "critic",                                                │
│      route_after_critic,  # Routing function                  │
│      {                                                        │
│          "REPLAN": "planner",                                 │
│          "NEXT_STAGE": "planner",                             │
│          "COMPLETE": "integration",                           │
│      }                                                        │
│  )                                                            │
│                                                               │
│  graph.add_edge("integration", END)                           │
│                                                               │
│  # Compile                                                    │
│  app = graph.compile()                                        │
└───────────────────────────────────────────────────────────────┘
```

### Routing Logic

```
┌───────────────────────────────────────────────────────────────┐
│  route_after_critic(state: JeevesState) -> str                │
│                                                               │
│  def route_after_critic(state: JeevesState) -> str:           │
│      decision = state["critic_output"].decision               │
│                                                               │
│      if decision == CriticDecision.REPLAN:                    │
│          # Plan was insufficient, retry                       │
│          logger.info("critic_replan", stage=state["stage"])   │
│          return "planner"                                     │
│                                                               │
│      elif decision == CriticDecision.NEXT_STAGE:              │
│          # Goal satisfied, move to next goal                  │
│          state["current_stage_index"] += 1                    │
│          state["completed_stages"].append(...)                │
│                                                               │
│          if state["current_stage_index"] >= max_stages:       │
│              logger.warning("max_stages_reached")             │
│              return "integration"                             │
│                                                               │
│          logger.info("critic_next_stage")                     │
│          return "planner"                                     │
│                                                               │
│      elif decision == CriticDecision.COMPLETE:                │
│          # All goals satisfied                                │
│          logger.info("critic_complete")                       │
│          return "integration"                                 │
│                                                               │
│      else:                                                    │
│          raise ValueError(f"Unknown decision: {decision}")    │
└───────────────────────────────────────────────────────────────┘
```

---

## Inter-Level: Using Avionics and Core Engine

### Agent Implementation Pattern

```
┌───────────────────────────────────────────────────────────────┐
│  Mission System Agent (Concrete Implementation)              │
│                                                               │
│  from jeeves_core_engine import Agent, AgentResult, StateDelta│
│  from avionics import LLMProtocol                      │
│                                                               │
│  class IntentAgent(Agent):                                    │
│      stage = AgentStage.INTENT                                │
│      capabilities = {"intent_classification"}                 │
│                                                               │
│      async def run(                                           │
│          self,                                                │
│          envelope: CoreEnvelope,  # ← From core engine        │
│          context: RunContext,     # ← From core engine        │
│      ) -> AgentResult:            # ← To core engine          │
│                                                               │
│          # 1. Get perception output from envelope             │
│          perception = envelope.agent_outputs.get("perception")│
│                                                               │
│          # 2. Build prompt                                    │
│          prompt = self.build_prompt(perception.normalized_query)│
│                                                               │
│          # 3. Call LLM (via Avionics adapter)                 │
│          response = await context.llm.generate(  # ← Avionics │
│              prompt=prompt,                                   │
│              model=context.config.intent_model,               │
│          )                                                    │
│                                                               │
│          # 4. Parse LLM output                                │
│          intent_data = JSONRepairKit.parse(response)          │
│          intent_output = IntentOutput(**intent_data)          │
│                                                               │
│          # 5. Return result (core engine pattern)             │
│          return AgentResult(                                  │
│              delta=StateDelta(                                │
│                  output_key="intent",                         │
│                  output_value=intent_output,                  │
│                  stage_transition=EnvelopeStage.PLANNING,     │
│              )                                                │
│          )                                                    │
└───────────────────────────────────────────────────────────────┘
```

**Dependencies:**
- **Core Engine:** Agent contract, CoreEnvelope, AgentResult, StateDelta
- **Avionics:** LLMProtocol implementation (via context.llm)

---

## Inter-Level: API Layer

### HTTP API to Orchestrator Flow (via Control Tower)

```
┌───────────────────────────────────────────────────────────────┐
│  CLIENT                                                       │
│  POST /api/v1/chat/messages                                   │
│  {                                                            │
│    "message": "How does auth work?",                          │
│    "user_id": "user123",                                      │
│    "session_id": "session456"                                 │
│  }                                                            │
└───────────────────────────┬───────────────────────────────────┘
                            │ HTTP/JSON
                            ↓
┌───────────────────────────────────────────────────────────────┐
│  API LAYER (mission_system/api/)                       │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  FastAPI Router (chat.py)                                │ │
│  │  1. Validate request (Pydantic)                          │ │
│  │  2. Get dependencies (DI):                               │ │
│  │     - control_tower                                      │ │
│  │     - memory_service (from Avionics)                     │ │
│  │  3. Submit to Control Tower                              │ │
│  └─────────────────────────────────────────────────────────┘ │
└───────────────────────────┬───────────────────────────────────┘
                            │
                            ↓
┌───────────────────────────────────────────────────────────────┐
│  CONTROL TOWER (control_tower/)                        │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  control_tower.submit_request(envelope)                  │ │
│  │  1. LifecycleManager: Create ProcessControlBlock         │ │
│  │  2. ResourceTracker: Check/allocate quotas               │ │
│  │  3. CommBusCoordinator: Dispatch to registered service   │ │
│  │  4. EventAggregator: Stream events back to Gateway       │ │
│  └─────────────────────────────────────────────────────────┘ │
└───────────────────────────┬───────────────────────────────────┘
                            │ dispatches
                            ↓
┌───────────────────────────────────────────────────────────────┐
│  ORCHESTRATOR (mission_system/orchestrator/)           │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  FlowService (registered with Control Tower)             │ │
│  │  1. Create CoreEnvelope (Core Engine)                    │ │
│  │  2. Convert to JeevesState (LangGraph)                   │ │
│  │  3. Execute LangGraph pipeline                           │ │
│  │  4. Stream agent events (SSE via EventAggregator)        │ │
│  │  5. Return final response                                │ │
│  └─────────────────────────────────────────────────────────┘ │
└───────────────────────────┬───────────────────────────────────┘
                            │ invokes
                            ↓
┌───────────────────────────────────────────────────────────────┐
│  CAPABILITY (External capability repository)                  │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  Capability-Defined Agent Pipeline                       │ │
│  │  Perception → Intent → Planner → ... → Integration      │ │
│  │                                                          │ │
│  │  Uses:                                                   │ │
│  │  • Core Engine (Agent, Envelope, StateDelta)     │ │
│  │  • Avionics (LLM, Database, Memory via context)         │ │
│  │  • Mission System (Tools, ToolRegistry)                 │ │
│  └─────────────────────────────────────────────────────────┘ │
└───────────────────────────┬───────────────────────────────────┘
                            │ returns
                            ↓
┌───────────────────────────────────────────────────────────────┐
│  RESPONSE                                                     │
│  {                                                            │
│    "answer": "Authentication starts in auth.py:42...",        │
│    "citations": [                                             │
│      {"file": "auth.py", "line": 42, "content": "..."},      │
│      {"file": "middleware.py", "line": 15, "content": "..."}  │
│    ],                                                         │
│    "metadata": {...}                                          │
│  }                                                            │
└───────────────────────────────────────────────────────────────┘
```

---

## Intra-Level: Evidence Chain Integrity

### Citation Flow (P1 Enforcement)

```
┌───────────────────────────────────────────────────────────────┐
│  TRAVERSER (Tool Execution)                                   │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  tool_result = await tool_registry.execute(              │ │
│  │      name="read_code",                                   │ │
│  │      params={"file": "auth.py", "lines": (40, 50)}       │ │
│  │  )                                                       │ │
│  │                                                          │ │
│  │  # Tool returns raw output with citations                │ │
│  │  ToolResult(                                             │ │
│  │      status="success",                                   │ │
│  │      data={                                              │ │
│  │          "content": "def login(user):\n    ...",          │ │
│  │          "citations": [                                  │ │
│  │              {"file": "auth.py", "line": 42}             │ │
│  │          ]                                               │ │
│  │      }                                                   │ │
│  │  )                                                       │ │
│  └─────────────────────────────────────────────────────────┘ │
└───────────────────────────┬───────────────────────────────────┘
                            │ passes to
                            ↓
┌───────────────────────────────────────────────────────────────┐
│  SYNTHESIZER (Aggregation)                                    │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  # RULE: Cannot add claims without citations             │ │
│  │                                                          │ │
│  │  execution = envelope.agent_outputs["traverser"]         │ │
│  │  all_citations = extract_citations(execution)            │ │
│  │                                                          │ │
│  │  # Call LLM to aggregate                                 │ │
│  │  summary = await llm.generate(                           │ │
│  │      prompt=build_synthesis_prompt(execution)            │ │
│  │  )                                                       │ │
│  │                                                          │ │
│  │  # Validate: All citations in summary exist in execution │ │
│  │  for citation in extract_citations_from_summary(summary):│ │
│  │      if citation not in all_citations:                   │ │
│  │          raise EvidenceChainViolation(                   │ │
│  │              f"Hallucinated citation: {citation}"        │ │
│  │          )                                               │ │
│  └─────────────────────────────────────────────────────────┘ │
└───────────────────────────┬───────────────────────────────────┘
                            │ passes to
                            ↓
┌───────────────────────────────────────────────────────────────┐
│  CRITIC (Validation)                                          │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  # RULE: Cannot add content, only validate               │ │
│  │                                                          │ │
│  │  synthesizer = envelope.agent_outputs["synthesizer"]     │ │
│  │  intent = envelope.agent_outputs["intent"]               │ │
│  │                                                          │ │
│  │  # Validate goal satisfaction                            │ │
│  │  verdict = await llm.generate(                           │ │
│  │      prompt=build_critic_prompt(                         │ │
│  │          goals=intent.goals,                             │ │
│  │          findings=synthesizer.findings                   │ │
│  │      )                                                   │ │
│  │  )                                                       │ │
│  │                                                          │ │
│  │  # Critic returns decision, NOT content                  │ │
│  │  CriticOutput(                                           │ │
│  │      decision=CriticDecision.COMPLETE,                   │ │
│  │      verdict="All goals satisfied",                      │ │
│  │      # NO new citations, NO new findings                 │ │
│  │  )                                                       │ │
│  └─────────────────────────────────────────────────────────┘ │
└───────────────────────────┬───────────────────────────────────┘
                            │ passes to
                            ↓
┌───────────────────────────────────────────────────────────────┐
│  INTEGRATION (Response Formatting)                            │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  # RULE: Only use completed_stages evidence              │ │
│  │                                                          │ │
│  │  # Collect all evidence from completed stages            │ │
│  │  all_findings = []                                       │ │
│  │  all_citations = []                                      │ │
│  │  for stage in envelope.completed_stages:                 │ │
│  │      synthesizer = stage.agent_outputs["synthesizer"]    │ │
│  │      all_findings.extend(synthesizer.findings)           │ │
│  │      all_citations.extend(synthesizer.citations)         │ │
│  │                                                          │ │
│  │  # Format response with citations                        │ │
│  │  response = format_response(                             │ │
│  │      findings=all_findings,                              │ │
│  │      citations=all_citations,                            │ │
│  │  )                                                       │ │
│  │                                                          │ │
│  │  # Final validation                                      │ │
│  │  validate_evidence_chain(response, all_citations)        │ │
│  └─────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────┘
```

**Contract Tests:** `tests/contract/test_evidence_chain.py` validates this flow.

---

## Intra-Level: Testing Strategy

### Test Pyramid

```
┌───────────────────────────────────────────────────────────────┐
│  E2E Tests (Slowest, Most Realistic)                          │
│  • Full pipeline with real services                           │
│  • HTTP API integration                                       │
│  • Multi-stage workflows                                      │
│  Location: mission_system/tests/e2e/                   │
└───────────────────────────────────────────────────────────────┘
                            ↑
┌───────────────────────────────────────────────────────────────┐
│  Integration Tests (Medium Speed)                             │
│  • Agent pipeline with real LLM                                │
│  • Database operations (testcontainers)                        │
│  • Tool execution on real files                                │
│  Location: mission_system/tests/integration/           │
└───────────────────────────────────────────────────────────────┘
                            ↑
┌───────────────────────────────────────────────────────────────┐
│  Contract Tests (Fast, Static Analysis)                       │
│  • Import boundary validation                                 │
│  • Evidence chain integrity                                   │
│  • Memory layer contracts                                     │
│  • State conversion (envelope ↔ LangGraph)                    │
│  Location: mission_system/tests/contract/              │
└───────────────────────────────────────────────────────────────┘
                            ↑
┌───────────────────────────────────────────────────────────────┐
│  Unit Tests (Fastest, Isolated)                               │
│  • Individual agents (mock LLM, mock tools)                    │
│  • Tool implementations (isolated execution)                   │
│  • Orchestration routing logic                                │
│  • Utility functions                                           │
│  Location: mission_system/tests/unit/                  │
└───────────────────────────────────────────────────────────────┘
```

### Example Unit Test

```
┌───────────────────────────────────────────────────────────────┐
│  Unit Test: Synthesizer Preserves Citations                  │
│                                                               │
│  async def test_synthesizer_preserves_citations():            │
│      """Synthesizer must not add claims without citations.""" │
│                                                               │
│      # Setup                                                  │
│      mock_llm = MockLLM(response='''                          │
│          {                                                    │
│              "summary": "Login starts at auth.py:42",         │
│              "findings": [...]                                │
│          }                                                    │
│      ''')                                                     │
│                                                               │
│      execution_output = ExecutionOutput(                      │
│          results=[...],                                       │
│          citations=[Citation(file="auth.py", line=42)]        │
│      )                                                        │
│                                                               │
│      envelope = CoreEnvelope(                                 │
│          agent_outputs={"traverser": execution_output}        │
│      )                                                        │
│                                                               │
│      context = RunContext(llm=mock_llm, ...)                  │
│                                                               │
│      # Execute                                                │
│      synthesizer = SynthesizerAgent()                         │
│      result = await synthesizer.run(envelope, context)        │
│                                                               │
│      # Validate                                               │
│      output = result.delta.output_value                       │
│                                                               │
│      # All citations in output must exist in execution        │
│      for citation in output.citations:                        │
│          assert citation in execution_output.citations, \     │
│              f"Hallucinated citation: {citation}"             │
└───────────────────────────────────────────────────────────────┘
```

---

## Cross-References

- **Constitution:** [CONSTITUTION.md](CONSTITUTION.md)
- **Control Tower:** [../control_tower/](../control_tower/) - Kernel layer (request routing)
- **Index:** [INDEX.md](INDEX.md)
- **Related Diagrams:**
  - [../control_tower/CONSTITUTION.md](../control_tower/CONSTITUTION.md)
  - [../avionics/ARCHITECTURE_DIAGRAM.md](../avionics/ARCHITECTURE_DIAGRAM.md)

---

*This architecture diagram shows the internal structure of the Mission System (intra-level) and how it uses Core Engine abstractions and Avionics infrastructure (inter-level) to provide orchestration for capabilities with strict evidence chain integrity.*
