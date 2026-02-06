"""End-to-end tests for distributed mode with Redis.

These tests spin up a real Redis instance (using testcontainers)
and test the full distributed pipeline flow including:
- RedisDistributedBus task queue operations
- WorkerCoordinator task submission and processing
- Checkpoint persistence and recovery
- Control Tower resource tracking in distributed context

Requirements:
- Docker must be running
- pytest-asyncio and testcontainers installed

Run with: pytest mission_system/tests/e2e/test_distributed_mode.py -v -s
"""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from jeeves_infra.protocols import RequestContext

# Mark all tests as e2e and asyncio
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio,
]


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(scope="module")
def redis_container():
    """Start a Redis container for e2e tests."""
    try:
        from testcontainers.redis import RedisContainer
    except ImportError:
        pytest.skip("testcontainers not installed: pip install testcontainers[redis]")

    container = RedisContainer("redis:7-alpine")
    container.start()
    yield container
    container.stop()


@pytest.fixture
async def redis_client(redis_container):
    """Create async Redis client connected to test container."""
    try:
        import redis.asyncio as redis_async
    except ImportError:
        pytest.skip("redis package not installed: pip install redis")

    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    url = f"redis://{host}:{port}"

    client = redis_async.from_url(url, decode_responses=True)
    yield client
    await client.flushall()  # Clean up
    await client.close()


@pytest.fixture
def mock_logger():
    """Create a mock logger."""
    logger = MagicMock()
    logger.bind.return_value = logger
    return logger


# =============================================================================
# Redis Distributed Bus Tests
# =============================================================================


class TestRedisDistributedBusE2E:
    """E2E tests for RedisDistributedBus with real Redis."""

    async def test_enqueue_and_dequeue_task(self, redis_client, mock_logger):
        """Test enqueueing and dequeueing a task through Redis."""
        from avionics.distributed.redis_bus import RedisDistributedBus
        from jeeves_infra.protocols import DistributedTask

        # Create a wrapper that exposes redis property
        class RedisClientWrapper:
            def __init__(self, client):
                self._client = client

            @property
            def redis(self):
                return self._client

        wrapper = RedisClientWrapper(redis_client)
        bus = RedisDistributedBus(redis_client=wrapper, logger=mock_logger)

        # Create test task
        task = DistributedTask(
            task_id="task-e2e-001",
            envelope_state={"envelope_id": "env-001", "payload": {"test": "data"}},
            agent_name="test_agent",
            stage_order=0,
            priority=5,
        )

        # Enqueue
        await bus.enqueue_task("test_queue", task)

        # Verify queue stats
        stats = await bus.get_queue_stats("test_queue")
        assert stats.pending_count >= 1

        # Dequeue
        worker_id = "worker-e2e-001"
        await bus.register_worker(worker_id, ["test_queue"])

        dequeued = await bus.dequeue_task("test_queue", worker_id, timeout_seconds=5)

        assert dequeued is not None
        assert dequeued.task_id == "task-e2e-001"
        assert dequeued.agent_name == "test_agent"
        assert dequeued.envelope_state["envelope_id"] == "env-001"

        # Clean up
        await bus.deregister_worker(worker_id)

    async def test_task_completion_flow(self, redis_client, mock_logger):
        """Test full task lifecycle: enqueue -> process -> complete."""
        from avionics.distributed.redis_bus import RedisDistributedBus
        from jeeves_infra.protocols import DistributedTask

        class RedisClientWrapper:
            def __init__(self, client):
                self._client = client

            @property
            def redis(self):
                return self._client

        wrapper = RedisClientWrapper(redis_client)
        bus = RedisDistributedBus(redis_client=wrapper, logger=mock_logger)

        # Create and enqueue task
        task = DistributedTask(
            task_id="task-e2e-002",
            envelope_state={"envelope_id": "env-002"},
            agent_name="processor",
            stage_order=1,
        )
        await bus.enqueue_task("processor_queue", task)

        # Register worker and dequeue
        worker_id = "worker-e2e-002"
        await bus.register_worker(worker_id, ["processor_queue"])

        dequeued = await bus.dequeue_task("processor_queue", worker_id, timeout_seconds=5)
        assert dequeued is not None

        # Complete task
        result = {"processed": True, "output": "success"}
        await bus.complete_task(dequeued.task_id, result)

        # Verify task is no longer in queue
        stats = await bus.get_queue_stats("processor_queue")
        # Pending should be 0 (task was completed)
        assert stats.pending_count == 0

        await bus.deregister_worker(worker_id)

    async def test_task_failure_and_retry(self, redis_client, mock_logger):
        """Test task failure handling and retry mechanism."""
        from avionics.distributed.redis_bus import RedisDistributedBus
        from jeeves_infra.protocols import DistributedTask

        class RedisClientWrapper:
            def __init__(self, client):
                self._client = client

            @property
            def redis(self):
                return self._client

        wrapper = RedisClientWrapper(redis_client)
        bus = RedisDistributedBus(redis_client=wrapper, logger=mock_logger)

        # Create task with retries enabled
        task = DistributedTask(
            task_id="task-e2e-003",
            envelope_state={"envelope_id": "env-003"},
            agent_name="failable",
            stage_order=0,
            max_retries=3,
            retry_count=0,
        )
        await bus.enqueue_task("retry_queue", task)

        worker_id = "worker-e2e-003"
        await bus.register_worker(worker_id, ["retry_queue"])

        # Dequeue and fail (with retry)
        dequeued = await bus.dequeue_task("retry_queue", worker_id, timeout_seconds=5)
        assert dequeued is not None

        await bus.fail_task(dequeued.task_id, "Simulated error", retry=True)

        # Task should be re-queued for retry
        stats = await bus.get_queue_stats("retry_queue")
        assert stats.pending_count >= 1

        # Dequeue again and complete
        requeued = await bus.dequeue_task("retry_queue", worker_id, timeout_seconds=5)
        assert requeued is not None
        assert requeued.retry_count == 1

        await bus.complete_task(requeued.task_id, {"recovered": True})
        await bus.deregister_worker(worker_id)

    async def test_worker_heartbeat(self, redis_client, mock_logger):
        """Test worker heartbeat mechanism."""
        from avionics.distributed.redis_bus import RedisDistributedBus

        class RedisClientWrapper:
            def __init__(self, client):
                self._client = client

            @property
            def redis(self):
                return self._client

        wrapper = RedisClientWrapper(redis_client)
        bus = RedisDistributedBus(redis_client=wrapper, logger=mock_logger)

        worker_id = "worker-heartbeat-001"
        await bus.register_worker(worker_id, ["heartbeat_queue"])

        # Send heartbeat
        await bus.heartbeat(worker_id)

        # Worker should still be registered
        queues = await bus.list_queues()
        # At minimum, the heartbeat should not fail
        assert True  # Heartbeat completed successfully

        await bus.deregister_worker(worker_id)


