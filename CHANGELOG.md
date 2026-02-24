# Changelog

All notable changes to jeeves-airframe will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `BodyLimitMiddleware` (ASGI) — rejects requests exceeding configurable size (default 1 MB)
- `max_request_body_bytes` field in `GatewayConfig`
- Rate limiting middleware error handling — returns 503 on kernel failure instead of crashing
- `redact_url()` utility in `utils/strings.py`
- Coverage configuration in `pyproject.toml` (`fail_under = 40`)
- 16 gateway unit tests (health, ready, root, body limit, CORS)
- 18 LLM provider unit tests (OpenAI HTTP, LiteLLM, factory)
- 83 orchestrator event tests
- 39 bootstrap tests
- Integration test scaffolding with `@pytest.mark.integration` gate
- GitHub Actions CI workflow (ruff, black, mypy, pytest-cov, pip-audit)
- Pre-commit hooks (ruff, black, mypy, trailing whitespace)

### Changed
- CORS default origins changed from `"*"` to `"http://localhost:8000,http://localhost:3000"`
- CORS wildcard + credentials combination now rejected at startup
- HTTP error responses in `chat.py` sanitized — 6 sites now return `"Internal server error"` instead of raw exception strings
- All 17 dependencies pinned with `<NEXT_MAJOR` upper bounds
- Redis URL credentials redacted in all 4 log sites (`client.py`, `connection_manager.py`)

### Removed
- `websocket_manager.py` and `websocket.py` (dead WebSocket code, ~280 lines)
- `/ws` endpoint and EventBridge wiring from `app.py`
- `TEST_WEBSOCKET_URL` from test configuration

### Fixed
- `event_context.py` parameter ordering for Python 3.13 compatibility
- `allow_credentials` extracted to `GatewayConfig` (was missing from CORS configuration)

## [0.1.0] - Initial release

Python infrastructure library for LLM agent orchestration.

- FastAPI gateway with health/ready endpoints and CORS
- Kernel IPC client (TCP + MessagePack transport)
- LLM provider abstraction (OpenAI HTTP, LiteLLM, mock) with factory
- Redis client and connection manager
- Event orchestration (emitter, context, bridge)
- Bootstrap system (`create_app_context`, config-from-env, quota sync)
- Rate limiting middleware (requires kernel)
- Structured logging and metrics
- String utilities (truncation, list normalization)
