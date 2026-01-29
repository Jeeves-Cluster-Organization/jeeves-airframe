# jeeves_infra - Database Module

**Parent:** [jeeves_infra Index](../INDEX.md)

---

## Overview

Database clients for PostgreSQL (primary). Implements connection pooling, health checks, and schema management.

Database clients implement `DatabaseClientProtocol` from `protocols`.

---

## Files

| File | Description |
|------|-------------|
| `__init__.py` | Package exports |
| `client.py` | Base database client interface |
| `client.py` | Protocol definitions and utilities |
| `factory.py` | Database client factory |
| `init_schema.py` | Schema initialization utilities |

## Subdirectories

| Directory | Description |
|-----------|-------------|
| `schemas/` | Database schema definitions |

**Note:** Implementation classes (`PostgreSQLClient`, etc.) and repository patterns are in `jeeves_infra/` package.

---

## Key Components

### PostgresClient (`postgres_client.py`)
Primary database client:
```python
class PostgresClient:
    async def execute(self, query: str, params: dict = None) -> None
    async def fetch_one(self, query: str, params: dict = None) -> Optional[dict]
    async def fetch_all(self, query: str, params: dict = None) -> List[dict]
    async def health_check(self) -> bool
```

### Connection Management (`connection_manager.py`)
- Connection pooling with configurable min/max connections
- Automatic reconnection on failure
- Health monitoring

---

## Constitutional Compliance

**S3 (Database Credentials):**
- Credentials via environment variables only
- No hardcoded passwords in production code
- Test fixtures use placeholder credentials

---

*Last updated: 2026-01-30*
