# Jeeves-Airframe Constitution

## 0) Purpose

Jeeves-airframe is a **reusable inference platform substrate** that standardizes how capabilities interact with heterogeneous LLM backends. It provides endpoint representation, backend adapters, health signals, and a stable stream-first inference contract.

Airframe is **capability-agnostic**. It knows nothing about agents, prompts, tools, or domain logic.

## 1) Ownership Boundaries

### Airframe MUST Own

| Concern | Description |
|---------|-------------|
| **Endpoint Representation** | `EndpointSpec` with name, base_url, backend_kind, tags, capacity hints, metadata |
| **Endpoint Discovery** | Registries (`StaticRegistry`, `K8sRegistry`) with watchability |
| **Backend Adapters** | Normalize request/response across llama.cpp, OpenAI, Anthropic, etc. |
| **Health Signals** | `HealthState` representation and optional `HealthProbe` mechanisms |
| **Observability Hooks** | Request-level spans, metrics fields, structured log context |
| **Error Taxonomy** | Stable categories: timeout, connection, backend, parse, unknown |

### Airframe MUST NOT Own

| Concern | Belongs To |
|---------|------------|
| Agent logic, prompts, pipelines | Capability |
| Endpoint selection policy (routing) | Capability |
| Tool execution | Capability |
| Workflow orchestration (queues, checkpoints) | Mission System |
| Cluster mutation (Helm, autoscaling) | Platform/Ops |

## 2) Canonical Inference Contract

Airframe exposes a single, backend-agnostic inference interface:

```python
async def stream_infer(
    endpoint: EndpointSpec,
    request: InferenceRequest
) -> AsyncIterator[InferenceStreamEvent]
```

### Request Contract

```python
@dataclass
class InferenceRequest:
    messages: List[Message]           # Required: chat messages
    model: Optional[str]              # Hint; endpoint may ignore
    tools: Optional[List[ToolSpec]]   # For function calling
    temperature: Optional[float]
    max_tokens: Optional[int]
    stream: bool = True
    extra_params: Dict[str, Any]      # Backend-specific passthrough
```

- Capabilities MUST NOT format backend-specific payloads
- Adapters MUST translate to backend wire format

### Response Contract (Stream Events)

```python
class StreamEventType(Enum):
    TOKEN = "token"           # Incremental content
    MESSAGE = "message"       # Complete message (non-streaming)
    TOOL_CALL = "tool_call"   # Function call request
    ERROR = "error"           # Error occurred
    DONE = "done"             # Stream complete
```

- Every stream MUST emit exactly one `DONE` event
- Non-streaming backends emit `MESSAGE` + `DONE`
- Errors are events, not exceptions

## 3) Error Semantics

```python
class ErrorCategory(Enum):
    TIMEOUT = "timeout"           # Request timed out
    CONNECTION = "connection"     # Network/DNS/TLS failure
    BACKEND = "backend"           # HTTP 4xx/5xx from backend
    PARSE = "parse"               # JSON/SSE parsing failure
    UNKNOWN = "unknown"           # Uncategorized
```

- Errors MUST preserve raw backend payloads when available
- Adapters MUST NOT raise backend-specific exceptions across public API
- Capabilities handle errors via stream events, not try/catch

## 4) Registry Contract

```python
class EndpointRegistry(ABC):
    def list_endpoints(self) -> List[EndpointSpec]: ...
    def get_health(self, name: str) -> Optional[HealthState]: ...
    def watch(self, callback) -> WatchHandle: ...
```

- Registries are **read-only** views of available endpoints
- `watch()` enables reactive updates without polling
- Health state starts as `unknown` until probed

## 5) Health Contract

```python
@dataclass
class HealthState:
    status: str          # healthy | degraded | unhealthy | unknown
    checked_at: float    # Unix timestamp
    detail: str          # Human-readable context
```

- Health probing is **optional** (probe may be None)
- Capabilities decide what to do with health (airframe just reports)

## 6) Adapter Contract

```python
class BackendAdapter(ABC):
    async def stream_infer(
        self, endpoint: EndpointSpec, request: InferenceRequest
    ) -> AsyncIterator[InferenceStreamEvent]: ...
```

- One adapter per backend kind (llama_server, openai_chat, etc.)
- Adapters handle retries, timeouts, SSE parsing internally
- New adapters MUST NOT break existing callers

## 7) Kubernetes Integration

K8s support is **optional and read-only**:

- Read endpoint specs from ConfigMap/CRD
- Watch for changes via polling
- No cluster mutation, no admin privileges required
- Import error if kubernetes package not installed (graceful)

## 8) Dependency Direction

```
┌─────────────────────────────────────────────┐
│            Capability Layer                 │
│  (agents, prompts, tools, routing policy)   │
└─────────────────┬───────────────────────────┘
                  │ imports from
┌─────────────────▼───────────────────────────┐
│             Airframe                         │
│  (endpoints, adapters, health, streaming)   │
│                                             │
│  ⚠️  NO imports from capability             │
│  ⚠️  NO imports from jeeves-core            │
└─────────────────────────────────────────────┘
                  │ imports from
┌─────────────────▼───────────────────────────┐
│         Standard Library + httpx            │
│         (+ optional: kubernetes)            │
└─────────────────────────────────────────────┘
```

## 9) Versioning Guarantees

| Change Type | Compatibility |
|-------------|---------------|
| New adapter | Backward compatible |
| New registry | Backward compatible |
| New StreamEventType | Backward compatible |
| New ErrorCategory | Backward compatible |
| Remove/rename public symbol | Breaking (major version) |
| Change InferenceRequest fields | Breaking (major version) |

## 10) Acceptance Criteria

A change to airframe is acceptable only if:

- [ ] No routing policy embedded in airframe
- [ ] No capability-specific logic
- [ ] Stream/error semantics preserved
- [ ] Adapters remain isolated
- [ ] K8s remains optional
- [ ] No new required dependencies beyond httpx
