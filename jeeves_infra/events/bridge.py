"""EventBridge - Translates kernel lifecycle events to frontend WebSocket events.

This bridge:
1. Subscribes to kernel lifecycle events via KernelEventAggregator
2. Translates them to frontend-friendly event formats
3. Forwards to WebSocket manager for real-time streaming
4. Handles interrupt-to-clarification/confirmation translation

Architecture:
    Kernel CommBus (Rust)
           | IPC Subscribe (streaming)
    KernelEventAggregator
           | subscribe("*", callback)
    EventBridge (translation layer)
           | broadcast
    WebSocketEventManager (frontend streaming)
"""

from __future__ import annotations

from typing import Any, Dict, Optional, TYPE_CHECKING

from jeeves_infra.protocols import InterruptKind
from jeeves_infra.protocols import LoggerProtocol

from dataclasses import dataclass

if TYPE_CHECKING:
    from jeeves_infra.events.aggregator import KernelEventAggregator


@dataclass
class KernelEvent:
    """Kernel event for pipeline orchestration."""
    event_type: str
    pid: str
    data: Dict[str, Any]


class EventBridge:
    """Bridges kernel lifecycle events to frontend WebSocket streams.

    Integration layer between:
    - KernelEventAggregator (CommBus event streaming)
    - WebSocketEventManager (frontend broadcasting)

    Usage:
        aggregator = KernelEventAggregator(kernel_client)
        bridge = EventBridge(aggregator, ws_manager, logger)
        await aggregator.start()
        bridge.start()
    """

    def __init__(
        self,
        event_aggregator: "KernelEventAggregator",
        websocket_manager: Any,  # WebSocketEventManager
        logger: LoggerProtocol,
    ) -> None:
        """Initialize EventBridge.

        Args:
            event_aggregator: KernelEventAggregator streaming CommBus events.
            websocket_manager: WebSocketEventManager for frontend broadcasting.
            logger: Logger instance.
        """
        self._aggregator = event_aggregator
        self._ws_manager = websocket_manager
        self._logger = logger.bind(component="event_bridge")
        self._started = False

    def start(self) -> None:
        """Start bridging events.

        Subscribes to all kernel events and begins forwarding to WebSocket.
        """
        if self._started:
            return

        # Subscribe to all kernel events (wildcard)
        self._aggregator.subscribe("*", self._on_kernel_event)
        self._started = True

        self._logger.info("event_bridge_started")

    def stop(self) -> None:
        """Stop bridging events."""
        if not self._started:
            return

        self._aggregator.unsubscribe("*", self._on_kernel_event)
        self._started = False

        self._logger.info("event_bridge_stopped")

    def _on_kernel_event(self, event: KernelEvent) -> None:
        """Handle kernel event from CommBus.

        Translates kernel events to frontend-friendly format and broadcasts.
        """
        try:
            # Map kernel event types to frontend event types
            frontend_event = self._translate_event(event)
            if frontend_event:
                # Broadcast to connected WebSocket clients
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(
                        self._ws_manager.broadcast(
                            frontend_event["type"],
                            frontend_event["data"],
                        )
                    )
                except RuntimeError:
                    # No running event loop - skip broadcast
                    self._logger.debug(
                        "event_bridge_no_loop",
                        event_type=event.event_type,
                    )
        except Exception as e:
            self._logger.error(
                "event_bridge_error",
                event_type=event.event_type,
                error=str(e),
            )

    def _translate_event(self, event: KernelEvent) -> Optional[Dict[str, Any]]:
        """Translate kernel event to frontend event format.

        Returns None if event should not be forwarded.
        """
        event_type = event.event_type
        data = event.data

        # Process lifecycle events
        if event_type == "process.created":
            return {
                "type": "orchestrator.started",
                "data": {
                    "request_id": data.get("request_id"),
                    "pid": event.pid,
                },
            }

        elif event_type == "process.state_changed":
            new_state = data.get("new_state")

            # Map to frontend-friendly names
            if new_state == "TERMINATED":
                return {
                    "type": "orchestrator.completed",
                    "data": {
                        "request_id": event.pid,
                        "status": "completed",
                    },
                }
            elif new_state == "WAITING":
                # Check if it's clarification or confirmation
                return None  # interrupt.raised will handle this

        elif event_type == "interrupt.raised":
            interrupt_type = data.get("interrupt_type")

            if interrupt_type == InterruptKind.CLARIFICATION.value:
                return {
                    "type": "orchestrator.clarification",
                    "data": {
                        "request_id": event.pid,
                        "clarification_question": data.get("question"),
                        "thread_id": event.pid,
                    },
                }

            elif interrupt_type == InterruptKind.CONFIRMATION.value:
                return {
                    "type": "orchestrator.confirmation",
                    "data": {
                        "request_id": event.pid,
                        "confirmation_message": data.get("message"),
                        "confirmation_id": data.get("confirmation_id"),
                    },
                }

            elif interrupt_type == InterruptKind.RESOURCE_EXHAUSTED.value:
                return {
                    "type": "orchestrator.resource_exhausted",
                    "data": {
                        "request_id": event.pid,
                        "reason": data.get("reason"),
                    },
                }

        elif event_type == "resource.exhausted":
            return {
                "type": "orchestrator.resource_exhausted",
                "data": {
                    "request_id": event.pid,
                    "resource": data.get("resource"),
                    "usage": data.get("usage"),
                    "quota": data.get("quota"),
                },
            }

        elif event_type == "process.cancelled":
            return {
                "type": "orchestrator.cancelled",
                "data": {
                    "request_id": event.pid,
                    "reason": data.get("reason"),
                },
            }

        # Default: don't forward internal kernel events
        return None


__all__ = ["EventBridge", "KernelEvent"]
