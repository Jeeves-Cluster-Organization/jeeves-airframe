"""Lightweight SQLite client for test fixtures.

Implements DatabaseClientProtocol using aiosqlite with :memory: databases.
No SQLAlchemy, no connection pools, no containers.
"""

import json
import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite


class SQLiteClient:
    """In-memory SQLite database client satisfying DatabaseClientProtocol."""

    def __init__(self, database_url: str = ":memory:", **kwargs):
        self.database_url = database_url
        self._db: Optional[aiosqlite.Connection] = None
        self._in_transaction = False

    @property
    def backend(self) -> str:
        return "sqlite"

    async def connect(self) -> None:
        self._db = await aiosqlite.connect(self.database_url)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA foreign_keys = ON")
        await self._db.execute("PRAGMA journal_mode = WAL")

    async def disconnect(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    async def execute(self, query: str, params: Optional[Dict[str, Any]] = None) -> None:
        q, p = self._convert_params(query, params)
        await self._db.execute(q, p)
        if not self._in_transaction:
            await self._db.commit()

    async def fetch_one(
        self, query: str, params: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        q, p = self._convert_params(query, params)
        cursor = await self._db.execute(q, p)
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def fetch_all(
        self, query: str, params: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        q, p = self._convert_params(query, params)
        cursor = await self._db.execute(q, p)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def insert(self, table: str, data: Dict[str, Any]) -> None:
        processed = {k: self._serialize_value(v) for k, v in data.items()}
        cols = ", ".join(processed.keys())
        placeholders = ", ".join(f":{k}" for k in processed.keys())
        query = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"
        await self._db.execute(query, processed)
        if not self._in_transaction:
            await self._db.commit()

    async def update(self, table: str, data: Dict[str, Any], where_clause: str, where_params=None) -> int:
        processed = {k: self._serialize_value(v) for k, v in data.items()}
        set_clause = ", ".join(f"{k} = :_set_{k}" for k in processed.keys())
        params = {f"_set_{k}": v for k, v in processed.items()}

        # Convert ? placeholders in where_clause to named params
        if where_params and isinstance(where_params, (list, tuple)):
            idx = [0]
            def _replacer(_m):
                name = f"_w{idx[0]}"
                idx[0] += 1
                return f":{name}"
            named_where = re.sub(r'\?', _replacer, where_clause)
            for i, val in enumerate(where_params):
                params[f"_w{i}"] = self._serialize_value(val)
        else:
            named_where = where_clause

        query = f"UPDATE {table} SET {set_clause} WHERE {named_where}"
        cursor = await self._db.execute(query, params)
        if not self._in_transaction:
            await self._db.commit()
        return cursor.rowcount

    @asynccontextmanager
    async def transaction(self):
        """Transaction context manager. Commits on success, rolls back on exception."""
        await self._db.execute("BEGIN")
        self._in_transaction = True
        try:
            yield self
            await self._db.commit()
        except Exception:
            await self._db.rollback()
            raise
        finally:
            self._in_transaction = False

    async def initialize_schema(self, schema_path: str) -> None:
        sql = Path(schema_path).read_text(encoding="utf-8")
        await self._db.executescript(sql)

    @staticmethod
    def from_json(value):
        """Parse JSON string to Python object. No-op if already parsed."""
        if isinstance(value, str):
            return json.loads(value)
        return value

    # -- internals --

    def _convert_params(self, query, params):
        if params is None:
            return query, []
        if isinstance(params, dict):
            return query, params
        return query, list(params)

    @staticmethod
    def _serialize_value(value: Any) -> Any:
        if isinstance(value, uuid.UUID):
            return str(value)
        if isinstance(value, (dict, list)):
            return json.dumps(value, default=str)
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, date):
            return value.isoformat()
        return value
