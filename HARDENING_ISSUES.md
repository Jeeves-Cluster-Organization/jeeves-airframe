# Jeeves-Airframe Hardening Issue Tracker

Systematic audit of `jeeves-airframe` — **revised after `48d3acc` refactor**
(complete postgres decoupling, code_indexer moved to capability layer,
chat_service unified to single SQL dialect, memory layers registry-driven).

Revision history:
- **v1** — Initial 20-issue audit
- **v2** — Re-evaluated after `b5de73b` (protocol-based DB registry)
- **v3** (current) — Re-evaluated after `48d3acc` (complete postgres decoupling)

20 open issues across 6 buckets. 3 resolved total.

---

## Bucket 1 — SQL Injection & Code Execution

### H-01: `eval()` on database data (RCE)
| | |
|---|---|
| **Severity** | ~~CRITICAL~~ |
| **Status** | RESOLVED in `b5de73b` — `pgvector_repository.py` deleted. |

### H-02: SQL injection via unvalidated filter-dictionary keys
| | |
|---|---|
| **Severity** | CRITICAL |
| **Status** | STILL PRESENT |
| **File** | `mission_system/memory/sql_adapter.py:205-208` |
| **Issue** | `filters` dict keys are f-string-interpolated into WHERE clauses (`f"{key} = ?"`). A crafted key like `"domain OR 1=1 --"` breaks out of the clause. |
| **Fix** | Validate keys against a per-table column allowlist before interpolation. |

### H-02b: SQL injection via unvalidated update-dictionary keys
| | |
|---|---|
| **Severity** | CRITICAL |
| **Status** | STILL PRESENT |
| **File** | `mission_system/memory/sql_adapter.py:271-272` |
| **Issue** | Same pattern as H-02 but in UPDATE SET clauses: `f"{key} = ?"`. |
| **Fix** | Same allowlist approach as H-02. |

### H-02c: SQL injection via `db.insert()` dictionary keys (NEW)
| | |
|---|---|
| **Severity** | HIGH |
| **Status** | NEW — surface expanded by `48d3acc` |
| **File** | `mission_system/memory/sql_adapter.py:97` (calls `db.insert("messages", message_data)`) → `tests/fixtures/sqlite_client.py:65-67` |
| **Issue** | `sql_adapter.write_message()` was refactored from parameterized INSERT to `db.insert("messages", message_data)` where `message_data` is a dict with hardcoded keys. Currently safe because keys are set in code, but the `insert()` method trusts all dict keys unconditionally. Any future caller passing user-influenced keys hits injection. This widens the attack surface created by H-03b. |
| **Fix** | The `db.insert()` / `db.update()` helpers should validate column names against a schema allowlist. |

### H-03: SQL injection via table/column interpolation in generic DB helpers
| | |
|---|---|
| **Severity** | ~~HIGH~~ |
| **Status** | RESOLVED in `b5de73b` — `postgres/client.py` deleted. |

### H-03b: Unsafe dynamic SQL in SQLite test fixture
| | |
|---|---|
| **Severity** | MEDIUM |
| **Status** | STILL PRESENT |
| **File** | `tests/fixtures/sqlite_client.py:65-67, 90` |
| **Issue** | `table` and column names from `data.keys()` are f-string interpolated without validation. |
| **Fix** | Add a table/column allowlist constant and validate before interpolation. |

---

## Bucket 2 — Authentication & Authorization

### H-04: No authentication on REST or WebSocket endpoints
| | |
|---|---|
| **Severity** | HIGH |
| **Status** | STILL PRESENT |
| **Files** | `jeeves_infra/gateway/routers/chat.py` (all endpoints), `jeeves_infra/gateway/app.py:309` |
| **Issue** | Every HTTP and WebSocket endpoint is open. `websocket_manager.py` has auth logic but it is never invoked. |
| **Fix** | Add auth middleware (JWT / API-key) to FastAPI; call `websocket_manager` auth from the endpoint. |

### H-05: CORS wildcard with `allow_credentials=True`
| | |
|---|---|
| **Severity** | HIGH |
| **Status** | STILL PRESENT |
| **File** | `jeeves_infra/gateway/app.py:64,154-155` |
| **Issue** | `CORS_ORIGINS` defaults to `"*"` with `allow_credentials=True`. |
| **Fix** | Default to localhost-only; require explicit production origins. |

### H-06: Hardcoded WebSocket dev token
| | |
|---|---|
| **Severity** | MEDIUM |
| **Status** | STILL PRESENT |
| **File** | `jeeves_infra/settings.py:165-166` |
| **Issue** | `websocket_auth_token = "local-dev-token"` and `websocket_auth_required = False`. |
| **Fix** | Remove default token; require env var when auth is enabled. |

---

## Bucket 3 — Insecure Defaults & Configuration

### H-07: Empty default database password
| | |
|---|---|
| **Severity** | MEDIUM |
| **Status** | STILL PRESENT — field renamed but default unchanged |
| **File** | `jeeves_infra/settings.py:196` (was `postgres_password`, now `db_password`) |
| **Issue** | `db_password: str = ""`. Connects with empty password if env var missing. |
| **48d3acc change** | Renamed from `postgres_password` to `db_password`. Default still empty string. |
| **Fix** | Require non-empty password or add startup validation outside dev mode. |

### H-07b: Hardcoded test database password in plain text (NEW)
| | |
|---|---|
| **Severity** | LOW |
| **Status** | NEW — visible after audit of test config renames |
| **Files** | `tests/config/environment.py:42`, `mission_system/tests/config/environment.py:42` |
| **Issue** | `TEST_DB_PASSWORD = os.getenv("DB_PASSWORD") or os.getenv("TEST_DB_PASSWORD", "dev_password_change_in_production")`. The default password is a string that says "change in production" but is trivially discoverable and could be used if anyone copies the test config to production. |
| **Fix** | Use an empty default and document the required env var. |

### H-08: No TLS enforcement and no security response headers
| | |
|---|---|
| **Severity** | MEDIUM |
| **Status** | STILL PRESENT |
| **File** | `jeeves_infra/gateway/app.py` |
| **Fix** | Add `SecurityHeadersMiddleware`; enforce TLS at reverse-proxy or app level. |

---

## Bucket 4 — Reliability & Error Handling

### H-09: 169 bare `except Exception` across 54 files
| | |
|---|---|
| **Severity** | HIGH |
| **Status** | STILL PRESENT — code_indexer deletion removed ~8, but count unchanged in remaining files |
| **Files** | Worst offenders: `gateway_chat.py` (11), `gateway/routers/chat.py` (7), `llm/gateway.py` (6), `sql_adapter.py` (6) |
| **Fix** | Narrow to specific exception types in the top 10 worst-offender files. |

### H-10: Fire-and-forget `asyncio.create_task()` with no error handling
| | |
|---|---|
| **Severity** | MEDIUM |
| **Status** | PARTIALLY IMPROVED |
| **Files** | Still unhandled: `gateway/sse.py:171`, `event_emitter.py:437`, `trace_recorder.py:291`, `websocket_manager.py:148` |
| **Fix** | Store refs and attach `add_done_callback` or use `TaskGroup`. |

### H-11: Low `try/finally` ratio — resource leak risk
| | |
|---|---|
| **Severity** | MEDIUM |
| **Status** | STILL PRESENT |
| **Fix** | Audit try blocks acquiring resources; ensure `finally` / `async with` / `AsyncExitStack`. |

### H-12: LLM fallback logic treats all errors as retriable
| | |
|---|---|
| **Severity** | MEDIUM |
| **Status** | STILL PRESENT |
| **File** | `jeeves_infra/llm/gateway.py:263-320` |
| **Fix** | Classify into retriable vs. fatal; only fall back on transient errors. |

---

## Bucket 5 — Operational Readiness

### H-13: Rate-limiting middleware exists but is not wired into the gateway
| | |
|---|---|
| **Severity** | HIGH |
| **Status** | STILL PRESENT |
| **Fix** | Import and add middleware to FastAPI startup in `gateway/app.py`. |

### H-14: No request payload size limits
| | |
|---|---|
| **Severity** | MEDIUM |
| **Status** | STILL PRESENT |
| **Fix** | Set `--limit-request-body` on uvicorn or add body-size middleware. |

### H-15: No CI/CD pipeline
| | |
|---|---|
| **Severity** | HIGH |
| **Status** | STILL ABSENT |
| **Fix** | Add GitHub Actions workflow running `ruff`, `mypy`, `pytest` on every PR. |

### H-16: No Dockerfile or docker-compose
| | |
|---|---|
| **Severity** | MEDIUM |
| **Status** | STILL ABSENT |
| **Fix** | Add multi-stage `Dockerfile` and `docker-compose.yml` for local dev. |

---

## Bucket 6 — Build, Deps & Test Infrastructure

### H-17: All dependencies unpinned with no lockfile
| | |
|---|---|
| **Severity** | HIGH |
| **Status** | STILL PRESENT |
| **Files** | `pyproject.toml:27-69`, `mission_system/pyproject.toml:24-36` |
| **48d3acc note** | `sqlalchemy[asyncio]` removed from optional deps and `database` extra removed from `[all]`. Reduces dep surface but remaining deps still unpinned. |
| **Fix** | Pin upper bounds or adopt `pip-tools`/`poetry` with a committed lockfile. |

### H-18: No test-coverage threshold enforced
| | |
|---|---|
| **Severity** | MEDIUM |
| **Status** | STILL PRESENT |
| **Fix** | Add `--cov-fail-under=80` to pytest addopts. |

### H-18b: `testpaths` excludes `mission_system/tests`
| | |
|---|---|
| **Severity** | MEDIUM |
| **Status** | STILL PRESENT |
| **File** | `pyproject.toml:95` — `testpaths = ["tests"]` |
| **Fix** | Change to `testpaths = ["tests", "mission_system/tests"]`. |

### H-18c: M1 contract gap — `source_type` not enforced at schema level
| | |
|---|---|
| **Severity** | MEDIUM |
| **Status** | STILL PRESENT |
| **Files** | `tests/fixtures/test_schema.sql:273`, `test_memory_contract_m1_canonical.py:172-182` |
| **Fix** | Add `CHECK (source_type IN ('fact', 'message', 'code'))` to schema. |

### H-19: `mission_system` allows Python 3.10 (EOL)
| | |
|---|---|
| **Severity** | LOW |
| **Status** | STILL PRESENT |
| **Fix** | Align to `requires-python = ">=3.11"`. |

### H-20: Unsafe `int()` casts on env vars
| | |
|---|---|
| **Severity** | LOW |
| **Status** | STILL PRESENT — `48d3acc` did not address unsafe `int()` casts in test config |
| **Files** | `jeeves_infra/gateway/app.py:61-63`, `mission_system/bootstrap.py:134-144`, `tests/config/environment.py:41,88` |
| **Fix** | Extend Pydantic Settings to all env-var parsing. |

---

## Revised Priority Matrix

| Priority | Issues | Theme |
|----------|--------|-------|
| **P0 — Fix immediately** | H-02, H-02b, H-02c, H-04, H-05 | SQL injection, no auth, CORS |
| **P1 — Fix before production** | H-06, H-07, H-09, H-13, H-15, H-17 | Insecure defaults, broad catches, rate-limit, CI, deps |
| **P2 — Fix soon** | H-03b, H-07b, H-08, H-10, H-11, H-12, H-14, H-16, H-18, H-18b, H-18c | Test SQL, TLS, async, leaks, coverage, contracts |
| **P3 — Improve** | H-19, H-20 | Python version, env-var parsing |

---

## `48d3acc` Delta Summary

### What this refactor did
- **Settings decoupled**: `postgres_*` fields renamed to `db_*`; `database_backend` is now a configurable string (default `"sqlite"`) instead of hardcoded `"postgres"` property
- **`sqlalchemy[asyncio]` dropped** from optional dependencies and `database` extra removed
- **`code_indexer.py` gutted** (562 → 12 lines): replaced with a stub that raises `ImportError` pointing to `jeeves_capability_hello_world`
- **`chat_service.py` unified**: eliminated `is_postgres` branch — single SQL dialect using `?` params and Python `datetime`/`timedelta` for filters (was dual Postgres/SQLite paths)
- **`sql_adapter.py`**: `write_message()` refactored from raw `INSERT...RETURNING` to `db.insert("messages", dict)` — removes Postgres-specific `RETURNING` but routes through unvalidated `insert()` helper
- **Memory layers**: hardcoded `MEMORY_LAYER_DEFINITIONS` in governance_service removed; now fetched from `CapabilityResourceRegistry.get_memory_layers()` — proper registry pattern
- **Capability protocol**: `CapabilityResourceRegistry` gained `register_memory_layers()` / `get_memory_layers()` methods
- **Test config**: all `POSTGRES_*` env vars renamed to `DB_*`; `requires_postgres` marker renamed to `requires_database`; `is_postgres_available` → `is_database_available`; test backend is now configurable via `TEST_DATABASE_BACKEND` env var (was hardcoded `Literal["postgres"]`)
- **`parse_postgres_url` → `parse_database_url`**: function renamed, keys changed (`POSTGRES_HOST` → `DB_HOST`, etc.), default user changed from `"postgres"` to `"assistant"`
- **Proto**: `MemoryLayerInfo.backend` comment updated from `postgres, pgvector` to `relational, vector, none`
- **Health router**: `DATABASE_BACKEND` default changed from `"postgres"` to `"unknown"`

### Resolved (1 additional)
- **H-09 (partial)**: `code_indexer.py` deletion removed ~8 `except Exception` blocks — reduces count from ~169 to ~161

### New issues (2 opened)
- **H-02c**: `db.insert()` now used from `sql_adapter.write_message()` — widens untrusted-key-in-SQL surface
- **H-07b**: Test config hardcodes `"dev_password_change_in_production"` as default password

### Issues improved but not closed
- **H-07**: Field renamed `postgres_password` → `db_password`, but default still empty string
- **H-17**: `sqlalchemy[asyncio]` removed from deps, reducing attack surface, but remaining deps still unpinned
- **H-20**: `48d3acc` added more `int()` casts in test config (`TEST_DB_PORT`, `DB_CONTAINER_TIMEOUT`) — issue slightly worsened

### Net: 20 open issues (was 20; closed 3 total, opened 6 total → 26 tracked, 3 resolved + 3 partially improved)

---

## Counts by Bucket

| Bucket | Open | Resolved | P0 | P1 | P2 | P3 |
|--------|------|----------|----|----|----|----|
| SQL Injection & Code Exec | 3 | 2 | 3 | — | 1 | — |
| Auth & Authorization | 3 | — | 2 | 1 | — | — |
| Insecure Defaults | 3 | — | — | 1 | 2 | — |
| Reliability & Errors | 4 | — | — | 1 | 3 | — |
| Operational Readiness | 4 | — | — | 2 | 2 | — |
| Build, Deps & Tests | 6 | — | — | 1 | 4 | 2 |
| **Total** | **23** | **2** | **5** | **6** | **12** | **2** |

---

## Cumulative Refactor Impact (b5de73b + 48d3acc)

| Metric | Before | After both refactors |
|--------|--------|---------------------|
| Total LOC deleted | — | ~5,700 |
| Postgres-specific code | ~2,800 LOC | 0 LOC |
| SQLAlchemy dependency | Required | Removed |
| DB backend | Hardcoded postgres | Registry-based, configurable |
| Code indexer | 562-line impl | 12-line stub (moved to capability) |
| Chat service | Dual SQL dialects | Single dialect |
| Memory layer config | Hardcoded in governance | Registry-driven |
| Test markers | `requires_postgres` | `requires_database` |
| **Security issues resolved** | — | **3** (H-01 eval RCE, H-03 postgres injection, code_indexer broad catches) |
| **Security issues introduced** | — | **6** (H-02b, H-02c, H-03b, H-07b, H-18b, H-18c) |
| **Net open issues** | 20 | 23 |

The two refactors successfully decoupled from PostgreSQL and reduced overall code surface by ~5,700 lines. However, the refactors focused on architectural flexibility, not security — and inadvertently widened the SQL injection surface by routing more operations through the unvalidated `db.insert()`/`db.update()` helpers. The 23 open issues should be addressed before production deployment.
