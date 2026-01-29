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
jeeves-core (Microkernel - Go)
```

This package provides infrastructure implementations for the jeeves-core microkernel:

- **gateway/** - HTTP/WebSocket/gRPC translation (FastAPI)
- **llm/** - LLM providers (LiteLLM, OpenAI HTTP, Mock)
- **postgres/** - PostgreSQL + pgvector implementations
- **redis/** - Distributed state backend
- **memory/** - Memory service implementations (repositories, services)
- **runtime/** - Python agent/pipeline execution
- **protocols/** - Type definitions and interfaces
- **observability/** - Metrics and tracing
- **tools/** - Tool executor

## Installation

```bash
# Core only (gRPC, protocols)
pip install jeeves-infra

# With specific features
pip install jeeves-infra[gateway]    # FastAPI, WebSocket
pip install jeeves-infra[postgres]   # PostgreSQL, pgvector
pip install jeeves-infra[redis]      # Redis client
pip install jeeves-infra[embeddings] # Sentence transformers
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
from jeeves_infra.postgres import PostgreSQLClient
from mission_system.gateway import create_gateway_app  # Gateway is in L2
```

## Packages

### jeeves_infra (L1: Infrastructure)

Core infrastructure with 230+ type exports:
- Protocols and interfaces
- LLM providers
- Memory services
- Database clients
- Observability
- Kernel client (gRPC to Go kernel)

### mission_system (L2: Orchestration)

Capability-agnostic orchestration infrastructure:
- Gateway (HTTP/WS/gRPC) - moved from jeeves_infra
- Agent profiles and configuration
- Prompt templates and blocks
- Event handling
- Vertical services

## Optional Dependencies

| Extra | Description |
|-------|-------------|
| `gateway` | FastAPI, uvicorn, websockets, SSE |
| `postgres` | asyncpg, SQLAlchemy, pgvector |
| `redis` | Redis client |
| `embeddings` | Sentence transformers, numpy |
| `llm` | LiteLLM, tiktoken |
| `dev` | pytest, black, ruff, mypy |
| `all` | All optional dependencies |

## Requirements

- Python 3.11+
- gRPC and protobuf (core)

## License

Apache-2.0
