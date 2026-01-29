"""Tests for M5: Heuristic Plan Triage utility.

Tests the fast <1ms validation of execution plans before they're sent
to the Executor, catching obviously problematic plans without LLM calls.
"""

import pytest
from mission_system.common.plan_triage import (
    triage_plan,
    get_plan_complexity_score,
    summarize_plan_for_logging,
    KNOWN_TOOLS,
)


class TestTriagePlan:
    """Test suite for triage_plan() function."""

    def test_valid_simple_plan(self):
        """Simple valid plan passes triage."""
        plan = {
            "intent": "Add a task",
            "confidence": 0.9,
            "execution_plan": [
                {"tool": "add_task", "parameters": {"user_id": "u1", "title": "Test"}}
            ]
        }
        is_valid, error = triage_plan(plan)
        assert is_valid is True
        assert error is None

    def test_empty_plan_fails(self):
        """Plan with no steps fails triage."""
        plan = {"execution_plan": []}
        is_valid, error = triage_plan(plan)
        assert is_valid is False
        assert "no steps" in error.lower()

    def test_plan_with_missing_execution_plan_key(self):
        """Plan without execution_plan key fails."""
        plan = {"intent": "unknown"}
        is_valid, error = triage_plan(plan)
        assert is_valid is False
        assert "no steps" in error.lower()

    def test_too_many_steps_fails(self):
        """Plan with >10 steps should fail."""
        steps = [{"tool": "add_task", "parameters": {}} for _ in range(15)]
        plan = {"execution_plan": steps}
        is_valid, error = triage_plan(plan)
        assert is_valid is False
        assert "15 steps" in error

    def test_circular_dependency_fails(self):
        """Step that depends on itself fails."""
        plan = {
            "execution_plan": [
                {
                    "id": "step1",
                    "tool": "add_task",
                    "parameters": {},
                    "depends_on": ["step1"]  # Self-reference
                }
            ]
        }
        is_valid, error = triage_plan(plan)
        assert is_valid is False
        assert "depends on itself" in error

    def test_multi_step_valid_plan(self):
        """Multi-step plan without issues passes."""
        plan = {
            "execution_plan": [
                {"tool": "get_tasks", "parameters": {"user_id": "u1"}},
                {"tool": "add_task", "parameters": {"user_id": "u1", "title": "New"}},
                {"tool": "task_complete", "parameters": {"title": "Old"}},
            ]
        }
        is_valid, error = triage_plan(plan)
        assert is_valid is True
        assert error is None

    def test_unknown_tool_logged_but_passes(self):
        """Unknown tools are logged but don't fail triage (registry is authoritative)."""
        plan = {
            "execution_plan": [
                {"tool": "unknown_tool_xyz", "parameters": {}}
            ]
        }
        is_valid, error = triage_plan(plan)
        # Unknown tools pass - the registry is authoritative
        assert is_valid is True

    def test_steps_key_alias(self):
        """Plan using 'steps' instead of 'execution_plan' works."""
        plan = {
            "steps": [
                {"tool": "add_task", "parameters": {"user_id": "u1"}}
            ]
        }
        is_valid, error = triage_plan(plan)
        assert is_valid is True


class TestPlanComplexityScore:
    """Test suite for get_plan_complexity_score() function."""

    def test_simple_plan_low_score(self):
        """Single-step plan has low complexity."""
        plan = {
            "execution_plan": [
                {"tool": "get_tasks", "parameters": {}}
            ]
        }
        score = get_plan_complexity_score(plan)
        assert score <= 3

    def test_complex_plan_high_score(self):
        """Multi-step plan with dependencies has higher score."""
        plan = {
            "execution_plan": [
                {"tool": "get_tasks", "parameters": {}, "depends_on": []},
                {"tool": "add_task", "parameters": {}, "depends_on": ["get_tasks"]},
                {"tool": "task_complete", "parameters": {}, "depends_on": ["add_task"]},
                {"tool": "search_tasks", "parameters": {}, "depends_on": []},
                {"tool": "delete_task", "parameters": {}, "depends_on": ["search_tasks"]},
                {"tool": "get_journal_entries", "parameters": {}, "depends_on": []},
            ]
        }
        score = get_plan_complexity_score(plan)
        assert score >= 5

    def test_empty_plan_minimal_score(self):
        """Empty plan has minimal score."""
        plan = {"execution_plan": []}
        score = get_plan_complexity_score(plan)
        assert score == 1  # Base score for 0 steps


class TestSummarizePlanForLogging:
    """Test suite for summarize_plan_for_logging() function."""

    def test_summary_contains_key_fields(self):
        """Summary includes step count, tools, complexity, intent, confidence."""
        plan = {
            "intent": "Create a new task for user",
            "confidence": 0.85,
            "execution_plan": [
                {"tool": "add_task", "parameters": {}},
                {"tool": "get_tasks", "parameters": {}},
            ]
        }
        summary = summarize_plan_for_logging(plan)

        assert summary["step_count"] == 2
        assert "add_task" in summary["tools"]
        assert "get_tasks" in summary["tools"]
        assert "complexity" in summary
        assert summary["confidence"] == 0.85
        assert "Create a new task" in summary["intent"]

    def test_summary_truncates_long_intent(self):
        """Intent is truncated at 50 chars."""
        long_intent = "This is a very long intent description that goes well beyond fifty characters"
        plan = {
            "intent": long_intent,
            "confidence": 0.5,
            "execution_plan": [{"tool": "get_tasks", "parameters": {}}]
        }
        summary = summarize_plan_for_logging(plan)
        assert len(summary["intent"]) <= 50


class TestKnownTools:
    """Test KNOWN_TOOLS constant."""

    def test_task_tools_present(self):
        """Task-related tools are in KNOWN_TOOLS."""
        assert "add_task" in KNOWN_TOOLS
        assert "get_tasks" in KNOWN_TOOLS
        assert "update_task" in KNOWN_TOOLS
        assert "delete_task" in KNOWN_TOOLS
        assert "task_complete" in KNOWN_TOOLS

    def test_journal_tools_present(self):
        """Journal tools are in KNOWN_TOOLS."""
        assert "add_journal_entry" in KNOWN_TOOLS
        assert "journal_ingest" in KNOWN_TOOLS
        assert "get_journal_entries" in KNOWN_TOOLS
