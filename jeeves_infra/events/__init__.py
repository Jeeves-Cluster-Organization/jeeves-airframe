"""Event integration layer for Control Tower.

This module bridges Control Tower's EventAggregator with Mission System's
EventOrchestrator and WebSocket event manager.
"""

from jeeves_infra.events.bridge import EventBridge

__all__ = ["EventBridge"]
