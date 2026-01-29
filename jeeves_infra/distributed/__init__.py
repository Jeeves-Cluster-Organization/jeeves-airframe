"""Distributed execution adapters for horizontal scaling.

Constitutional Amendment XXIV: Horizontal Scaling Support.
Concrete implementations of DistributedBusProtocol.
"""

from jeeves_infra.distributed.redis_bus import RedisDistributedBus

__all__ = ["RedisDistributedBus"]
