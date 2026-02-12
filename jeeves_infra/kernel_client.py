"""IPC Client for Rust Kernel.

Async Python client for communicating with the Rust kernel via TCP + msgpack.

Usage:
    from jeeves_infra.kernel_client import KernelClient

    async with KernelClient.connect("localhost:50051") as client:
        pcb = await client.create_process(
            pid="req-123",
            user_id="user-1",
            session_id="session-1",
        )

        usage = await client.record_usage(
            pid="req-123",
            llm_calls=1,
            tokens_in=100,
            tokens_out=50,
        )

        result = await client.check_quota(pid="req-123")
        if not result.within_bounds:
            print(f"Quota exceeded: {result.exceeded_reason}")
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from jeeves_infra.ipc import IpcTransport, IpcError

logger = logging.getLogger(__name__)

# Default kernel address from environment
DEFAULT_KERNEL_ADDRESS = os.getenv("JEEVES_KERNEL_ADDRESS", "localhost:50051")


@dataclass
class QuotaCheckResult:
    """Result of a quota check."""
    within_bounds: bool
    exceeded_reason: str = ""
    llm_calls: int = 0
    tool_calls: int = 0
    agent_hops: int = 0
    tokens_in: int = 0
    tokens_out: int = 0


@dataclass
class ProcessInfo:
    """Simplified process information."""
    pid: str
    request_id: str
    user_id: str
    session_id: str
    state: str  # NEW, READY, RUNNING, WAITING, BLOCKED, TERMINATED, ZOMBIE
    priority: str  # REALTIME, HIGH, NORMAL, LOW, IDLE
    llm_calls: int = 0
    tool_calls: int = 0
    agent_hops: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    current_stage: str = ""


@dataclass
class AgentExecutionMetrics:
    """Metrics from agent execution."""
    llm_calls: int = 0
    tool_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    duration_ms: int = 0


@dataclass
class OrchestratorInstruction:
    """Instruction from the kernel orchestrator."""
    kind: str  # RUN_AGENT, TERMINATE, WAIT_INTERRUPT
    agent_name: str = ""
    agent_config: Optional[Dict[str, Any]] = None
    envelope: Optional[Dict[str, Any]] = None
    terminal_reason: str = ""
    termination_message: str = ""
    interrupt_pending: bool = False
    interrupt: Optional[Dict[str, Any]] = None


@dataclass
class OrchestrationSessionState:
    """Current state of an orchestration session."""
    process_id: str
    current_stage: str
    stage_order: List[str]
    envelope: Optional[Dict[str, Any]] = None
    edge_traversals: Dict[str, int] = field(default_factory=dict)
    terminated: bool = False
    terminal_reason: str = ""


@dataclass
class QuotaDefaults:
    """Kernel's default resource quota."""
    max_llm_calls: int = 100
    max_tool_calls: int = 50
    max_agent_hops: int = 10
    max_iterations: int = 20
    timeout_seconds: int = 300
    soft_timeout_seconds: int = 240
    max_input_tokens: int = 100_000
    max_output_tokens: int = 50_000
    max_context_tokens: int = 150_000
    rate_limit_rpm: int = 60
    rate_limit_rph: int = 1000
    rate_limit_burst: int = 10
    max_inference_requests: int = 50
    max_inference_input_chars: int = 500_000


@dataclass
class SystemStatusResult:
    """Full system status snapshot from the kernel."""
    processes_total: int = 0
    processes_by_state: Dict[str, int] = field(default_factory=dict)
    services_healthy: int = 0
    services_degraded: int = 0
    services_unhealthy: int = 0
    active_orchestration_sessions: int = 0
    commbus_events_published: int = 0
    commbus_commands_sent: int = 0
    commbus_queries_executed: int = 0
    commbus_active_subscribers: int = 0


class KernelClient:
    """Async IPC client for the Rust kernel.

    Provides methods to interact with:
    - KernelService: Process lifecycle and resource management
    - EngineService: Envelope operations and pipeline execution
    - OrchestrationService: Kernel-driven pipeline orchestration

    Usage:
        async with KernelClient.connect("localhost:50051") as client:
            pcb = await client.create_process(pid="req-123", ...)
            usage = await client.record_usage(pid="req-123", llm_calls=1)
    """

    def __init__(self, transport: IpcTransport):
        """Initialize the client with an IPC transport.

        Args:
            transport: Connected IpcTransport instance.
        """
        self._transport = transport

    @classmethod
    @asynccontextmanager
    async def connect(
        cls,
        address: str = DEFAULT_KERNEL_ADDRESS,
        **kwargs,
    ) -> AsyncIterator["KernelClient"]:
        """Create a connected client as an async context manager.

        Args:
            address: Kernel address (host:port).

        Yields:
            Connected KernelClient instance.
        """
        host, _, port_str = address.rpartition(":")
        if not host:
            host = "127.0.0.1"
        port = int(port_str) if port_str else 50051

        transport = IpcTransport(host=host, port=port)
        await transport.connect()
        client = cls(transport)
        try:
            yield client
        finally:
            await client.close()

    async def close(self):
        """Close the IPC transport."""
        await self._transport.close()

    # =========================================================================
    # Process Lifecycle (KernelService)
    # =========================================================================

    async def create_process(
        self,
        pid: str,
        *,
        request_id: str = "",
        user_id: str = "",
        session_id: str = "",
        priority: str = "NORMAL",
        max_llm_calls: int = 100,
        max_tool_calls: int = 200,
        max_agent_hops: int = 200,
        max_iterations: int = 50,
        timeout_seconds: int = 300,
    ) -> ProcessInfo:
        """Create a new process in the kernel."""
        body = {
            "pid": pid,
            "request_id": request_id or pid,
            "user_id": user_id,
            "session_id": session_id,
            "priority": priority,
            "quota": {
                "max_llm_calls": max_llm_calls,
                "max_tool_calls": max_tool_calls,
                "max_agent_hops": max_agent_hops,
                "max_iterations": max_iterations,
                "timeout_seconds": timeout_seconds,
            },
        }
        try:
            response = await self._transport.request("kernel", "CreateProcess", body)
            return self._dict_to_process_info(response)
        except IpcError as e:
            logger.error(f"Failed to create process {pid}: {e}")
            raise KernelClientError(f"CreateProcess failed: {e}") from e

    async def get_process(self, pid: str) -> Optional[ProcessInfo]:
        """Get process information by PID. Returns None if not found."""
        try:
            response = await self._transport.request("kernel", "GetProcess", {"pid": pid})
            return self._dict_to_process_info(response)
        except IpcError as e:
            if e.code == "NOT_FOUND":
                return None
            logger.error(f"Failed to get process {pid}: {e}")
            raise KernelClientError(f"GetProcess failed: {e}") from e

    async def schedule_process(self, pid: str) -> ProcessInfo:
        """Schedule a process (transition NEW -> READY)."""
        try:
            response = await self._transport.request("kernel", "ScheduleProcess", {"pid": pid})
            return self._dict_to_process_info(response)
        except IpcError as e:
            logger.error(f"Failed to schedule process {pid}: {e}")
            raise KernelClientError(f"ScheduleProcess failed: {e}") from e

    async def get_next_runnable(self) -> Optional[ProcessInfo]:
        """Get the next runnable process (transitions READY -> RUNNING)."""
        try:
            response = await self._transport.request("kernel", "GetNextRunnable", {})
            if response.get("pid"):
                return self._dict_to_process_info(response)
            return None
        except IpcError as e:
            if e.code == "NOT_FOUND":
                return None
            logger.error(f"Failed to get next runnable: {e}")
            raise KernelClientError(f"GetNextRunnable failed: {e}") from e

    async def transition_state(
        self,
        pid: str,
        new_state: str,
        reason: str = "",
    ) -> ProcessInfo:
        """Transition a process to a new state."""
        body = {"pid": pid, "new_state": new_state, "reason": reason}
        try:
            response = await self._transport.request("kernel", "TransitionState", body)
            return self._dict_to_process_info(response)
        except IpcError as e:
            logger.error(f"Failed to transition process {pid}: {e}")
            raise KernelClientError(f"TransitionState failed: {e}") from e

    async def terminate_process(
        self,
        pid: str,
        reason: str = "",
        force: bool = False,
    ) -> ProcessInfo:
        """Terminate a process."""
        body = {"pid": pid, "reason": reason, "force": force}
        try:
            response = await self._transport.request("kernel", "TerminateProcess", body)
            return self._dict_to_process_info(response)
        except IpcError as e:
            logger.error(f"Failed to terminate process {pid}: {e}")
            raise KernelClientError(f"TerminateProcess failed: {e}") from e

    # =========================================================================
    # Resource Management (KernelService)
    # =========================================================================

    async def record_usage(
        self,
        pid: str,
        *,
        llm_calls: int = 0,
        tool_calls: int = 0,
        agent_hops: int = 0,
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> QuotaCheckResult:
        """Record resource usage for a process."""
        body = {
            "pid": pid,
            "llm_calls": llm_calls,
            "tool_calls": tool_calls,
            "agent_hops": agent_hops,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
        }
        try:
            response = await self._transport.request("kernel", "RecordUsage", body)
            return QuotaCheckResult(
                within_bounds=True,
                llm_calls=response.get("llm_calls", 0),
                tool_calls=response.get("tool_calls", 0),
                agent_hops=response.get("agent_hops", 0),
                tokens_in=response.get("tokens_in", 0),
                tokens_out=response.get("tokens_out", 0),
            )
        except IpcError as e:
            logger.error(f"Failed to record usage for {pid}: {e}")
            raise KernelClientError(f"RecordUsage failed: {e}") from e

    async def check_quota(self, pid: str) -> QuotaCheckResult:
        """Check if a process is within its resource quota."""
        try:
            response = await self._transport.request("kernel", "CheckQuota", {"pid": pid})
            return QuotaCheckResult(
                within_bounds=response.get("within_bounds", True),
                exceeded_reason=response.get("exceeded_reason", ""),
                llm_calls=response.get("llm_calls", 0),
                tool_calls=response.get("tool_calls", 0),
                agent_hops=response.get("agent_hops", 0),
                tokens_in=response.get("tokens_in", 0),
                tokens_out=response.get("tokens_out", 0),
            )
        except IpcError as e:
            logger.error(f"Failed to check quota for {pid}: {e}")
            raise KernelClientError(f"CheckQuota failed: {e}") from e

    async def check_rate_limit(
        self,
        user_id: str,
        endpoint: str = "",
        record: bool = True,
    ) -> Dict[str, Any]:
        """Check rate limit for a user."""
        body = {"user_id": user_id, "endpoint": endpoint, "record": record}
        try:
            return await self._transport.request("kernel", "CheckRateLimit", body)
        except IpcError as e:
            logger.error(f"Failed to check rate limit for {user_id}: {e}")
            raise KernelClientError(f"CheckRateLimit failed: {e}") from e

    # =========================================================================
    # Quota Defaults (Single Source of Truth)
    # =========================================================================

    async def set_quota_defaults(self, **overrides: int) -> QuotaDefaults:
        """Set (merge) kernel default quota. Only non-zero fields overwrite.

        Args:
            **overrides: Quota fields to override (e.g. max_llm_calls=200).

        Returns:
            The merged QuotaDefaults now active in the kernel.
        """
        body = {"quota": {k: v for k, v in overrides.items() if v is not None}}
        try:
            response = await self._transport.request("kernel", "SetQuotaDefaults", body)
            return self._dict_to_quota_defaults(response)
        except IpcError as e:
            logger.error(f"Failed to set quota defaults: {e}")
            raise KernelClientError(f"SetQuotaDefaults failed: {e}") from e

    async def get_quota_defaults(self) -> QuotaDefaults:
        """Get the kernel's current default quota."""
        try:
            response = await self._transport.request("kernel", "GetQuotaDefaults", {})
            return self._dict_to_quota_defaults(response)
        except IpcError as e:
            logger.error(f"Failed to get quota defaults: {e}")
            raise KernelClientError(f"GetQuotaDefaults failed: {e}") from e

    # =========================================================================
    # System Status
    # =========================================================================

    async def get_system_status(self) -> SystemStatusResult:
        """Get full system status snapshot from the kernel."""
        try:
            response = await self._transport.request("kernel", "GetSystemStatus", {})
            procs = response.get("processes", {})
            svcs = response.get("services", {})
            orch = response.get("orchestration", {})
            cb = response.get("commbus", {})
            return SystemStatusResult(
                processes_total=procs.get("total", 0),
                processes_by_state=dict(procs.get("by_state", {})),
                services_healthy=svcs.get("healthy", 0),
                services_degraded=svcs.get("degraded", 0),
                services_unhealthy=svcs.get("unhealthy", 0),
                active_orchestration_sessions=orch.get("active_sessions", 0),
                commbus_events_published=cb.get("events_published", 0),
                commbus_commands_sent=cb.get("commands_sent", 0),
                commbus_queries_executed=cb.get("queries_executed", 0),
                commbus_active_subscribers=cb.get("active_subscribers", 0),
            )
        except IpcError as e:
            logger.error(f"Failed to get system status: {e}")
            raise KernelClientError(f"GetSystemStatus failed: {e}") from e

    # =========================================================================
    # CommBus Event Subscription
    # =========================================================================

    async def subscribe_events(
        self,
        event_types: List[str],
        subscriber_id: str = "",
    ) -> AsyncIterator[Dict[str, Any]]:
        """Subscribe to kernel CommBus events (streaming).

        Yields event dicts with keys: event_type, payload, timestamp_ms, source.
        The payload is a JSON string that should be parsed by the consumer.

        Args:
            event_types: Event type patterns to subscribe to
                (e.g. ["process.created", "process.state_changed"]).
            subscriber_id: Optional subscriber ID for tracking.

        Yields:
            Event dicts from the CommBus stream.
        """
        body: Dict[str, Any] = {"event_types": event_types}
        if subscriber_id:
            body["subscriber_id"] = subscriber_id
        async for chunk in self._transport.request_stream(
            "commbus", "Subscribe", body
        ):
            yield chunk

    # =========================================================================
    # Queries (KernelService)
    # =========================================================================

    async def list_processes(
        self,
        state: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> List[ProcessInfo]:
        """List processes matching filters."""
        body = {
            "state": state or "",
            "user_id": user_id or "",
        }
        try:
            response = await self._transport.request("kernel", "ListProcesses", body)
            return [self._dict_to_process_info(p) for p in response.get("processes", [])]
        except IpcError as e:
            logger.error(f"Failed to list processes: {e}")
            raise KernelClientError(f"ListProcesses failed: {e}") from e

    async def get_process_counts(self) -> Dict[str, int]:
        """Get process counts by state."""
        try:
            response = await self._transport.request("kernel", "GetProcessCounts", {})
            counts = dict(response.get("counts_by_state", {}))
            counts["total"] = response.get("total", 0)
            counts["queue_depth"] = response.get("queue_depth", 0)
            return counts
        except IpcError as e:
            logger.error(f"Failed to get process counts: {e}")
            raise KernelClientError(f"GetProcessCounts failed: {e}") from e

    # =========================================================================
    # Envelope Operations (EngineService)
    # =========================================================================

    async def create_envelope(
        self,
        raw_input: str,
        *,
        user_id: str = "",
        session_id: str = "",
        request_id: str = "",
        metadata: Optional[Dict[str, str]] = None,
        stage_order: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Create a new envelope via the Rust engine."""
        body = {
            "raw_input": raw_input,
            "user_id": user_id,
            "session_id": session_id,
            "request_id": request_id,
            "metadata": metadata or {},
            "stage_order": stage_order or [],
        }
        try:
            return await self._transport.request("engine", "CreateEnvelope", body)
        except IpcError as e:
            logger.error(f"Failed to create envelope: {e}")
            raise KernelClientError(f"CreateEnvelope failed: {e}") from e

    async def check_bounds(self, envelope: Dict[str, Any]) -> Dict[str, Any]:
        """Check if an envelope is within bounds."""
        try:
            return await self._transport.request("engine", "CheckBounds", envelope)
        except IpcError as e:
            logger.error(f"Failed to check bounds: {e}")
            raise KernelClientError(f"CheckBounds failed: {e}") from e

    # =========================================================================
    # Orchestration (OrchestrationService)
    # =========================================================================

    async def initialize_orchestration_session(
        self,
        process_id: str,
        pipeline_config: Dict[str, Any],
        envelope: Dict[str, Any],
        force: bool = False,
    ) -> OrchestrationSessionState:
        """Initialize a new orchestration session."""
        body = {
            "process_id": process_id,
            "pipeline_config": json.dumps(pipeline_config),
            "envelope": json.dumps(envelope),
            "force": force,
        }
        try:
            response = await self._transport.request("orchestration", "InitializeSession", body)
            return self._dict_to_session_state(response)
        except IpcError as e:
            if e.code == "ALREADY_EXISTS":
                logger.warning(f"Session already exists for {process_id}")
                raise KernelClientError(f"Session already exists for process {process_id}") from e
            if e.code == "TIMEOUT":
                logger.error(f"Deadline exceeded initializing session {process_id}")
                raise KernelClientError("Request deadline exceeded") from e
            logger.error(f"Failed to initialize orchestration session {process_id}: {e}")
            raise KernelClientError(f"InitializeSession failed: {e}") from e

    async def get_next_instruction(
        self,
        process_id: str,
    ) -> OrchestratorInstruction:
        """Get the next instruction from the kernel."""
        try:
            response = await self._transport.request(
                "orchestration", "GetNextInstruction", {"process_id": process_id},
            )
            return self._dict_to_instruction(response)
        except IpcError as e:
            if e.code == "TIMEOUT":
                logger.error(f"Deadline exceeded getting next instruction for {process_id}")
                raise KernelClientError("Request deadline exceeded") from e
            logger.error(f"Failed to get next instruction for {process_id}: {e}")
            raise KernelClientError(f"GetNextInstruction failed: {e}") from e

    async def report_agent_result(
        self,
        process_id: str,
        agent_name: str,
        output: Optional[Dict[str, Any]] = None,
        metrics: Optional[AgentExecutionMetrics] = None,
        success: bool = True,
        error: str = "",
    ) -> OrchestratorInstruction:
        """Report agent execution result and get next instruction."""
        body: Dict[str, Any] = {
            "process_id": process_id,
            "agent_name": agent_name,
            "output": json.dumps(output) if output else "",
            "success": success,
            "error": error,
        }
        if metrics:
            body["metrics"] = {
                "llm_calls": metrics.llm_calls,
                "tool_calls": metrics.tool_calls,
                "tokens_in": metrics.tokens_in,
                "tokens_out": metrics.tokens_out,
                "duration_ms": metrics.duration_ms,
            }
        try:
            response = await self._transport.request("orchestration", "ReportAgentResult", body)
            return self._dict_to_instruction(response)
        except IpcError as e:
            if e.code == "TIMEOUT":
                logger.error(f"Deadline exceeded reporting agent result for {process_id}/{agent_name}")
                raise KernelClientError("Request deadline exceeded") from e
            logger.error(f"Failed to report agent result for {process_id}/{agent_name}: {e}")
            raise KernelClientError(f"ReportAgentResult failed: {e}") from e

    async def get_orchestration_session_state(
        self,
        process_id: str,
    ) -> OrchestrationSessionState:
        """Get current orchestration session state."""
        try:
            response = await self._transport.request(
                "orchestration", "GetSessionState", {"process_id": process_id},
            )
            return self._dict_to_session_state(response)
        except IpcError as e:
            if e.code == "TIMEOUT":
                logger.error(f"Deadline exceeded getting session state for {process_id}")
                raise KernelClientError("Request deadline exceeded") from e
            logger.error(f"Failed to get session state for {process_id}: {e}")
            raise KernelClientError(f"GetSessionState failed: {e}") from e

    # =========================================================================
    # High-Level Convenience Methods
    # =========================================================================

    async def record_llm_call(
        self,
        pid: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> Optional[str]:
        """Record an LLM call. Returns exceeded reason if quota exceeded."""
        try:
            await self.record_usage(pid=pid, llm_calls=1, tokens_in=tokens_in, tokens_out=tokens_out)
            result = await self.check_quota(pid)
            if not result.within_bounds:
                return result.exceeded_reason
            return None
        except KernelClientError:
            return None

    async def record_tool_call(self, pid: str) -> Optional[str]:
        """Record a tool call. Returns exceeded reason if quota exceeded."""
        try:
            await self.record_usage(pid=pid, tool_calls=1)
            result = await self.check_quota(pid)
            if not result.within_bounds:
                return result.exceeded_reason
            return None
        except KernelClientError:
            return None

    async def record_agent_hop(self, pid: str) -> Optional[str]:
        """Record an agent hop. Returns exceeded reason if quota exceeded."""
        try:
            await self.record_usage(pid=pid, agent_hops=1)
            result = await self.check_quota(pid)
            if not result.within_bounds:
                return result.exceeded_reason
            return None
        except KernelClientError:
            return None

    # =========================================================================
    # Inference Methods (Kernel-Tracked)
    # =========================================================================

    async def embed_batch(
        self,
        pid: str,
        texts: list[str],
        embedding_fn: "Callable[[list[str]], list[list[float]]] | None" = None,
    ) -> list[list[float]]:
        """Compute embeddings for multiple texts with kernel tracking."""
        if not texts:
            return []
        if embedding_fn is None:
            raise KernelClientError(
                "embedding_fn is required. Pass a function like "
                "EmbeddingService().embed_batch to compute embeddings."
            )
        try:
            return embedding_fn(texts)
        except Exception as e:
            raise KernelClientError(f"Embedding computation failed: {e}") from e

    async def embed(
        self,
        pid: str,
        text: str,
        embedding_fn: "Callable[[str], list[float]] | None" = None,
    ) -> list[float]:
        """Compute embedding for a single text with kernel tracking."""
        if embedding_fn is None:
            raise KernelClientError(
                "embedding_fn is required. Pass a function like "
                "EmbeddingService().embed to compute embeddings."
            )
        try:
            return embedding_fn(text)
        except Exception as e:
            raise KernelClientError(f"Embedding computation failed: {e}") from e

    # =========================================================================
    # Internal Helpers
    # =========================================================================

    def _dict_to_process_info(self, d: Dict[str, Any]) -> ProcessInfo:
        """Convert response dict to ProcessInfo."""
        usage = d.get("usage", {})
        return ProcessInfo(
            pid=d.get("pid", ""),
            request_id=d.get("request_id", ""),
            user_id=d.get("user_id", ""),
            session_id=d.get("session_id", ""),
            state=d.get("state", "UNKNOWN"),
            priority=d.get("priority", "NORMAL"),
            llm_calls=usage.get("llm_calls", 0),
            tool_calls=usage.get("tool_calls", 0),
            agent_hops=usage.get("agent_hops", 0),
            tokens_in=usage.get("tokens_in", 0),
            tokens_out=usage.get("tokens_out", 0),
            current_stage=d.get("current_stage", ""),
        )

    def _dict_to_quota_defaults(self, d: Dict[str, Any]) -> QuotaDefaults:
        """Convert response dict to QuotaDefaults."""
        return QuotaDefaults(
            max_llm_calls=d.get("max_llm_calls", 100),
            max_tool_calls=d.get("max_tool_calls", 50),
            max_agent_hops=d.get("max_agent_hops", 10),
            max_iterations=d.get("max_iterations", 20),
            timeout_seconds=d.get("timeout_seconds", 300),
            soft_timeout_seconds=d.get("soft_timeout_seconds", 240),
            max_input_tokens=d.get("max_input_tokens", 100_000),
            max_output_tokens=d.get("max_output_tokens", 50_000),
            max_context_tokens=d.get("max_context_tokens", 150_000),
            rate_limit_rpm=d.get("rate_limit_rpm", 60),
            rate_limit_rph=d.get("rate_limit_rph", 1000),
            rate_limit_burst=d.get("rate_limit_burst", 10),
            max_inference_requests=d.get("max_inference_requests", 50),
            max_inference_input_chars=d.get("max_inference_input_chars", 500_000),
        )

    def _dict_to_instruction(self, d: Dict[str, Any]) -> OrchestratorInstruction:
        """Convert response dict to OrchestratorInstruction."""
        agent_config = None
        raw_config = d.get("agent_config")
        if raw_config:
            if isinstance(raw_config, str):
                try:
                    agent_config = json.loads(raw_config)
                except json.JSONDecodeError:
                    pass
            elif isinstance(raw_config, dict):
                agent_config = raw_config

        envelope = None
        raw_envelope = d.get("envelope")
        if raw_envelope:
            if isinstance(raw_envelope, str):
                try:
                    envelope = json.loads(raw_envelope)
                except json.JSONDecodeError:
                    pass
            elif isinstance(raw_envelope, dict):
                envelope = raw_envelope

        return OrchestratorInstruction(
            kind=d.get("kind", "UNSPECIFIED"),
            agent_name=d.get("agent_name", ""),
            agent_config=agent_config,
            envelope=envelope,
            terminal_reason=d.get("terminal_reason", ""),
            termination_message=d.get("termination_message", ""),
            interrupt_pending=d.get("interrupt_pending", False),
            interrupt=d.get("interrupt"),
        )

    def _dict_to_session_state(self, d: Dict[str, Any]) -> OrchestrationSessionState:
        """Convert response dict to OrchestrationSessionState."""
        envelope = None
        raw_envelope = d.get("envelope")
        if raw_envelope:
            if isinstance(raw_envelope, str):
                try:
                    envelope = json.loads(raw_envelope)
                except json.JSONDecodeError:
                    pass
            elif isinstance(raw_envelope, dict):
                envelope = raw_envelope

        return OrchestrationSessionState(
            process_id=d.get("process_id", ""),
            current_stage=d.get("current_stage", ""),
            stage_order=d.get("stage_order", []),
            envelope=envelope,
            edge_traversals=d.get("edge_traversals", {}),
            terminated=d.get("terminated", False),
            terminal_reason=d.get("terminal_reason", ""),
        )


class KernelClientError(Exception):
    """Exception raised for kernel client errors."""
    pass


__all__ = [
    "KernelClient",
    "KernelClientError",
    "QuotaCheckResult",
    "QuotaDefaults",
    "SystemStatusResult",
    "ProcessInfo",
    "AgentExecutionMetrics",
    "OrchestratorInstruction",
    "OrchestrationSessionState",
    "DEFAULT_KERNEL_ADDRESS",
]
