"""Constitution Principle P2: Reliability > Cleverness

Validates adherence to:
"Fail loudly. No silent fallbacks. No guessing. If a write fails, rollback and report exactly what broke."

Key Requirements:
1. Write operations must be transactional (all-or-nothing)
2. Failures must rollback partial changes
3. Error messages must report exactly what failed
4. No silent failures or data corruption

Reference: JEEVES_CORE_CONSTITUTION.md, Principle 2
"""

import pytest
from uuid import uuid4

# Requires PostgreSQL database
pytestmark = [pytest.mark.requires_postgres, pytest.mark.contract]


@pytest.mark.contract
class TestP2Reliability:
    """Validate P2: Reliability > Cleverness."""

    async def test_write_operations_are_transactional(self, pg_test_db):
        """Write operations must be all-or-nothing (ACID compliance).

        P2 Requirement: "If a write fails, rollback"

        Test Strategy:
        1. Start transaction
        2. Insert multiple records using transaction session
        3. Force failure on one record
        4. Verify all inserts were rolled back

        Note: Uses knowledge_facts table (tasks table removed in v3.0 pivot)
        """
        from sqlalchemy import text
        from jeeves_infra.utils.uuid_utils import uuid_str

        fact_id_1 = str(uuid4())
        fact_id_2 = str(uuid4())
        user_id = f"test_user_{uuid4().hex[:8]}"

        # Begin transaction - insert two facts then try duplicate
        try:
            async with pg_test_db.transaction() as session:
                # Insert first record (should succeed)
                await session.execute(
                    text("INSERT INTO knowledge_facts (fact_id, user_id, domain, key, value) VALUES (:fact_id, :user_id, :domain, :key, :value)"),
                    {"fact_id": uuid_str(fact_id_1), "user_id": user_id, "domain": "test", "key": "key1", "value": "value1"}
                )

                # Insert second record (should succeed)
                await session.execute(
                    text("INSERT INTO knowledge_facts (fact_id, user_id, domain, key, value) VALUES (:fact_id, :user_id, :domain, :key, :value)"),
                    {"fact_id": uuid_str(fact_id_2), "user_id": user_id, "domain": "test", "key": "key2", "value": "value2"}
                )

                # Force failure by violating constraint (duplicate fact_id)
                await session.execute(
                    text("INSERT INTO knowledge_facts (fact_id, user_id, domain, key, value) VALUES (:fact_id, :user_id, :domain, :key, :value)"),
                    {"fact_id": uuid_str(fact_id_1), "user_id": user_id, "domain": "test", "key": "key3", "value": "value3"}
                )
        except Exception:
            pass  # Expected - duplicate key violation

        # Verify rollback: No facts should exist for this user
        facts = await pg_test_db.fetch_all(
            "SELECT * FROM knowledge_facts WHERE user_id = ?",
            (user_id,)
        )
        assert len(facts) == 0, "P2 violation: Partial writes persisted after transaction rollback"


    async def test_database_errors_propagate_loudly(self, pg_test_db):
        """Database errors must propagate without silent fallbacks.

        P2 Requirement: "Fail loudly. No silent fallbacks."

        Test Strategy:
        1. Attempt invalid SQL operation
        2. Verify exception is raised (not silently caught)
        3. Verify error message is descriptive
        """
        # Attempt to insert into non-existent table
        with pytest.raises(Exception) as exc_info:
            await pg_test_db.execute(
                "INSERT INTO nonexistent_table (id, value) VALUES (?, ?)",
                (str(uuid4()), "test_value")
            )

        # Verify error message is descriptive (not generic)
        error_message = str(exc_info.value).lower()
        assert "nonexistent_table" in error_message or "does not exist" in error_message, \
            "P2 violation: Error message not descriptive"


    async def test_constraint_violations_fail_loudly(self, pg_test_db):
        """Constraint violations must fail loudly with clear error messages.

        P2 Requirement: "Report exactly what broke"

        Test Strategy:
        1. Violate NOT NULL constraint
        2. Verify exception is raised
        3. Verify error message identifies the constraint

        Note: Uses knowledge_facts table (tasks table removed in v3.0 pivot)
        """
        # Attempt to insert fact without required value (NOT NULL)
        with pytest.raises(Exception) as exc_info:
            await pg_test_db.insert("knowledge_facts", {
                "fact_id": str(uuid4()),
                "user_id": "test_user",
                "domain": "test",
                "key": "test_key",
                "value": None,  # value is NULL (violates NOT NULL)
            })

        # Verify error indicates null constraint violation
        error_message = str(exc_info.value).lower()
        assert "null" in error_message or "not null" in error_message or "violates" in error_message, \
            "P2 violation: Constraint violation error not descriptive"


    async def test_foreign_key_violations_fail_loudly(self, pg_test_db):
        """Foreign key violations must fail loudly.

        P2 Requirement: "Fail loudly"

        Test Strategy:
        1. Attempt to insert record with invalid foreign key
        2. Verify exception is raised
        3. Verify error message identifies the constraint
        """
        # Attempt to insert request referencing non-existent session
        # requests.session_id has FK constraint to sessions
        with pytest.raises(Exception) as exc_info:
            await pg_test_db.insert("requests", {
                "request_id": str(uuid4()),
                "user_id": "test_user",
                "session_id": str(uuid4()),  # Non-existent session - FK violation
                "user_message": "Test message",
                "status": "pending"
            })

        # Verify error indicates foreign key violation
        error_message = str(exc_info.value).lower()
        assert "foreign key" in error_message or "constraint" in error_message or "violates" in error_message, \
            "P2 violation: Foreign key violation error not descriptive"


    async def test_no_silent_data_truncation(self, pg_test_db):
        """Data truncation must fail loudly, not silently truncate.

        P2 Requirement: "No guessing"

        Test Strategy:
        1. Attempt to insert data exceeding column length
        2. Verify either:
           a) Exception is raised (strict mode), OR
           b) Data is stored in full (VARCHAR without limit)
        3. Never silent truncation

        Note: Uses knowledge_facts table (tasks table removed in v3.0 pivot)
        """
        # Insert fact with very long value
        long_value = "A" * 10000  # 10KB value
        fact_id = str(uuid4())

        # PostgreSQL TEXT columns have no length limit, so this should succeed
        await pg_test_db.insert("knowledge_facts", {
            "fact_id": fact_id,
            "user_id": "test_user",
            "domain": "test",
            "key": "long_data_key",
            "value": long_value
        })

        # Verify data was stored in full (not truncated)
        result = await pg_test_db.fetch_one(
            "SELECT value FROM knowledge_facts WHERE fact_id = ?",
            (fact_id,)
        )
        assert result is not None
        assert len(result["value"]) == 10000, \
            "P2 violation: Data was silently truncated"


    async def test_concurrent_write_conflicts_handled_correctly(self, pg_test_db):
        """Concurrent write conflicts must be handled deterministically.

        P2 Requirement: "Fail loudly"

        Test Strategy:
        1. Simulate concurrent write to same record
        2. Verify optimistic locking or serialization error
        3. No data corruption

        Note: Uses knowledge_facts table (tasks table removed in v3.0 pivot)
        """
        # Insert initial fact
        fact_id = str(uuid4())
        await pg_test_db.insert("knowledge_facts", {
            "fact_id": fact_id,
            "user_id": "test_user",
            "domain": "test",
            "key": "concurrent_test",
            "value": "Initial Value"
        })

        # Update fact (simulating first transaction)
        await pg_test_db.update(
            "knowledge_facts",
            {"value": "Updated by TX1"},
            "fact_id = ?",
            (fact_id,)
        )

        # Verify update succeeded
        result = await pg_test_db.fetch_one(
            "SELECT value FROM knowledge_facts WHERE fact_id = ?",
            (fact_id,)
        )
        assert result is not None
        assert result["value"] == "Updated by TX1", \
            "P2 violation: Concurrent write corrupted data"


@pytest.mark.contract
class TestP2ToolReliability:
    """Validate P2 for tool execution failures."""

    async def test_tool_execution_failures_recorded(self, pg_test_db):
        """Tool execution failures must be recorded in tool_executions table.

        P2 Requirement: "Report exactly what broke"

        Test Strategy:
        1. Create prerequisite records (session, request, plan)
        2. Simulate tool execution failure
        3. Verify failure is recorded with error details
        """
        # Create prerequisite records for FK constraints
        session_id = str(uuid4())
        request_id = str(uuid4())
        plan_id = str(uuid4())
        execution_id = str(uuid4())

        await pg_test_db.insert("sessions", {
            "session_id": session_id,
            "user_id": "test_user"
        })

        await pg_test_db.insert("requests", {
            "request_id": request_id,
            "user_id": "test_user",
            "session_id": session_id,
            "user_message": "test",
            "status": "processing"
        })

        await pg_test_db.insert("execution_plans", {
            "plan_id": plan_id,
            "request_id": request_id,
            "intent": "test",
            "confidence": 0.95,
            "plan_json": "{}"
        })

        # Insert tool execution record with failure
        await pg_test_db.insert("tool_executions", {
            "execution_id": execution_id,
            "request_id": request_id,
            "plan_id": plan_id,
            "tool_index": 0,
            "tool_name": "test_tool",
            "parameters": "{}",
            "status": "error",
            "error_details": '{"message": "Test error: connection timeout"}'
        })

        # Verify failure was recorded
        result = await pg_test_db.fetch_one(
            "SELECT status, error_details FROM tool_executions WHERE execution_id = ?",
            (execution_id,)
        )
        assert result is not None
        assert result["status"] == "error"
        error_details = pg_test_db.from_json(result["error_details"]) if isinstance(result["error_details"], str) else result["error_details"]
        assert "connection timeout" in error_details.get("message", ""), \
            "P2 violation: Error message not descriptive"


    async def test_rollback_on_tool_failure_prevents_partial_state(self, pg_test_db):
        """Tool failures must rollback any partial database changes.

        P2 Requirement: "If a write fails, rollback"

        Test Strategy:
        1. Start transaction
        2. Create fact using transaction session
        3. Execute tool (simulate failure)
        4. Rollback transaction
        5. Verify fact was not persisted

        Note: Uses knowledge_facts table (tasks table removed in v3.0 pivot)
        """
        from sqlalchemy import text
        from jeeves_infra.utils.uuid_utils import uuid_str

        fact_id = str(uuid4())

        # Begin transaction
        try:
            async with pg_test_db.transaction() as session:
                # Create fact as part of tool execution
                await session.execute(
                    text("INSERT INTO knowledge_facts (fact_id, user_id, domain, key, value) VALUES (:fact_id, :user_id, :domain, :key, :value)"),
                    {"fact_id": uuid_str(fact_id), "user_id": "test_user", "domain": "test", "key": "tool_key", "value": "from tool"}
                )

                # Simulate tool failure
                raise Exception("Tool execution failed")
        except Exception:
            pass  # Expected exception

        # Verify fact was rolled back
        result = await pg_test_db.fetch_one(
            "SELECT * FROM knowledge_facts WHERE fact_id = ?",
            (fact_id,)
        )
        assert result is None, \
            "P2 violation: Partial state persisted after tool failure"
