"""Mock implementations for jeeves_core_engine protocols.

These mocks allow jeeves_infra tests to run in isolation without
depending on the actual core engine implementation.

Centralized Architecture (v4.0):
- Uses Envelope (not CoreEnvelope)
- Stage order defined in pipeline config, not enum
"""

import pytest
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MockEnvelope:
    """Mock Envelope for testing jeeves_infra components.

    This provides a minimal envelope interface that jeeves_infra
    components may depend on, without requiring the full
    jeeves_core_engine implementation.

    Centralized Architecture (v4.0):
    - Uses `outputs` dict instead of per-stage fields
    - Stage tracking via `current_stage` string
    """

    raw_input: str = "Test query"
    user_id: str = "test-user"
    session_id: str = "test-session"
    envelope_id: str = "test-envelope-001"
    request_id: str = "test-request-001"
    current_stage: str = "perception"

    # Dynamic outputs (v4.0 architecture)
    outputs: Dict[str, Any] = field(default_factory=dict)

    # Stage order
    stage_order: List[str] = field(default_factory=lambda: [
        "perception", "intent", "planner", "executor",
        "synthesizer", "critic", "integration"
    ])

    # Control flags
    terminated: bool = False
    clarification_pending: bool = False
    confirmation_pending: bool = False
    terminal_reason: Optional[str] = None
    terminal_message: Optional[str] = None

    # Counters
    iteration: int = 0
    llm_call_count: int = 0
    agent_hop_count: int = 0

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Goals (v4.0)
    all_goals: List[str] = field(default_factory=list)
    remaining_goals: List[str] = field(default_factory=list)
    goal_completion_status: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "raw_input": self.raw_input,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "envelope_id": self.envelope_id,
            "current_stage": self.current_stage,
            "terminated": self.terminated,
            "iteration": self.iteration,
            "llm_call_count": self.llm_call_count,
            "outputs": self.outputs,
        }

    def terminate(self, message: str, reason: str) -> None:
        """Mark envelope as terminated."""
        self.terminated = True
        self.terminal_message = message
        self.terminal_reason = reason

    def can_continue(self) -> bool:
        """Check if pipeline can continue."""
        return not self.terminated and self.iteration < 10


@pytest.fixture
def mock_envelope_factory():
    """Factory for creating mock envelopes.

    Usage:
        def test_something(mock_envelope_factory):
            envelope = mock_envelope_factory(user_id="custom-user")
    """
    def _create(**kwargs) -> MockEnvelope:
        return MockEnvelope(**kwargs)
    return _create


@pytest.fixture
def mock_envelope(mock_envelope_factory) -> MockEnvelope:
    """Create a basic mock envelope."""
    return mock_envelope_factory()
