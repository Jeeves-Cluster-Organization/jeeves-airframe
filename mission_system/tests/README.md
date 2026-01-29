# Mission System Tests

**Constitutional Layer**: Application Orchestration (depends on Avionics + Core Engine)

**Location**: `mission_system/tests/`

---

## Overview

Mission System tests validate the orchestration framework, tools, and API layer. Tests follow the **LLAMASERVER_ALWAYS** policy: real LLM testing by default, with mock fallbacks only for CI.

### Constitutional Compliance

Per [Mission System Constitution](../CONSTITUTION.md):

- **R1: Evidence Chain Integrity (P1)** - Contract tests enforce citation requirements
- **R2: Tool Boundary (P1 + P3)** - Tests validate composite tool behavior
- **R3: Bounded Retry (P3)** - Tests verify retry limits and graceful degradation
- **Layer Contract** - Tests use `contracts.py` exports, not core_engine directly

---

## Test Structure

```
tests/
├── conftest.py                    # LLAMASERVER_ALWAYS policy, markers
├── acceptance/                    # Acceptance tests
│   └── test_pytest_imports.py
├── config/                        # Test configuration
│   ├── markers.py                 # Centralized marker configuration
│   ├── llm_config.py              # LLM provider configuration
│   ├── environment.py             # Environment detection
│   └── services.py                # Service availability checks
├── contract/                      # Constitutional compliance tests
│   ├── test_import_boundaries.py  # Layer boundary enforcement
│   ├── test_app_layer_boundaries.py  # App layer contract validation
│   └── test_evidence_chain.py     # P1 citation requirement tests
├── fixtures/                      # Test fixtures
│   ├── agents.py                  # Envelope fixtures (from contracts)
│   ├── database.py                # PostgreSQL fixtures
│   ├── llm.py                     # LLM fixtures (real llamaserver)
│   ├── services.py                # Service fixtures
│   └── mocks/
│       ├── core_mocks.py
│       └── avionics_mocks.py
├── unit/                          # Unit tests
│   ├── orchestrator/              # Orchestration tests
│   ├── test_confirmation_manager.py
│   └── test_websocket_event_manager.py
├── integration/                   # Integration tests
│   ├── test_api.py                # API endpoint tests
│   ├── test_gateway.py            # Gateway tests
│   ├── test_multistage_pipeline.py  # Multi-stage execution
│   └── test_checkpoint_recovery.py  # Checkpointing
└── e2e/                           # End-to-end tests
```

---

## Dependencies

### Lightweight (Contract/Unit Tests)

```bash
pip install pytest pytest-asyncio pydantic structlog
```

### Integration Tests

```bash
# API testing
pip install fastapi httpx websockets

# Database
pip install testcontainers psycopg2-binary pgvector
```

### E2E Tests (Full Stack)

```bash
# Real LLM (LLAMASERVER_ALWAYS policy)
# Requires llamaserver running on localhost:8080

# ML models (heavy)
pip install sentence-transformers  # 1.5GB+ download

# Start services
docker compose up -d postgres llama-server
```

---

## Running Tests

### Quick Start (Lightweight Tests Only)

```bash
# Contract tests (fast, no services required)
pytest mission_system/tests/contract -v

# Expected: Import boundary and layer validation tests pass
```

### Unit Tests (No External Services)

```bash
# Run unit tests with mocked dependencies
pytest mission_system/tests/unit -m "not requires_llamaserver and not requires_postgres"

# Expected: Orchestrator logic, confirmation manager tests pass
```

### Integration Tests (Requires Services)

```bash
# Start services
docker compose up -d postgres llama-server

# Run integration tests
pytest mission_system/tests/integration -v

# Expected: API, gateway, multi-stage pipeline tests pass
```

### E2E Tests (Full Stack)

```bash
# Requires all services running
docker compose up -d

# Run E2E tests
pytest mission_system/tests -m e2e

# Expected: Full 7-agent pipeline execution with real LLM
```

### Test Tiers

**Tier 1: Contract Tests (No Dependencies)**
```bash
pytest mission_system/tests/contract -v
# Import boundaries, layer contracts, evidence chain validation
# Runtime: < 5 seconds
```

**Tier 2: Unit Tests (Mock LLM)**
```bash
pytest mission_system/tests/unit \
  -m "not requires_llamaserver and not requires_postgres" \
  -v
# Orchestrator, rate limiter, confirmation manager
# Runtime: < 10 seconds
```

**Tier 3: Integration Tests (Real Services)**
```bash
pytest mission_system/tests/integration \
  -m "requires_postgres or requires_llamaserver" \
  -v
# API endpoints, gateway, multi-stage pipeline
# Runtime: 30-60 seconds
```

**Tier 4: E2E Tests (Full Stack)**
```bash
pytest mission_system/tests -m e2e -v
# Complete 7-agent pipeline with real LLM
# Runtime: 60+ seconds
```

---

## Test Markers

Mission System uses comprehensive markers defined in `tests/config/markers.py`:

### LLM/Service Markers
- **`@pytest.mark.e2e`** - End-to-end tests requiring real LLM
- **`@pytest.mark.requires_llamaserver`** - Tests requiring llama-server
- **`@pytest.mark.requires_azure`** - Tests requiring Azure OpenAI SDK
- **`@pytest.mark.uses_llm`** - Tests that call LLM (requires real llamaserver)
- **`@pytest.mark.requires_llm_quality`** - Tests requiring capable LLM (7B+) for nuanced NLP

### Infrastructure Markers
- **`@pytest.mark.requires_services`** - Tests requiring full Docker stack (postgres + llama-server)
- **`@pytest.mark.requires_postgres`** - Tests requiring PostgreSQL only
- **`@pytest.mark.requires_docker`** - Tests requiring Docker/testcontainers
- **`@pytest.mark.requires_full_app`** - Tests using TestClient with full app lifespan
- **`@pytest.mark.websocket`** - WebSocket tests (requires services)

### Heavy Dependencies
- **`@pytest.mark.heavy`** - Tests with heavy dependencies (ML models, large downloads)
- **`@pytest.mark.requires_ml`** - Tests requiring ML models (sentence-transformers)
- **`@pytest.mark.requires_openai`** - Tests requiring OpenAI package
- **`@pytest.mark.requires_anthropic`** - Tests requiring Anthropic package

### Test Categories
- **`@pytest.mark.slow`** - Slow-running tests (> 5 seconds)
- **`@pytest.mark.contract`** - Constitution/contract validation tests
- **`@pytest.mark.v2_memory`** - V2 memory infrastructure tests
- **`@pytest.mark.prod`** - Production tests (requires `PROD_TESTS_ENABLED=1`)

### Auto-Skip Logic

Markers automatically skip tests when dependencies unavailable (defined in `markers.py`):

```python
# Test marked with @pytest.mark.requires_llamaserver
# Auto-skipped if llamaserver not reachable at localhost:8080
# Skip message: "llama-server not available - run: docker compose up -d llama-server"
```

---

## Fixtures Provided

### Envelope Fixtures (from contracts)

- **`envelope_factory`** - Creates envelopes via `mission_system.contracts`
- **`sample_envelope`** - Basic envelope for tests
- **`envelope_with_perception`** - Envelope at PERCEPTION stage
- **`envelope_with_intent`** - Envelope with IntentOutput
- **`envelope_with_plan`** - Envelope with PlanOutput
- **`envelope_with_execution`** - Envelope with ExecutionOutput
- **`envelope_with_synthesizer`** - Envelope with SynthesizerOutput
- **`envelope_with_critic`** - Envelope with CriticOutput

**Example**:
```python
from mission_system.contracts import EnvelopeStage

def test_intent_stage(envelope_with_perception):
    """Test starting from INTENT stage."""
    envelope = envelope_with_perception
    assert envelope.stage == EnvelopeStage.INTENT
    assert envelope.perception is not None
```

### LLM Fixtures

- **`llm_provider`** - Real llamaserver provider (LLAMASERVER_ALWAYS policy)
- **`schema_path`** - Path to JSON schemas for structured output

**Example**:
```python
@pytest.mark.requires_llamaserver
async def test_llm_generation(llm_provider):
    """Test with real LLM."""
    response = await llm_provider.generate(
        prompt="List 3 colors",
        agent_role="planner"
    )
    assert len(response) > 0
```

### Database Fixtures

- **`postgres_container`** - PostgreSQL testcontainer
- **`pg_test_db`** - Fresh database per test
- **`create_test_prerequisites`** - Creates test schema
- **`create_session_only`** - Creates sessions table only

### Service Fixtures

- **`session_service`** - Session state service
- **`tool_health_service`** - Tool health tracking service
- **`tool_registry`** - Tool registry with 9 composite tools

### Mock Fixtures

- **`mock_db`** - Mock database client
- **`mock_tool_executor`** - Mock tool executor
- **`mock_llm_provider`** - Mock LLM (for unit tests without llamaserver)

---

## Test Coverage

### ✅ Contract Tests (Fast, No Dependencies)

**Files**: `contract/test_import_boundaries.py`, `test_app_layer_boundaries.py`, `test_evidence_chain.py`

**What's Tested**:
- Core engine MUST NOT import from avionics/mission
- Avionics MUST NOT import from mission system
- Mission system MUST NOT import from app layer
- App layer MUST use `mission_system.contracts` (not core_engine directly)
- Evidence chain integrity (P1 enforcement)

**Example**:
```python
def test_core_engine_no_mission_imports():
    """Core engine must not import from mission system."""
    core_imports = extract_imports("coreengine/")
    assert not any(
        "mission_system" in imp for imp in core_imports
    ), "Core imports from mission system (boundary violation)"
```

### ✅ Unit Tests (Mock LLM)

**Files**: `unit/orchestrator/`, `unit/test_confirmation_manager.py`, etc.

**What's Tested**:
- Orchestrator routing logic (REPLAN, NEXT_STAGE, COMPLETE)
- Confirmation manager (risky operations)
- WebSocket event manager
- Node profiles and event context

Note: Rate limiting is handled by `control_tower` - see `control_tower/resources/rate_limiter.py`.

**Example**:
```python
@pytest.mark.asyncio
async def test_confirmation_manager():
    """Confirmation manager tracks risky operations."""
    manager = ConfirmationManager()
    await manager.request_confirmation("delete_file", "/path/to/file")
    assert manager.has_pending_confirmation("delete_file")
```

### ⚠️ Integration Tests (Requires Services)

**Files**: `integration/test_api.py`, `test_gateway.py`, `test_multistage_pipeline.py`

**Requires**: PostgreSQL, llamaserver

**What's Tested**:
- API endpoints (`POST /api/v1/chat/messages`, etc.)
- Gateway routers and SSE streaming
- Multi-stage pipeline execution
- Checkpoint recovery
- WebSocket connections

**Flakiness Note**: Integration tests may be flaky due to:
- Network timeouts to llamaserver
- LLM non-deterministic responses
- Database race conditions
- Async timing issues

**Mitigation Strategies**:
```python
# 1. Add timeout markers
@pytest.mark.timeout(30)
async def test_api_endpoint():
    ...

# 2. Add retry for flaky tests
@pytest.mark.flaky(reruns=3, reruns_delay=2)
async def test_llm_integration():
    ...

# 3. Use mock LLM for deterministic tests
@pytest.mark.unit
async def test_pipeline_logic(mock_llm_provider):
    # Deterministic - no real LLM calls
    ...
```

### ⚠️ E2E Tests (Full Stack Required)

**Files**: `e2e/` (if present)

**Requires**: Full Docker stack + real LLM

**What's Tested**:
- Complete 7-agent pipeline execution
- Real tool execution (read_code, grep_search, etc.)
- Real LLM reasoning and decision-making
- Evidence chain from tool → synthesizer → response

**LLAMASERVER_ALWAYS Policy**:
- E2E tests REQUIRE real LLM (no mock fallback)
- Auto-skip if llamaserver not available
- Use capable model (7B+) for nuanced NLP tasks

---

## Flakiness Investigation & Mitigation

Per audit findings: "Tests in mission_system are a bit more flakey"

### Root Causes

1. **LLM Non-Determinism**
   - Real LLM responses vary between runs
   - Small models (< 7B) struggle with JSON formatting
   - **Fix**: Use `@pytest.mark.requires_llm_quality` for tests requiring capable models

2. **Network Timeouts**
   - Llamaserver may be slow to respond
   - Docker containers may not be ready
   - **Fix**: Add `@pytest.mark.timeout(30)` and health checks

3. **Database Race Conditions**
   - Concurrent test execution may conflict
   - Shared session state between tests
   - **Fix**: Use `pg_test_db` fixture for isolated database per test

4. **Async Timing Issues**
   - WebSocket connection timing
   - Event emission timing
   - **Fix**: Add `await asyncio.sleep(0.1)` or use proper async barriers

### Recommended Markers for Flaky Tests

```python
# Option 1: Increase timeout
@pytest.mark.timeout(60)  # Fail after 60s instead of 30s
async def test_slow_llm_operation():
    ...

# Option 2: Allow retries
@pytest.mark.flaky(reruns=3, reruns_delay=2)
async def test_network_dependent():
    ...

# Option 3: Require capable LLM
@pytest.mark.requires_llm_quality  # Skip if model < 7B
async def test_nuanced_nlp():
    ...

# Option 4: Skip in CI
@pytest.mark.skipif(IS_CI, reason="Flaky in CI environment")
async def test_timing_sensitive():
    ...
```

---

## CI/CD Integration

### Fast CI (Contract + Unit Tests)

```yaml
# .github/workflows/test-mission-fast.yml
jobs:
  test-mission-fast:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
      - run: |
          pip install pytest pytest-asyncio pydantic structlog
          # Contract tests (no dependencies)
          pytest mission_system/tests/contract -v
          # Unit tests (no services)
          pytest mission_system/tests/unit \
            -m "not requires_llamaserver and not requires_postgres" \
            -v
```

**Expected**: Contract + unit tests pass in < 10 seconds

### Integration CI (With Services)

```yaml
# .github/workflows/test-mission-integration.yml
jobs:
  test-mission-integration:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg16
      llama-server:
        image: ghcr.io/ggerganov/llama.cpp:server
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
      - run: |
          pip install -r requirements/test.txt
          pytest mission_system/tests/integration \
            -m "not e2e and not heavy" \
            -v
```

**Expected**: Integration tests pass in 30-60 seconds

### Nightly CI (E2E + Heavy Tests)

```yaml
# .github/workflows/test-mission-nightly.yml
on:
  schedule:
    - cron: '0 2 * * *'  # 2 AM daily
jobs:
  test-mission-e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - run: |
          docker compose up -d
          pytest mission_system/tests -m e2e -v
```

**Expected**: Full E2E tests pass (may take 5+ minutes)

---

## Development Workflow

### 1. Run Contract Tests First

```bash
# Fastest - validates constitutional compliance
pytest mission_system/tests/contract -v

# Should always pass (no external deps)
```

### 2. Run Unit Tests During Development

```bash
# Fast feedback loop with mocked LLM
pytest mission_system/tests/unit \
  -m "not requires_llamaserver" \
  -v

# Watch mode
pytest-watch mission_system/tests/unit
```

### 3. Run Integration Tests Before PR

```bash
# Start services
docker compose up -d postgres llama-server

# Run integration tests
pytest mission_system/tests/integration -v
```

### 4. Run E2E Tests Before Merge

```bash
# Full stack validation
docker compose up -d
pytest mission_system/tests -m e2e -v
```

---

## Common Issues

### Issue 1: llamaserver Not Available

**Error**: `llama-server not available - run: docker compose up -d llama-server`

**Solution**:
```bash
docker compose up -d llama-server
# Wait for health check
curl http://localhost:8080/health
```

### Issue 2: PostgreSQL Not Available

**Error**: `PostgreSQL not available - run: docker compose up -d postgres`

**Solution**:
```bash
docker compose up -d postgres
# Verify connection
docker compose ps postgres
```

### Issue 3: Flaky Test Failures

**Error**: Test passes sometimes, fails other times

**Solution**:
```python
# Add timeout
@pytest.mark.timeout(60)

# Add retry
@pytest.mark.flaky(reruns=3)

# Or skip in CI
@pytest.mark.skipif(IS_CI, reason="Flaky in CI")
```

### Issue 4: Small Model Failures

**Error**: Test requires nuanced NLP, small model (3B) fails

**Solution**:
```python
# Mark test as requiring capable model
@pytest.mark.requires_llm_quality
async def test_intent_extraction():
    # Auto-skips if model < 7B
    ...
```

---

## Related Documentation

- **Constitution**: [../CONSTITUTION.md](../CONSTITUTION.md) - Mission System rules
- **Test Configuration**: [config/markers.py](config/markers.py) - Marker definitions
- **Protocols Tests**: [../../protocols/tests/](../../protocols/tests/)
- **Avionics Tests**: [../../avionics/tests/README.md](../../avionics/tests/README.md)
- **Capability Layer Tests**: Test documentation in respective capability repositories

## Dependencies Note

**Foundation Layers**:
- **L0: protocols** - Protocol definitions, InterruptKind enum, Envelope
- **L0: shared** - Shared utilities (logging via `get_component_logger`, serialization, UUID)
- **L1: jeeves-airframe** - Inference platform substrate (backend adapters for HTTP, SSE, retries)
- **L3: avionics** - Infrastructure orchestration (LLM providers delegate to Airframe)

Tests should import from these foundation layers for types and utilities:
```python
from protocols import Envelope, InterruptKind
from shared import get_component_logger, parse_datetime
from jeeves_infra.llm import LLMProvider  # Delegates to Airframe adapters
```

---

**Last Updated**: 2025-12-16
**Test Files**: 40
**Contract Tests**: Fast (< 5s)
**Unit Tests**: Fast with mocks (< 10s)
**Integration Tests**: Requires services (30-60s)
**E2E Tests**: Requires full stack (60+ s)
**Known Issue**: Some integration tests are flaky (LLM non-determinism, network timing)
