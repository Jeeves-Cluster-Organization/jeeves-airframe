# jeeves-infra

Infrastructure layer for Jeeves - adapters above the kernel.

## Architecture

```
Capabilities (User Space)
       │
       ↓
jeeves-infra (Kernel Modules / Drivers)  <- THIS PACKAGE
       │
       ↓
jeeves-core (Microkernel - Rust)
```

This package provides infrastructure implementations for the jeeves-core microkernel:

- **gateway/** - HTTP/WebSocket translation (FastAPI)
- **llm/** - LLM providers (LiteLLM, OpenAI HTTP, Mock)
- **database/** - Database backend registry and factory
- **redis/** - Distributed state backend
- **runtime/** - Python agent/pipeline execution
- **protocols/** - Type definitions and interfaces
- **observability/** - Metrics and tracing
- **tools/** - Tool catalog and executor

## Installation

```bash
# Core only (IPC, protocols)
pip install jeeves-infra

# With specific features
pip install jeeves-infra[gateway]    # FastAPI, WebSocket
pip install jeeves-infra[redis]      # Redis client
pip install jeeves-infra[llm]        # LiteLLM, tiktoken

# All features
pip install jeeves-infra[all]

# Development
pip install jeeves-infra[dev]
```

## Quick Start

```python
from jeeves_infra.protocols import (
    RequestContext,
    LLMProviderProtocol,
    Envelope,
    AgentConfig,
)
from jeeves_infra.llm import OpenAIHTTPProvider
from jeeves_infra.runtime import Agent, PipelineRunner
from jeeves_infra.kernel_client import get_kernel_client

# Use protocols for type safety
from jeeves_infra.database import DatabaseClientProtocol
from jeeves_infra.gateway import create_gateway_app
```

## Packages

### jeeves_infra

Core infrastructure with 230+ type exports:
- Protocols and interfaces
- LLM providers
- Gateway (HTTP/WebSocket)
- Memory services
- Database clients
- Observability

### Orchestration (within jeeves_infra)

Capability-agnostic orchestration infrastructure:
- Agent profiles and configuration
- Prompt templates and blocks
- Event handling
- Vertical services

## Optional Dependencies

| Extra | Description |
|-------|-------------|
| `gateway` | FastAPI, uvicorn, websockets, SSE |
| `redis` | Redis client |
| `llm` | LiteLLM, tiktoken |
| `dev` | pytest, black, ruff, mypy |
| `all` | All optional dependencies |

## Requirements

- Python 3.11+
- msgpack (IPC transport)

## License

Apache-2.0
