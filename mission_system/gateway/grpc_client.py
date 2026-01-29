"""
gRPC client stubs for internal services.

Provides async client connections to:
- JeevesFlowService (orchestration)
- GovernanceService (system health)

Constitution v3.0 Compliance:
  REMOVED: KanbanService, JournalService, OpenLoopService stubs
  These features were permanently deleted in the v3.0 pivot.
"""

from __future__ import annotations

import asyncio
from typing import Optional
from contextlib import asynccontextmanager

import grpc
from jeeves_infra.logging import get_current_logger
from jeeves_infra.protocols import LoggerProtocol

# These will be generated from proto/jeeves.proto
# Run: python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. proto/jeeves.proto
try:
    from proto import jeeves_pb2
    from proto import jeeves_pb2_grpc
except ImportError:
    jeeves_pb2 = None
    jeeves_pb2_grpc = None


class GrpcClientManager:
    """
    Manages gRPC channel and service stubs.

    Usage:
        async with GrpcClientManager("orchestrator:50051") as client:
            async for event in client.flow.StartFlow(request):
                print(event)
    """

    def __init__(
        self,
        orchestrator_host: str = "localhost",
        orchestrator_port: int = 50051,
        *,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        logger: Optional[LoggerProtocol] = None,
    ):
        self._logger = logger or get_current_logger()
        self.address = f"{orchestrator_host}:{orchestrator_port}"
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        self._channel: Optional[grpc.aio.Channel] = None
        self._flow_stub = None
        self._governance_stub = None

    async def connect(self) -> None:
        """Establish gRPC channel and create stubs."""
        if jeeves_pb2_grpc is None:
            raise RuntimeError(
                "gRPC stubs not generated. Run: "
                "python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. proto/jeeves.proto"
            )

        # Create async channel with retry options
        # NOTE: Keepalive settings tuned to match orchestrator server config.
        # Server allows pings every 30s (http2.min_ping_interval_without_data_ms).
        # Client sends pings every 60s to stay under server limit and prevent
        # GOAWAY with ENHANCE_YOUR_CALM ("too_many_pings") errors.
        options = [
            ("grpc.max_receive_message_length", 50 * 1024 * 1024),  # 50MB
            ("grpc.max_send_message_length", 50 * 1024 * 1024),
            ("grpc.keepalive_time_ms", 60000),  # Send keepalive every 60s (was 30s)
            ("grpc.keepalive_timeout_ms", 20000),  # Wait 20s for response (was 10s)
            ("grpc.keepalive_permit_without_calls", True),  # Keepalive even when idle
        ]

        self._channel = grpc.aio.insecure_channel(self.address, options=options)

        # Wait for channel to be ready
        try:
            await asyncio.wait_for(
                self._channel.channel_ready(),
                timeout=10.0
            )
        except asyncio.TimeoutError:
            self._logger.warning("grpc_channel_connection_timeout", address=self.address)
            # Continue anyway - might connect later

        # Create stubs
        self._flow_stub = jeeves_pb2_grpc.JeevesFlowServiceStub(self._channel)
        self._governance_stub = jeeves_pb2_grpc.GovernanceServiceStub(self._channel)

        self._logger.info("grpc_client_connected", address=self.address)

    async def disconnect(self) -> None:
        """Close gRPC channel."""
        if self._channel:
            await self._channel.close()
            self._channel = None
            self._logger.info("grpc_client_disconnected", address=self.address)

    async def __aenter__(self) -> "GrpcClientManager":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.disconnect()

    @property
    def flow(self):
        """JeevesFlowService stub."""
        if not self._flow_stub:
            raise RuntimeError("Client not connected. Call connect() first.")
        return self._flow_stub

    @property
    def governance(self):
        """GovernanceService stub."""
        if not self._governance_stub:
            raise RuntimeError("Client not connected. Call connect() first.")
        return self._governance_stub

    async def health_check(self) -> bool:
        """Check if orchestrator is reachable."""
        if not self._channel:
            return False

        try:
            # Use gRPC health check if available
            from grpc_health.v1 import health_pb2, health_pb2_grpc

            health_stub = health_pb2_grpc.HealthStub(self._channel)
            request = health_pb2.HealthCheckRequest(service="")
            response = await asyncio.wait_for(
                health_stub.Check(request),
                timeout=5.0
            )
            return response.status == health_pb2.HealthCheckResponse.SERVING
        except Exception as e:
            self._logger.debug("grpc_health_check_failed", error=str(e))
            # Fallback: try to check channel state
            try:
                state = self._channel.get_state(try_to_connect=True)
                return state == grpc.ChannelConnectivity.READY
            except Exception:
                return False


# Singleton instance (initialized in app lifespan)
_client: Optional[GrpcClientManager] = None


def get_grpc_client() -> GrpcClientManager:
    """Get the global gRPC client instance."""
    if _client is None:
        raise RuntimeError("gRPC client not initialized. Check app lifespan.")
    return _client


def set_grpc_client(client: GrpcClientManager) -> None:
    """Set the global gRPC client instance."""
    global _client
    _client = client
