"""Unit tests for RedisDistributedBus.

Tests distributed task queue, worker coordination, and retry logic.
Coverage target: 80%+

Test Strategy:
- Test all public methods (enqueue, dequeue, complete, fail, worker mgmt, stats)
- Test edge cases (timeouts, retries, missing data)
- Test retry logic with exponential backoff
- Test worker lifecycle and task requeuing
- Mock Redis client to avoid infrastructure dependencies
"""

import pytest
import json
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call
from typing import Any, Dict

from jeeves_infra.distributed.redis_bus import RedisDistributedBus
from jeeves_infra.protocols import DistributedTask, QueueStats


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    redis = AsyncMock()
    # Common methods
    redis.hset = AsyncMock()
    redis.hgetall = AsyncMock()
    redis.hget = AsyncMock()
    redis.hincrby = AsyncMock()
    redis.zadd = AsyncMock()
    redis.zcard = AsyncMock()
    redis.bzpopmin = AsyncMock()
    redis.sadd = AsyncMock()
    redis.srem = AsyncMock()
    redis.smembers = AsyncMock()
    redis.delete = AsyncMock()
    redis.expire = AsyncMock()
    redis.scan_iter = AsyncMock()
    return redis


@pytest.fixture
def mock_redis_client(mock_redis):
    """Mock Redis client wrapper."""
    client = MagicMock()
    client.redis = mock_redis
    return client


@pytest.fixture
def mock_logger():
    """Mock logger."""
    logger = MagicMock()
    return logger


@pytest.fixture
def bus(mock_redis_client, mock_logger):
    """Create bus with mocked dependencies."""
    return RedisDistributedBus(mock_redis_client, mock_logger)


@pytest.fixture
def sample_task():
    """Sample distributed task."""
    return DistributedTask(
        task_id="task_123",
        envelope_state={"foo": "bar", "step": 1},
        agent_name="planner",
        stage_order=1,
        checkpoint_id="ckpt_abc",
        created_at=None,
        retry_count=0,
        max_retries=3,
        priority=5,
    )


# =============================================================================
# Initialization Tests
# =============================================================================

class TestInitialization:
    """Test bus initialization."""

    def test_init_stores_dependencies(self, mock_redis_client, mock_logger):
        """Test that bus stores redis and logger."""
        bus = RedisDistributedBus(mock_redis_client, mock_logger)

        assert bus._redis is mock_redis_client
        assert bus._logger is mock_logger

    def test_init_without_logger(self, mock_redis_client):
        """Test that bus works without explicit logger."""
        bus = RedisDistributedBus(mock_redis_client)

        assert bus._redis is mock_redis_client
        assert bus._logger is not None  # Should get default logger


# =============================================================================
# Enqueue Task Tests
# =============================================================================

class TestEnqueueTask:
    """Test task enqueueing."""

    @pytest.mark.asyncio
    async def test_enqueue_task_stores_data(self, bus, sample_task, mock_redis, mock_logger):
        """Test that enqueue stores task data in Redis."""
        queue_name = "agent:planner"

        result = await bus.enqueue_task(queue_name, sample_task)

        # Should return task ID
        assert result == "task_123"

        # Should store task hash
        mock_redis.hset.assert_called()
        hset_call = mock_redis.hset.call_args
        assert hset_call[0][0] == "dbus:task:task_123"

        task_data = hset_call[1]["mapping"]
        assert task_data["task_id"] == "task_123"
        assert task_data["queue_name"] == queue_name
        assert task_data["agent_name"] == "planner"
        assert task_data["stage_order"] == 1
        assert task_data["checkpoint_id"] == "ckpt_abc"
        assert task_data["priority"] == 5
        assert task_data["retry_count"] == 0
        assert task_data["max_retries"] == 3
        assert task_data["status"] == "pending"
        assert "envelope_state" in task_data
        assert json.loads(task_data["envelope_state"]) == {"foo": "bar", "step": 1}

        # Should set TTL
        mock_redis.expire.assert_called_with("dbus:task:task_123", 86400)

        # Should add to priority queue
        mock_redis.zadd.assert_called_once()
        zadd_call = mock_redis.zadd.call_args
        assert zadd_call[0][0] == "dbus:queue:agent:planner"

        # Should increment stats
        assert mock_redis.hincrby.called

        # Should log
        mock_logger.debug.assert_called_with(
            "task_enqueued",
            task_id="task_123",
            queue="agent:planner",
            priority=5,
        )

    @pytest.mark.asyncio
    async def test_enqueue_high_priority_task(self, bus, mock_redis):
        """Test that high priority tasks get lower score (processed first)."""
        high_priority_task = DistributedTask(
            task_id="task_urgent",
            envelope_state={},
            agent_name="planner",
            stage_order=0,
            priority=10,  # High priority
        )

        await bus.enqueue_task("agent:planner", high_priority_task)

        # Check zadd score (lower = higher priority)
        zadd_call = mock_redis.zadd.call_args
        score_dict = zadd_call[0][1]
        score = score_dict["task_urgent"]

        # Score should be current time minus (priority * 1000)
        # Higher priority = lower score = processed first
        assert score < time.time()

    @pytest.mark.asyncio
    async def test_enqueue_task_without_checkpoint(self, bus, mock_redis):
        """Test enqueuing task without checkpoint_id."""
        task = DistributedTask(
            task_id="task_no_ckpt",
            envelope_state={},
            agent_name="planner",
            stage_order=0,
            checkpoint_id=None,
        )

        await bus.enqueue_task("agent:test", task)

        hset_call = mock_redis.hset.call_args
        task_data = hset_call[1]["mapping"]
        assert task_data["checkpoint_id"] == ""  # Empty string for None


# =============================================================================
# Dequeue Task Tests
# =============================================================================

class TestDequeueTask:
    """Test task dequeuing."""

    @pytest.mark.asyncio
    async def test_dequeue_task_success(self, bus, mock_redis, mock_logger):
        """Test successful task dequeue."""
        queue_name = "agent:planner"
        worker_id = "worker_1"

        # Mock bzpopmin result (queue_name, task_id, score)
        mock_redis.bzpopmin.return_value = (
            b"dbus:queue:agent:planner",
            b"task_123",
            123.45,
        )

        # Mock task data
        mock_redis.hgetall.return_value = {
            "task_id": "task_123",
            "queue_name": queue_name,
            "envelope_state": json.dumps({"foo": "bar"}),
            "agent_name": "planner",
            "stage_order": "1",
            "checkpoint_id": "ckpt_abc",
            "created_at": "2024-01-01T00:00:00Z",
            "retry_count": "0",
            "max_retries": "3",
            "priority": "5",
        }

        result = await bus.dequeue_task(queue_name, worker_id, timeout_seconds=30)

        # Should call bzpopmin with timeout
        mock_redis.bzpopmin.assert_called_once_with(
            "dbus:queue:agent:planner",
            timeout=30,
        )

        # Should load task data
        mock_redis.hgetall.assert_called_with("dbus:task:task_123")

        # Should update task status to processing
        status_update_call = [c for c in mock_redis.hset.call_args_list if "status" in str(c)]
        assert len(status_update_call) > 0

        # Should add to processing set
        mock_redis.sadd.assert_called_with("dbus:processing:worker_1", "task_123")

        # Should return DistributedTask
        assert isinstance(result, DistributedTask)
        assert result.task_id == "task_123"
        assert result.envelope_state == {"foo": "bar"}
        assert result.agent_name == "planner"
        assert result.stage_order == 1
        assert result.checkpoint_id == "ckpt_abc"
        assert result.retry_count == 0
        assert result.max_retries == 3
        assert result.priority == 5

        # Should log
        mock_logger.debug.assert_called_with(
            "task_dequeued",
            task_id="task_123",
            queue=queue_name,
            worker_id=worker_id,
        )

    @pytest.mark.asyncio
    async def test_dequeue_timeout(self, bus, mock_redis):
        """Test dequeue timeout when no tasks available."""
        mock_redis.bzpopmin.return_value = None

        result = await bus.dequeue_task("agent:planner", "worker_1", timeout_seconds=1)

        assert result is None

    @pytest.mark.asyncio
    async def test_dequeue_missing_task_data(self, bus, mock_redis, mock_logger):
        """Test dequeue when task data is missing."""
        mock_redis.bzpopmin.return_value = (b"queue", b"task_missing", 123)
        mock_redis.hgetall.return_value = None

        result = await bus.dequeue_task("agent:test", "worker_1")

        assert result is None
        mock_logger.warning.assert_called_with("task_data_missing", task_id="task_missing")

    @pytest.mark.asyncio
    async def test_dequeue_handles_byte_strings(self, bus, mock_redis):
        """Test that dequeue handles byte strings from Redis."""
        mock_redis.bzpopmin.return_value = (
            b"queue",
            b"task_bytes",  # Byte string
            123,
        )

        mock_redis.hgetall.return_value = {
            "task_id": "task_bytes",
            "queue_name": "agent:test",
            "envelope_state": "{}",
            "agent_name": "test",
            "stage_order": "0",
            "retry_count": "0",
            "max_retries": "3",
            "priority": "0",
        }

        result = await bus.dequeue_task("agent:test", "worker_1")

        assert result is not None
        assert result.task_id == "task_bytes"


# =============================================================================
# Complete Task Tests
# =============================================================================

class TestCompleteTask:
    """Test task completion."""

    @pytest.mark.asyncio
    async def test_complete_task_success(self, bus, mock_redis, mock_logger):
        """Test successful task completion."""
        task_id = "task_123"
        result = {"status": "success", "output": "done"}

        # Mock task data
        mock_redis.hgetall.return_value = {
            "queue_name": "agent:planner",
            "worker_id": "worker_1",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }

        await bus.complete_task(task_id, result)

        # Should update task status
        status_update_calls = [c for c in mock_redis.hset.call_args_list if "completed" in str(c)]
        assert len(status_update_calls) > 0

        # Should remove from processing set
        mock_redis.srem.assert_called_with("dbus:processing:worker_1", task_id)

        # Should increment completed stat
        hincrby_calls = mock_redis.hincrby.call_args_list
        completed_call = [c for c in hincrby_calls if c[0][1] == "completed"]
        assert len(completed_call) > 0

        # Should log
        mock_logger.debug.assert_called_with("task_completed", task_id=task_id)

    @pytest.mark.asyncio
    async def test_complete_task_not_found(self, bus, mock_redis, mock_logger):
        """Test completing non-existent task."""
        mock_redis.hgetall.return_value = None

        await bus.complete_task("task_missing", {})

        mock_logger.warning.assert_called_with(
            "complete_task_not_found",
            task_id="task_missing",
        )

    @pytest.mark.asyncio
    async def test_complete_task_calculates_duration(self, bus, mock_redis):
        """Test that completion calculates processing time."""
        task_id = "task_timed"
        started_at = datetime.now(timezone.utc)

        mock_redis.hgetall.return_value = {
            "queue_name": "agent:test",
            "worker_id": "worker_1",
            "started_at": started_at.isoformat(),
        }

        # Mock hget for avg_time_ms
        mock_redis.hget.return_value = "1000"  # 1 second average

        await bus.complete_task(task_id, {})

        # Should update average processing time
        assert mock_redis.hget.called


# =============================================================================
# Fail Task Tests
# =============================================================================

class TestFailTask:
    """Test task failure and retry logic."""

    @pytest.mark.asyncio
    async def test_fail_task_with_retry(self, bus, mock_redis, mock_logger):
        """Test task failure triggers retry."""
        task_id = "task_retry"
        error = "Connection timeout"

        mock_redis.hgetall.return_value = {
            "queue_name": "agent:planner",
            "worker_id": "worker_1",
            "retry_count": "0",
            "max_retries": "3",
        }

        await bus.fail_task(task_id, error, retry=True)

        # Should remove from processing set
        mock_redis.srem.assert_called_with("dbus:processing:worker_1", task_id)

        # Should update retry_count and re-enqueue
        hset_calls = mock_redis.hset.call_args_list
        retry_update = [c for c in hset_calls if "retry_count" in str(c)]
        assert len(retry_update) > 0

        # Should re-add to queue with backoff
        mock_redis.zadd.assert_called()
        zadd_call = mock_redis.zadd.call_args
        score_dict = zadd_call[0][1]
        score = score_dict[task_id]

        # Score should be in future (backoff delay)
        assert score > time.time()

        # Should log retry
        mock_logger.info.assert_called_with(
            "task_retry_scheduled",
            task_id=task_id,
            retry=1,
            max_retries=3,
        )

    @pytest.mark.asyncio
    async def test_fail_task_max_retries_exceeded(self, bus, mock_redis, mock_logger):
        """Test task failure after max retries."""
        task_id = "task_failed"
        error = "Permanent error"

        mock_redis.hgetall.return_value = {
            "queue_name": "agent:planner",
            "worker_id": "worker_1",
            "retry_count": "3",  # Already at max
            "max_retries": "3",
        }

        await bus.fail_task(task_id, error, retry=True)

        # Should NOT re-enqueue
        mock_redis.zadd.assert_not_called()

        # Should mark as permanently failed
        hset_calls = mock_redis.hset.call_args_list
        failed_status = [c for c in hset_calls if "failed" in str(c)]
        assert len(failed_status) > 0

        # Should increment failed stat
        hincrby_calls = mock_redis.hincrby.call_args_list
        failed_stat = [c for c in hincrby_calls if c[0][1] == "failed"]
        assert len(failed_stat) > 0

        # Should log permanent failure
        mock_logger.warning.assert_called_with(
            "task_failed_permanently",
            task_id=task_id,
            error=error,
        )

    @pytest.mark.asyncio
    async def test_fail_task_without_retry(self, bus, mock_redis):
        """Test task failure without retry."""
        task_id = "task_no_retry"

        mock_redis.hgetall.return_value = {
            "queue_name": "agent:test",
            "worker_id": "worker_1",
            "retry_count": "0",
            "max_retries": "3",
        }

        await bus.fail_task(task_id, "Error", retry=False)

        # Should NOT re-enqueue even though retries available
        mock_redis.zadd.assert_not_called()

    @pytest.mark.asyncio
    async def test_fail_task_exponential_backoff(self, bus, mock_redis):
        """Test exponential backoff on retries."""
        task_id = "task_backoff"

        mock_redis.hgetall.return_value = {
            "queue_name": "agent:test",
            "worker_id": "worker_1",
            "retry_count": "2",  # Third attempt
            "max_retries": "5",
        }

        await bus.fail_task(task_id, "Error", retry=True)

        # Check backoff score (should be 2^3 = 8 seconds in future)
        zadd_call = mock_redis.zadd.call_args
        score_dict = zadd_call[0][1]
        score = score_dict[task_id]

        # Score should be ~8 seconds from now (2^3)
        expected_time = time.time() + 8
        assert abs(score - expected_time) < 2  # Allow 2s tolerance


# =============================================================================
# Worker Management Tests
# =============================================================================

class TestWorkerManagement:
    """Test worker registration and lifecycle."""

    @pytest.mark.asyncio
    async def test_register_worker(self, bus, mock_redis, mock_logger):
        """Test worker registration."""
        worker_id = "worker_1"
        capabilities = ["agent:*", "agent:planner"]

        await bus.register_worker(worker_id, capabilities)

        # Should create worker hash
        mock_redis.hset.assert_called()
        hset_call = mock_redis.hset.call_args
        assert hset_call[0][0] == "dbus:worker:worker_1"

        worker_data = hset_call[1]["mapping"]
        assert worker_data["worker_id"] == worker_id
        assert json.loads(worker_data["capabilities"]) == capabilities
        assert worker_data["status"] == "active"

        # Should set TTL (5 minutes)
        mock_redis.expire.assert_called_with("dbus:worker:worker_1", 300)

        # Should add to active workers set
        mock_redis.sadd.assert_called_with("dbus:workers:active", worker_id)

        # Should log
        mock_logger.info.assert_called_with(
            "worker_registered",
            worker_id=worker_id,
            capabilities=capabilities,
        )

    @pytest.mark.asyncio
    async def test_deregister_worker(self, bus, mock_redis, mock_logger):
        """Test worker deregistration."""
        worker_id = "worker_shutdown"

        # Mock processing tasks
        mock_redis.smembers.return_value = [b"task_1", b"task_2"]

        # Mock task data for requeuing
        mock_redis.hgetall.return_value = {
            "queue_name": "agent:test",
            "worker_id": worker_id,
            "retry_count": "0",
            "max_retries": "3",
        }

        await bus.deregister_worker(worker_id)

        # Should get processing tasks
        mock_redis.smembers.assert_called_with(f"dbus:processing:{worker_id}")

        # Should requeue tasks (via fail_task)
        # This triggers zadd for re-enqueueing
        assert mock_redis.zadd.call_count >= 2  # At least 2 tasks

        # Should delete worker data
        delete_call = mock_redis.delete.call_args
        assert "dbus:worker:worker_shutdown" in delete_call[0]
        assert "dbus:processing:worker_shutdown" in delete_call[0]

        # Should remove from active set
        mock_redis.srem.assert_called_with("dbus:workers:active", worker_id)

        # Should log
        mock_logger.info.assert_called_with("worker_deregistered", worker_id=worker_id)

    @pytest.mark.asyncio
    async def test_heartbeat(self, bus, mock_redis):
        """Test worker heartbeat."""
        worker_id = "worker_alive"

        await bus.heartbeat(worker_id)

        # Should update last_heartbeat
        mock_redis.hset.assert_called_with(
            "dbus:worker:worker_alive",
            "last_heartbeat",
            unittest.mock.ANY,  # Timestamp
        )

        # Should extend TTL
        mock_redis.expire.assert_called_with("dbus:worker:worker_alive", 300)


# =============================================================================
# Queue Stats Tests
# =============================================================================

class TestQueueStats:
    """Test queue statistics."""

    @pytest.mark.asyncio
    async def test_get_queue_stats(self, bus, mock_redis):
        """Test getting queue statistics."""
        queue_name = "agent:planner"

        # Mock queue depth
        mock_redis.zcard.return_value = 5  # 5 pending tasks

        # Mock stats
        mock_redis.hgetall.return_value = {
            "in_progress": "3",
            "completed": "100",
            "failed": "2",
            "avg_time_ms": "1500.5",
        }

        # Mock active workers
        mock_redis.smembers.return_value = [b"worker_1", b"worker_2"]

        # Mock worker data
        async def mock_hgetall_worker(key):
            if "worker_1" in key:
                return {"capabilities": json.dumps(["agent:*"])}
            elif "worker_2" in key:
                return {"capabilities": json.dumps(["agent:planner"])}
            return {}

        mock_redis.hgetall.side_effect = [
            # First call: stats
            {
                "in_progress": "3",
                "completed": "100",
                "failed": "2",
                "avg_time_ms": "1500.5",
            },
            # Second/third calls: worker data
            {"capabilities": json.dumps(["agent:*"])},
            {"capabilities": json.dumps(["agent:planner"])},
        ]

        result = await bus.get_queue_stats(queue_name)

        # Should return QueueStats
        assert isinstance(result, QueueStats)
        assert result.queue_name == queue_name
        assert result.pending_count == 5
        assert result.in_progress_count == 3
        assert result.completed_count == 100
        assert result.failed_count == 2
        assert result.avg_processing_time_ms == 1500.5
        assert result.workers_active == 2  # Both workers can handle this queue

    @pytest.mark.asyncio
    async def test_list_queues(self, bus, mock_redis):
        """Test listing all queues."""
        # Mock scan_iter as async generator
        async def mock_scan(match=None):
            for key in [b"dbus:queue:agent:planner", b"dbus:queue:agent:executor"]:
                yield key

        mock_redis.scan_iter = mock_scan

        result = await bus.list_queues()

        # Should return queue names
        assert "agent:planner" in result
        assert "agent:executor" in result
        assert len(result) == 2


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_enqueue_empty_envelope_state(self, bus, mock_redis):
        """Test enqueueing task with empty envelope state."""
        task = DistributedTask(
            task_id="task_empty",
            envelope_state={},  # Empty
            agent_name="test",
            stage_order=0,
        )

        await bus.enqueue_task("agent:test", task)

        hset_call = mock_redis.hset.call_args
        task_data = hset_call[1]["mapping"]
        assert json.loads(task_data["envelope_state"]) == {}

    @pytest.mark.asyncio
    async def test_dequeue_string_task_id(self, bus, mock_redis):
        """Test dequeue when task_id is already a string."""
        mock_redis.bzpopmin.return_value = (
            "queue",
            "task_string",  # String, not bytes
            123,
        )

        mock_redis.hgetall.return_value = {
            "task_id": "task_string",
            "queue_name": "agent:test",
            "envelope_state": "{}",
            "agent_name": "test",
            "stage_order": "0",
            "retry_count": "0",
            "max_retries": "3",
            "priority": "0",
        }

        result = await bus.dequeue_task("agent:test", "worker_1")

        assert result.task_id == "task_string"

    @pytest.mark.asyncio
    async def test_complete_task_without_worker_id(self, bus, mock_redis):
        """Test completing task without worker_id in data."""
        mock_redis.hgetall.return_value = {
            "queue_name": "agent:test",
            # No worker_id field
        }

        # Should not crash
        await bus.complete_task("task_no_worker", {})

        # Should not attempt to remove from processing set
        mock_redis.srem.assert_not_called()


# Note: Import unittest.mock for ANY matcher
import unittest.mock
