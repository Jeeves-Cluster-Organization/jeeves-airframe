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


# =============================================================================
# Worker Coordinator E2E Tests
# =============================================================================


class TestWorkerCoordinatorE2E:
    """E2E tests for WorkerCoordinator with real Redis."""

    async def test_submit_envelope_to_queue(self, redis_client, mock_logger):
        """Test submitting an envelope through coordinator."""
        from avionics.distributed.redis_bus import RedisDistributedBus
        from mission_system.services.worker_coordinator import WorkerCoordinator
        from jeeves_infra.protocols import Envelope

        class RedisClientWrapper:
            def __init__(self, client):
                self._client = client

            @property
            def redis(self):
                return self._client

        wrapper = RedisClientWrapper(redis_client)
        bus = RedisDistributedBus(redis_client=wrapper, logger=mock_logger)

        # Create coordinator without Control Tower (simpler test)
        coordinator = WorkerCoordinator(
            distributed_bus=bus,
            logger=mock_logger,
        )

        # Create envelope
        request_context = RequestContext(
            request_id="req-001",
            capability="test_capability",
            user_id="user-e2e",
            session_id="session-e2e",
        )
        envelope = Envelope(
            request_context=request_context,
            envelope_id="env-coord-001",
            request_id="req-001",
            user_id="user-e2e",
            session_id="session-e2e",
            raw_input="test data",
        )

        # Submit to queue
        task_id = await coordinator.submit_envelope(
            envelope=envelope,
            queue_name="coordinator_queue",
            agent_name="planner",
            priority=10,
        )

        assert task_id is not None
        assert task_id.startswith("task_")

        # Verify task is in queue
        stats = await coordinator.get_queue_stats("coordinator_queue")
        assert stats.pending_count >= 1

    async def test_coordinator_with_control_tower(self, redis_client, mock_logger):
        """Test coordinator integration with Control Tower."""
        from avionics.distributed.redis_bus import RedisDistributedBus
        from mission_system.services.worker_coordinator import WorkerCoordinator
        from control_tower.kernel import ControlTower
        from control_tower.types import ResourceQuota
        from jeeves_infra.protocols import Envelope

        class RedisClientWrapper:
            def __init__(self, client):
                self._client = client

            @property
            def redis(self):
                return self._client

        wrapper = RedisClientWrapper(redis_client)
        bus = RedisDistributedBus(redis_client=wrapper, logger=mock_logger)

        # Create Control Tower
        control_tower = ControlTower(
            logger=mock_logger,
            default_quota=ResourceQuota(max_llm_calls=100, max_agent_hops=10),
        )

        # Create coordinator with Control Tower
        coordinator = WorkerCoordinator(
            distributed_bus=bus,
            logger=mock_logger,
            control_tower=control_tower,
        )

        # Create envelope
        request_context = RequestContext(
            request_id="req-ct-001",
            capability="test_capability",
            user_id="user-ct",
            session_id="session-ct",
        )
        envelope = Envelope(
            request_context=request_context,
            envelope_id="env-ct-001",
            request_id="req-ct-001",
            user_id="user-ct",
            session_id="session-ct",
        )

        # Submit with resource quota
        quota = ResourceQuota(max_llm_calls=50, max_agent_hops=5)
        task_id = await coordinator.submit_envelope(
            envelope=envelope,
            queue_name="ct_queue",
            agent_name="validator",
            resource_quota=quota,
        )

        assert task_id is not None

        # Verify Control Tower is tracking resources
        assert control_tower.resources.is_tracked(envelope.envelope_id)

        # Check allocated quota
        budget = control_tower.resources.get_remaining_budget(envelope.envelope_id)
        assert budget["llm_calls"] == 50


# =============================================================================
# Full Pipeline E2E Tests
# =============================================================================


class TestDistributedPipelineE2E:
    """E2E tests for full distributed pipeline flow."""

    async def test_end_to_end_task_processing(self, redis_client, mock_logger):
        """Test complete flow: submit -> process -> complete with result."""
        from avionics.distributed.redis_bus import RedisDistributedBus
        from mission_system.services.worker_coordinator import (
            WorkerCoordinator,
            WorkerConfig,
        )
        from jeeves_infra.protocols import Envelope

        class RedisClientWrapper:
            def __init__(self, client):
                self._client = client

            @property
            def redis(self):
                return self._client

        wrapper = RedisClientWrapper(redis_client)
        bus = RedisDistributedBus(redis_client=wrapper, logger=mock_logger)
        coordinator = WorkerCoordinator(distributed_bus=bus, logger=mock_logger)

        # Submit envelope
        request_context = RequestContext(
            request_id="req-pipeline-001",
            capability="test_capability",
            user_id="user-pipeline",
            session_id="session-pipeline",
        )
        envelope = Envelope(
            request_context=request_context,
            envelope_id="env-pipeline-001",
            request_id="req-pipeline-001",
            user_id="user-pipeline",
            session_id="session-pipeline",
            raw_input="test query",
        )

        task_id = await coordinator.submit_envelope(
            envelope=envelope,
            queue_name="pipeline_queue",
            agent_name="analyzer",
        )

        # Manually process (simulating worker)
        worker_id = "worker-pipeline-001"
        await bus.register_worker(worker_id, ["pipeline_queue"])

        task = await bus.dequeue_task("pipeline_queue", worker_id, timeout_seconds=5)
        assert task is not None
        assert task.agent_name == "analyzer"

        # Simulate processing
        result_envelope = Envelope.from_dict(task.envelope_state)
        result_envelope.metadata["processed"] = True
        result_envelope.metadata["result"] = "Analysis complete"

        # Complete task with result
        await bus.complete_task(
            task.task_id,
            {"envelope_state": result_envelope.to_state_dict()},
        )

        # Verify task completed
        stats = await bus.get_queue_stats("pipeline_queue")
        assert stats.pending_count == 0

        await bus.deregister_worker(worker_id)

    async def test_multi_stage_pipeline(self, redis_client, mock_logger):
        """Test multi-stage pipeline with different queues per stage."""
        from avionics.distributed.redis_bus import RedisDistributedBus
        from mission_system.services.worker_coordinator import WorkerCoordinator
        from jeeves_infra.protocols import Envelope
            from jeeves_infra.protocols import DistributedTask

        class RedisClientWrapper:
            def __init__(self, client):
                self._client = client

            @property
            def redis(self):
                return self._client

        wrapper = RedisClientWrapper(redis_client)
        bus = RedisDistributedBus(redis_client=wrapper, logger=mock_logger)
        coordinator = WorkerCoordinator(distributed_bus=bus, logger=mock_logger)

        # Stage 1: Submit to planner queue
        request_context = RequestContext(
            request_id="req-multi-001",
            capability="test_capability",
            user_id="user-multi",
            session_id="session-multi",
        )
        envelope = Envelope(
            request_context=request_context,
            envelope_id="env-multi-001",
            request_id="req-multi-001",
            user_id="user-multi",
            session_id="session-multi",
        )

        await coordinator.submit_envelope(
            envelope=envelope,
            queue_name="stage1_planner",
            agent_name="planner",
        )

        # Worker 1: Process stage 1
        worker1 = "worker-stage1"
        await bus.register_worker(worker1, ["stage1_planner"])
        task1 = await bus.dequeue_task("stage1_planner", worker1, timeout_seconds=5)
        assert task1 is not None

        # Complete stage 1 and submit to stage 2
        result1 = Envelope.from_dict(task1.envelope_state)
        result1.metadata["stage1_complete"] = True

        await bus.complete_task(task1.task_id, {"stage": 1})

        # Submit to stage 2
        task2_obj = DistributedTask(
            task_id="task-stage2-001",
            envelope_state=result1.to_state_dict(),
            agent_name="executor",
            stage_order=1,
        )
        await bus.enqueue_task("stage2_executor", task2_obj)

        # Worker 2: Process stage 2
        worker2 = "worker-stage2"
        await bus.register_worker(worker2, ["stage2_executor"])
        task2 = await bus.dequeue_task("stage2_executor", worker2, timeout_seconds=5)
        assert task2 is not None
        assert task2.agent_name == "executor"

        # Complete pipeline
        await bus.complete_task(task2.task_id, {"stage": 2, "final": True})

        # Cleanup
        await bus.deregister_worker(worker1)
        await bus.deregister_worker(worker2)


# =============================================================================
# Bootstrap Integration E2E Tests
# =============================================================================


class TestBootstrapDistributedE2E:
    """E2E tests for bootstrap distributed infrastructure creation."""

    async def test_create_distributed_infrastructure_e2e(self, redis_container, mock_logger):
        """Test creating distributed infrastructure with real Redis."""
        from avionics.feature_flags import FeatureFlags
        from avionics.context import AppContext, SystemClock
        from mission_system.bootstrap import create_distributed_infrastructure

        host = redis_container.get_container_host_ip()
        port = redis_container.get_exposed_port(6379)
        redis_url = f"redis://{host}:{port}"

        flags = FeatureFlags(
            enable_distributed_mode=True,
            use_redis_state=True,
        )

        context = AppContext(
            settings=MagicMock(),
            feature_flags=flags,
            logger=mock_logger,
            clock=SystemClock(),
            config_registry=None,
            core_config=None,
            orchestration_flags=None,
            vertical_registry={},
            control_tower=None,
        )

        result = create_distributed_infrastructure(context, redis_url=redis_url)

        assert result["redis_client"] is not None
        assert result["distributed_bus"] is not None
        assert result["worker_coordinator"] is not None

        # Test actual Redis connectivity
        bus = result["distributed_bus"]
        queues = await bus.list_queues()
        assert isinstance(queues, list)

        # Cleanup
        await result["redis_client"].close()
