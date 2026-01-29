"""Event integration layer for Control Tower.

This module bridges Control Tower's EventAggregator with Mission System's
EventOrchestrator and WebSocket event manager.
"""

from mission_system.events.bridge import EventBridge

__all__ = ["EventBridge"]
