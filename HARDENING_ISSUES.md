# Jeeves-Airframe Hardening Issue Tracker

Systematic audit of `jeeves-airframe` — **revised after `b5de73b` refactor**
(protocol-based DB registry, postgres-specific code removed, SQLite test infra added).

20 issues grouped into 6 buckets.  Each has a severity, status vs. prior audit,
affected files, and remediation note.

---

## Bucket 1 — SQL Injection & Code Execution

### H-01: `eval()` on database data (RCE)
| | |
|---|---|
| **Severity** | ~~CRITICAL~~ |
| **Status** | RESOLVED — `pgvector_repository.py` deleted in `b5de73b`. Replacement uses `json.loads()`. |

### H-02: SQL injection via unvalidated filter-dictionary keys
| | |
|---|---|
| **Severity** | CRITICAL |
| **Status** | STILL PRESENT — migrated from pgvector to sql_adapter |
| **File** | `mission_system/memory/sql_adapter.py:205-208` |
| **Issue** | `filters` dict keys are f-string-interpolated into WHERE clauses (`f"{key} = ?"`). A crafted key like `"domain OR 1=1 --"` breaks out of the clause. |
| **Fix** | Validate keys against a per-table column allowlist before interpolation. |

### H-02b: SQL injection via unvalidated update-dictionary keys (NEW)
| | |
|---|---|
| **Severity** | CRITICAL |
| **Status** | NEW — introduced in same refactor |
| **File** | `mission_system/memory/sql_adapter.py:271-272` |
| **Issue** | Same pattern as H-02 but in UPDATE SET clauses: `f"{key} = ?"`. |
| **Fix** | Same allowlist approach as H-02. |

### H-03: SQL injection via table/column interpolation in generic DB helpers
| | |
|---|---|
| **Severity** | ~~HIGH~~ |
| **Status** | RESOLVED — `postgres/client.py` deleted. Remaining table-name interpolation in `sql_adapter.py` uses a hardcoded `type_to_table` mapping with validation (lines 138-141, 195-198). |

### H-03b: Unsafe dynamic SQL in SQLite test fixture (NEW)
| | |
|---|---|
| **Severity** | MEDIUM |
| **Status** | NEW |
| **File** | `tests/fixtures/sqlite_client.py:65-67, 90` |
| **Issue** | `table` and column names from `data.keys()` are f-string interpolated. Currently only called with hardcoded values from test fixtures, but no guard prevents misuse. |
| **Fix** | Add a table allowlist constant and validate before interpolation. |

---

## Bucket 2 — Authentication & Authorization

### H-04: No authentication on REST or WebSocket endpoints
| | |
|---|---|
| **Severity** | HIGH |
| **Status** | STILL PRESENT |
| **Files** | `jeeves_infra/gateway/routers/chat.py` (all endpoints), `jeeves_infra/gateway/app.py:309` |
| **Issue** | Every HTTP and WebSocket endpoint is open. `websocket_manager.py` has auth validation logic (lines 73-85) but it is **never invoked** from the actual endpoint handler. |
| **Fix** | Add auth middleware (JWT / API-key) to FastAPI; call `websocket_manager` auth from the endpoint. |

### H-05: CORS wildcard with `allow_credentials=True`
| | |
|---|---|
| **Severity** | HIGH |
| **Status** | STILL PRESENT |
| **File** | `jeeves_infra/gateway/app.py:64,154-155` |
| **Issue** | `CORS_ORIGINS` defaults to `"*"` combined with `allow_credentials=True`, `allow_methods=["*"]`, `allow_headers=["*"]`. Textbook misconfiguration enabling cross-origin credential theft. |
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

### H-07: Empty default PostgreSQL password
| | |
|---|---|
| **Severity** | MEDIUM |
| **Status** | STILL PRESENT |
| **File** | `jeeves_infra/settings.py:195` |
| **Issue** | `postgres_password: str = ""`. Connects with empty password if env var missing. |
| **Fix** | Require non-empty password or add startup validation. |

### H-08: No TLS enforcement and no security response headers
| | |
|---|---|
| **Severity** | MEDIUM |
| **Status** | STILL PRESENT |
| **File** | `jeeves_infra/gateway/app.py` |
| **Issue** | No HTTPS redirect, no `Strict-Transport-Security`, `X-Frame-Options`, `X-Content-Type-Options`, or `Content-Security-Policy`. |
| **Fix** | Add `SecurityHeadersMiddleware`; enforce TLS at reverse-proxy or app level. |

---

## Bucket 4 — Reliability & Error Handling

### H-09: 169 bare `except Exception` across 54 files
| | |
|---|---|
| **Severity** | HIGH |
| **Status** | STILL PRESENT |
| **Files** | Worst offenders: `gateway_chat.py` (11), `gateway/routers/chat.py` (7), `llm/gateway.py` (6), `sql_adapter.py` (6), repositories (8 each) |
| **Issue** | Broad catches mask bugs, swallow unexpected errors, make debugging difficult. |
| **Fix** | Narrow to specific exception types. Prioritize the 10 worst-offender files first. |

### H-10: Fire-and-forget `asyncio.create_task()` with no error handling
| | |
|---|---|
| **Severity** | MEDIUM |
| **Status** | PARTIALLY IMPROVED — `memory/manager.py` now tracks tasks via `_track_task()` |
| **Files** | Still unhandled: `gateway/sse.py:171`, `event_emitter.py:437`, `trace_recorder.py:291`, `websocket_manager.py:148` |
| **Fix** | Store refs and attach `add_done_callback` or use `TaskGroup`. |

### H-11: Low `try/finally` ratio — resource leak risk
| | |
|---|---|
| **Severity** | MEDIUM |
| **Status** | STILL PRESENT |
| **Files** | `jeeves_infra/` — ~14.7% of try blocks have `finally` |
| **Fix** | Audit try blocks acquiring resources; ensure `finally` / `async with` / `AsyncExitStack`. |

### H-12: LLM fallback logic treats all errors as retriable
| | |
|---|---|
| **Severity** | MEDIUM |
| **Status** | STILL PRESENT |
| **File** | `jeeves_infra/llm/gateway.py:263-320` |
| **Issue** | Provider fallback catches `Exception` uniformly — does not distinguish 503 (retry) from 401 (fatal). |
| **Fix** | Classify into retriable vs. fatal; only fall back on transient errors. |

---

## Bucket 5 — Operational Readiness

### H-13: Rate-limiting middleware exists but is not wired into the gateway
| | |
|---|---|
| **Severity** | HIGH |
| **Status** | STILL PRESENT |
| **Files** | `jeeves_infra/middleware/rate_limit.py` (370-line impl), `jeeves_infra/gateway/app.py` (not imported) |
| **Fix** | Import and add middleware to FastAPI startup. |

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
| **Fix** | Pin upper bounds or adopt `pip-tools`/`poetry` with a committed lockfile. |

### H-18: No test-coverage threshold enforced
| | |
|---|---|
| **Severity** | MEDIUM |
| **Status** | STILL PRESENT |
| **File** | `pyproject.toml` (pytest config) |
| **Fix** | Add `--cov-fail-under=80` to pytest addopts. |

### H-18b: `testpaths` excludes `mission_system/tests` (NEW)
| | |
|---|---|
| **Severity** | MEDIUM |
| **Status** | NEW |
| **File** | `pyproject.toml:95` — `testpaths = ["tests"]` |
| **Issue** | `mission_system/tests/` is not in pytest discovery. Those tests only run if explicitly targeted. |
| **Fix** | Change to `testpaths = ["tests", "mission_system/tests"]`. |

### H-18c: M1 contract gap — `source_type` not enforced at schema level (NEW)
| | |
|---|---|
| **Severity** | MEDIUM |
| **Status** | NEW — documented as skip in contract test |
| **Files** | `tests/fixtures/test_schema.sql:273`, `mission_system/tests/contract/test_memory_contract_m1_canonical.py:172-182` |
| **Issue** | `semantic_chunks.source_type` allows arbitrary strings. Contract test skips rather than fails. |
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
| **Status** | STILL PRESENT |
| **Fix** | Extend Pydantic Settings to gateway and bootstrap configs. |

---

## Revised Priority Matrix

| Priority | Issues | Theme |
|----------|--------|-------|
| **P0 — Fix immediately** | H-02, H-02b, H-04, H-05 | SQL injection, no auth, CORS |
| **P1 — Fix before production** | H-06, H-07, H-09, H-13, H-15, H-17 | Insecure defaults, broad catches, rate-limit, CI, deps |
| **P2 — Fix soon** | H-03b, H-08, H-10, H-11, H-12, H-14, H-16, H-18, H-18b, H-18c | Test SQL, TLS, async, leaks, coverage, contracts |
| **P3 — Improve** | H-19, H-20 | Python version, env-var parsing |

---

## Post-Refactor Delta Summary

### Resolved (2 issues closed)
- **H-01** `eval()` RCE — file deleted, replacement uses `json.loads()`
- **H-03** Generic postgres helper SQL injection — file deleted, replacement validates via mapping

### New (4 issues opened)
- **H-02b** SQL injection via update dict keys in `sql_adapter.py`
- **H-03b** Unsafe dynamic SQL in `sqlite_client.py` test fixture
- **H-18b** `testpaths` excludes `mission_system/tests`
- **H-18c** M1 contract gap on `source_type` validation

### Net: 20 open issues (was 20; closed 2, opened 4 → 22 tracked, 2 resolved)

---

## Counts by Bucket

| Bucket | Open | Resolved | P0 | P1 | P2 | P3 |
|--------|------|----------|----|----|----|----|
| SQL Injection & Code Exec | 2 | 2 | 2 | — | 1 | — |
| Auth & Authorization | 3 | — | 2 | 1 | — | — |
| Insecure Defaults | 2 | — | — | 1 | 1 | — |
| Reliability & Errors | 4 | — | — | 1 | 3 | — |
| Operational Readiness | 4 | — | — | 2 | 2 | — |
| Build, Deps & Tests | 5 | — | — | 1 | 3 | 2 |
| **Total** | **20** | **2** | **4** | **6** | **10** | **2** |
