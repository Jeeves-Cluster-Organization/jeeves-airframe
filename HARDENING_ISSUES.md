# Jeeves-Airframe Hardening Issue Tracker

Systematic audit of `jeeves-airframe` identifying the top 20 hardening issues,
grouped into 5 buckets by domain.  Each issue has a severity, affected files, and
a brief remediation note.

---

## Bucket 1 — Critical Security Vulnerabilities

### H-01: `eval()` on database data (RCE)
| | |
|---|---|
| **Severity** | CRITICAL |
| **File** | `mission_system/memory/repositories/pgvector_repository.py:369` |
| **Issue** | `eval(row.embedding)` parses a string from PostgreSQL. If the DB is compromised or a row is injected, arbitrary Python executes. |
| **Fix** | Replace with `json.loads()` or `ast.literal_eval()`. |

### H-02: SQL injection via unvalidated filter-dictionary keys
| | |
|---|---|
| **Severity** | CRITICAL |
| **File** | `mission_system/memory/repositories/pgvector_repository.py:214-216` |
| **Issue** | `filters` dict keys are interpolated directly into a WHERE clause (`f"{key} = :{param_name}"`). An attacker-controlled key like `"1=1; DROP TABLE--"` breaks out. |
| **Fix** | Validate keys against an allowlist of known column names before interpolation. |

### H-03: SQL injection via table/column name interpolation
| | |
|---|---|
| **Severity** | HIGH |
| **Files** | `jeeves_infra/postgres/client.py:639,672`, `mission_system/memory/sql_adapter.py:152,156,291,349,353` |
| **Issue** | Table and column names are f-string interpolated. While some paths use config-based allowlists, the `postgres/client.py` generic helpers do not enforce one. |
| **Fix** | Add a column/table allowlist guard in the generic DB helpers, or use identifier-quoting (`psycopg2.sql.Identifier` equivalent for asyncpg). |

### H-04: No authentication on any REST or WebSocket endpoint
| | |
|---|---|
| **Severity** | HIGH |
| **Files** | `jeeves_infra/gateway/routers/chat.py` (all endpoints), `jeeves_infra/gateway/app.py:309` |
| **Issue** | Every HTTP and WebSocket endpoint is open. WebSocket auth is disabled by default (`websocket_auth_required: bool = False`). |
| **Fix** | Add an auth middleware or dependency (JWT / API-key) to the FastAPI app and enforce it by default. |

---

## Bucket 2 — Insecure Defaults & Configuration

### H-05: CORS wildcard with `allow_credentials=True`
| | |
|---|---|
| **Severity** | HIGH |
| **File** | `jeeves_infra/gateway/app.py:64,154-155` |
| **Issue** | `CORS_ORIGINS` defaults to `"*"`, and is combined with `allow_credentials=True`, `allow_methods=["*"]`, `allow_headers=["*"]`. This is a textbook CORS misconfiguration enabling cross-origin credential theft. |
| **Fix** | Default to an empty or localhost-only origin list. Require explicit configuration for production origins. |

### H-06: Hardcoded WebSocket dev token
| | |
|---|---|
| **Severity** | MEDIUM |
| **File** | `jeeves_infra/settings.py:165-166` |
| **Issue** | `websocket_auth_token = "local-dev-token"` is checked in shipped code. Any attacker reading the source knows the token. |
| **Fix** | Remove the default; require the token to be set via environment variable when auth is enabled. |

### H-07: Empty default PostgreSQL password
| | |
|---|---|
| **Severity** | MEDIUM |
| **File** | `jeeves_infra/settings.py:195` |
| **Issue** | `postgres_password: str = ""`. If the env var is missing, the app connects with an empty password. |
| **Fix** | Make `postgres_password` a required field (no default), or add a startup validator that refuses to start with an empty password outside dev mode. |

### H-08: No TLS enforcement and no security response headers
| | |
|---|---|
| **Severity** | MEDIUM |
| **Files** | `jeeves_infra/gateway/app.py` (entire file) |
| **Issue** | No HTTPS redirect, no `Strict-Transport-Security`, `X-Frame-Options`, `X-Content-Type-Options`, or `Content-Security-Policy` headers. |
| **Fix** | Add a `SecurityHeadersMiddleware` and consider enforcing TLS at the reverse-proxy or app level. |

---

## Bucket 3 — Reliability & Error Handling

### H-09: 169 bare `except Exception` across 54 files
| | |
|---|---|
| **Severity** | HIGH |
| **Files** | Worst offenders: `gateway_chat.py` (11), `memory/repositories/event_repository.py` (8), `memory/repositories/trace_repository.py` (8), `memory/services/code_indexer.py` (8), `gateway/routers/chat.py` (7) |
| **Issue** | Broad catches mask bugs, swallow unexpected errors, and make debugging extremely difficult. Many catch-and-log without re-raising or returning a meaningful error. |
| **Fix** | Narrow each `except` to the specific exception type(s) expected. At a minimum, log the full traceback and re-raise unrecoverable errors. Tackle the worst-offender files first. |

### H-10: Fire-and-forget `asyncio.create_task()` with no error handling
| | |
|---|---|
| **Severity** | MEDIUM |
| **Files** | `jeeves_infra/gateway/sse.py:171`, `mission_system/memory/services/event_emitter.py:437`, `mission_system/memory/services/trace_recorder.py:291` |
| **Issue** | Tasks are created and never stored or awaited. If they raise, the exception is silently swallowed by the event loop. |
| **Fix** | Store task references and attach `add_done_callback` error handlers, or use a `TaskGroup`. |

### H-11: Low `try/finally` ratio — resource leak risk
| | |
|---|---|
| **Severity** | MEDIUM |
| **Files** | `jeeves_infra/` — 177 `try` blocks but only 26 `finally` blocks (14.7%) |
| **Issue** | Database connections, gRPC channels, and file handles may not be cleaned up on unexpected exceptions. |
| **Fix** | Audit try blocks that acquire resources and ensure cleanup via `finally`, `async with`, or `contextlib.AsyncExitStack`. |

### H-12: LLM fallback logic treats all errors as retriable
| | |
|---|---|
| **Severity** | MEDIUM |
| **File** | `jeeves_infra/llm/gateway.py:263-320` |
| **Issue** | Provider fallback catches `Exception` without distinguishing transient failures (timeout, 503) from permanent ones (401 auth, 400 bad request). This wastes quota and delays user-facing errors. |
| **Fix** | Classify exceptions into retriable vs. fatal categories. Only fall back on transient errors. |

---

## Bucket 4 — Operational Readiness

### H-13: Rate-limiting middleware exists but is not wired into the gateway
| | |
|---|---|
| **Severity** | HIGH |
| **Files** | `jeeves_infra/middleware/rate_limit.py` (exists), `jeeves_infra/gateway/app.py` (does NOT import or add it) |
| **Issue** | The rate limiter is implemented but never added to the FastAPI app. All endpoints are unprotected from request flooding. |
| **Fix** | Add the rate-limit middleware to the app startup in `gateway/app.py`. |

### H-14: No request payload size limits
| | |
|---|---|
| **Severity** | MEDIUM |
| **Files** | `jeeves_infra/gateway/app.py`, uvicorn configuration |
| **Issue** | No `max_upload_size` or body-size limit configured. A single large POST can exhaust memory. |
| **Fix** | Set `--limit-request-body` on uvicorn or add a body-size-checking middleware. |

### H-15: No CI/CD pipeline
| | |
|---|---|
| **Severity** | HIGH |
| **Files** | (absent — no `.github/workflows/`, no `Jenkinsfile`) |
| **Issue** | No automated testing, linting, type-checking, or deployment pipeline. Changes are not validated before merge. |
| **Fix** | Add a GitHub Actions (or equivalent) workflow that runs `ruff`, `mypy`, and `pytest` on every PR. |

### H-16: No Dockerfile or docker-compose
| | |
|---|---|
| **Severity** | MEDIUM |
| **Files** | (absent) |
| **Issue** | No containerization config. Runtime environment is not reproducible, and the dependency on Postgres/Redis/jeeves-core has no orchestration file. |
| **Fix** | Add a multi-stage `Dockerfile` and a `docker-compose.yml` for local development with Postgres, Redis, and llama-server. |

---

## Bucket 5 — Build & Dependency Health

### H-17: All dependencies unpinned with no lockfile
| | |
|---|---|
| **Severity** | HIGH |
| **Files** | `pyproject.toml:27-69`, `mission_system/pyproject.toml:24-36` |
| **Issue** | Every dependency uses `>=` with no upper bound (e.g., `grpcio>=1.60.0`, `fastapi>=0.109.0`). There is no `poetry.lock`, `pip-compile` output, or any lockfile. Builds are non-reproducible. |
| **Fix** | Pin dependencies with upper bounds (e.g., `grpcio>=1.60.0,<2`) or adopt `pip-tools`/`poetry` and commit the lockfile. |

### H-18: No test-coverage threshold enforced
| | |
|---|---|
| **Severity** | MEDIUM |
| **File** | `pyproject.toml` (pytest config) |
| **Issue** | `pytest-cov` is a dev dependency, but no `--cov-fail-under` is configured. Coverage can regress silently. |
| **Fix** | Add `addopts = "--cov=jeeves_infra --cov=mission_system --cov-fail-under=80"` to `[tool.pytest.ini_options]`. |

### H-19: `mission_system` allows Python 3.10 (EOL)
| | |
|---|---|
| **Severity** | LOW |
| **File** | `mission_system/pyproject.toml:10` (`requires-python = ">=3.10"`) |
| **Issue** | Python 3.10 reached end-of-life Oct 2024. Root `pyproject.toml` correctly requires 3.11+, but `mission_system` still permits 3.10. |
| **Fix** | Align to `requires-python = ">=3.11"`. |

### H-20: Unsafe `int()` casts on env vars without error handling
| | |
|---|---|
| **Severity** | LOW |
| **Files** | `jeeves_infra/gateway/app.py:61-63`, `mission_system/bootstrap.py:134-144` |
| **Issue** | `int(os.getenv(...))` will crash on non-numeric values with an unhelpful `ValueError`. |
| **Fix** | Use Pydantic `Settings` for all env-var parsing (already used for `jeeves_infra/settings.py`; extend to gateway and bootstrap configs). |

---

## Priority Matrix

| Priority | Issues | Theme |
|----------|--------|-------|
| **P0 — Fix immediately** | H-01, H-02, H-03, H-04, H-05 | RCE, injection, no auth, CORS |
| **P1 — Fix before production** | H-06, H-07, H-09, H-13, H-15, H-17 | Insecure defaults, broad catches, rate-limit, CI, deps |
| **P2 — Fix soon** | H-08, H-10, H-11, H-12, H-14, H-16, H-18 | TLS, async errors, resource leaks, payload limits |
| **P3 — Improve** | H-19, H-20 | Python version, env-var parsing |

---

## Counts by Bucket

| Bucket | Issues | P0 | P1 | P2 | P3 |
|--------|--------|----|----|----|----|
| Critical Security | H-01 to H-04 | 4 | — | — | — |
| Insecure Defaults | H-05 to H-08 | 1 | 2 | 1 | — |
| Reliability & Errors | H-09 to H-12 | — | 1 | 3 | — |
| Operational Readiness | H-13 to H-16 | — | 1 | 2 | — |
| Build & Deps | H-17 to H-20 | — | 1 | 1 | 2 |
| **Total** | **20** | **5** | **5** | **7** | **2** |
