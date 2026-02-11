"""DatabasePersistence — structured pipeline state storage.

Stores envelope state with flat queryable columns + encoded nested fields.
Nested field serialization is injected via encode/decode callables (capability decides format).
"""

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from jeeves_infra.protocols import DatabaseClientProtocol

# Flat fields extracted from envelope state → stored as typed columns
_FLAT_FIELDS = [
    "envelope_id", "request_id", "user_id", "session_id",
    "raw_input", "current_stage", "iteration", "max_iterations",
    "llm_call_count", "max_llm_calls", "agent_hop_count", "max_agent_hops",
    "terminated", "terminal_reason", "termination_reason",
    "interrupt_pending", "parallel_mode",
    "current_stage_number", "max_stages",
    "received_at", "completed_at",
]

# Boolean fields requiring int conversion for SQLite
_BOOL_FIELDS = ("terminated", "interrupt_pending", "parallel_mode")

# Nested fields — encoded via callback before storage
_NESTED_FIELDS = [
    "outputs", "metadata", "request_context", "interrupt",
    "active_stages", "completed_stage_set", "failed_stages",
    "stage_order", "all_goals", "remaining_goals",
    "goal_completion_status", "errors",
    "processing_history", "prior_plans", "loop_feedback", "completed_stages",
]

PIPELINE_STATE_DDL = """
CREATE TABLE IF NOT EXISTS pipeline_state (
    thread_id TEXT PRIMARY KEY,
    envelope_id TEXT,
    request_id TEXT,
    user_id TEXT,
    session_id TEXT,
    raw_input TEXT,
    current_stage TEXT,
    iteration INTEGER DEFAULT 0,
    max_iterations INTEGER DEFAULT 3,
    llm_call_count INTEGER DEFAULT 0,
    max_llm_calls INTEGER DEFAULT 10,
    agent_hop_count INTEGER DEFAULT 0,
    max_agent_hops INTEGER DEFAULT 21,
    terminated INTEGER DEFAULT 0,
    terminal_reason TEXT,
    termination_reason TEXT,
    interrupt_pending INTEGER DEFAULT 0,
    parallel_mode INTEGER DEFAULT 0,
    current_stage_number INTEGER DEFAULT 1,
    max_stages INTEGER DEFAULT 5,
    received_at TEXT,
    completed_at TEXT,
    outputs TEXT,
    metadata TEXT,
    request_context TEXT,
    interrupt TEXT,
    active_stages TEXT,
    completed_stage_set TEXT,
    failed_stages TEXT,
    stage_order TEXT,
    all_goals TEXT,
    remaining_goals TEXT,
    goal_completion_status TEXT,
    errors TEXT,
    processing_history TEXT,
    prior_plans TEXT,
    loop_feedback TEXT,
    completed_stages TEXT,
    stored_at TEXT NOT NULL DEFAULT (datetime('now')),
    modified_at TEXT NOT NULL DEFAULT (datetime('now'))
)
"""


class DatabasePersistence:
    """Persistence protocol adapter backed by DatabaseClientProtocol.

    Flat envelope fields stored as typed columns (queryable).
    Nested fields encoded via injected callables (capability decides format).
    """

    def __init__(
        self,
        db: "DatabaseClientProtocol",
        encode: Optional[Callable[[Any], str]] = None,
        decode: Optional[Callable[[str], Any]] = None,
    ):
        self._db = db
        self._encode = encode
        self._decode = decode
        self._schema_ready = False

    async def _ensure_schema(self) -> None:
        if self._schema_ready:
            return
        await self._db.execute(PIPELINE_STATE_DDL)
        self._schema_ready = True

    async def save_state(self, thread_id: str, state: Dict[str, Any]) -> None:
        await self._ensure_schema()
        now = datetime.now(timezone.utc).isoformat()

        row: Dict[str, Any] = {"thread_id": thread_id, "modified_at": now}

        # Flat fields — direct column storage
        for key in _FLAT_FIELDS:
            value = state.get(key)
            if key in _BOOL_FIELDS:
                row[key] = int(bool(value)) if value is not None else 0
            else:
                row[key] = value

        # Nested fields — encode via callback
        if self._encode:
            for key in _NESTED_FIELDS:
                value = state.get(key)
                if value is not None:
                    row[key] = self._encode(value)
                else:
                    row[key] = None

        await self._db.upsert("pipeline_state", row, key_columns=["thread_id"])

    async def load_state(self, thread_id: str) -> Optional[Dict[str, Any]]:
        await self._ensure_schema()
        row = await self._db.fetch_one(
            "SELECT * FROM pipeline_state WHERE thread_id = :thread_id",
            {"thread_id": thread_id},
        )
        if row is None:
            return None

        result = dict(row)

        # Restore booleans
        for key in _BOOL_FIELDS:
            result[key] = bool(result.get(key, 0))

        # Decode nested fields
        if self._decode:
            for key in _NESTED_FIELDS:
                value = result.get(key)
                if value is not None and isinstance(value, str):
                    result[key] = self._decode(value)

        # Remove storage-only fields
        result.pop("stored_at", None)
        result.pop("modified_at", None)

        return result
