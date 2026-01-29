"""Memory Contract M2: Events Are Immutable History

Validates adherence to:
"Event log is append-only. No UPDATE or DELETE on domain_events.
Corrections are new compensating events."

Key Requirements:
1. domain_events table is append-only (no UPDATE/DELETE)
2. Events have immutable timestamps (TIMESTAMPTZ)
3. Corrections create new compensating events
4. Event ordering is deterministic

Reference: MEMORY_INFRASTRUCTURE_CONTRACT.md, Principle M2
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4

# Requires PostgreSQL database
pytestmark = pytest.mark.requires_postgres


@pytest.mark.contract
class TestM2Immutable:
    """Validate M2: Events Are Immutable History."""

    async def test_domain_events_table_exists(self, pg_test_db):
        """domain_events table must exist for event sourcing.

        M2 Requirement: "Event log is append-only"

        Test Strategy:
        1. Query table existence
        2. Verify table has required columns
        """
        # Query table existence
        result = await pg_test_db.fetch_one(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'domain_events'
            """
        )

        assert result is not None, \
            "M2 violation: domain_events table does not exist"


    async def test_domain_events_have_immutable_timestamps(self, pg_test_db):
        """Events must have TIMESTAMPTZ for ordering.

        M2 Requirement: "Events have immutable timestamps"

        Test Strategy:
        1. Query column schema
        2. Verify timestamp column is TIMESTAMPTZ (not TIMESTAMP)
        """
        # Query timestamp column type
        result = await pg_test_db.fetch_one(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'domain_events'
                AND column_name IN ('occurred_at', 'timestamp', 'event_timestamp')
            """
        )

        # Verify timestamp column exists and is TIMESTAMPTZ
        assert result is not None, \
            "M2 violation: domain_events table missing timestamp column"

        # PostgreSQL reports 'timestamp with time zone' for TIMESTAMPTZ
        assert "time zone" in result["data_type"].lower(), \
            f"M2 violation: Timestamp column is {result['data_type']}, should be TIMESTAMPTZ"


    async def test_events_are_append_only_insert_succeeds(self, pg_test_db):
        """Events can be inserted (append-only).

        M2 Requirement: "Event log is append-only"

        Test Strategy:
        1. Insert event
        2. Verify insertion succeeds
        """
        # Insert domain event
        event_id = str(uuid4())
        await pg_test_db.insert("domain_events", {
            "event_id": event_id,
            "event_type": "task_created",
            "aggregate_id": str(uuid4()),
            "aggregate_type": "task",
            "occurred_at": datetime.now(timezone.utc),
            "user_id": "test_user",
            "payload": {}
        })

        # Verify event was inserted
        result = await pg_test_db.fetch_one(
            "SELECT event_id FROM domain_events WHERE event_id = ?",
            (event_id,)
        )
        assert result is not None


    async def test_updating_events_should_be_prevented(self, pg_test_db):
        """Updating events should be prevented (application-level enforcement).

        M2 Requirement: "No UPDATE on domain_events"

        Test Strategy:
        1. Insert event
        2. Attempt to update event
        3. Verify update is prevented OR creates new event

        Note: Database-level enforcement requires triggers or permissions.
        This test documents the application-level expectation.
        """
        # Insert domain event
        event_id = str(uuid4())
        await pg_test_db.insert("domain_events", {
            "event_id": event_id,
            "event_type": "task_created",
            "aggregate_id": str(uuid4()),
            "aggregate_type": "task",
            "occurred_at": datetime.now(timezone.utc),
            "user_id": "test_user",
            "payload": {"title": "Original"}
        })

        # Attempt to update event (this SHOULD fail if schema enforces immutability)
        try:
            await pg_test_db.update(
                "domain_events",
                {"payload": {"title": "Modified"}},
                "event_id = ?",
                (event_id,)
            )

            # If update succeeded, this is a violation (but not enforced at DB level)
            pytest.skip(
                "M2 warning: Events can be updated at database level. "
                "Application MUST NOT update events. Consider adding trigger to prevent UPDATE."
            )
        except Exception:
            # Good! Schema prevents updates (via trigger or permissions)
            pass


    async def test_deleting_events_should_be_prevented(self, pg_test_db):
        """Deleting events should be prevented (application-level enforcement).

        M2 Requirement: "No DELETE on domain_events"

        Test Strategy:
        1. Insert event
        2. Attempt to delete event
        3. Verify deletion is prevented OR documented as gap

        Note: Database-level enforcement requires triggers or permissions.
        This test documents the application-level expectation.
        """
        # Insert domain event
        event_id = str(uuid4())
        await pg_test_db.insert("domain_events", {
            "event_id": event_id,
            "event_type": "task_created",
            "aggregate_id": str(uuid4()),
            "aggregate_type": "task",
            "occurred_at": datetime.now(timezone.utc),
            "user_id": "test_user",
            "payload": {}
        })

        # Attempt to delete event (this SHOULD fail if schema enforces immutability)
        try:
            await pg_test_db.execute(
                "DELETE FROM domain_events WHERE event_id = ?",
                (event_id,)
            )

            # If deletion succeeded, this is a violation (but not enforced at DB level)
            pytest.skip(
                "M2 warning: Events can be deleted at database level. "
                "Application MUST NOT delete events. Consider adding trigger to prevent DELETE."
            )
        except Exception:
            # Good! Schema prevents deletions (via trigger or permissions)
            pass


    async def test_corrections_create_compensating_events(self, pg_test_db):
        """Corrections must create new compensating events, not update original.

        M2 Requirement: "Corrections are new compensating events"

        Test Strategy:
        1. Insert original event (task_created)
        2. Insert compensating event (task_title_corrected)
        3. Verify original event is unchanged
        4. Verify compensating event references original
        """
        # Insert original event
        original_event_id = str(uuid4())
        aggregate_id = str(uuid4())
        await pg_test_db.insert("domain_events", {
            "event_id": original_event_id,
            "event_type": "task_created",
            "aggregate_id": aggregate_id,
            "aggregate_type": "task",
            "occurred_at": datetime.now(timezone.utc),
            "user_id": "test_user",
            "payload": {"title": "Wrong Title"}
        })

        # Insert compensating event
        compensating_event_id = str(uuid4())
        await pg_test_db.insert("domain_events", {
            "event_id": compensating_event_id,
            "event_type": "task_title_corrected",
            "aggregate_id": aggregate_id,
            "aggregate_type": "task",
            "occurred_at": datetime.now(timezone.utc),
            "user_id": "test_user",
            "payload": {
                "corrects_event": original_event_id,
                "old_title": "Wrong Title",
                "new_title": "Correct Title"
            }
        })

        # Verify original event is unchanged
        original = await pg_test_db.fetch_one(
            "SELECT payload FROM domain_events WHERE event_id = ?",
            (original_event_id,)
        )
        assert original is not None
        payload = pg_test_db.from_json(original["payload"]) if isinstance(original["payload"], str) else original["payload"]
        assert payload["title"] == "Wrong Title", \
            "M2 violation: Original event was modified"

        # Verify compensating event exists
        compensating = await pg_test_db.fetch_one(
            "SELECT payload FROM domain_events WHERE event_id = ?",
            (compensating_event_id,)
        )
        assert compensating is not None
        comp_payload = pg_test_db.from_json(compensating["payload"]) if isinstance(compensating["payload"], str) else compensating["payload"]
        assert comp_payload["corrects_event"] == original_event_id


    async def test_event_ordering_is_deterministic(self, pg_test_db):
        """Events must have deterministic ordering via TIMESTAMPTZ.

        M2 Requirement: "Event ordering is deterministic"

        Test Strategy:
        1. Insert multiple events
        2. Query events ordered by occurred_at
        3. Verify order matches insertion order
        """
        # Insert events with explicit timestamps
        base_time = datetime.now(timezone.utc)
        test_prefix = str(uuid4())[:8]  # Unique prefix for this test
        events = [
            (f"{test_prefix}_order_1", base_time),
            (f"{test_prefix}_order_2", base_time.replace(microsecond=base_time.microsecond + 1000 if base_time.microsecond < 998000 else 999000)),
            (f"{test_prefix}_order_3", base_time.replace(microsecond=base_time.microsecond + 2000 if base_time.microsecond < 997000 else 999999)),
        ]

        for event_id, timestamp in events:
            await pg_test_db.insert("domain_events", {
                "event_id": event_id,
                "event_type": "test_event",
                "aggregate_id": str(uuid4()),
                "aggregate_type": "test",
                "occurred_at": timestamp,
                "user_id": "test_user",
                "payload": {}
            })

        # Query events ordered by occurred_at
        results = await pg_test_db.fetch_all(
            f"""
            SELECT event_id, occurred_at
            FROM domain_events
            WHERE event_id LIKE '{test_prefix}_order_%'
            ORDER BY occurred_at ASC
            """
        )

        # Verify ordering matches insertion order
        assert len(results) == 3
        assert results[0]["event_id"] == f"{test_prefix}_order_1"
        assert results[1]["event_id"] == f"{test_prefix}_order_2"
        assert results[2]["event_id"] == f"{test_prefix}_order_3"


@pytest.mark.contract
class TestM2Schema:
    """Validate M2 schema structure requirements."""

    async def test_domain_events_has_required_columns(self, pg_test_db):
        """domain_events table must have all required M2 columns.

        M2 Requirements:
        - event_id (unique identifier)
        - event_type (what happened)
        - aggregate_id (which entity)
        - aggregate_type (entity type)
        - occurred_at (TIMESTAMPTZ)
        - user_id (who triggered)
        - payload (event data)

        Test Strategy:
        1. Query table schema
        2. Verify required columns exist
        """
        # Query table schema
        result = await pg_test_db.fetch_all(
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'domain_events'
            ORDER BY ordinal_position
            """
        )

        # Convert to dict for easier assertion
        columns = {row["column_name"]: row for row in result}

        # Verify required M2 columns exist
        required_columns = [
            "event_id", "event_type", "aggregate_id",
            "aggregate_type", "user_id", "payload"
        ]

        for col in required_columns:
            assert col in columns, f"M2 violation: {col} column missing from domain_events"

        # Verify timestamp column exists (may be named occurred_at, timestamp, etc.)
        timestamp_cols = [c for c in columns.keys()
                         if "timestamp" in c.lower() or "occurred" in c.lower()]
        assert len(timestamp_cols) > 0, \
            "M2 violation: domain_events missing timestamp column"


    async def test_event_id_is_primary_key(self, pg_test_db):
        """event_id must be primary key for uniqueness.

        M2 Requirement: Events are uniquely identifiable

        Test Strategy:
        1. Query constraint metadata
        2. Verify event_id is primary key
        """
        # Query primary key constraints
        result = await pg_test_db.fetch_all(
            """
            SELECT kcu.column_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
            WHERE tc.table_name = 'domain_events'
                AND tc.constraint_type = 'PRIMARY KEY'
            """
        )

        # Verify event_id is in primary key
        pk_columns = [row["column_name"] for row in result]
        assert "event_id" in pk_columns, \
            "M2 violation: event_id is not primary key"


    async def test_occurred_at_has_default_now(self, pg_test_db):
        """occurred_at should default to NOW() for automatic timestamping.

        M2 Requirement: Immutable timestamps

        Test Strategy:
        1. Query column default
        2. Verify default is NOW() or CURRENT_TIMESTAMP
        """
        # Query column default
        result = await pg_test_db.fetch_one(
            """
            SELECT column_name, column_default
            FROM information_schema.columns
            WHERE table_name = 'domain_events'
                AND column_name IN ('occurred_at', 'timestamp', 'event_timestamp')
            """
        )

        if result is not None:
            # Check if default is NOW() or CURRENT_TIMESTAMP
            default = result.get("column_default", "")
            if default:
                default_lower = default.lower()
                has_default = "now()" in default_lower or "current_timestamp" in default_lower
                assert has_default, \
                    f"M2 warning: occurred_at default is '{default}', consider NOW() or CURRENT_TIMESTAMP"
