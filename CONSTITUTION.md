# Jeeves Infra Constitution

Architectural principles for the Python infrastructure layer.

## Purpose

Jeeves Infra is the **infrastructure layer** that bridges capabilities to the Go micro-kernel. It provides reusable services without domain-specific logic.

## Core Principles

### 1. Infrastructure, Not Domain Logic

The infrastructure layer provides:
- **LLM Providers** - Backend adapters for different LLM services
- **Database Clients** - PostgreSQL, Redis connections
- **Runtime** - Agent execution, pipeline runner
- **Gateway** - HTTP/WebSocket API
- **Observability** - Metrics, logging

The infrastructure layer does NOT provide:
- Domain-specific agents
- Domain-specific tools
- Prompt templates
- Business logic

### 2. Backend Agnostic

LLM providers normalize different backends:

```python
# Same interface, different backends
provider = OpenAIHTTPProvider(base_url="http://localhost:11434/v1")
provider = AnthropicProvider(api_key="...")
provider = LiteLLMProvider(model="gpt-4")
```

Capabilities use the same interface regardless of backend.

### 3. Stream-First Design

All LLM operations support streaming:

```python
async for event in provider.stream(messages):
    if event.type == "token":
        yield event.content
    elif event.type == "done":
        break
```

Non-streaming is implemented as buffered streaming.

### 4. Error Taxonomy

Errors are categorized, not backend-specific:

| Category | Meaning |
|----------|---------|
| `timeout` | Request exceeded time limit |
| `connection` | Network/DNS/TLS failure |
| `backend` | HTTP 4xx/5xx from backend |
| `parse` | JSON/SSE parsing failure |

Capabilities handle error categories, not backend exceptions.

### 5. Kernel Communication

Infrastructure communicates with the Go kernel via gRPC:

```python
kernel = KernelClient(channel)
await kernel.record_llm_call(pid, tokens_in=100, tokens_out=50)
```

Infrastructure does NOT bypass the kernel for:
- Process lifecycle
- Resource quota tracking
- Pipeline state management

## Layer Dependencies

```
Capabilities  ────────────────────────────
     ↑ imports
Infrastructure ─── THIS LAYER ────────────
     ↑ gRPC
Kernel (Go) ──────────────────────────────
```

- Infrastructure imports from kernel client only
- Infrastructure does NOT import from capabilities
- Capabilities import from infrastructure

## Contribution Criteria

Changes to jeeves-infra must demonstrate:

1. **Reusability** - Can multiple capabilities use this?
2. **No domain logic** - Is this truly infrastructure?
3. **Backward compatibility** - Does this break existing callers?
4. **Stream support** - Does this support streaming patterns?

### Acceptable Changes

- New LLM provider adapters
- New database client implementations
- Performance improvements
- Bug fixes with test coverage

### Requires Discussion

- New public protocols/interfaces
- Changes to error taxonomy
- New required dependencies

### Not Acceptable

- Domain-specific agents or tools
- Prompt templates
- Business logic
- Bypassing kernel for state management

## Testing Requirements

All changes must include:
- Unit tests for new functionality
- Integration tests for provider changes
- Mock-based tests that don't require live backends
