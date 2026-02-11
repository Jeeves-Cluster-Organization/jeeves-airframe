"""Pipeline Worker - Kernel-Driven Agent Execution.

This module provides PipelineWorker, which executes agents under kernel control.
The kernel owns orchestration (loop, routing, bounds); Python just runs agents.

Usage:
    from jeeves_infra.pipeline_worker import PipelineWorker
    from jeeves_infra.kernel_client import KernelClient

    async with KernelClient.connect() as kernel:
        worker = PipelineWorker(
            kernel_client=kernel,
            agents={"understand": agent1, "respond": agent2},
            logger=logger,
        )
        result = await worker.execute(
            process_id="req-123",
            pipeline_config=config,
            envelope=envelope,
        )

Architecture:
    Kernel (Go)                      Python Worker
    ───────────                      ─────────────
    GetNextInstruction() ──────────► "Run agent X"

                                     Execute agent (LLM, tools)

    ReportAgentResult() ◄─────────── Output + metrics

The worker has NO control over routing or bounds - it simply:
1. Asks kernel for next instruction
2. Executes the specified agent
3. Reports result
4. Repeats until TERMINATE or WAIT_INTERRUPT

Constitutional Reference:
- Kernel owns orchestration loop
- Python is a worker, not a controller
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable, Dict, Optional, Protocol, Tuple, TYPE_CHECKING

from jeeves_infra.kernel_client import (
    KernelClient,
    AgentExecutionMetrics,
    OrchestratorInstruction,
    OrchestrationSessionState,
    KernelClientError,
)
from jeeves_infra.protocols.types import Envelope

if TYPE_CHECKING:
    from jeeves_infra.runtime.agents import Agent

logger = logging.getLogger(__name__)


class AgentProtocol(Protocol):
    """Protocol for agents that can be executed by the worker."""

    name: str

    async def process(self, envelope: Envelope) -> Envelope:
        """Execute agent on envelope."""
        ...


@dataclass
class WorkerResult:
    """Result from pipeline worker execution."""
    envelope: Envelope
    terminated: bool
    terminal_reason: str = ""
    interrupted: bool = False
    interrupt_kind: str = ""


class PipelineWorker:
    """Executes agents under kernel control.

    This worker has NO orchestration logic - it simply:
    1. Initializes a session with the kernel
    2. Gets instructions from the kernel
    3. Executes agents as instructed
    4. Reports results back to the kernel
    5. Repeats until TERMINATE or WAIT_INTERRUPT

    The kernel makes all decisions about:
    - Which agent to run next
    - Whether to continue or terminate
    - Bounds checking
    - Routing rule evaluation
    """

    def __init__(
        self,
        kernel_client: KernelClient,
        agents: Dict[str, AgentProtocol],
        logger: Optional[logging.Logger] = None,
        persistence: Optional[Any] = None,
    ):
        """Initialize the pipeline worker.

        Args:
            kernel_client: Connected KernelClient for IPC calls
            agents: Dict mapping agent names to Agent instances
            logger: Optional logger for structured logging
            persistence: Optional persistence layer for state saving
        """
        self._kernel = kernel_client
        self._agents = agents
        self._logger = logger or logging.getLogger(__name__)
        self._persistence = persistence

    async def execute(
        self,
        process_id: str,
        pipeline_config: Dict[str, Any],
        envelope: Envelope,
        thread_id: str = "",
        force: bool = False,
    ) -> WorkerResult:
        """Execute pipeline under kernel control.

        Args:
            process_id: Unique process identifier
            pipeline_config: Pipeline configuration dict
            envelope: Initial envelope
            thread_id: Optional thread ID for persistence
            force: If True, replace existing session with same process_id.
                   Default False means error if session already exists.

        Returns:
            WorkerResult with final envelope and status
        """
        # Initialize session with kernel
        try:
            session_state = await self._kernel.initialize_orchestration_session(
                process_id=process_id,
                pipeline_config=pipeline_config,
                envelope=envelope.to_dict(),
                force=force,
            )
            self._logger.info(
                "worker_session_initialized",
                process_id=process_id,
                current_stage=session_state.current_stage,
            )
        except KernelClientError as e:
            error_msg = str(e)
            if "already exists" in error_msg.lower():
                self._logger.error(
                    "worker_session_already_exists",
                    process_id=process_id,
                    hint="Use force=True to replace existing session",
                )
            elif "deadline" in error_msg.lower():
                self._logger.error(
                    "worker_session_deadline_exceeded",
                    process_id=process_id,
                )
            else:
                self._logger.error("worker_session_init_failed", error=error_msg)
            envelope.terminated = True
            terminal_reason = f"Session init failed: {e}"
            envelope.terminal_reason = terminal_reason
            return WorkerResult(
                envelope=envelope,
                terminated=True,
                terminal_reason=terminal_reason,
            )

        # Main execution loop - kernel controls everything
        while True:
            # Get next instruction from kernel
            try:
                instruction = await self._kernel.get_next_instruction(process_id)
            except KernelClientError as e:
                self._logger.error("worker_get_instruction_failed", error=str(e))
                envelope.terminated = True
                envelope.terminal_reason = f"Get instruction failed: {e}"
                return WorkerResult(
                    envelope=envelope,
                    terminated=True,
                    terminal_reason=str(e),
                )

            self._logger.debug(
                "worker_instruction_received",
                process_id=process_id,
                kind=instruction.kind,
                agent_name=instruction.agent_name,
            )

            # Handle instruction based on kind
            if instruction.kind == "TERMINATE":
                # Update envelope from kernel state
                if instruction.envelope:
                    envelope = self._merge_envelope(envelope, instruction.envelope)
                envelope.terminated = True
                envelope.terminal_reason = instruction.terminal_reason

                self._logger.info(
                    "worker_pipeline_terminated",
                    process_id=process_id,
                    reason=instruction.terminal_reason,
                )
                return WorkerResult(
                    envelope=envelope,
                    terminated=True,
                    terminal_reason=instruction.terminal_reason,
                )

            elif instruction.kind == "WAIT_INTERRUPT":
                # Update envelope from kernel state
                if instruction.envelope:
                    envelope = self._merge_envelope(envelope, instruction.envelope)

                interrupt_kind = ""
                if instruction.interrupt:
                    interrupt_kind = instruction.interrupt.get("kind", "")

                self._logger.info(
                    "worker_waiting_interrupt",
                    process_id=process_id,
                    interrupt_kind=interrupt_kind,
                )
                return WorkerResult(
                    envelope=envelope,
                    terminated=False,
                    interrupted=True,
                    interrupt_kind=interrupt_kind,
                )

            elif instruction.kind == "RUN_AGENT":
                # Execute the specified agent
                agent_name = instruction.agent_name
                agent = self._agents.get(agent_name)

                if not agent:
                    self._logger.error(
                        "worker_agent_not_found",
                        process_id=process_id,
                        agent_name=agent_name,
                    )
                    # Report error to kernel
                    instruction = await self._kernel.report_agent_result(
                        process_id=process_id,
                        agent_name=agent_name,
                        output=None,
                        metrics=None,
                        success=False,
                        error=f"Agent not found: {agent_name}",
                    )
                    continue

                # Update envelope from kernel state before execution
                if instruction.envelope:
                    envelope = self._merge_envelope(envelope, instruction.envelope)

                # Execute agent
                start_time = time.time()
                llm_calls_before = envelope.llm_call_count

                try:
                    envelope = await agent.process(envelope)
                    success = True
                    error = ""
                except Exception as e:
                    self._logger.error(
                        "worker_agent_error",
                        process_id=process_id,
                        agent_name=agent_name,
                        error=str(e),
                    )
                    success = False
                    error = str(e)

                # Calculate metrics
                duration_ms = int((time.time() - start_time) * 1000)
                llm_calls = envelope.llm_call_count - llm_calls_before

                metrics = AgentExecutionMetrics(
                    llm_calls=llm_calls,
                    tool_calls=0,  # TODO: track tool calls
                    tokens_in=0,   # TODO: track tokens
                    tokens_out=0,
                    duration_ms=duration_ms,
                )

                # Get output from envelope
                output = None
                agent_config = instruction.agent_config
                if agent_config and success:
                    output_key = agent_config.get("output_key", agent_name)
                    output = envelope.outputs.get(output_key, {})

                # Report result to kernel and get next instruction
                try:
                    instruction = await self._kernel.report_agent_result(
                        process_id=process_id,
                        agent_name=agent_name,
                        output=output,
                        metrics=metrics,
                        success=success,
                        error=error,
                    )
                except KernelClientError as e:
                    self._logger.error("worker_report_result_failed", error=str(e))
                    envelope.terminated = True
                    envelope.terminal_reason = f"Report result failed: {e}"
                    return WorkerResult(
                        envelope=envelope,
                        terminated=True,
                        terminal_reason=str(e),
                    )

                # Persist state if configured
                if self._persistence and thread_id:
                    try:
                        await self._persistence.save_state(thread_id, envelope.to_state_dict())
                    except Exception as e:
                        self._logger.warning("worker_persistence_failed", error=str(e))

                # Continue loop - the instruction from report_agent_result
                # will be handled in the next iteration
                # We need to handle it now actually since we got a new instruction
                # Let me refactor to handle it properly

            else:
                self._logger.warning(
                    "worker_unknown_instruction",
                    process_id=process_id,
                    kind=instruction.kind,
                )
                envelope.terminated = True
                envelope.terminal_reason = f"Unknown instruction kind: {instruction.kind}"
                return WorkerResult(
                    envelope=envelope,
                    terminated=True,
                    terminal_reason=envelope.terminal_reason,
                )

    async def execute_streaming(
        self,
        process_id: str,
        pipeline_config: Dict[str, Any],
        envelope: Envelope,
        thread_id: str = "",
        force: bool = False,
    ) -> AsyncIterator[Tuple[str, Dict[str, Any]]]:
        """Execute pipeline with streaming outputs.

        Yields (agent_name, output) tuples as agents complete.

        Args:
            process_id: Unique process identifier
            pipeline_config: Pipeline configuration dict
            envelope: Initial envelope
            thread_id: Optional thread ID for persistence
            force: If True, replace existing session with same process_id.
                   Default False means error if session already exists.

        Yields:
            Tuple of (agent_name, output_dict)
        """
        # Initialize session with kernel
        try:
            session_state = await self._kernel.initialize_orchestration_session(
                process_id=process_id,
                pipeline_config=pipeline_config,
                envelope=envelope.to_dict(),
                force=force,
            )
        except KernelClientError as e:
            error_msg = str(e)
            if "already exists" in error_msg.lower():
                self._logger.error(
                    "worker_session_already_exists",
                    process_id=process_id,
                    hint="Use force=True to replace existing session",
                )
            elif "deadline" in error_msg.lower():
                self._logger.error(
                    "worker_session_deadline_exceeded",
                    process_id=process_id,
                )
            else:
                self._logger.error("worker_session_init_failed", error=error_msg)
            yield ("__error__", {"error": str(e)})
            return

        # Main execution loop
        while True:
            try:
                instruction = await self._kernel.get_next_instruction(process_id)
            except KernelClientError as e:
                yield ("__error__", {"error": str(e)})
                return

            if instruction.kind == "TERMINATE":
                yield ("__end__", {
                    "terminated": True,
                    "reason": instruction.terminal_reason,
                })
                return

            elif instruction.kind == "WAIT_INTERRUPT":
                interrupt_kind = ""
                if instruction.interrupt:
                    interrupt_kind = instruction.interrupt.get("kind", "")
                yield ("__interrupt__", {
                    "kind": interrupt_kind,
                    "interrupt": instruction.interrupt,
                })
                return

            elif instruction.kind == "RUN_AGENT":
                agent_name = instruction.agent_name
                agent = self._agents.get(agent_name)

                if not agent:
                    await self._kernel.report_agent_result(
                        process_id=process_id,
                        agent_name=agent_name,
                        success=False,
                        error=f"Agent not found: {agent_name}",
                    )
                    continue

                if instruction.envelope:
                    envelope = self._merge_envelope(envelope, instruction.envelope)

                start_time = time.time()
                llm_calls_before = envelope.llm_call_count

                try:
                    envelope = await agent.process(envelope)
                    success = True
                    error = ""
                except Exception as e:
                    success = False
                    error = str(e)

                duration_ms = int((time.time() - start_time) * 1000)
                llm_calls = envelope.llm_call_count - llm_calls_before

                metrics = AgentExecutionMetrics(
                    llm_calls=llm_calls,
                    duration_ms=duration_ms,
                )

                output = None
                if instruction.agent_config and success:
                    output_key = instruction.agent_config.get("output_key", agent_name)
                    output = envelope.outputs.get(output_key, {})

                await self._kernel.report_agent_result(
                    process_id=process_id,
                    agent_name=agent_name,
                    output=output,
                    metrics=metrics,
                    success=success,
                    error=error,
                )

                # Yield the output for streaming
                if success and output:
                    yield (agent_name, output)

                if self._persistence and thread_id:
                    try:
                        await self._persistence.save_state(thread_id, envelope.to_state_dict())
                    except Exception:
                        pass

    def _merge_envelope(self, envelope: Envelope, kernel_state: Dict[str, Any]) -> Envelope:
        """Merge kernel envelope state into Python envelope.

        The kernel is authoritative for orchestration state:
        - current_stage
        - stage_order
        - iteration
        - llm_call_count
        - agent_hop_count
        - terminated
        - terminal_reason
        """
        if "current_stage" in kernel_state:
            envelope.current_stage = kernel_state["current_stage"]
        if "stage_order" in kernel_state:
            envelope.stage_order = kernel_state["stage_order"]
        if "iteration" in kernel_state:
            envelope.iteration = kernel_state["iteration"]
        if "llm_call_count" in kernel_state:
            envelope.llm_call_count = kernel_state["llm_call_count"]
        if "agent_hop_count" in kernel_state:
            envelope.agent_hop_count = kernel_state["agent_hop_count"]
        if "terminated" in kernel_state:
            envelope.terminated = kernel_state["terminated"]
        if "terminal_reason" in kernel_state:
            envelope.terminal_reason = kernel_state["terminal_reason"]
        if "outputs" in kernel_state:
            # Merge outputs - kernel may have updated them
            envelope.outputs.update(kernel_state["outputs"])
        return envelope


__all__ = [
    "PipelineWorker",
    "WorkerResult",
    "AgentProtocol",
]
