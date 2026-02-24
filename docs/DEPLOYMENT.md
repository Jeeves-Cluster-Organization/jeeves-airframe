# Deployment Guide

## Prerequisites

- Python 3.11+
- A running jeeves-core kernel (IPC on TCP)
- Redis (optional, for distributed state)

## Install

```bash
pip install -e ".[dev]"
```

## Configuration

Airframe is a library — capabilities (game, etc.) compose their own entry points and import airframe. Configuration is via environment variables.

### Gateway

| Env Var | Default | Description |
|---------|---------|-------------|
| `API_HOST` | `0.0.0.0` | API server bind address |
| `API_PORT` | `8000` | API server port |
| `CORS_ORIGINS` | `http://localhost:8000,http://localhost:3000` | Comma-separated allowed origins |
| `MAX_REQUEST_BODY_BYTES` | `1048576` (1 MB) | Max request body size |
| `DEBUG` | `false` | FastAPI debug mode |
| `JAEGER_ENDPOINT` | `jaeger:4317` | OpenTelemetry exporter endpoint |

### Kernel Connection

| Env Var | Default | Description |
|---------|---------|-------------|
| `ORCHESTRATOR_HOST` | `localhost` | Kernel IPC host |
| `ORCHESTRATOR_PORT` | `50051` | Kernel IPC port |
| `JEEVES_KERNEL_ADDRESS` | `localhost:50051` | Alternative: host:port for kernel client |

### LLM Providers

| Env Var | Default | Description |
|---------|---------|-------------|
| `JEEVES_LLM_ADAPTER` | `openai_http` | Provider: `openai_http`, `litellm`, `mock` |
| `JEEVES_LLM_MODEL` | — | Model identifier (required) |
| `JEEVES_LLM_BASE_URL` | — | API base URL |
| `JEEVES_LLM_API_KEY` | — | API key |
| `JEEVES_LLM_TIMEOUT` | `120` | Request timeout (seconds) |
| `JEEVES_LLM_MAX_RETRIES` | `3` | Max retry attempts |

Legacy provider vars (used by `Settings`):

| Env Var | Default | Description |
|---------|---------|-------------|
| `LLM_PROVIDER` | `llamaserver` | Provider type |
| `LLAMASERVER_HOST` | `http://localhost:8080` | Local LLM server |
| `OPENAI_API_KEY` | — | OpenAI key |
| `ANTHROPIC_API_KEY` | — | Anthropic key |

### Pipeline Defaults

| Env Var | Default | Description |
|---------|---------|-------------|
| `CORE_MAX_ITERATIONS` | `3` | Pipeline iterations per request |
| `CORE_MAX_LLM_CALLS` | `10` | LLM invocations per request |
| `CORE_MAX_AGENT_HOPS` | `21` | Agent transitions per request |
| `CORE_MAX_INPUT_TOKENS` | `4096` | Max input tokens |
| `CORE_MAX_OUTPUT_TOKENS` | `2048` | Max output tokens |
| `CORE_MAX_CONTEXT_TOKENS` | `16384` | Max context window |

### Redis (Optional)

| Env Var | Default | Description |
|---------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379` | Redis connection URL |
| `REDIS_POOL_SIZE` | `10` | Connection pool size |
| `FEATURE_USE_REDIS_STATE` | `false` | Enable Redis state backend |

### Rate Limiting

| Env Var | Default | Description |
|---------|---------|-------------|
| `REQUESTS_PER_MINUTE` | `60` | Per-user rate limit |
| `RATE_LIMIT_INTERVAL_SECONDS` | `60.0` | Sliding window duration |

### Logging

| Env Var | Default | Description |
|---------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Global log level |
| `FEATURE_ENABLE_TRACING` | `false` | OpenTelemetry tracing |
| `FEATURE_ENABLE_DEBUG_LOGGING` | `false` | Verbose debug output |

### Feature Flags

All feature flags use the `FEATURE_` prefix:

| Env Var | Default | Description |
|---------|---------|-------------|
| `FEATURE_ENABLE_DISTRIBUTED_MODE` | `false` | Multi-node deployment |
| `FEATURE_ENABLE_TRACING` | `false` | Distributed tracing |
| `FEATURE_MEMORY_SEMANTIC_MODE` | `log_and_use` | Semantic search: `disabled`, `log_only`, `log_and_use` |
| `FEATURE_MEMORY_WORKING_MEMORY` | `true` | Session summarization |
| `FEATURE_MEMORY_GRAPH_MODE` | `enabled` | Knowledge graph |

## Health Checks

- `GET /health` — Always returns 200 (liveness)
- `GET /ready` — Returns 200 when services are registered, 503 otherwise (readiness)

## Production Considerations

- Set `CORS_ORIGINS` to your actual frontend domain(s) — wildcard (`*`) with credentials is rejected at startup
- Set `LOG_LEVEL=WARNING` and `FEATURE_ENABLE_TRACING=true` for production observability
- Configure `JEEVES_LLM_*` vars for your LLM provider
- Redis credentials in `REDIS_URL` are automatically redacted in logs
- No TLS on kernel IPC — run kernel and airframe on the same host or behind a VPN
- Body size limit (1 MB default) applies to all HTTP endpoints
