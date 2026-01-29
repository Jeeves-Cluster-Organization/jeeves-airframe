# Jeeves Infra

Python infrastructure layer for the Jeeves AI agent platform.

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![PyPI](https://img.shields.io/badge/PyPI-jeeves--infra-blue)](https://pypi.org/project/jeeves-infra/)

## Overview

Jeeves Infra provides the **infrastructure layer** that sits between capabilities (user applications) and the Go micro-kernel. It includes:

- **LLM Providers** - OpenAI, Anthropic, LiteLLM, and local model support
- **Database Clients** - PostgreSQL with pgvector for embeddings
- **HTTP Gateway** - FastAPI-based REST and WebSocket endpoints
- **Runtime** - Python agent execution and pipeline orchestration
- **Observability** - Prometheus metrics and structured logging

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Capabilities (User Space)                                       │
│  mini-swe-agent, chat-agent, custom capabilities                │
└─────────────────────────────────────────────────────────────────┘
                              │ imports
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  jeeves-infra (Infrastructure Layer)  ← THIS PACKAGE            │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │     LLM      │  │   Database   │  │   Gateway    │          │
│  │  Providers   │  │   Clients    │  │  (FastAPI)   │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Runtime    │  │  Protocols   │  │ Observability│          │
│  │   (Agents)   │  │  (Types)     │  │  (Metrics)   │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                              │ gRPC
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  jeeves-core (Micro-Kernel - Go)                                │
│  Pipeline orchestration, bounds checking, state management      │
└─────────────────────────────────────────────────────────────────┘
```

## Installation

```bash
# Core package (gRPC, protocols, runtime)
pip install jeeves-infra

# With specific features
pip install jeeves-infra[gateway]     # FastAPI, WebSocket, SSE
pip install jeeves-infra[postgres]    # PostgreSQL, pgvector
pip install jeeves-infra[redis]       # Redis client
pip install jeeves-infra[embeddings]  # Sentence transformers
pip install jeeves-infra[llm]         # LiteLLM, tiktoken

# All features
pip install jeeves-infra[all]

# Development
pip install jeeves-infra[dev]
```

## Quick Start

### Using LLM Providers

```python
from jeeves_infra.llm import OpenAIHTTPProvider

# Create provider for local LLM (Ollama, llama-server, etc.)
provider = OpenAIHTTPProvider(
    base_url="http://localhost:11434/v1",
    model="qwen2.5:7b",
)

# Generate completion
response = await provider.generate(
    messages=[{"role": "user", "content": "Hello!"}],
    max_tokens=100,
)
```

### Using the Runtime

```python
from jeeves_infra.runtime import Agent, PipelineRunner
from jeeves_infra.protocols import AgentConfig, PipelineConfig

# Configure pipeline
config = PipelineConfig(
    name="my_pipeline",
    max_iterations=10,
    agents=[
        AgentConfig(
            name="analyzer",
            has_llm=True,
            has_tools=True,
            default_next="executor",
        ),
    ],
)

# Create and run pipeline
runner = PipelineRunner(config)
result = await runner.run(task="Analyze this code")
```

### Connecting to Go Kernel

```python
from jeeves_infra.kernel_client import KernelClient
import grpc.aio as grpc_aio

# Connect to running Go kernel
channel = grpc_aio.insecure_channel("localhost:50051")
kernel = KernelClient(channel)

# Record metrics
await kernel.record_llm_call(pid="task-123", tokens_in=100, tokens_out=50)
```

## Package Structure

### jeeves_infra (Core)

| Module | Description |
|--------|-------------|
| `protocols` | Type definitions, interfaces, 230+ exports |
| `llm` | LLM providers (OpenAI HTTP, LiteLLM, Mock) |
| `runtime` | Agent execution, pipeline runner |
| `kernel_client` | gRPC client for Go kernel |
| `postgres` | PostgreSQL + pgvector clients |
| `redis` | Redis state backend |
| `gateway` | FastAPI HTTP/WebSocket/gRPC gateway |
| `observability` | Prometheus metrics, structured logging |
| `tools` | Tool executor and registry |

### mission_system (Orchestration)

Higher-level orchestration infrastructure:

| Module | Description |
|--------|-------------|
| `orchestrator` | Capability-agnostic orchestration |
| `prompts` | Prompt templates and blocks |
| `profiles` | Agent configuration profiles |

## Configuration

### Environment Variables

```bash
# Database
export JEEVES_DATABASE_URL="postgresql://user:pass@localhost/jeeves"

# LLM Provider
export JEEVES_LLM_ADAPTER="openai_http"
export JEEVES_LLM_BASE_URL="http://localhost:11434/v1"
export JEEVES_LLM_MODEL="qwen2.5:7b"

# Go Kernel
export KERNEL_GRPC_ADDRESS="localhost:50051"

# Metrics
export JEEVES_METRICS_PORT="9090"
```

## Requirements

- Python 3.11+
- gRPC and protobuf (core)
- Go kernel running for full functionality

## Related Projects

- [jeeves-core](https://github.com/Jeeves-Cluster-Organization/jeeves-core) - Go micro-kernel
- [mini-swe-agent](https://github.com/Jeeves-Cluster-Organization/mini-swe-agent) - Software engineering capability

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

Apache License 2.0 - see [LICENSE](LICENSE) for details.

```
Copyright 2024 Jeeves Cluster Organization

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```
