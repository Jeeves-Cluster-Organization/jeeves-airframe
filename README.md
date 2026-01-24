# Jeeves-Airframe

Inference platform abstraction layer for Jeeves. Handles endpoint representation, backend adapters, health signals, and streaming contracts independently from agent logic and capability concerns.

## Quick Start

```bash
# Install
pip install jeeves-airframe

# With K8s support
pip install "jeeves-airframe[k8s]"

# Development
pip install "jeeves-airframe[dev]"
```

## Architecture

```
airframe/
├── __init__.py          # Public exports
├── types.py             # InferenceRequest, Message, StreamEvent, etc.
├── endpoints.py         # EndpointSpec, HealthState, BackendKind
├── registry.py          # EndpointRegistry, StaticRegistry
├── client.py            # AirframeClient (adapter dispatch)
├── health.py            # HealthProbe, HttpHealthProbe
├── telemetry.py         # Observability hooks
├── selftest.py          # Import verification
├── CONSTITUTION.md      # Architectural principles
├── adapters/
│   ├── base.py          # BackendAdapter ABC
│   ├── llama_server.py  # llama.cpp server adapter
│   └── openai_chat.py   # OpenAI Chat Completions adapter
└── k8s/
    ├── __init__.py      # K8sRegistry export
    ├── registry.py      # ConfigMap-based registry
    └── types.py         # K8s-specific types
```

## Core Concepts

### Endpoint Registry
Discover and manage inference endpoints dynamically.

```python
from airframe import StaticRegistry, EndpointSpec, BackendKind

registry = StaticRegistry([
    EndpointSpec(
        name="local-llama",
        base_url="http://localhost:8080",
        backend_kind=BackendKind.LLAMA_SERVER,
    ),
])
```

### Inference Streaming
Stream responses asynchronously with built-in error handling.

```python
from airframe import AirframeClient, InferenceRequest, Message

client = AirframeClient(registry=registry)
request = InferenceRequest(
    messages=[Message(role="user", content="Hello, world!")],
    model="default",
)

async for event in client.stream(request):
    print(event)
```

### Health Monitoring
Check endpoint health and capacity.

```python
from airframe import HttpHealthProbe

probe = HttpHealthProbe(base_url="http://localhost:8080")
health_state = await probe.check()
print(f"Status: {health_state.status}")
print(f"Capacity: {health_state.capacity_used}/{health_state.capacity_total}")
```

## Error Handling

Airframe normalizes errors across backends into stable categories:

- **timeout**: Request exceeded deadline
- **connection**: Network/DNS failure
- **backend**: Server returned error
- **parse**: Response parsing failed
- **unknown**: Uncategorized error

```python
from airframe import AirframeError, ErrorCategory

try:
    async for event in client.stream(request):
        process(event)
except AirframeError as e:
    if e.category == ErrorCategory.TIMEOUT:
        retry_with_backoff()
    elif e.category == ErrorCategory.CONNECTION:
        fallback_endpoint()
    else:
        log_and_escalate(e)
```

## Verification

```bash
# Basic selftest
python -m airframe.selftest

# Run tests
pytest tests/ -v

# With K8s deps
pytest tests/k8s/ -v
```

## Dependencies

**Core:**
- httpx (streaming HTTP)
- pydantic (type validation)
- structlog (structured logging)

**Optional:**
- kubernetes (K8s ConfigMap registry)
- PyYAML (K8s YAML parsing)

## Constitution

See [CONSTITUTION.md](./CONSTITUTION.md) for architectural principles:

- **Ownership**: Airframe owns endpoints, adapters, health; capabilities own routing policy
- **Stream-first**: All inference exposed as async streams
- **Error taxonomy**: Stable categories across backends
- **Backend isolation**: Adapters normalize protocol differences
- **Optional K8s**: Kubernetes integration never required

## License

Apache License 2.0

## Contributing

Bug reports and feature requests welcome at https://github.com/Jeeves-Cluster-Organization/jeeves-airframe/issues
