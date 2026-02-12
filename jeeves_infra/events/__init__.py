"""Event integration layer.

Bridges the Rust kernel's CommBus lifecycle events to the gateway's
WebSocket event manager for real-time frontend streaming.

Flow: Kernel CommBus → KernelEventAggregator → EventBridge → WebSocket
"""

from jeeves_infra.events.aggregator import KernelEventAggregator
from jeeves_infra.events.bridge import EventBridge

__all__ = ["EventBridge", "KernelEventAggregator"]
