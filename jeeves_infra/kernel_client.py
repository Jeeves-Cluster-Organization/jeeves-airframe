"""Python gRPC Client for Go Kernel.

This module provides an async Python client that wraps the gRPC stubs
for communicating with the Go kernel (KernelService) and engine (EngineService).

Usage:
    from jeeves_infra.kernel_client import KernelClient, get_kernel_client

    # Create client with connection
    async with KernelClient.connect("localhost:50051") as client:
        # Create and manage processes
        pcb = await client.create_process(
            pid="req-123",
            user_id="user-1",
            session_id="session-1",
        )

        # Record resource usage
        usage = await client.record_usage(
            pid="req-123",
            llm_calls=1,
            tokens_in=100,
            tokens_out=50,
        )

        # Check quota
        result = await client.check_quota(pid="req-123")
        if not result.within_bounds:
            print(f"Quota exceeded: {result.exceeded_reason}")

Constitutional Reference:
- Session 15: Wire Python capabilities to Go kernel via gRPC
- jeeves-core = pure Go, Python calls via gRPC
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional, TYPE_CHECKING

import grpc
from grpc import aio as grpc_aio

from jeeves_infra.protocols import engine_pb2 as pb2
from jeeves_infra.protocols import engine_pb2_grpc as pb2_grpc

logger = logging.getLogger(__name__)

# Default kernel address from environment
DEFAULT_KERNEL_ADDRESS = os.getenv("KERNEL_GRPC_ADDRESS", "localhost:50051")


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


class KernelClient:
    """Async gRPC client for the Go kernel.

    Provides methods to interact with:
    - KernelService: Process lifecycle and resource management
    - EngineService: Envelope operations and pipeline execution

    Usage:
        async with KernelClient.connect("localhost:50051") as client:
            pcb = await client.create_process(pid="req-123", ...)
            usage = await client.record_usage(pid="req-123", llm_calls=1)

    Authentication:
        The Go kernel requires user context (user_id, session_id) for all
        operations. CreateProcess takes these as request fields. Subsequent
        operations require gRPC metadata headers. Use set_context() to set
        the default context, or pass user_id/session_id to individual methods.
    """

    def __init__(
        self,
        channel: grpc_aio.Channel,
        kernel_stub: Optional[pb2_grpc.KernelServiceStub] = None,
        engine_stub: Optional[pb2_grpc.EngineServiceStub] = None,
    ):
        """Initialize the client with a gRPC channel.

        Args:
            channel: Async gRPC channel to the kernel
            kernel_stub: Optional pre-created KernelService stub
            engine_stub: Optional pre-created EngineService stub
        """
        self._channel = channel
        # KernelServiceStub now generated - use it directly
        self._kernel_stub = kernel_stub or pb2_grpc.KernelServiceStub(channel)
        self._engine_stub = engine_stub or pb2_grpc.EngineServiceStub(channel)
        self._commbus_client: Optional["CommBusClient"] = None
        self._closed = False
        # Default context for authentication (can be overridden per-call)
        self._default_user_id: str = ""
        self._default_session_id: str = ""
        self._default_request_id: str = ""

    @classmethod
    @asynccontextmanager
    async def connect(
        cls,
        address: str = DEFAULT_KERNEL_ADDRESS,
        *,
        secure: bool = False,
        credentials: Optional[grpc.ChannelCredentials] = None,
    ) -> AsyncIterator["KernelClient"]:
        """Create a connected client as an async context manager.

        Args:
            address: Kernel gRPC address (host:port)
            secure: Use secure channel (TLS)
            credentials: Optional TLS credentials

        Yields:
            Connected KernelClient instance
        """
        if secure:
            if credentials is None:
                credentials = grpc.ssl_channel_credentials()
            channel = grpc_aio.secure_channel(address, credentials)
        else:
            channel = grpc_aio.insecure_channel(address)

        client = cls(channel)
        try:
            yield client
        finally:
            await client.close()

    async def close(self):
        """Close the gRPC channel."""
        if not self._closed:
            await self._channel.close()
            self._closed = True

    @property
    def commbus(self) -> "CommBusClient":
        """Get CommBus client for pub/sub operations.

        The CommBusClient is lazily created on first access.

        Returns:
            CommBusClient instance
        """
        if self._commbus_client is None:
            self._commbus_client = CommBusClient(self._channel)
        return self._commbus_client

    def set_context(
        self,
        user_id: str = "",
        session_id: str = "",
        request_id: str = "",
    ) -> "KernelClient":
        """Set default authentication context for subsequent calls.

        The Go kernel requires user_id and session_id for process operations.
        This context is sent as gRPC metadata headers.

        Args:
            user_id: User identifier
            session_id: Session identifier
            request_id: Request identifier (optional)

        Returns:
            Self for method chaining
        """
        self._default_user_id = user_id
        self._default_session_id = session_id
        self._default_request_id = request_id
        return self

    def _get_metadata(self) -> List[tuple]:
        """Build gRPC metadata for authentication.

        Returns:
            List of metadata tuples for gRPC call
        """
        metadata = []
        if self._default_user_id:
            metadata.append(("user_id", self._default_user_id))
        if self._default_session_id:
            metadata.append(("session_id", self._default_session_id))
        if self._default_request_id:
            metadata.append(("request_id", self._default_request_id))
        return metadata

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
        """Create a new process in the kernel.

        Args:
            pid: Process ID (usually envelope_id)
            request_id: Request ID
            user_id: User identifier
            session_id: Session identifier
            priority: Scheduling priority (REALTIME, HIGH, NORMAL, LOW, IDLE)
            max_llm_calls: Max LLM API calls
            max_tool_calls: Max tool executions
            max_agent_hops: Max agent transitions
            max_iterations: Max loop iterations
            timeout_seconds: Execution timeout

        Returns:
            ProcessInfo for the created process
        """
        # Map priority string to enum
        priority_map = {
            "REALTIME": pb2.SCHEDULING_PRIORITY_REALTIME,
            "HIGH": pb2.SCHEDULING_PRIORITY_HIGH,
            "NORMAL": pb2.SCHEDULING_PRIORITY_NORMAL,
            "LOW": pb2.SCHEDULING_PRIORITY_LOW,
            "IDLE": pb2.SCHEDULING_PRIORITY_IDLE,
        }

        quota = pb2.ResourceQuota(
            max_llm_calls=max_llm_calls,
            max_tool_calls=max_tool_calls,
            max_agent_hops=max_agent_hops,
            max_iterations=max_iterations,
            timeout_seconds=timeout_seconds,
        )

        request = pb2.CreateProcessRequest(
            pid=pid,
            request_id=request_id or pid,
            user_id=user_id,
            session_id=session_id,
            priority=priority_map.get(priority, pb2.SCHEDULING_PRIORITY_NORMAL),
            quota=quota,
        )

        try:
            # CreateProcess takes context in request fields, not metadata
            response = await self._call_kernel("CreateProcess", request)
            # Store context for subsequent operations on this process
            if user_id:
                self._default_user_id = user_id
            if session_id:
                self._default_session_id = session_id
            if request_id:
                self._default_request_id = request_id
            return self._pcb_to_info(response)
        except grpc.RpcError as e:
            logger.error(f"Failed to create process {pid}: {e}")
            raise KernelClientError(f"CreateProcess failed: {e}") from e

    async def get_process(self, pid: str) -> Optional[ProcessInfo]:
        """Get process information by PID.

        Args:
            pid: Process ID

        Returns:
            ProcessInfo if found, None if not found
        """
        request = pb2.GetProcessRequest(pid=pid)
        try:
            response = await self._call_kernel("GetProcess", request)
            return self._pcb_to_info(response)
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                return None
            logger.error(f"Failed to get process {pid}: {e}")
            raise KernelClientError(f"GetProcess failed: {e}") from e

    async def schedule_process(self, pid: str) -> ProcessInfo:
        """Schedule a process (transition NEW -> READY).

        Args:
            pid: Process ID

        Returns:
            Updated ProcessInfo
        """
        request = pb2.ScheduleProcessRequest(pid=pid)
        try:
            response = await self._call_kernel("ScheduleProcess", request)
            return self._pcb_to_info(response)
        except grpc.RpcError as e:
            logger.error(f"Failed to schedule process {pid}: {e}")
            raise KernelClientError(f"ScheduleProcess failed: {e}") from e

    async def get_next_runnable(self) -> Optional[ProcessInfo]:
        """Get the next runnable process (transitions READY -> RUNNING).

        Returns:
            ProcessInfo for the highest priority ready process, None if queue empty
        """
        request = pb2.GetNextRunnableRequest()
        try:
            response = await self._call_kernel("GetNextRunnable", request)
            if response.pid:
                return self._pcb_to_info(response)
            return None
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                return None
            logger.error(f"Failed to get next runnable: {e}")
            raise KernelClientError(f"GetNextRunnable failed: {e}") from e

    async def transition_state(
        self,
        pid: str,
        new_state: str,
        reason: str = "",
    ) -> ProcessInfo:
        """Transition a process to a new state.

        Args:
            pid: Process ID
            new_state: Target state (READY, RUNNING, WAITING, BLOCKED, TERMINATED)
            reason: Reason for the transition

        Returns:
            Updated ProcessInfo
        """
        state_map = {
            "NEW": pb2.PROCESS_STATE_NEW,
            "READY": pb2.PROCESS_STATE_READY,
            "RUNNING": pb2.PROCESS_STATE_RUNNING,
            "WAITING": pb2.PROCESS_STATE_WAITING,
            "BLOCKED": pb2.PROCESS_STATE_BLOCKED,
            "TERMINATED": pb2.PROCESS_STATE_TERMINATED,
            "ZOMBIE": pb2.PROCESS_STATE_ZOMBIE,
        }

        request = pb2.TransitionStateRequest(
            pid=pid,
            new_state=state_map.get(new_state, pb2.PROCESS_STATE_UNSPECIFIED),
            reason=reason,
        )
        try:
            response = await self._call_kernel("TransitionState", request)
            return self._pcb_to_info(response)
        except grpc.RpcError as e:
            logger.error(f"Failed to transition process {pid}: {e}")
            raise KernelClientError(f"TransitionState failed: {e}") from e

    async def terminate_process(
        self,
        pid: str,
        reason: str = "",
        force: bool = False,
    ) -> ProcessInfo:
        """Terminate a process.

        Args:
            pid: Process ID
            reason: Termination reason
            force: Force termination without cleanup

        Returns:
            Updated ProcessInfo
        """
        request = pb2.TerminateProcessRequest(
            pid=pid,
            reason=reason,
            force=force,
        )
        try:
            response = await self._call_kernel("TerminateProcess", request)
            return self._pcb_to_info(response)
        except grpc.RpcError as e:
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
        """Record resource usage for a process.

        Args:
            pid: Process ID
            llm_calls: Number of LLM calls to record
            tool_calls: Number of tool calls to record
            agent_hops: Number of agent hops to record
            tokens_in: Input tokens used
            tokens_out: Output tokens used

        Returns:
            QuotaCheckResult with current usage state
        """
        request = pb2.RecordUsageRequest(
            pid=pid,
            llm_calls=llm_calls,
            tool_calls=tool_calls,
            agent_hops=agent_hops,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
        try:
            response = await self._call_kernel("RecordUsage", request)
            return QuotaCheckResult(
                within_bounds=True,  # RecordUsage doesn't return bounds check
                llm_calls=response.llm_calls,
                tool_calls=response.tool_calls,
                agent_hops=response.agent_hops,
                tokens_in=response.tokens_in,
                tokens_out=response.tokens_out,
            )
        except grpc.RpcError as e:
            logger.error(f"Failed to record usage for {pid}: {e}")
            raise KernelClientError(f"RecordUsage failed: {e}") from e

    async def check_quota(self, pid: str) -> QuotaCheckResult:
        """Check if a process is within its resource quota.

        Args:
            pid: Process ID

        Returns:
            QuotaCheckResult with bounds check result
        """
        request = pb2.CheckQuotaRequest(pid=pid)
        try:
            response = await self._call_kernel("CheckQuota", request)
            return QuotaCheckResult(
                within_bounds=response.within_bounds,
                exceeded_reason=response.exceeded_reason,
                llm_calls=response.usage.llm_calls if response.usage else 0,
                tool_calls=response.usage.tool_calls if response.usage else 0,
                agent_hops=response.usage.agent_hops if response.usage else 0,
                tokens_in=response.usage.tokens_in if response.usage else 0,
                tokens_out=response.usage.tokens_out if response.usage else 0,
            )
        except grpc.RpcError as e:
            logger.error(f"Failed to check quota for {pid}: {e}")
            raise KernelClientError(f"CheckQuota failed: {e}") from e

    async def check_rate_limit(
        self,
        user_id: str,
        endpoint: str = "",
        record: bool = True,
    ) -> Dict[str, Any]:
        """Check rate limit for a user.

        Args:
            user_id: User identifier
            endpoint: API endpoint (for per-endpoint limits)
            record: Whether to record this request against the limit

        Returns:
            Dict with rate limit status
        """
        request = pb2.CheckRateLimitRequest(
            user_id=user_id,
            endpoint=endpoint,
            record=record,
        )
        try:
            response = await self._call_kernel("CheckRateLimit", request)
            return {
                "allowed": response.allowed,
                "exceeded": response.exceeded,
                "reason": response.reason,
                "limit_type": response.limit_type,
                "current_count": response.current_count,
                "limit": response.limit,
                "retry_after_seconds": response.retry_after_seconds,
                "remaining": response.remaining,
            }
        except grpc.RpcError as e:
            logger.error(f"Failed to check rate limit for {user_id}: {e}")
            raise KernelClientError(f"CheckRateLimit failed: {e}") from e

    # =========================================================================
    # Queries (KernelService)
    # =========================================================================

    async def list_processes(
        self,
        state: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> List[ProcessInfo]:
        """List processes matching filters.

        Args:
            state: Filter by state (RUNNING, READY, etc.)
            user_id: Filter by user ID

        Returns:
            List of ProcessInfo
        """
        state_map = {
            "NEW": pb2.PROCESS_STATE_NEW,
            "READY": pb2.PROCESS_STATE_READY,
            "RUNNING": pb2.PROCESS_STATE_RUNNING,
            "WAITING": pb2.PROCESS_STATE_WAITING,
            "BLOCKED": pb2.PROCESS_STATE_BLOCKED,
            "TERMINATED": pb2.PROCESS_STATE_TERMINATED,
            "ZOMBIE": pb2.PROCESS_STATE_ZOMBIE,
        }

        request = pb2.ListProcessesRequest(
            state=state_map.get(state, pb2.PROCESS_STATE_UNSPECIFIED) if state else pb2.PROCESS_STATE_UNSPECIFIED,
            user_id=user_id or "",
        )
        try:
            response = await self._call_kernel("ListProcesses", request)
            return [self._pcb_to_info(pcb) for pcb in response.processes]
        except grpc.RpcError as e:
            logger.error(f"Failed to list processes: {e}")
            raise KernelClientError(f"ListProcesses failed: {e}") from e

    async def get_process_counts(self) -> Dict[str, int]:
        """Get process counts by state.

        Returns:
            Dict mapping state names to counts
        """
        request = pb2.GetProcessCountsRequest()
        try:
            response = await self._call_kernel("GetProcessCounts", request)
            counts = dict(response.counts_by_state)
            counts["total"] = response.total
            counts["queue_depth"] = response.queue_depth
            return counts
        except grpc.RpcError as e:
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
    ) -> pb2.Envelope:
        """Create a new envelope via the Go engine.

        Args:
            raw_input: User input text
            user_id: User identifier
            session_id: Session identifier
            request_id: Request ID (generated if empty)
            metadata: Additional metadata
            stage_order: Pipeline stage order

        Returns:
            Created Envelope
        """
        request = pb2.CreateEnvelopeRequest(
            raw_input=raw_input,
            user_id=user_id,
            session_id=session_id,
            request_id=request_id,
            metadata=metadata or {},
            stage_order=stage_order or [],
        )
        try:
            return await self._engine_stub.CreateEnvelope(request)
        except grpc.RpcError as e:
            logger.error(f"Failed to create envelope: {e}")
            raise KernelClientError(f"CreateEnvelope failed: {e}") from e

    async def check_bounds(self, envelope: pb2.Envelope) -> Dict[str, Any]:
        """Check if an envelope is within bounds.

        Args:
            envelope: Envelope to check

        Returns:
            Dict with bounds check result
        """
        try:
            response = await self._engine_stub.CheckBounds(envelope)
            return {
                "can_continue": response.can_continue,
                "terminal_reason": pb2.TerminalReason.Name(response.terminal_reason),
                "llm_calls_remaining": response.llm_calls_remaining,
                "agent_hops_remaining": response.agent_hops_remaining,
                "iterations_remaining": response.iterations_remaining,
            }
        except grpc.RpcError as e:
            logger.error(f"Failed to check bounds: {e}")
            raise KernelClientError(f"CheckBounds failed: {e}") from e

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
            await self.record_usage(
                pid=pid,
                llm_calls=1,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
            )
            result = await self.check_quota(pid)
            if not result.within_bounds:
                return result.exceeded_reason
            return None
        except KernelClientError:
            return None  # Silent failure for backward compatibility

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
    # Internal Helpers
    # =========================================================================

    async def _call_kernel(self, method_name: str, request: Any) -> Any:
        """Call a KernelService method via the generated stub.

        Args:
            method_name: Name of the RPC method to call
            request: Proto request message

        Returns:
            Proto response message
        """
        method = getattr(self._kernel_stub, method_name, None)
        if method is None:
            raise KernelClientError(f"Unknown KernelService method: {method_name}")

        # Build metadata for authentication (Go kernel requires this for most ops)
        metadata = self._get_metadata()
        if metadata:
            return await method(request, metadata=metadata)
        return await method(request)

    def _pcb_to_info(self, pcb: pb2.ProcessControlBlock) -> ProcessInfo:
        """Convert ProcessControlBlock to ProcessInfo."""
        state_names = {
            pb2.PROCESS_STATE_UNSPECIFIED: "UNSPECIFIED",
            pb2.PROCESS_STATE_NEW: "NEW",
            pb2.PROCESS_STATE_READY: "READY",
            pb2.PROCESS_STATE_RUNNING: "RUNNING",
            pb2.PROCESS_STATE_WAITING: "WAITING",
            pb2.PROCESS_STATE_BLOCKED: "BLOCKED",
            pb2.PROCESS_STATE_TERMINATED: "TERMINATED",
            pb2.PROCESS_STATE_ZOMBIE: "ZOMBIE",
        }
        priority_names = {
            pb2.SCHEDULING_PRIORITY_UNSPECIFIED: "UNSPECIFIED",
            pb2.SCHEDULING_PRIORITY_REALTIME: "REALTIME",
            pb2.SCHEDULING_PRIORITY_HIGH: "HIGH",
            pb2.SCHEDULING_PRIORITY_NORMAL: "NORMAL",
            pb2.SCHEDULING_PRIORITY_LOW: "LOW",
            pb2.SCHEDULING_PRIORITY_IDLE: "IDLE",
        }

        usage = pcb.usage if pcb.usage else pb2.ResourceUsage()
        return ProcessInfo(
            pid=pcb.pid,
            request_id=pcb.request_id,
            user_id=pcb.user_id,
            session_id=pcb.session_id,
            state=state_names.get(pcb.state, "UNKNOWN"),
            priority=priority_names.get(pcb.priority, "NORMAL"),
            llm_calls=usage.llm_calls,
            tool_calls=usage.tool_calls,
            agent_hops=usage.agent_hops,
            tokens_in=usage.tokens_in,
            tokens_out=usage.tokens_out,
            current_stage=pcb.current_stage,
        )


class KernelClientError(Exception):
    """Exception raised for kernel client errors."""
    pass


# =============================================================================
# CommBus Client (Agentic OS IPC)
# =============================================================================

class CommBusClient:
    """Python wrapper for Go CommBus via gRPC.

    Provides access to the kernel's CommBus for pub/sub operations.
    This follows the Agentic OS pattern: Python → kernel_client → gRPC → Go kernel.

    Usage:
        async with KernelClient.connect() as client:
            # Publish event
            await client.commbus.publish("AgentStarted", {"agent_name": "planner"})

            # Query with response
            result = await client.commbus.query("GetSettings", {"key": "llm"})

    CommBus patterns:
        - Publish: Fire-and-forget, fan-out to all subscribers
        - Send: Fire-and-forget, single handler
        - Query: Request-response, synchronous
    """

    def __init__(self, channel: grpc_aio.Channel):
        """Initialize CommBus client.

        Args:
            channel: Async gRPC channel to the kernel
        """
        self._stub = pb2_grpc.CommBusServiceStub(channel)

    async def publish(self, event_type: str, payload: Dict[str, Any]) -> bool:
        """Publish event to all subscribers.

        Args:
            event_type: Type of event (e.g., "AgentStarted", "ToolCompleted")
            payload: JSON-serializable event data

        Returns:
            True if published successfully
        """
        import json
        request = pb2.CommBusPublishRequest(
            event_type=event_type,
            payload=json.dumps(payload).encode("utf-8"),
        )
        try:
            response = await self._stub.Publish(request)
            if not response.success:
                logger.warning(f"CommBus publish failed: {response.error}")
            return response.success
        except grpc.RpcError as e:
            logger.error(f"CommBus publish error: {e}")
            return False

    async def send(self, command_type: str, payload: Dict[str, Any]) -> bool:
        """Send command to single handler.

        Args:
            command_type: Type of command (e.g., "InvalidateCache")
            payload: JSON-serializable command data

        Returns:
            True if sent successfully
        """
        import json
        request = pb2.CommBusSendRequest(
            command_type=command_type,
            payload=json.dumps(payload).encode("utf-8"),
        )
        try:
            response = await self._stub.Send(request)
            if not response.success:
                logger.warning(f"CommBus send failed: {response.error}")
            return response.success
        except grpc.RpcError as e:
            logger.error(f"CommBus send error: {e}")
            return False

    async def query(
        self,
        query_type: str,
        payload: Dict[str, Any],
        timeout_ms: int = 30000,
    ) -> Any:
        """Send query and wait for response.

        Args:
            query_type: Type of query (e.g., "GetSettings", "GetPrompt")
            payload: JSON-serializable query data
            timeout_ms: Query timeout in milliseconds

        Returns:
            Query result (deserialized from JSON)

        Raises:
            RuntimeError: If query fails
        """
        import json
        request = pb2.CommBusQueryRequest(
            query_type=query_type,
            payload=json.dumps(payload).encode("utf-8"),
            timeout_ms=timeout_ms,
        )
        try:
            response = await self._stub.Query(request)
            if not response.success:
                raise RuntimeError(f"CommBus query failed: {response.error}")
            return json.loads(response.result.decode("utf-8"))
        except grpc.RpcError as e:
            logger.error(f"CommBus query error: {e}")
            raise RuntimeError(f"CommBus query failed: {e}") from e


# =============================================================================
# Global Client Management
# =============================================================================

_global_client: Optional[KernelClient] = None
_client_lock = asyncio.Lock()


async def get_kernel_client(
    address: str = DEFAULT_KERNEL_ADDRESS,
) -> KernelClient:
    """Get the global kernel client, creating if needed.

    This provides a singleton client for use across the application.
    The client manages its own connection lifecycle.

    Args:
        address: Kernel gRPC address (used only on first call)

    Returns:
        Global KernelClient instance
    """
    global _global_client
    async with _client_lock:
        if _global_client is None:
            channel = grpc_aio.insecure_channel(address)
            _global_client = KernelClient(channel)
            logger.info(f"Created global kernel client connected to {address}")
        return _global_client


async def close_kernel_client():
    """Close the global kernel client."""
    global _global_client
    async with _client_lock:
        if _global_client is not None:
            await _global_client.close()
            _global_client = None
            logger.info("Closed global kernel client")


def reset_kernel_client():
    """Reset the global kernel client (for testing)."""
    global _global_client
    _global_client = None


async def get_commbus() -> Optional[CommBusClient]:
    """Get CommBus client via global kernel client.

    This is a convenience function for getting CommBus access
    without explicitly creating a KernelClient.

    Returns:
        CommBusClient if kernel is available, None otherwise
    """
    try:
        client = await get_kernel_client()
        return client.commbus
    except Exception as e:
        logger.warning(f"Failed to get CommBus: {e}")
        return None


__all__ = [
    "KernelClient",
    "KernelClientError",
    "QuotaCheckResult",
    "ProcessInfo",
    "CommBusClient",
    "get_kernel_client",
    "close_kernel_client",
    "reset_kernel_client",
    "get_commbus",
    "DEFAULT_KERNEL_ADDRESS",
]
