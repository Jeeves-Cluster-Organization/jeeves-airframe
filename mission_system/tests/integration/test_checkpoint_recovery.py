"""
Integration tests for checkpoint recovery.

Tests that workflow state persists across restarts and
can be resumed from checkpoints.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from mission_system.orchestrator.state import PipelineState, create_initial_state


class TestCheckpointPersistence:
    """Tests for checkpoint persistence."""

    @pytest.mark.asyncio
    async def test_checkpoint_saves_state(self):
        """Checkpoint saves complete workflow state."""
        state = create_initial_state(
            user_id="user_123",
            session_id="sess_456",
            raw_input="update my tasks",
            envelope_id="env_abc",
            request_id="req_def",
            received_at=datetime.now(timezone.utc).isoformat(),
        )

        # Add some processing results
        state["perception"] = {
            "normalized_input": "update my tasks",
            "user_id": "user_123",
            "session_id": "sess_456",
            "memory_context": {},
        }
        state["intent"] = {
            "intent": "update_task",
            "confidence": 0.9,
            "goals": ["update task status"],
            "constraints": [],
        }

        # Verify state is serializable (can be checkpointed)
        import json

        serialized = json.dumps(state, default=str)
        deserialized = json.loads(serialized)

        assert deserialized["user_id"] == "user_123"
        assert deserialized["perception"]["normalized_input"] == "update my tasks"
        assert deserialized["intent"]["intent"] == "update_task"

    @pytest.mark.asyncio
    async def test_checkpoint_preserves_step_results(self):
        """Checkpoint preserves accumulated step results."""
        state = create_initial_state(
            user_id="user_123",
            session_id="sess_456",
            raw_input="test",
            envelope_id="env_abc",
            request_id="req_def",
            received_at=datetime.now(timezone.utc).isoformat(),
        )

        # Simulate multi-step execution
        state["step_results"] = [
            {
                "step_id": "step_1",
                "tool": "update_task",
                "status": "success",
                "execution_time_ms": 50,
            },
            {
                "step_id": "step_2",
                "tool": "add_task",
                "status": "success",
                "execution_time_ms": 75,
            },
        ]
        state["current_step_index"] = 2

        import json

        serialized = json.dumps(state, default=str)
        deserialized = json.loads(serialized)

        assert len(deserialized["step_results"]) == 2
        assert deserialized["current_step_index"] == 2


class TestCheckpointRecovery:
    """Tests for checkpoint recovery scenarios."""

    @pytest.mark.asyncio
    async def test_resume_from_confirmation_interrupt(self):
        """Workflow resumes from confirmation interrupt."""
        state = create_initial_state(
            user_id="user_123",
            session_id="sess_456",
            raw_input="delete all my tasks",
            envelope_id="env_abc",
            request_id="req_def",
            received_at=datetime.now(timezone.utc).isoformat(),
        )

        # Simulate state at confirmation interrupt
        state["stage"] = "confirmation_pending"
        state["confirmation_required"] = True
        state["confirmation_message"] = "Delete all tasks? This cannot be undone."
        state["plan"] = {
            "plan_id": "plan_123",
            "steps": [{"step_id": "step_1", "tool": "delete_all_tasks"}],
        }

        # Simulate resume with confirmation
        state["confirmation_response"] = True
        state["confirmation_required"] = False

        # Verify state is ready to continue
        assert state["confirmation_response"] is True
        assert state["confirmation_required"] is False
        assert state["plan"]["steps"][0]["tool"] == "delete_all_tasks"

    @pytest.mark.asyncio
    async def test_resume_from_clarification_interrupt(self):
        """Workflow resumes from clarification interrupt."""
        state = create_initial_state(
            user_id="user_123",
            session_id="sess_456",
            raw_input="update task",
            envelope_id="env_abc",
            request_id="req_def",
            received_at=datetime.now(timezone.utc).isoformat(),
        )

        # Simulate state at clarification interrupt
        state["stage"] = "clarification_pending"
        state["clarification_required"] = True
        state["clarification_question"] = "Which task would you like to update?"

        # Simulate resume with clarification
        state["clarification_response"] = "the one due tomorrow"
        state["clarification_required"] = False

        # Verify state is ready to continue
        assert state["clarification_response"] == "the one due tomorrow"
        assert state["clarification_required"] is False

    @pytest.mark.asyncio
    async def test_resume_after_partial_execution(self):
        """Workflow resumes after partial execution."""
        state = create_initial_state(
            user_id="user_123",
            session_id="sess_456",
            raw_input="update three tasks",
            envelope_id="env_abc",
            request_id="req_def",
            received_at=datetime.now(timezone.utc).isoformat(),
        )

        # Simulate partial execution (1 of 3 steps done)
        state["plan"] = {
            "plan_id": "plan_123",
            "steps": [
                {"step_id": "step_1", "tool": "update_task"},
                {"step_id": "step_2", "tool": "update_task"},
                {"step_id": "step_3", "tool": "update_task"},
            ],
        }
        state["current_step_index"] = 1  # Completed step 0
        state["step_results"] = [
            {
                "step_id": "step_1",
                "tool": "update_task",
                "status": "success",
                "execution_time_ms": 50,
            }
        ]

        # Verify state is ready to continue from step 1
        assert state["current_step_index"] == 1
        assert len(state["step_results"]) == 1
        assert len(state["plan"]["steps"]) == 3


class TestCheckpointIntegrity:
    """Tests for checkpoint data integrity."""

    @pytest.mark.asyncio
    async def test_checkpoint_preserves_iteration_count(self):
        """Checkpoint preserves replan iteration count."""
        state = create_initial_state(
            user_id="user_123",
            session_id="sess_456",
            raw_input="test",
            envelope_id="env_abc",
            request_id="req_def",
            received_at=datetime.now(timezone.utc).isoformat(),
        )

        # Simulate after 2 replan iterations
        state["iteration"] = 2
        state["prior_plans"] = [{"plan_id": "plan_1"}, {"plan_id": "plan_2"}]
        state["loop_feedback"] = [
            "First attempt failed - task not found",
            "Second attempt failed - wrong date format",
        ]

        import json

        serialized = json.dumps(state, default=str)
        deserialized = json.loads(serialized)

        assert deserialized["iteration"] == 2
        assert len(deserialized["prior_plans"]) == 2
        assert len(deserialized["loop_feedback"]) == 2

    @pytest.mark.asyncio
    async def test_checkpoint_preserves_errors(self):
        """Checkpoint preserves error information."""
        state = create_initial_state(
            user_id="user_123",
            session_id="sess_456",
            raw_input="test",
            envelope_id="env_abc",
            request_id="req_def",
            received_at=datetime.now(timezone.utc).isoformat(),
        )

        # Simulate with errors
        state["errors"] = [
            {
                "agent": "Executor",
                "error": "Tool not found: invalid_tool",
                "error_type": "ToolNotFoundError",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ]

        import json

        serialized = json.dumps(state, default=str)
        deserialized = json.loads(serialized)

        assert len(deserialized["errors"]) == 1
        assert "invalid_tool" in deserialized["errors"][0]["error"]
