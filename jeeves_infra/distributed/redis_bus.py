"""Redis distributed bus for horizontal scaling.

Constitutional Amendment XXIV: Horizontal Scaling Support.
Implements DistributedBusProtocol using Redis streams and sorted sets.
"""

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from jeeves_infra.protocols import (
    DistributedBusProtocol,
    DistributedTask,
    QueueStats,
)
from jeeves_infra.protocols import LoggerProtocol
from jeeves_infra.logging import get_current_logger
from jeeves_infra.utils.serialization import parse_datetime


class RedisDistributedBus:
    """Redis implementation of DistributedBusProtocol.

    Uses Redis data structures for distributed task execution:
    - Sorted sets for priority queues (ZADD/BZPOPMIN)
    - Hashes for task state and worker registration
    - Streams for task completion events

    Usage:
        bus = RedisDistributedBus(redis_client)

        # Producer: enqueue task
        task_id = await bus.enqueue_task(
            "agent:planner",
            DistributedTask(
                task_id="task_123",
                envelope_state=envelope.to_state_dict(),
                agent_name="planner",
                stage_order=1,
            ),
        )

        # Worker: process tasks
        await bus.register_worker("worker_1", ["agent:*"])
        while True:
            task = await bus.dequeue_task("agent:planner", "worker_1")
            if task:
                try:
                    result = await process(task)
                    await bus.complete_task(task.task_id, result)
                except Exception as e:
                    await bus.fail_task(task.task_id, str(e))
    """

    # Key prefixes
    QUEUE_PREFIX = "dbus:queue:"
    TASK_PREFIX = "dbus:task:"
    WORKER_PREFIX = "dbus:worker:"
    STATS_PREFIX = "dbus:stats:"
    PROCESSING_PREFIX = "dbus:processing:"

    def __init__(
        self,
        redis_client: Any,
        logger: Optional[LoggerProtocol] = None,
    ):
        """Initialize distributed bus.

        Args:
            redis_client: RedisClient instance
            logger: Logger for DI (uses context logger if not provided)
        """
        self._redis = redis_client
        self._logger = logger or get_current_logger()

    async def enqueue_task(
        self,
        queue_name: str,
        task: DistributedTask,
    ) -> str:
        """Enqueue task for worker processing.

        Args:
            queue_name: Target queue (e.g., "agent:planner", "agent:default")
            task: Task payload with envelope state

        Returns:
            Task ID for tracking
        """
        redis = self._redis.redis

        # Store task data in hash
        task_key = f"{self.TASK_PREFIX}{task.task_id}"
        task_data = {
            "task_id": task.task_id,
            "queue_name": queue_name,
            "envelope_state": json.dumps(task.envelope_state),
            "agent_name": task.agent_name,
            "stage_order": task.stage_order,
            "checkpoint_id": task.checkpoint_id or "",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "retry_count": task.retry_count,
            "max_retries": task.max_retries,
            "priority": task.priority,
            "status": "pending",
        }
        await redis.hset(task_key, mapping=task_data)
        await redis.expire(task_key, 86400)  # 24 hour TTL

        # Add to priority queue (lower score = higher priority)
        queue_key = f"{self.QUEUE_PREFIX}{queue_name}"
        score = time.time() - (task.priority * 1000)  # Priority offset
        await redis.zadd(queue_key, {task.task_id: score})

        # Update stats
        await self._increment_stat(queue_name, "enqueued")

        self._logger.debug(
            "task_enqueued",
            task_id=task.task_id,
            queue=queue_name,
            priority=task.priority,
        )

        return task.task_id

    async def dequeue_task(
        self,
        queue_name: str,
        worker_id: str,
        timeout_seconds: int = 30,
    ) -> Optional[DistributedTask]:
        """Dequeue task for processing (blocking with timeout).

        Args:
            queue_name: Queue to pull from
            worker_id: Worker claiming the task
            timeout_seconds: How long to wait for task

        Returns:
            Task to process, or None if timeout
        """
        redis = self._redis.redis
        queue_key = f"{self.QUEUE_PREFIX}{queue_name}"

        # Blocking pop from sorted set (lowest score first)
        result = await redis.bzpopmin(queue_key, timeout=timeout_seconds)

        if not result:
            return None

        _, task_id, _ = result
        task_id = task_id if isinstance(task_id, str) else task_id.decode()

        # Load task data
        task_key = f"{self.TASK_PREFIX}{task_id}"
        task_data = await redis.hgetall(task_key)

        if not task_data:
            self._logger.warning("task_data_missing", task_id=task_id)
            return None

        # Mark as processing
        await redis.hset(task_key, mapping={
            "status": "processing",
            "worker_id": worker_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
        })

        # Track in processing set (for dead letter detection)
        processing_key = f"{self.PROCESSING_PREFIX}{worker_id}"
        await redis.sadd(processing_key, task_id)

        # Update stats
        await self._increment_stat(queue_name, "dequeued")

        self._logger.debug(
            "task_dequeued",
            task_id=task_id,
            queue=queue_name,
            worker_id=worker_id,
        )

        return DistributedTask(
            task_id=task_id,
            envelope_state=json.loads(task_data.get("envelope_state", "{}")),
            agent_name=task_data.get("agent_name", ""),
            stage_order=int(task_data.get("stage_order", 0)),
            checkpoint_id=task_data.get("checkpoint_id") or None,
            created_at=task_data.get("created_at"),
            retry_count=int(task_data.get("retry_count", 0)),
            max_retries=int(task_data.get("max_retries", 3)),
            priority=int(task_data.get("priority", 0)),
        )

    async def complete_task(
        self,
        task_id: str,
        result: Dict[str, Any],
    ) -> None:
        """Mark task as completed with result."""
        redis = self._redis.redis
        task_key = f"{self.TASK_PREFIX}{task_id}"

        # Get task info
        task_data = await redis.hgetall(task_key)
        if not task_data:
            self._logger.warning("complete_task_not_found", task_id=task_id)
            return

        queue_name = task_data.get("queue_name", "unknown")
        worker_id = task_data.get("worker_id", "")

        # Update task status
        await redis.hset(task_key, mapping={
            "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "result": json.dumps(result),
        })

        # Remove from processing set
        if worker_id:
            processing_key = f"{self.PROCESSING_PREFIX}{worker_id}"
            await redis.srem(processing_key, task_id)

        # Update stats
        await self._increment_stat(queue_name, "completed")

        # Calculate processing time for stats
        started_at = task_data.get("started_at")
        if started_at:
            start = parse_datetime(started_at)
            if start:
                duration_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                await self._update_processing_time(queue_name, duration_ms)

        self._logger.debug("task_completed", task_id=task_id)

    async def fail_task(
        self,
        task_id: str,
        error: str,
        retry: bool = True,
    ) -> None:
        """Mark task as failed, optionally retry."""
        redis = self._redis.redis
        task_key = f"{self.TASK_PREFIX}{task_id}"

        # Get task info
        task_data = await redis.hgetall(task_key)
        if not task_data:
            self._logger.warning("fail_task_not_found", task_id=task_id)
            return

        queue_name = task_data.get("queue_name", "unknown")
        worker_id = task_data.get("worker_id", "")
        retry_count = int(task_data.get("retry_count", 0))
        max_retries = int(task_data.get("max_retries", 3))

        # Remove from processing set
        if worker_id:
            processing_key = f"{self.PROCESSING_PREFIX}{worker_id}"
            await redis.srem(processing_key, task_id)

        # Check if we should retry
        if retry and retry_count < max_retries:
            # Increment retry count and re-enqueue
            new_retry_count = retry_count + 1
            await redis.hset(task_key, mapping={
                "status": "pending",
                "retry_count": new_retry_count,
                "last_error": error,
                "last_failed_at": datetime.now(timezone.utc).isoformat(),
            })

            # Re-add to queue with backoff (exponential: 2^retry seconds delay)
            queue_key = f"{self.QUEUE_PREFIX}{queue_name}"
            backoff_score = time.time() + (2 ** new_retry_count)
            await redis.zadd(queue_key, {task_id: backoff_score})

            self._logger.info(
                "task_retry_scheduled",
                task_id=task_id,
                retry=new_retry_count,
                max_retries=max_retries,
            )
        else:
            # Permanent failure
            await redis.hset(task_key, mapping={
                "status": "failed",
                "failed_at": datetime.now(timezone.utc).isoformat(),
                "error": error,
            })

            await self._increment_stat(queue_name, "failed")

            self._logger.warning(
                "task_failed_permanently",
                task_id=task_id,
                error=error,
            )

    async def register_worker(
        self,
        worker_id: str,
        capabilities: List[str],
    ) -> None:
        """Register worker with capabilities.

        Args:
            worker_id: Unique worker identifier
            capabilities: List of queue patterns (e.g., ["agent:*", "agent:planner"])
        """
        redis = self._redis.redis
        worker_key = f"{self.WORKER_PREFIX}{worker_id}"

        await redis.hset(worker_key, mapping={
            "worker_id": worker_id,
            "capabilities": json.dumps(capabilities),
            "registered_at": datetime.now(timezone.utc).isoformat(),
            "last_heartbeat": datetime.now(timezone.utc).isoformat(),
            "status": "active",
        })
        await redis.expire(worker_key, 300)  # 5 minute TTL (must heartbeat)

        # Add to active workers set
        await redis.sadd("dbus:workers:active", worker_id)

        self._logger.info(
            "worker_registered",
            worker_id=worker_id,
            capabilities=capabilities,
        )

    async def deregister_worker(
        self,
        worker_id: str,
    ) -> None:
        """Deregister worker (on shutdown)."""
        redis = self._redis.redis
        worker_key = f"{self.WORKER_PREFIX}{worker_id}"

        # Get tasks being processed by this worker
        processing_key = f"{self.PROCESSING_PREFIX}{worker_id}"
        processing_tasks = await redis.smembers(processing_key)

        # Requeue any in-progress tasks
        for task_id in processing_tasks:
            task_id = task_id if isinstance(task_id, str) else task_id.decode()
            await self.fail_task(task_id, "Worker shutdown", retry=True)

        # Remove worker
        await redis.delete(worker_key, processing_key)
        await redis.srem("dbus:workers:active", worker_id)

        self._logger.info("worker_deregistered", worker_id=worker_id)

    async def heartbeat(
        self,
        worker_id: str,
    ) -> None:
        """Send worker heartbeat."""
        redis = self._redis.redis
        worker_key = f"{self.WORKER_PREFIX}{worker_id}"

        await redis.hset(worker_key, "last_heartbeat",
                        datetime.now(timezone.utc).isoformat())
        await redis.expire(worker_key, 300)  # Extend TTL

    async def get_queue_stats(
        self,
        queue_name: str,
    ) -> QueueStats:
        """Get queue statistics for monitoring."""
        redis = self._redis.redis
        queue_key = f"{self.QUEUE_PREFIX}{queue_name}"
        stats_key = f"{self.STATS_PREFIX}{queue_name}"

        # Get queue depth
        pending_count = await redis.zcard(queue_key)

        # Get stats from hash
        stats = await redis.hgetall(stats_key)

        # Count active workers for this queue
        active_workers = await redis.smembers("dbus:workers:active")
        workers_active = 0
        for wid in active_workers:
            wid = wid if isinstance(wid, str) else wid.decode()
            worker_key = f"{self.WORKER_PREFIX}{wid}"
            worker_data = await redis.hgetall(worker_key)
            if worker_data:
                caps = json.loads(worker_data.get("capabilities", "[]"))
                # Simple pattern matching (would need glob in production)
                if queue_name in caps or "agent:*" in caps:
                    workers_active += 1

        return QueueStats(
            queue_name=queue_name,
            pending_count=pending_count,
            in_progress_count=int(stats.get("in_progress", 0)),
            completed_count=int(stats.get("completed", 0)),
            failed_count=int(stats.get("failed", 0)),
            avg_processing_time_ms=float(stats.get("avg_time_ms", 0)),
            workers_active=workers_active,
        )

    async def list_queues(self) -> List[str]:
        """List all active queues."""
        redis = self._redis.redis
        pattern = f"{self.QUEUE_PREFIX}*"

        keys = []
        async for key in redis.scan_iter(match=pattern):
            key = key if isinstance(key, str) else key.decode()
            queue_name = key[len(self.QUEUE_PREFIX):]
            keys.append(queue_name)

        return keys

    async def _increment_stat(self, queue_name: str, stat: str) -> None:
        """Increment queue statistic."""
        redis = self._redis.redis
        stats_key = f"{self.STATS_PREFIX}{queue_name}"
        await redis.hincrby(stats_key, stat, 1)

    async def _update_processing_time(
        self,
        queue_name: str,
        duration_ms: float,
    ) -> None:
        """Update average processing time (exponential moving average)."""
        redis = self._redis.redis
        stats_key = f"{self.STATS_PREFIX}{queue_name}"

        # Simple moving average
        current = float(await redis.hget(stats_key, "avg_time_ms") or 0)
        count = int(await redis.hget(stats_key, "completed") or 1)

        # EMA with alpha based on sample count
        alpha = min(0.1, 2.0 / (count + 1))
        new_avg = current * (1 - alpha) + duration_ms * alpha

        await redis.hset(stats_key, "avg_time_ms", new_avg)
