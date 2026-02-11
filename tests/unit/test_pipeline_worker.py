"""Tests for PipelineWorker - Kernel-Driven Agent Execution.

These tests verify that:
1. PipelineWorker correctly initializes sessions with the kernel
2. PipelineWorker executes agents as instructed by the kernel
3. PipelineWorker reports results back to the kernel
4. PipelineWorker handles termination and interrupts correctly
"""

import logging
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass
from typing import Any, Dict, Optional

from jeeves_infra.pipeline_worker import PipelineWorker, WorkerResult
from jeeves_infra.kernel_client import (
    OrchestratorInstruction,
    OrchestrationSessionState,
    AgentExecutionMetrics,
)
from jeeves_infra.protocols.types import Envelope


# Create a test logger that accepts structlog-style keyword arguments
class StructlogCompatibleLogger:
    """Test logger that accepts keyword arguments like structlog."""

    def __init__(self):
        self._logger = logging.getLogger("test_pipeline_worker")

    def _log(self, level, msg, **kwargs):
        # Just ignore the kwargs for test purposes
        getattr(self._logger, level)(msg)

    def debug(self, msg, **kwargs):
        self._log("debug", msg, **kwargs)

    def info(self, msg, **kwargs):
        self._log("info", msg, **kwargs)

    def warning(self, msg, **kwargs):
        self._log("warning", msg, **kwargs)

    def error(self, msg, **kwargs):
        self._log("error", msg, **kwargs)


test_logger = StructlogCompatibleLogger()


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_kernel_client():
    """Create a mock KernelClient."""
    client = AsyncMock()
    return client


@pytest.fixture
def mock_envelope():
    """Create a mock Envelope."""
    envelope = MagicMock(spec=Envelope)
    envelope.envelope_id = "test-envelope-1"
    envelope.current_stage = "start"
    envelope.stage_order = []
    envelope.iteration = 0
    envelope.llm_call_count = 0
    envelope.agent_hop_count = 0
    envelope.terminated = False
    envelope.terminal_reason = None
    envelope.outputs = {}
    envelope.to_dict.return_value = {
        "envelope_id": "test-envelope-1",
        "current_stage": "start",
        "outputs": {},
    }
    return envelope


@pytest.fixture
def mock_agent():
    """Create a mock Agent."""
    agent = AsyncMock()
    agent.name = "understand"

    async def process(envelope):
        envelope.outputs["understand"] = {"intent": "greeting"}
        return envelope

    agent.process = process
    return agent


@pytest.fixture
def mock_agents(mock_agent):
    """Create a dict of mock agents."""
    understand_agent = MagicMock()
    understand_agent.name = "understand"
    understand_agent.process = AsyncMock()

    think_agent = MagicMock()
    think_agent.name = "think"
    think_agent.process = AsyncMock()

    respond_agent = MagicMock()
    respond_agent.name = "respond"
    respond_agent.process = AsyncMock()

    # Each agent modifies the envelope and returns it
    async def understand_process(envelope):
        envelope.outputs["understand"] = {"intent": "greeting"}
        return envelope

    async def think_process(envelope):
        envelope.outputs["think"] = {"plan": "respond with greeting"}
        return envelope

    async def respond_process(envelope):
        envelope.outputs["final_response"] = {"response": "Hello!"}
        return envelope

    understand_agent.process.side_effect = understand_process
    think_agent.process.side_effect = think_process
    respond_agent.process.side_effect = respond_process

    return {
        "understand": understand_agent,
        "think": think_agent,
        "respond": respond_agent,
    }


@pytest.fixture
def pipeline_config():
    """Create a test pipeline config."""
    return {
        "name": "test_pipeline",
        "max_iterations": 10,
        "max_llm_calls": 100,
        "max_agent_hops": 20,
        "agents": [
            {
                "name": "understand",
                "stage_order": 0,
                "default_next": "think",
                "output_key": "understand",
            },
            {
                "name": "think",
                "stage_order": 1,
                "default_next": "respond",
                "output_key": "think",
            },
            {
                "name": "respond",
                "stage_order": 2,
                "default_next": "end",
                "output_key": "final_response",
            },
        ],
    }


# =============================================================================
# Initialization Tests
# =============================================================================

@pytest.mark.asyncio
async def test_pipeline_worker_initialization(mock_kernel_client, mock_agents, mock_envelope, pipeline_config):
    """Test PipelineWorker correctly initializes a session with the kernel."""
    # Setup mock responses
    mock_kernel_client.initialize_orchestration_session.return_value = OrchestrationSessionState(
        process_id="test-envelope-1",
        current_stage="understand",
        stage_order=["understand", "think", "respond"],
    )
    mock_kernel_client.get_next_instruction.return_value = OrchestratorInstruction(
        kind="TERMINATE",
        terminal_reason="COMPLETED",
        termination_message="Pipeline completed",
        envelope={"current_stage": "end", "outputs": {}},
    )

    worker = PipelineWorker(
        kernel_client=mock_kernel_client,
        agents=mock_agents,
        logger=test_logger,
    )

    result = await worker.execute(
        process_id="test-envelope-1",
        pipeline_config=pipeline_config,
        envelope=mock_envelope,
    )

    # Verify session was initialized
    mock_kernel_client.initialize_orchestration_session.assert_called_once()
    call_args = mock_kernel_client.initialize_orchestration_session.call_args
    assert call_args.kwargs["process_id"] == "test-envelope-1"

    # Verify result
    assert isinstance(result, WorkerResult)
    assert result.terminated is True


# =============================================================================
# Agent Execution Tests
# =============================================================================

@pytest.mark.asyncio
async def test_pipeline_worker_executes_agents(mock_kernel_client, mock_agents, mock_envelope, pipeline_config):
    """Test PipelineWorker executes agents as instructed by kernel."""
    # Setup mock - kernel instructs to run 3 agents then terminate
    mock_kernel_client.initialize_orchestration_session.return_value = OrchestrationSessionState(
        process_id="test-envelope-1",
        current_stage="understand",
        stage_order=["understand", "think", "respond"],
    )

    # The worker calls get_next_instruction in a loop:
    # 1st call → RUN_AGENT (understand)
    # 2nd call → RUN_AGENT (think)
    # 3rd call → RUN_AGENT (respond)
    # 4th call → TERMINATE
    instruction_sequence = [
        OrchestratorInstruction(
            kind="RUN_AGENT",
            agent_name="understand",
            agent_config={"output_key": "understand"},
            envelope={"current_stage": "understand"},
        ),
        OrchestratorInstruction(
            kind="RUN_AGENT",
            agent_name="think",
            agent_config={"output_key": "think"},
            envelope={"current_stage": "think"},
        ),
        OrchestratorInstruction(
            kind="RUN_AGENT",
            agent_name="respond",
            agent_config={"output_key": "final_response"},
            envelope={"current_stage": "respond"},
        ),
        OrchestratorInstruction(
            kind="TERMINATE",
            terminal_reason="COMPLETED",
            envelope={"current_stage": "end"},
        ),
    ]

    # report_agent_result returns are not used in the loop, but still called
    mock_kernel_client.get_next_instruction.side_effect = instruction_sequence
    mock_kernel_client.report_agent_result.return_value = OrchestratorInstruction(
        kind="RUN_AGENT",  # Not actually used
        agent_name="",
    )

    worker = PipelineWorker(
        kernel_client=mock_kernel_client,
        agents=mock_agents,
        logger=test_logger,
    )

    result = await worker.execute(
        process_id="test-envelope-1",
        pipeline_config=pipeline_config,
        envelope=mock_envelope,
    )

    # Verify all agents were called
    assert mock_agents["understand"].process.called
    assert mock_agents["think"].process.called
    assert mock_agents["respond"].process.called

    # Verify results were reported to kernel
    assert mock_kernel_client.report_agent_result.call_count == 3

    # Verify final result
    assert result.terminated is True
    assert result.terminal_reason == "COMPLETED"


# =============================================================================
# Termination Tests
# =============================================================================

@pytest.mark.asyncio
async def test_pipeline_worker_handles_immediate_termination(mock_kernel_client, mock_agents, mock_envelope, pipeline_config):
    """Test PipelineWorker handles immediate termination from kernel."""
    mock_kernel_client.initialize_orchestration_session.return_value = OrchestrationSessionState(
        process_id="test-envelope-1",
        current_stage="understand",
        stage_order=["understand"],
    )
    mock_kernel_client.get_next_instruction.return_value = OrchestratorInstruction(
        kind="TERMINATE",
        terminal_reason="MAX_LLM_CALLS_EXCEEDED",
        termination_message="LLM quota exceeded",
        envelope={"current_stage": "understand", "terminated": True},
    )

    worker = PipelineWorker(
        kernel_client=mock_kernel_client,
        agents=mock_agents,
        logger=test_logger,
    )

    result = await worker.execute(
        process_id="test-envelope-1",
        pipeline_config=pipeline_config,
        envelope=mock_envelope,
    )

    # No agents should be executed
    for agent in mock_agents.values():
        assert not agent.process.called

    # Verify termination
    assert result.terminated is True
    assert "MAX_LLM_CALLS" in result.terminal_reason


# =============================================================================
# Interrupt Tests
# =============================================================================

@pytest.mark.asyncio
async def test_pipeline_worker_handles_interrupt(mock_kernel_client, mock_agents, mock_envelope, pipeline_config):
    """Test PipelineWorker handles interrupt instructions from kernel."""
    mock_kernel_client.initialize_orchestration_session.return_value = OrchestrationSessionState(
        process_id="test-envelope-1",
        current_stage="understand",
        stage_order=["understand"],
    )
    mock_kernel_client.get_next_instruction.return_value = OrchestratorInstruction(
        kind="WAIT_INTERRUPT",
        interrupt_pending=True,
        interrupt={
            "kind": "CLARIFICATION",
            "question": "What do you mean?",
        },
        envelope={"current_stage": "clarification"},
    )

    worker = PipelineWorker(
        kernel_client=mock_kernel_client,
        agents=mock_agents,
        logger=test_logger,
    )

    result = await worker.execute(
        process_id="test-envelope-1",
        pipeline_config=pipeline_config,
        envelope=mock_envelope,
    )

    # Verify interrupt handling
    assert result.terminated is False
    assert result.interrupted is True
    assert result.interrupt_kind == "CLARIFICATION"


# =============================================================================
# Error Handling Tests
# =============================================================================

@pytest.mark.asyncio
async def test_pipeline_worker_handles_agent_not_found(mock_kernel_client, mock_envelope, pipeline_config):
    """Test PipelineWorker reports error when agent not found."""
    mock_kernel_client.initialize_orchestration_session.return_value = OrchestrationSessionState(
        process_id="test-envelope-1",
        current_stage="unknown_agent",
        stage_order=["unknown_agent"],
    )
    # First call returns RUN_AGENT, second call (after error) returns TERMINATE
    mock_kernel_client.get_next_instruction.side_effect = [
        OrchestratorInstruction(
            kind="RUN_AGENT",
            agent_name="unknown_agent",
            agent_config={"output_key": "unknown"},
            envelope={"current_stage": "unknown_agent"},
        ),
        OrchestratorInstruction(
            kind="TERMINATE",
            terminal_reason="TOOL_FAILED_FATALLY",
            envelope={"terminated": True},
        ),
    ]
    # report_agent_result return value is not used in the loop
    mock_kernel_client.report_agent_result.return_value = OrchestratorInstruction(
        kind="RUN_AGENT",
        agent_name="",
    )

    # Empty agents dict - no agents registered
    worker = PipelineWorker(
        kernel_client=mock_kernel_client,
        agents={},
        logger=test_logger,
    )

    result = await worker.execute(
        process_id="test-envelope-1",
        pipeline_config=pipeline_config,
        envelope=mock_envelope,
    )

    # Verify error was reported to kernel
    mock_kernel_client.report_agent_result.assert_called_once()
    call_args = mock_kernel_client.report_agent_result.call_args
    assert call_args.kwargs["success"] is False
    assert "not found" in call_args.kwargs["error"]


@pytest.mark.asyncio
async def test_pipeline_worker_handles_agent_exception(mock_kernel_client, mock_envelope, pipeline_config):
    """Test PipelineWorker reports error when agent raises exception."""
    mock_kernel_client.initialize_orchestration_session.return_value = OrchestrationSessionState(
        process_id="test-envelope-1",
        current_stage="understand",
        stage_order=["understand"],
    )
    # First call returns RUN_AGENT, second call (after error) returns TERMINATE
    mock_kernel_client.get_next_instruction.side_effect = [
        OrchestratorInstruction(
            kind="RUN_AGENT",
            agent_name="understand",
            agent_config={"output_key": "understand"},
            envelope={"current_stage": "understand"},
        ),
        OrchestratorInstruction(
            kind="TERMINATE",
            terminal_reason="TOOL_FAILED_FATALLY",
            envelope={"terminated": True},
        ),
    ]
    # report_agent_result return value is not used in the loop
    mock_kernel_client.report_agent_result.return_value = OrchestratorInstruction(
        kind="RUN_AGENT",
        agent_name="",
    )

    # Agent that raises an exception
    failing_agent = AsyncMock()
    failing_agent.name = "understand"
    failing_agent.process = AsyncMock(side_effect=ValueError("LLM call failed"))

    worker = PipelineWorker(
        kernel_client=mock_kernel_client,
        agents={"understand": failing_agent},
        logger=test_logger,
    )

    result = await worker.execute(
        process_id="test-envelope-1",
        pipeline_config=pipeline_config,
        envelope=mock_envelope,
    )

    # Verify error was reported to kernel
    mock_kernel_client.report_agent_result.assert_called_once()
    call_args = mock_kernel_client.report_agent_result.call_args
    assert call_args.kwargs["success"] is False
    assert "LLM call failed" in call_args.kwargs["error"]


@pytest.mark.asyncio
async def test_pipeline_worker_handles_session_init_failure(mock_kernel_client, mock_agents, mock_envelope, pipeline_config):
    """Test PipelineWorker handles session initialization failure."""
    from jeeves_infra.kernel_client import KernelClientError

    mock_kernel_client.initialize_orchestration_session.side_effect = KernelClientError("Connection failed")

    worker = PipelineWorker(
        kernel_client=mock_kernel_client,
        agents=mock_agents,
        logger=test_logger,
    )

    result = await worker.execute(
        process_id="test-envelope-1",
        pipeline_config=pipeline_config,
        envelope=mock_envelope,
    )

    # Verify termination due to error
    assert result.terminated is True
    assert "Session init failed" in result.terminal_reason


# =============================================================================
# Streaming Tests
# =============================================================================

@pytest.mark.asyncio
async def test_pipeline_worker_streaming(mock_kernel_client, mock_agents, mock_envelope, pipeline_config):
    """Test PipelineWorker streaming execution."""
    mock_kernel_client.initialize_orchestration_session.return_value = OrchestrationSessionState(
        process_id="test-envelope-1",
        current_stage="understand",
        stage_order=["understand", "respond"],
    )
    # Streaming also calls get_next_instruction in a loop
    mock_kernel_client.get_next_instruction.side_effect = [
        OrchestratorInstruction(
            kind="RUN_AGENT",
            agent_name="understand",
            agent_config={"output_key": "understand"},
            envelope={"current_stage": "understand"},
        ),
        OrchestratorInstruction(
            kind="RUN_AGENT",
            agent_name="respond",
            agent_config={"output_key": "final_response"},
            envelope={"current_stage": "respond"},
        ),
        OrchestratorInstruction(
            kind="TERMINATE",
            terminal_reason="COMPLETED",
            envelope={"current_stage": "end"},
        ),
    ]
    # report_agent_result return value is not used, just provide a default
    mock_kernel_client.report_agent_result.return_value = OrchestratorInstruction(
        kind="RUN_AGENT",
        agent_name="",
    )

    worker = PipelineWorker(
        kernel_client=mock_kernel_client,
        agents=mock_agents,
        logger=test_logger,
    )

    events = []
    async for event in worker.execute_streaming(
        process_id="test-envelope-1",
        pipeline_config=pipeline_config,
        envelope=mock_envelope,
    ):
        events.append(event)

    # Verify we got agent outputs and end event
    event_names = [e[0] for e in events]
    assert "understand" in event_names
    assert "respond" in event_names
    assert "__end__" in event_names
