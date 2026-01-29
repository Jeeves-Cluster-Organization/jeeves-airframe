"""Worker coordinator service for distributed execution.

Constitutional Amendment XXIV: Horizontal Scaling Support.
Coordinates worker processes for distributed pipeline execution.

Kernel Integration:
- Creates process via KernelClient for lifecycle tracking
- Uses ResourceTracker for resource quota management
- Tracks resource usage from workers
- Reports lifecycle events to kernel
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from jeeves_infra.protocols import (
    DistributedBusProtocol,
    DistributedTask,
    QueueStats,
    CheckpointProtocol,
    Envelope,
    PipelineConfig,
    AgentConfig,
    PipelineRunner,
    LoggerProtocol,
)
from jeeves_infra.logging import get_current_logger

if TYPE_CHECKING:
    from jeeves_infra.kernel_client import KernelClient
    from jeeves_infra.resource_tracker import ResourceTracker


@dataclass
class WorkerConfig:
    """Configuration for a distributed worker."""

    worker_id: str
    queues: List[str]
    max_concurrent_tasks: int = 5
    heartbeat_interval_seconds: int = 30
    task_timeout_seconds: int = 300


@dataclass
class WorkerStatus:
    """Current status of a worker."""

    worker_id: str
    status: str  # "starting", "running", "stopping", "stopped"
    active_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    last_heartbeat: Optional[datetime] = None
    queues: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "worker_id": self.worker_id,
            "status": self.status,
            "active_tasks": self.active_tasks,
            "completed_tasks": self.completed_tasks,
            "failed_tasks": self.failed_tasks,
            "last_heartbeat": (
                self.last_heartbeat.isoformat() if self.last_heartbeat else None
            ),
            "queues": self.queues,
        }


class WorkerCoordinator:
    """Coordinates distributed workers for pipeline execution.

    Usage:
        coordinator = WorkerCoordinator(
            distributed_bus=redis_bus,
            checkpoint_adapter=postgres_checkpoint,
            runtime=unified_runtime,
            kernel_client=kernel_client,
            resource_tracker=resource_tracker,
        )

        # Submit work
        task_id = await coordinator.submit_envelope(envelope, "agent:planner")

        # Or run as worker
        await coordinator.run_worker(WorkerConfig(
            worker_id="worker-1",
            queues=["agent:*"],
        ))
    """

    def __init__(
        self,
        distributed_bus: DistributedBusProtocol,
        checkpoint_adapter: Optional[CheckpointProtocol] = None,
        runtime: Optional[PipelineRunner] = None,
        logger: Optional[LoggerProtocol] = None,
        kernel_client: Optional["KernelClient"] = None,
        resource_tracker: Optional["ResourceTracker"] = None,
    ):
        """Initialize worker coordinator.

        Args:
            distributed_bus: DistributedBusProtocol implementation
            checkpoint_adapter: Optional CheckpointProtocol for state persistence
            runtime: PipelineRunner for executing agents (required for workers)
            logger: Logger for DI
            kernel_client: Optional KernelClient for process lifecycle management
            resource_tracker: Optional ResourceTracker for quota management
        """
        self._bus = distributed_bus
        self._checkpoints = checkpoint_adapter
        self._runtime = runtime
        self._logger = logger or get_current_logger()
        self._kernel = kernel_client
        self._tracker = resource_tracker

        self._workers: Dict[str, WorkerStatus] = {}
        self._shutdown_event: Optional[asyncio.Event] = None

    async def submit_envelope(
        self,
        envelope: Envelope,
        queue_name: str,
        agent_name: Optional[str] = None,
        priority: int = 0,
    ) -> str:
        """Submit envelope for distributed processing.

        Kernel Integration:
        - Creates process via KernelClient for lifecycle tracking
        - Resource tracking via ResourceTracker

        Args:
            envelope: Envelope to process
            queue_name: Target queue
            agent_name: Specific agent to run (or next in pipeline)
            priority: Task priority (higher = more urgent)

        Returns:
            Task ID for tracking
        """
        task_id = f"task_{uuid.uuid4().hex[:16]}"
        pid = envelope.envelope_id

        # Create process via kernel if available
        if self._kernel:
            try:
                await self._kernel.create_process(
                    pid=pid,
                    user_id=envelope.metadata.get("user_id", "system"),
                    session_id=envelope.metadata.get("session_id", "default"),
                )
                self._logger.info(
                    "kernel_process_created",
                    pid=pid,
                    priority=priority,
                )
            except Exception as e:
                self._logger.warning(
                    "kernel_process_create_failed",
                    pid=pid,
                    error=str(e),
                )

        # Save checkpoint before enqueueing
        checkpoint_id = None
        if self._checkpoints:
            checkpoint_id = f"ckpt_{uuid.uuid4().hex[:16]}"
            await self._checkpoints.save_checkpoint(
                envelope_id=envelope.envelope_id,
                checkpoint_id=checkpoint_id,
                agent_name=agent_name or "submit",
                state=envelope.to_state_dict(),
                metadata={"queue": queue_name, "priority": priority},
            )

        task = DistributedTask(
            task_id=task_id,
            envelope_state=envelope.to_state_dict(),
            agent_name=agent_name or "",
            stage_order=envelope.current_stage if hasattr(envelope, "current_stage") else 0,
            checkpoint_id=checkpoint_id,
            priority=priority,
        )

        await self._bus.enqueue_task(queue_name, task)

        self._logger.info(
            "envelope_submitted",
            task_id=task_id,
            envelope_id=envelope.envelope_id,
            queue=queue_name,
            has_kernel=self._kernel is not None,
        )

        return task_id

    async def run_worker(
        self,
        config: WorkerConfig,
        agent_handler: Optional[Callable[[Envelope, str], Envelope]] = None,
    ) -> None:
        """Run as a distributed worker.

        Args:
            config: Worker configuration
            agent_handler: Optional custom handler for agent execution
        """
        self._shutdown_event = asyncio.Event()

        # Register worker
        await self._bus.register_worker(config.worker_id, config.queues)

        status = WorkerStatus(
            worker_id=config.worker_id,
            status="running",
            queues=config.queues,
            last_heartbeat=datetime.now(timezone.utc),
        )
        self._workers[config.worker_id] = status

        self._logger.info(
            "worker_started",
            worker_id=config.worker_id,
            queues=config.queues,
        )

        # Start heartbeat task
        heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(config.worker_id, config.heartbeat_interval_seconds)
        )

        # Process tasks
        try:
            await self._process_loop(config, agent_handler)
        finally:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

            # Deregister
            await self._bus.deregister_worker(config.worker_id)
            status.status = "stopped"

            self._logger.info(
                "worker_stopped",
                worker_id=config.worker_id,
                completed=status.completed_tasks,
                failed=status.failed_tasks,
            )

    async def stop_worker(self, worker_id: str) -> None:
        """Signal worker to stop gracefully."""
        if self._shutdown_event:
            self._shutdown_event.set()

    async def get_worker_status(self, worker_id: str) -> Optional[WorkerStatus]:
        """Get status of a specific worker."""
        return self._workers.get(worker_id)

    async def list_workers(self) -> List[WorkerStatus]:
        """List all known workers."""
        return list(self._workers.values())

    async def get_queue_stats(self, queue_name: str) -> QueueStats:
        """Get statistics for a queue."""
        return await self._bus.get_queue_stats(queue_name)

    async def list_queues(self) -> List[str]:
        """List all active queues."""
        return await self._bus.list_queues()

    async def _process_loop(
        self,
        config: WorkerConfig,
        agent_handler: Optional[Callable],
    ) -> None:
        """Main task processing loop."""
        status = self._workers[config.worker_id]
        semaphore = asyncio.Semaphore(config.max_concurrent_tasks)

        while not self._shutdown_event.is_set():
            # Process each queue
            for queue in config.queues:
                if self._shutdown_event.is_set():
                    break

                await semaphore.acquire()

                try:
                    task = await self._bus.dequeue_task(
                        queue,
                        config.worker_id,
                        timeout_seconds=5,  # Short timeout for responsiveness
                    )

                    if task:
                        status.active_tasks += 1
                        asyncio.create_task(
                            self._process_task(
                                task,
                                config,
                                agent_handler,
                                semaphore,
                            )
                        )
                    else:
                        semaphore.release()

                except Exception as e:
                    semaphore.release()
                    self._logger.error(
                        "worker_dequeue_error",
                        queue=queue,
                        error=str(e),
                    )
                    await asyncio.sleep(1)  # Back off on error

    async def _process_task(
        self,
        task: DistributedTask,
        config: WorkerConfig,
        agent_handler: Optional[Callable],
        semaphore: asyncio.Semaphore,
    ) -> None:
        """Process a single task.

        Resource Tracking:
        - Records agent hop via ResourceTracker
        - Checks quota before and after execution
        - Terminates process via kernel if quota exceeded
        """
        status = self._workers[config.worker_id]
        pid = None

        try:
            # Reconstruct envelope from state
            envelope = Envelope.from_dict(task.envelope_state)
            pid = envelope.envelope_id

            # Record agent hop and check quota
            if self._tracker and pid:
                exceeded = await self._tracker.record_agent_hop(pid)
                if exceeded:
                    self._logger.warning(
                        "task_quota_exceeded",
                        task_id=task.task_id,
                        pid=pid,
                        reason=exceeded,
                    )
                    # Terminate via kernel if available
                    if self._kernel:
                        await self._kernel.terminate_process(pid, reason=exceeded)
                    await self._bus.fail_task(
                        task.task_id,
                        f"Quota exceeded: {exceeded}",
                        retry=False,
                    )
                    status.failed_tasks += 1
                    return

            # Execute agent
            if agent_handler:
                result_envelope = await agent_handler(envelope, task.agent_name)
            elif self._runtime:
                result_envelope = await self._runtime.run_single_agent(
                    envelope,
                    task.agent_name,
                )
            else:
                raise RuntimeError("No handler or runtime configured")

            # Record resource usage from result envelope
            if self._tracker and pid:
                # Extract usage from envelope metadata if available
                llm_calls = result_envelope.metadata.get("llm_call_count", 0)
                tool_calls = result_envelope.metadata.get("tool_call_count", 0)
                tokens_in = result_envelope.metadata.get("total_tokens_in", 0)
                tokens_out = result_envelope.metadata.get("total_tokens_out", 0)

                if llm_calls:
                    exceeded = await self._tracker.record_llm_call(
                        pid, tokens_in=tokens_in, tokens_out=tokens_out
                    )
                    if exceeded:
                        result_envelope.terminated = True
                        result_envelope.termination_reason = exceeded

                if tool_calls:
                    for _ in range(tool_calls):
                        exceeded = await self._tracker.record_tool_call(pid)
                        if exceeded:
                            result_envelope.terminated = True
                            result_envelope.termination_reason = exceeded
                            break

            # Save checkpoint if enabled
            if self._checkpoints:
                checkpoint_id = f"ckpt_{uuid.uuid4().hex[:16]}"
                await self._checkpoints.save_checkpoint(
                    envelope_id=envelope.envelope_id,
                    checkpoint_id=checkpoint_id,
                    agent_name=task.agent_name,
                    state=result_envelope.to_state_dict(),
                    metadata={
                        "worker_id": config.worker_id,
                        "task_id": task.task_id,
                    },
                )

            # Complete task
            await self._bus.complete_task(
                task.task_id,
                {"envelope_state": result_envelope.to_state_dict()},
            )

            status.completed_tasks += 1

            self._logger.debug(
                "task_completed",
                task_id=task.task_id,
                agent=task.agent_name,
                has_tracker=self._tracker is not None,
            )

        except Exception as e:
            status.failed_tasks += 1

            self._logger.error(
                "task_failed",
                task_id=task.task_id,
                agent=task.agent_name,
                error=str(e),
            )

            # Terminate via kernel on failure
            if self._kernel and pid:
                try:
                    await self._kernel.terminate_process(pid, reason=str(e))
                except Exception as term_err:
                    self._logger.warning(
                        "kernel_terminate_failed",
                        pid=pid,
                        error=str(term_err),
                    )

            await self._bus.fail_task(
                task.task_id,
                str(e),
                retry=task.retry_count < task.max_retries,
            )

        finally:
            status.active_tasks -= 1
            semaphore.release()

    async def _heartbeat_loop(
        self,
        worker_id: str,
        interval_seconds: int,
    ) -> None:
        """Send periodic heartbeats."""
        while True:
            try:
                await asyncio.sleep(interval_seconds)
                await self._bus.heartbeat(worker_id)

                if worker_id in self._workers:
                    self._workers[worker_id].last_heartbeat = datetime.now(timezone.utc)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.warning(
                    "heartbeat_failed",
                    worker_id=worker_id,
                    error=str(e),
                )


class DistributedPipelineRunner:
    """Runs pipelines across distributed workers.

    Higher-level abstraction that manages routing tasks to appropriate
    queues based on agent configuration.
    """

    def __init__(
        self,
        coordinator: WorkerCoordinator,
        pipeline_config: PipelineConfig,
        logger: Optional[LoggerProtocol] = None,
    ):
        """Initialize distributed runner.

        Args:
            coordinator: WorkerCoordinator for task submission
            pipeline_config: Pipeline configuration
            logger: Logger for DI
        """
        self._coordinator = coordinator
        self._config = pipeline_config
        self._logger = logger or get_current_logger()

    async def run(self, envelope: Envelope) -> str:
        """Run pipeline on envelope, distributing work to workers.

        Args:
            envelope: Input envelope

        Returns:
            Task ID for first stage
        """
        # Find first agent in pipeline
        first_agent = self._get_first_agent()

        if not first_agent:
            raise ValueError("Pipeline has no agents configured")

        # Determine queue from agent config
        queue_name = self._get_queue_for_agent(first_agent)

        # Submit to coordinator
        task_id = await self._coordinator.submit_envelope(
            envelope,
            queue_name,
            agent_name=first_agent.name,
        )

        self._logger.info(
            "distributed_pipeline_started",
            envelope_id=envelope.envelope_id,
            task_id=task_id,
            first_agent=first_agent.name,
        )

        return task_id

    def _get_first_agent(self) -> Optional[AgentConfig]:
        """Get first agent in pipeline order."""
        if not self._config.agents:
            return None

        return min(self._config.agents, key=lambda a: a.stage_order)

    def _get_queue_for_agent(self, agent: AgentConfig) -> str:
        """Determine queue name for agent.

        Uses agent capabilities or falls back to name-based routing.
        """
        # Check for explicit queue in agent metadata
        if hasattr(agent, "metadata") and agent.metadata:
            queue = agent.metadata.get("queue")
            if queue:
                return queue

        # Route by capability
        if agent.capabilities:
            for cap in agent.capabilities:
                if cap.name == "llm":
                    return "agent:llm"
                if cap.name == "tools":
                    return "agent:tools"

        # Default: route by name
        return f"agent:{agent.name}"
