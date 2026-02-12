"""KernelEventAggregator - Streams kernel lifecycle events via CommBus.

Replaces the phantom EventAggregator dependency in EventBridge.
Connects to the Rust kernel's CommBus via IPC streaming and dispatches
events to registered callbacks.

Architecture:
    Kernel CommBus (Rust)
           | IPC Subscribe (streaming)
    KernelEventAggregator (this module)
           | callback dispatch
    EventBridge → WebSocketEventManager → Frontend
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from jeeves_infra.events.bridge import KernelEvent

if TYPE_CHECKING:
    from jeeves_infra.kernel_client import KernelClient

logger = logging.getLogger(__name__)

# Event types the kernel emits (from ipc/handlers/kernel.rs)
LIFECYCLE_EVENT_TYPES = [
    "process.created",
    "process.state_changed",
    "process.terminated",
    "resource.exhausted",
    "interrupt.raised",
    "process.cancelled",
]


class KernelEventAggregator:
    """Aggregates kernel lifecycle events from CommBus for downstream consumers.

    Subscribes to the Rust kernel's CommBus via IPC streaming and dispatches
    KernelEvent instances to registered callbacks.

    Usage:
        aggregator = KernelEventAggregator(kernel_client)
        aggregator.subscribe("*", on_event)
        await aggregator.start()
        ...
        await aggregator.stop()
    """

    def __init__(
        self,
        kernel_client: "KernelClient",
        event_types: Optional[List[str]] = None,
        reconnect_delay: float = 2.0,
        max_reconnect_delay: float = 60.0,
    ) -> None:
        self._client = kernel_client
        self._event_types = event_types or LIFECYCLE_EVENT_TYPES
        self._reconnect_delay = reconnect_delay
        self._max_reconnect_delay = max_reconnect_delay
        self._callbacks: List[Callable[[KernelEvent], None]] = []
        self._task: Optional[asyncio.Task] = None
        self._running = False

    def subscribe(self, pattern: str, callback: Callable[[KernelEvent], None]) -> None:
        """Register a callback for kernel events.

        Args:
            pattern: Event pattern (currently only "*" is supported).
            callback: Function to call with each KernelEvent.
        """
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def unsubscribe(self, pattern: str, callback: Callable[[KernelEvent], None]) -> None:
        """Unregister a callback."""
        try:
            self._callbacks.remove(callback)
        except ValueError:
            pass

    async def start(self) -> None:
        """Start the background event subscription loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("kernel_event_aggregator_started", extra={
            "event_types": self._event_types,
        })

    async def stop(self) -> None:
        """Stop the background event subscription loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("kernel_event_aggregator_stopped")

    async def _run_loop(self) -> None:
        """Main loop: subscribe to CommBus, dispatch events, reconnect on failure."""
        delay = self._reconnect_delay

        while self._running:
            try:
                async for chunk in self._client.subscribe_events(
                    event_types=self._event_types,
                    subscriber_id="event-bridge",
                ):
                    if not self._running:
                        break

                    event = self._parse_event(chunk)
                    if event:
                        self._dispatch(event)

                # Stream ended normally (kernel shutdown)
                if self._running:
                    logger.warning("kernel_event_stream_ended")

            except asyncio.CancelledError:
                break
            except Exception as e:
                if not self._running:
                    break
                logger.warning(
                    "kernel_event_stream_error",
                    extra={"error": str(e), "reconnect_delay": delay},
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, self._max_reconnect_delay)
                continue

            # Reset delay on clean stream end
            delay = self._reconnect_delay

    def _parse_event(self, chunk: Dict[str, Any]) -> Optional[KernelEvent]:
        """Parse a CommBus stream chunk into a KernelEvent."""
        try:
            event_type = chunk.get("event_type", "")
            payload_str = chunk.get("payload", "{}")

            if isinstance(payload_str, str):
                data = json.loads(payload_str)
            elif isinstance(payload_str, dict):
                data = payload_str
            else:
                data = {}

            pid = data.get("pid", "")
            return KernelEvent(event_type=event_type, pid=pid, data=data)
        except (json.JSONDecodeError, TypeError) as e:
            logger.debug("kernel_event_parse_error", extra={
                "error": str(e), "chunk": str(chunk)[:200],
            })
            return None

    def _dispatch(self, event: KernelEvent) -> None:
        """Dispatch event to all registered callbacks."""
        for callback in self._callbacks:
            try:
                callback(event)
            except Exception as e:
                logger.error(
                    "kernel_event_callback_error",
                    extra={"error": str(e), "event_type": event.event_type},
                )


__all__ = ["KernelEventAggregator", "LIFECYCLE_EVENT_TYPES"]
