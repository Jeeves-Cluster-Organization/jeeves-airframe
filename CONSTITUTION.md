# Jeeves-Airframe Constitution

## 0) Purpose

Jeeves-airframe (`jeeves_infra`) is the **unified infrastructure and orchestration framework** for the Jeeves ecosystem. It provides everything between the Rust micro-kernel (jeeves-core) and the capability layer: LLM providers, pipeline execution, gateway, orchestration, memory handling, configuration, and bootstrap.

## 1) Ownership Boundaries

### jeeves_infra MUST Own

| Domain | Description |
|--------|-------------|
| **Protocols & Types** | All interfaces, type definitions, capability registration (`protocols.py`) |
| **LLM Infrastructure** | Providers, factory, gateway, cost calculator (`llm/`) |
| **Gateway** | FastAPI HTTP/WS/SSE/gRPC server, routers, lifespan (`gateway/`) |
| **Kernel Client** | gRPC bridge to Rust kernel (`kernel_client.py`) |
| **Pipeline Runner** | Kernel-driven agent execution (`runtime/`) |
| **Tool Execution** | ToolExecutor framework - not tool catalogs, capability owns those (`wiring.py`) |
| **Database Abstraction** | Factory, registry, protocols - not implementations (`database/`) |
| **Bootstrap** | AppContext creation, composition root (`bootstrap.py`) |
| **Capability Wiring** | Registration, discovery, router mounting (`capability_wiring.py`) |
| **Config** | Agent profiles, registry, constants (`config/`) |
| **Orchestrator** | Event context, emitter, governance, flow, vertical service (`orchestrator/`) |
| **Memory Handlers** | CommBus handler registration, message types (`memory/`) |
| **Events** | Event bridge for kernel <-> gateway (`events/`) |
| **Observability** | Metrics, tracing, OTEL |
| **Logging** | Structlog infrastructure (`logging.py`) |
| **Health** | Kubernetes liveness/readiness probes (`health.py`) |
| **Feature Flags** | Runtime toggles (`feature_flags.py`) |
| **Settings** | Application configuration (`settings.py`) |

### jeeves_infra MUST NOT Own

| Concern | Belongs To |
|---------|------------|
| Agent logic, prompts, tools | Capability |
| Domain-specific database backends | Capability |
| Pipeline configuration (AgentConfig lists) | Capability |
| Tool catalogs and tool implementations | Capability |
| Domain services (ChatbotService, etc.) | Capability |
| Cluster mutation (Helm, autoscaling) | Platform/Ops |

## 2) Dependency Direction

```
Capability Layer (agents, prompts, tools, domain DB, memory services)
       | imports from
       v
jeeves_infra (everything in section 1)
       | gRPC bridge
       v
jeeves-core (Rust kernel)
```

- jeeves_infra MUST NOT import from any capability
- jeeves_infra communicates with jeeves-core via gRPC (`kernel_client.py`)
- Capabilities import from jeeves_infra public modules only

## 3) Public API Surface

Capabilities may import from these modules:

| Module | Purpose |
|--------|---------|
| `jeeves_infra.protocols` | All type definitions, Envelope, AgentConfig, PipelineConfig |
| `jeeves_infra.bootstrap` | `create_app_context()` — returns AppContext with `kernel_client`, `llm_provider_factory`, `config_registry` eagerly provisioned |
| `jeeves_infra.wiring` | `create_tool_executor` (tool executor framework), `get_database_client` |
| `jeeves_infra.settings` | `get_settings()` |
| `jeeves_infra.kernel_client` | `KernelClient` class (instance provided via AppContext, no global accessor) |
| `jeeves_infra.orchestrator` | EventOrchestrator, create_event_context |
| `jeeves_infra.memory.messages` | CommBus message types |
| `jeeves_infra.config.constants` | Platform constants |
| `jeeves_infra.logging` | get_current_logger |
| `jeeves_infra.feature_flags` | get_feature_flags |

**Bootstrap pattern (K8s-style eager provisioning):**

```python
from jeeves_infra.bootstrap import create_app_context

app_context = create_app_context()
# app_context.kernel_client       — gRPC bridge (or None)
# app_context.llm_provider_factory — creates LLM providers per agent role
# app_context.config_registry     — configuration registry
# app_context.settings            — application settings
```

**Apps MUST NOT** import `jeeves_infra.wiring`, `jeeves_infra.kernel_client`, or `jeeves_infra.llm` directly. Apps use the capability layer entry point (e.g., `create_hello_world_from_app_context(app_context)`).

## 4) Canonical Inference Contract

```python
async def stream_infer(
    endpoint: EndpointSpec,
    request: InferenceRequest
) -> AsyncIterator[InferenceStreamEvent]
```

- Capabilities MUST NOT format backend-specific payloads
- Adapters MUST translate to backend wire format
- Every stream MUST emit exactly one DONE event
- Errors are events, not exceptions

## 5) Error Semantics

```python
class ErrorCategory(Enum):
    TIMEOUT = "timeout"
    CONNECTION = "connection"
    BACKEND = "backend"
    PARSE = "parse"
    UNKNOWN = "unknown"
```

- Errors MUST preserve raw backend payloads when available
- Adapters MUST NOT raise backend-specific exceptions across public API

## 6) Acceptance Criteria

A change to jeeves_infra is acceptable only if:

- [ ] No capability-specific logic embedded
- [ ] No tool implementations (only tool executor framework)
- [ ] No database backend implementations (only factory/registry)
- [ ] Stream/error semantics preserved
- [ ] K8s integration remains optional
- [ ] Dependency direction maintained (no capability imports)
