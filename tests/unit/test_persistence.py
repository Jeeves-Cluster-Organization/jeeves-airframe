"""Unit tests for DatabasePersistence.

Tests the structured-column + callback injection persistence adapter.
"""

import json
import pytest

from jeeves_infra.runtime.persistence import DatabasePersistence
from fixtures.sqlite_client import SQLiteClient


@pytest.fixture
async def db():
    client = SQLiteClient(":memory:")
    await client.connect()
    yield client
    await client.disconnect()


@pytest.fixture
async def persistence(db):
    return DatabasePersistence(db, encode=json.dumps, decode=json.loads)


# =============================================================================
# Core round-trip
# =============================================================================


@pytest.mark.asyncio
async def test_save_and_load_flat_fields(persistence):
    """Flat fields round-trip through typed columns."""
    state = {
        "envelope_id": "env-1",
        "request_id": "req-1",
        "user_id": "user-1",
        "session_id": "sess-1",
        "current_stage": "understand",
        "iteration": 3,
        "terminated": False,
        "outputs": {"understand": {"intent": "greeting"}},
    }
    await persistence.save_state("thread-1", state)
    loaded = await persistence.load_state("thread-1")
    assert loaded["envelope_id"] == "env-1"
    assert loaded["iteration"] == 3
    assert loaded["terminated"] is False
    assert loaded["outputs"] == {"understand": {"intent": "greeting"}}


@pytest.mark.asyncio
async def test_load_nonexistent_returns_none(persistence):
    """load_state for unknown thread_id returns None."""
    result = await persistence.load_state("does-not-exist")
    assert result is None


@pytest.mark.asyncio
async def test_save_overwrites_existing(persistence):
    """Second save with same thread_id overwrites via upsert."""
    await persistence.save_state("thread-1", {"iteration": 1, "outputs": {}})
    await persistence.save_state("thread-1", {"iteration": 2, "outputs": {"a": 1}})
    loaded = await persistence.load_state("thread-1")
    assert loaded["iteration"] == 2
    assert loaded["outputs"] == {"a": 1}


# =============================================================================
# Schema auto-creation
# =============================================================================


@pytest.mark.asyncio
async def test_auto_creates_table(db):
    """First call to load_state creates the pipeline_state table."""
    p = DatabasePersistence(db, encode=json.dumps, decode=json.loads)
    row = await db.fetch_one(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='pipeline_state'"
    )
    assert row is None

    await p.load_state("any")

    row = await db.fetch_one(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='pipeline_state'"
    )
    assert row is not None
    assert row["name"] == "pipeline_state"


# =============================================================================
# Nested fields with encode/decode callbacks
# =============================================================================


@pytest.mark.asyncio
async def test_nested_fields_encoded(persistence, db):
    """Nested fields stored as encoded strings, decoded on load."""
    state = {
        "outputs": {"understand": {"intent": "question", "entities": ["python"]}},
        "metadata": {"session_context": {"turn": 5}},
        "request_context": {"request_id": "r1", "capability": "test"},
    }
    await persistence.save_state("thread-nested", state)

    # Verify raw storage is encoded strings
    row = await db.fetch_one(
        "SELECT outputs, metadata FROM pipeline_state WHERE thread_id = :t",
        {"t": "thread-nested"},
    )
    assert isinstance(row["outputs"], str)

    # Verify decoded load
    loaded = await persistence.load_state("thread-nested")
    assert loaded["outputs"] == state["outputs"]
    assert loaded["metadata"] == state["metadata"]


@pytest.mark.asyncio
async def test_no_callbacks_skips_nested(db):
    """Without encode/decode, nested fields are stored as None."""
    p = DatabasePersistence(db)
    await p.save_state("thread-no-cb", {"iteration": 1, "outputs": {"a": 1}})
    loaded = await p.load_state("thread-no-cb")
    assert loaded["iteration"] == 1
    assert loaded.get("outputs") is None


# =============================================================================
# Boolean fields
# =============================================================================


@pytest.mark.asyncio
async def test_boolean_fields_round_trip(persistence):
    """Boolean fields stored as int, restored as bool."""
    state = {
        "terminated": True,
        "interrupt_pending": False,
        "parallel_mode": True,
    }
    await persistence.save_state("thread-bool", state)
    loaded = await persistence.load_state("thread-bool")
    assert loaded["terminated"] is True
    assert loaded["interrupt_pending"] is False
    assert loaded["parallel_mode"] is True


# =============================================================================
# Multiple threads
# =============================================================================


@pytest.mark.asyncio
async def test_multiple_threads_isolated(persistence):
    """Different thread_ids store independent state."""
    await persistence.save_state("thread-a", {"current_stage": "understand"})
    await persistence.save_state("thread-b", {"current_stage": "respond"})

    a = await persistence.load_state("thread-a")
    b = await persistence.load_state("thread-b")
    assert a["current_stage"] == "understand"
    assert b["current_stage"] == "respond"


# =============================================================================
# Storage-only fields stripped
# =============================================================================


@pytest.mark.asyncio
async def test_storage_fields_not_in_loaded_state(persistence):
    """stored_at and modified_at are storage metadata, not returned."""
    await persistence.save_state("thread-meta", {"iteration": 1})
    loaded = await persistence.load_state("thread-meta")
    assert "stored_at" not in loaded
    assert "modified_at" not in loaded
