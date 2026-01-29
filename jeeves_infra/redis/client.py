"""Redis client for distributed state management.

Provides shared state primitives for distributed deployment:
- Rate limiting (sliding window)
- Distributed locks with TTL
- Embedding cache
- Session state

Only used when deployment_mode="distributed" and use_redis_state=True.
"""

import asyncio
import time
import json
from typing import Optional, List, Tuple, Any
from datetime import datetime, timedelta

from jeeves_infra.logging import get_current_logger
from jeeves_infra.protocols import LoggerProtocol


class RedisClient:
    """Async Redis client for distributed state management.

    This is a lightweight wrapper that provides common distributed
    primitives. Requires redis package and running Redis server.

    For single-node deployments, use in-memory alternatives instead.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        logger: Optional[LoggerProtocol] = None,
    ):
        """Initialize Redis client.

        Args:
            redis_url: Redis connection URL
                      Format: redis://[:password]@host:port/db
            logger: Logger for DI (uses context logger if not provided)
        """
        self._logger = logger or get_current_logger()
        self.redis_url = redis_url
        self.redis = None
        self._connected = False

    async def connect(self):
        """Establish Redis connection."""
        try:
            import redis.asyncio as redis

            self.redis = await redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )

            # Test connection
            await self.redis.ping()
            self._connected = True

            self._logger.info("redis_connected", url=self.redis_url)

        except ImportError:
            self._logger.error(
                "redis_import_failed",
                message="Install redis package: pip install redis"
            )
            raise
        except Exception as e:
            self._logger.error("redis_connection_failed", error=str(e), url=self.redis_url)
            raise

    async def disconnect(self):
        """Close Redis connection."""
        if self.redis:
            await self.redis.close()
            self._connected = False
            self._logger.info("redis_disconnected")

    async def rate_limit_check(
        self,
        user_id: str,
        limit: int,
        window_seconds: int = 60
    ) -> Tuple[bool, int]:
        """Sliding window rate limiter.

        Uses Redis sorted sets with timestamps as scores for accurate
        rate limiting across distributed instances.

        Args:
            user_id: User identifier
            limit: Maximum requests allowed in window
            window_seconds: Time window in seconds

        Returns:
            Tuple of (allowed, remaining_requests)
            - allowed: True if request should be allowed
            - remaining_requests: Number of requests left in window

        Example:
            allowed, remaining = await redis.rate_limit_check(
                user_id="user_123",
                limit=10,
                window_seconds=60
            )
            if not allowed:
                raise RateLimitExceeded(f"Try again in {window_seconds}s")
        """
        if not self._connected:
            await self.connect()

        key = f"rate_limit:{user_id}"
        now = time.time()
        window_start = now - window_seconds

        # Use pipeline for atomic operations
        pipe = self.redis.pipeline()

        # Remove old entries outside window
        pipe.zremrangebyscore(key, 0, window_start)

        # Count requests in current window
        pipe.zcard(key)

        # Add current request
        pipe.zadd(key, {str(now): now})

        # Set expiry on key (cleanup)
        pipe.expire(key, window_seconds + 10)

        results = await pipe.execute()
        current_count = results[1]  # Count before adding current request

        allowed = current_count < limit
        remaining = max(0, limit - current_count - (1 if allowed else 0))

        self._logger.debug(
            "rate_limit_check",
            user_id=user_id,
            current_count=current_count,
            limit=limit,
            allowed=allowed,
            remaining=remaining
        )

        return (allowed, remaining)

    async def acquire_lock(
        self,
        key: str,
        ttl_seconds: int = 30,
        owner: Optional[str] = None
    ) -> bool:
        """Acquire distributed lock with automatic expiry.

        Uses Redis SET with NX (only if not exists) and EX (expiry) options
        for atomic lock acquisition.

        Args:
            key: Lock key
            ttl_seconds: Lock TTL (auto-release after this time)
            owner: Lock owner identifier (for debugging)

        Returns:
            True if lock acquired, False if already held

        Example:
            if await redis.acquire_lock("job:123", ttl_seconds=60):
                try:
                    # Do work
                    pass
                finally:
                    await redis.release_lock("job:123")
        """
        if not self._connected:
            await self.connect()

        lock_key = f"lock:{key}"
        lock_value = owner or f"lock_{time.time()}"

        # SET key value NX EX ttl
        # NX = only set if not exists
        # EX = expiry in seconds
        acquired = await self.redis.set(
            lock_key,
            lock_value,
            nx=True,
            ex=ttl_seconds
        )

        if acquired:
            self._logger.debug("lock_acquired", key=key, owner=owner, ttl=ttl_seconds)
        else:
            self._logger.debug("lock_acquisition_failed", key=key, owner=owner)

        return bool(acquired)

    async def release_lock(self, key: str) -> bool:
        """Release distributed lock.

        Args:
            key: Lock key

        Returns:
            True if lock was released, False if didn't exist
        """
        if not self._connected:
            await self.connect()

        lock_key = f"lock:{key}"
        deleted = await self.redis.delete(lock_key)

        if deleted:
            self._logger.debug("lock_released", key=key)

        return deleted > 0

    async def cache_embedding(
        self,
        text_hash: str,
        vector: List[float],
        ttl: int = 3600
    ) -> None:
        """Cache computed embedding vector.

        Args:
            text_hash: Hash of text (e.g., SHA256)
            vector: Embedding vector
            ttl: Time-to-live in seconds (default 1 hour)

        Note:
            Vectors are stored as JSON arrays. For production with
            large volumes, consider Redis Vector Search extension.
        """
        if not self._connected:
            await self.connect()

        key = f"embedding:{text_hash}"
        value = json.dumps(vector)

        await self.redis.setex(key, ttl, value)

        self._logger.debug(
            "embedding_cached",
            text_hash=text_hash,
            vector_dim=len(vector),
            ttl=ttl
        )

    async def get_cached_embedding(
        self,
        text_hash: str
    ) -> Optional[List[float]]:
        """Retrieve cached embedding.

        Args:
            text_hash: Hash of text

        Returns:
            Embedding vector if cached, None otherwise
        """
        if not self._connected:
            await self.connect()

        key = f"embedding:{text_hash}"
        value = await self.redis.get(key)

        if value:
            self._logger.debug("embedding_cache_hit", text_hash=text_hash)
            return json.loads(value)
        else:
            self._logger.debug("embedding_cache_miss", text_hash=text_hash)
            return None

    async def set_value(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> None:
        """Set arbitrary value with optional TTL.

        Args:
            key: Key name
            value: Value (will be JSON serialized)
            ttl: Optional time-to-live in seconds
        """
        if not self._connected:
            await self.connect()

        serialized = json.dumps(value)

        if ttl:
            await self.redis.setex(key, ttl, serialized)
        else:
            await self.redis.set(key, serialized)

    async def get_value(self, key: str) -> Optional[Any]:
        """Get value by key.

        Args:
            key: Key name

        Returns:
            Deserialized value or None
        """
        if not self._connected:
            await self.connect()

        value = await self.redis.get(key)

        if value:
            return json.loads(value)
        return None

    async def delete(self, key: str) -> bool:
        """Delete key.

        Args:
            key: Key to delete

        Returns:
            True if key existed and was deleted
        """
        if not self._connected:
            await self.connect()

        deleted = await self.redis.delete(key)
        return deleted > 0

    async def increment(self, key: str, amount: int = 1) -> int:
        """Increment counter.

        Args:
            key: Counter key
            amount: Amount to increment

        Returns:
            New counter value
        """
        if not self._connected:
            await self.connect()

        return await self.redis.incrby(key, amount)

    async def get_stats(self) -> dict:
        """Get Redis server stats.

        Returns:
            Dictionary with server info
        """
        if not self._connected:
            await self.connect()

        info = await self.redis.info("stats")
        return {
            "total_commands_processed": info.get("total_commands_processed", 0),
            "total_connections_received": info.get("total_connections_received", 0),
            "keyspace_hits": info.get("keyspace_hits", 0),
            "keyspace_misses": info.get("keyspace_misses", 0),
        }


# Module-level instance (lazy-init)
_redis_client: Optional[RedisClient] = None


def get_redis_client(redis_url: str = "redis://localhost:6379") -> RedisClient:
    """Get global Redis client instance.

    Args:
        redis_url: Redis connection URL

    Returns:
        RedisClient instance
    """
    global _redis_client

    if _redis_client is None:
        _redis_client = RedisClient(redis_url)

    return _redis_client
