"""Agent and envelope fixtures for mission system tests.

Centralized Architecture (v4.0):
- Uses Envelope with dynamic outputs dict
- Pre-populated envelope fixtures for each pipeline stage
- No concrete agent classes (agents are config-driven)

Usage:
    @pytest.fixture
    def my_test(envelope_with_intent):
        # Envelope already has perception and intent outputs
        assert envelope_with_intent.current_stage == "planner"
"""

import pytest
from typing import Callable, Dict, Any
from mission_system.contracts_core import (
    Envelope,
    create_envelope,
)
from jeeves_infra.protocols import RequestContext
from mission_system.tests.fixtures.mocks import (
    MockDatabaseClient,
    MockLLMAdapter,
)


# =============================================================================
# FACTORY FIXTURES
# =============================================================================

@pytest.fixture
def envelope_factory() -> Callable[..., Envelope]:
    """Factory for creating test envelopes.

    Usage:
        def test_something(envelope_factory):
            env = envelope_factory(raw_input="custom query")
    """
    def _create(
        raw_input: str = "test query",
        session_id: str = "test-session",
        user_id: str = "test-user",
        **kwargs
    ) -> Envelope:
        request_context = RequestContext(
            request_id=kwargs.pop("request_id", "req_test_fixture"),
            capability="test_capability",
            session_id=session_id,
            user_id=user_id,
        )
        return create_envelope(
            raw_input=raw_input,
            request_context=request_context,
            **kwargs,
        )
    return _create


@pytest.fixture
def sample_envelope(envelope_factory) -> Envelope:
    """Basic sample envelope for tests."""
    return envelope_factory(raw_input="Where is the main function defined?")


# =============================================================================
# MOCK FIXTURES
# =============================================================================

@pytest.fixture
def mock_db() -> MockDatabaseClient:
    """Mock database client for isolated testing."""
    return MockDatabaseClient()


@pytest.fixture
def mock_tool_executor():
    """Mock tool executor for testing executor/traverser stages."""
    class MockToolExecutor:
        def __init__(self):
            self.executed_tools = []

        async def execute(self, tool_name: str, params: Dict[str, Any]) -> Dict:
            self.executed_tools.append((tool_name, params))
            return {"status": "success", "result": f"Executed {tool_name}"}

    return MockToolExecutor()


@pytest.fixture
def mock_llm_provider() -> MockLLMAdapter:
    """Mock LLM provider for isolated testing."""
    return MockLLMAdapter()


# =============================================================================
# PRE-POPULATED ENVELOPE FIXTURES
# =============================================================================

@pytest.fixture
def envelope_with_perception(envelope_factory) -> Envelope:
    """Envelope with perception output populated.

    State: perception -> intent (current)
    """
    env = envelope_factory()
    env.set_output("perception", {
        "normalized_input": "Where is the main function defined?",
        "context_summary": "",
        "detected_languages": ["python"],
        "session_scope": "test-session",
    })
    env.current_stage = "intent"
    return env


@pytest.fixture
def envelope_with_intent(envelope_with_perception) -> Envelope:
    """Envelope with intent output populated.

    State: perception -> intent -> planner (current)

    Note: Uses tool_suite (new architecture) instead of intent field.
    """
    env = envelope_with_perception
    env.set_output("intent", {
        "tool_suite": "symbol_lookup",  # New architecture
        "search_targets": ["main"],  # Required by new architecture
        "goals": ["Find the definition of main function"],
        "confidence": 0.9,
        "clarification_needed": False,
        "clarification_question": None,
    })
    env.initialize_goals(["Find the definition of main function"])
    env.current_stage = "planner"
    return env


@pytest.fixture
def envelope_with_plan(envelope_with_intent) -> Envelope:
    """Envelope with plan output populated.

    State: perception -> intent -> planner -> executor (current)
    """
    env = envelope_with_intent
    env.set_output("plan", {
        "plan_id": f"plan_{env.envelope_id}",
        "steps": [
            {"step_id": "s1", "tool": "search_symbol", "parameters": {"symbol": "main"}},
            {"step_id": "s2", "tool": "read_file", "parameters": {"path": "src/main.py"}},
        ],
        "rationale": "Search for main function, then read its definition",
        "feasibility_score": 0.85,
    })
    env.current_stage = "executor"
    return env


@pytest.fixture
def envelope_with_execution(envelope_with_plan) -> Envelope:
    """Envelope with execution output populated.

    State: perception -> intent -> planner -> executor -> synthesizer (current)
    """
    env = envelope_with_plan
    env.set_output("execution", {
        "results": [
            {
                "step_id": "s1",
                "tool": "search_symbol",
                "status": "success",
                "data": {"matches": [{"file": "src/main.py", "line": 10}]},
            },
            {
                "step_id": "s2",
                "tool": "read_file",
                "status": "success",
                "data": {"content": "def main():\n    print('hello')"},
            },
        ],
        "all_succeeded": True,
        "summary": "Found main function at src/main.py:10",
    })
    env.current_stage = "synthesizer"
    return env


@pytest.fixture
def envelope_with_synthesizer(envelope_with_execution) -> Envelope:
    """Envelope with synthesizer output populated.

    State: perception -> intent -> planner -> executor -> synthesizer -> critic (current)
    """
    env = envelope_with_execution
    env.set_output("synthesizer", {
        "entities": [
            {"name": "main", "type": "function", "location": "src/main.py:10"}
        ],
        "key_flows": [],
        "patterns": [],
        "summary": "Found main function at src/main.py:10",
        "evidence_summary": "Based on symbol search and file read",
    })
    env.current_stage = "critic"
    return env


@pytest.fixture
def envelope_with_critic(envelope_with_synthesizer) -> Envelope:
    """Envelope with critic output populated.

    State: perception -> intent -> planner -> executor -> synthesizer -> critic -> integration (current)
    """
    env = envelope_with_synthesizer
    env.set_output("critic", {
        "verdict": "approved",
        "confidence": 0.95,
        "intent_alignment_score": 0.92,
        "issues": [],
        "recommendations": [],
        "goal_updates": {
            "satisfied": ["Find the definition of main function"],
            "pending": [],
            "added": [],
        },
    })
    env.current_stage = "integration"
    # Mark goal as satisfied
    if env.all_goals:
        for goal in env.all_goals:
            env.goal_completion_status[goal] = "satisfied"
        env.remaining_goals = []
    return env


# =============================================================================
# SPECIAL STATE FIXTURES
# =============================================================================

@pytest.fixture
def envelope_with_clarification(envelope_with_perception) -> Envelope:
    """Envelope in clarification-required state.

    Note: Uses tool_suite (new architecture) instead of intent field.
    """
    env = envelope_with_perception
    env.set_output("intent", {
        "tool_suite": "text_search",  # Default when unclear
        "search_targets": [],  # Empty because clarification needed
        "goals": [],
        "confidence": 0.3,
        "clarification_needed": True,
        "clarification_question": "Could you specify which 'main' function you mean?",
    })
    env.clarification_pending = True
    env.clarification_question = "Could you specify which 'main' function you mean?"
    env.current_stage = "clarification"
    return env


@pytest.fixture
def envelope_with_loop_back(envelope_with_critic) -> Envelope:
    """Envelope that needs loop_back (critic verdict=loop_back)."""
    env = envelope_with_critic
    # Override critic output with loop_back verdict
    env.set_output("critic", {
        "verdict": "loop_back",
        "confidence": 0.5,
        "intent_alignment_score": 0.4,
        "issues": ["Results don't fully address the question"],
        "refine_intent_hint": "Focus on the entry point main function, not helper functions",
        "recommendations": ["Search for __main__ guard pattern"],
    })
    env.current_stage = "intent"
    env.iteration = 1
    env.metadata["loop_feedback_for_intent"] = {
        "prior_intent": env.outputs.get("intent", {}),
        "refine_hint": "Focus on the entry point main function, not helper functions",
        "issues": ["Results don't fully address the question"],
    }
    return env


__all__ = [
    # Factory fixtures
    "envelope_factory",
    "sample_envelope",
    # Mock fixtures
    "mock_db",
    "mock_tool_executor",
    "mock_llm_provider",
    # Pre-populated envelope fixtures
    "envelope_with_perception",
    "envelope_with_intent",
    "envelope_with_plan",
    "envelope_with_execution",
    "envelope_with_synthesizer",
    "envelope_with_critic",
    # Special state fixtures
    "envelope_with_clarification",
    "envelope_with_loop_back",
]
