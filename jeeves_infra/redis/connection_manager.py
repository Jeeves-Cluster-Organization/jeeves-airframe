"""Connection manager for deployment-mode-aware backend selection.

Provides unified interface for state management that transparently
switches between single-node (in-memory) and distributed (Redis)
backends based on deployment_mode configuration.
"""

from typing import Optional, Tuple, List, Any
from jeeves_infra.settings import Settings
from jeeves_infra.feature_flags import get_feature_flags
from jeeves_infra.logging import get_current_logger
from jeeves_infra.protocols import LoggerProtocol


class StateBackend:
    """Abstract interface for state storage backends."""

    async def rate_limit_check(
        self,
        user_id: str,
        limit: int,
        window_seconds: int
    ) -> Tuple[bool, int]:
        """Check if user is within rate limit."""
        raise NotImplementedError

    async def acquire_lock(
        self,
        key: str,
        ttl_seconds: int,
        owner: Optional[str] = None
    ) -> bool:
        """Acquire distributed/process lock."""
        raise NotImplementedError

    async def release_lock(self, key: str) -> bool:
        """Release lock."""
        raise NotImplementedError

    async def cache_embedding(
        self,
        text_hash: str,
        vector: List[float],
        ttl: int
    ) -> None:
        """Cache embedding vector."""
        raise NotImplementedError

    async def get_cached_embedding(
        self,
        text_hash: str
    ) -> Optional[List[float]]:
        """Retrieve cached embedding."""
        raise NotImplementedError


class InMemoryStateBackend(StateBackend):
    """In-memory state backend for single-node deployments.

    Uses simple Python dicts with manual expiry tracking.
    Not thread-safe for multi-process deployments.
    """

    def __init__(self, logger: Optional[LoggerProtocol] = None):
        """Initialize in-memory backend.

        Args:
            logger: Logger for DI (uses context logger if not provided)
        """
        self._logger = logger or get_current_logger()
        self.rate_limits = {}  # user_id -> [(timestamp, ...)]
        self.locks = {}  # key -> (owner, expiry_time)
        self.embedding_cache = {}  # text_hash -> (vector, expiry_time)

        self._logger.info("state_backend_initialized", backend="in_memory")

    async def rate_limit_check(
        self,
        user_id: str,
        limit: int,
        window_seconds: int
    ) -> Tuple[bool, int]:
        """In-memory rate limiting using sliding window."""
        import time

        now = time.time()
        window_start = now - window_seconds

        # Get or create rate limit entry
        if user_id not in self.rate_limits:
            self.rate_limits[user_id] = []

        # Remove old entries
        self.rate_limits[user_id] = [
            ts for ts in self.rate_limits[user_id]
            if ts > window_start
        ]

        current_count = len(self.rate_limits[user_id])
        allowed = current_count < limit

        if allowed:
            self.rate_limits[user_id].append(now)

        remaining = max(0, limit - current_count - (1 if allowed else 0))

        return (allowed, remaining)

    async def acquire_lock(
        self,
        key: str,
        ttl_seconds: int,
        owner: Optional[str] = None
    ) -> bool:
        """In-memory lock acquisition."""
        import time

        now = time.time()

        # Check if lock exists and not expired
        if key in self.locks:
            lock_owner, expiry = self.locks[key]
            if expiry > now:
                # Lock still valid
                return False
            else:
                # Lock expired, remove it
                del self.locks[key]

        # Acquire lock
        self.locks[key] = (owner or "unknown", now + ttl_seconds)
        return True

    async def release_lock(self, key: str) -> bool:
        """Release in-memory lock."""
        if key in self.locks:
            del self.locks[key]
            return True
        return False

    async def cache_embedding(
        self,
        text_hash: str,
        vector: List[float],
        ttl: int
    ) -> None:
        """Cache embedding in memory."""
        import time

        expiry = time.time() + ttl
        self.embedding_cache[text_hash] = (vector, expiry)

    async def get_cached_embedding(
        self,
        text_hash: str
    ) -> Optional[List[float]]:
        """Get cached embedding from jeeves_infra.memory."""
        import time

        if text_hash in self.embedding_cache:
            vector, expiry = self.embedding_cache[text_hash]

            if expiry > time.time():
                return vector
            else:
                # Expired, remove it
                del self.embedding_cache[text_hash]

        return None


class RedisStateBackend(StateBackend):
    """Redis-based state backend for distributed deployments."""

    def __init__(self, redis_url: str, logger: Optional[LoggerProtocol] = None):
        """Initialize Redis backend.

        Args:
            redis_url: Redis connection URL
            logger: Logger for DI (uses context logger if not provided)
        """
        from jeeves_infra.redis.client import get_redis_client

        self._logger = logger or get_current_logger()
        self.redis = get_redis_client(redis_url)
        self._logger.info("state_backend_initialized", backend="redis", url=redis_url)

    async def rate_limit_check(
        self,
        user_id: str,
        limit: int,
        window_seconds: int
    ) -> Tuple[bool, int]:
        """Redis-backed rate limiting."""
        return await self.redis.rate_limit_check(user_id, limit, window_seconds)

    async def acquire_lock(
        self,
        key: str,
        ttl_seconds: int,
        owner: Optional[str] = None
    ) -> bool:
        """Redis-backed distributed lock."""
        return await self.redis.acquire_lock(key, ttl_seconds, owner)

    async def release_lock(self, key: str) -> bool:
        """Release Redis lock."""
        return await self.redis.release_lock(key)

    async def cache_embedding(
        self,
        text_hash: str,
        vector: List[float],
        ttl: int
    ) -> None:
        """Cache embedding in Redis."""
        await self.redis.cache_embedding(text_hash, vector, ttl)

    async def get_cached_embedding(
        self,
        text_hash: str
    ) -> Optional[List[float]]:
        """Get cached embedding from Redis."""
        return await self.redis.get_cached_embedding(text_hash)


class ConnectionManager:
    """Manages state backend selection based on deployment mode.

    Provides a unified interface that transparently routes to either
    in-memory (single-node) or Redis (distributed) backend.

    Example:
        manager = ConnectionManager(settings, logger=logger)
        backend = await manager.get_state_backend()

        allowed, remaining = await backend.rate_limit_check(
            user_id="user_123",
            limit=10,
            window_seconds=60
        )
    """

    def __init__(self, settings: Settings, logger: Optional[LoggerProtocol] = None):
        """Initialize connection manager.

        Args:
            settings: Application settings
            logger: Logger for DI (uses context logger if not provided)
        """
        self._logger = logger or get_current_logger()
        self.settings = settings
        self.feature_flags = get_feature_flags()
        self._backend: Optional[StateBackend] = None

    async def get_state_backend(self) -> StateBackend:
        """Get appropriate state backend for current deployment mode.

        Returns:
            StateBackend instance (InMemory or Redis)
        """
        if self._backend is not None:
            return self._backend

        # Check deployment mode and feature flags
        use_redis = (
            self.settings.deployment_mode == "distributed"
            and self.feature_flags.use_redis_state
        )

        if use_redis:
            # Distributed mode: use Redis
            redis_url = getattr(
                self.settings,
                "redis_url",
                "redis://localhost:6379"
            )

            self._logger.info(
                "initializing_state_backend",
                mode="distributed",
                backend="redis",
                url=redis_url
            )

            self._backend = RedisStateBackend(redis_url, logger=self._logger)

            # Connect to Redis
            if hasattr(self._backend, 'redis'):
                await self._backend.redis.connect()

        else:
            # Single-node mode: use in-memory
            self._logger.info(
                "initializing_state_backend",
                mode="single_node",
                backend="in_memory"
            )

            self._backend = InMemoryStateBackend(logger=self._logger)

        return self._backend

    async def close(self):
        """Close backend connections."""
        if self._backend and isinstance(self._backend, RedisStateBackend):
            await self._backend.redis.disconnect()


# Global instance (lazy-init)
_connection_manager: Optional[ConnectionManager] = None


def get_connection_manager(settings: Settings) -> ConnectionManager:
    """Get global connection manager instance.

    Args:
        settings: Application settings

    Returns:
        ConnectionManager instance
    """
    global _connection_manager

    if _connection_manager is None:
        _connection_manager = ConnectionManager(settings)

    return _connection_manager
