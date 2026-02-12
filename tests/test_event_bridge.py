"""Tests for EventBridge and KernelEventAggregator.

Tests the full event pipeline:
  CommBus event → KernelEventAggregator → EventBridge → WebSocket broadcast
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from jeeves_infra.events.bridge import EventBridge, KernelEvent
from jeeves_infra.events.aggregator import KernelEventAggregator


# =============================================================================
# KernelEvent parsing
# =============================================================================

class TestKernelEvent:
    def test_create_kernel_event(self):
        event = KernelEvent(
            event_type="process.created",
            pid="pid-123",
            data={"request_id": "req-1", "user_id": "user-1"},
        )
        assert event.event_type == "process.created"
        assert event.pid == "pid-123"
        assert event.data["request_id"] == "req-1"


# =============================================================================
# EventBridge translation
# =============================================================================

class TestEventBridgeTranslation:
    """Test EventBridge._translate_event for all kernel event types."""

    def _make_bridge(self):
        aggregator = MagicMock()
        ws_manager = MagicMock()
        logger = MagicMock()
        logger.bind = MagicMock(return_value=logger)
        return EventBridge(aggregator, ws_manager, logger)

    def test_process_created(self):
        bridge = self._make_bridge()
        event = KernelEvent("process.created", "pid-1", {
            "request_id": "req-1", "user_id": "user-1",
        })
        result = bridge._translate_event(event)
        assert result == {
            "type": "orchestrator.started",
            "data": {"request_id": "req-1", "pid": "pid-1"},
        }

    def test_process_terminated(self):
        bridge = self._make_bridge()
        event = KernelEvent("process.state_changed", "pid-1", {
            "old_state": "RUNNING", "new_state": "TERMINATED",
        })
        result = bridge._translate_event(event)
        assert result == {
            "type": "orchestrator.completed",
            "data": {"request_id": "pid-1", "status": "completed"},
        }

    def test_process_waiting_returns_none(self):
        bridge = self._make_bridge()
        event = KernelEvent("process.state_changed", "pid-1", {
            "old_state": "RUNNING", "new_state": "WAITING",
        })
        result = bridge._translate_event(event)
        assert result is None  # interrupt.raised handles WAITING

    def test_resource_exhausted(self):
        bridge = self._make_bridge()
        event = KernelEvent("resource.exhausted", "pid-1", {
            "resource": "llm_calls",
            "usage": {"llm_calls": 10},
            "quota": {"max_llm_calls": 10},
        })
        result = bridge._translate_event(event)
        assert result["type"] == "orchestrator.resource_exhausted"
        assert result["data"]["resource"] == "llm_calls"
        assert result["data"]["usage"] == {"llm_calls": 10}

    def test_process_cancelled(self):
        bridge = self._make_bridge()
        event = KernelEvent("process.cancelled", "pid-1", {
            "reason": "User cancelled",
        })
        result = bridge._translate_event(event)
        assert result == {
            "type": "orchestrator.cancelled",
            "data": {"request_id": "pid-1", "reason": "User cancelled"},
        }

    def test_unknown_event_returns_none(self):
        bridge = self._make_bridge()
        event = KernelEvent("internal.debug", "pid-1", {})
        result = bridge._translate_event(event)
        assert result is None


# =============================================================================
# EventBridge start/stop
# =============================================================================

class TestEventBridgeLifecycle:
    def test_start_subscribes(self):
        aggregator = MagicMock()
        ws_manager = MagicMock()
        logger = MagicMock()
        logger.bind = MagicMock(return_value=logger)

        bridge = EventBridge(aggregator, ws_manager, logger)
        bridge.start()

        aggregator.subscribe.assert_called_once_with("*", bridge._on_kernel_event)
        assert bridge._started

    def test_stop_unsubscribes(self):
        aggregator = MagicMock()
        ws_manager = MagicMock()
        logger = MagicMock()
        logger.bind = MagicMock(return_value=logger)

        bridge = EventBridge(aggregator, ws_manager, logger)
        bridge.start()
        bridge.stop()

        aggregator.unsubscribe.assert_called_once_with("*", bridge._on_kernel_event)
        assert not bridge._started

    def test_start_idempotent(self):
        aggregator = MagicMock()
        ws_manager = MagicMock()
        logger = MagicMock()
        logger.bind = MagicMock(return_value=logger)

        bridge = EventBridge(aggregator, ws_manager, logger)
        bridge.start()
        bridge.start()  # Second call should be no-op

        assert aggregator.subscribe.call_count == 1


# =============================================================================
# KernelEventAggregator
# =============================================================================

class TestKernelEventAggregator:
    def test_subscribe_and_unsubscribe(self):
        client = MagicMock()
        aggregator = KernelEventAggregator(client)

        callback = MagicMock()
        aggregator.subscribe("*", callback)
        assert callback in aggregator._callbacks

        aggregator.unsubscribe("*", callback)
        assert callback not in aggregator._callbacks

    def test_parse_event_valid(self):
        client = MagicMock()
        aggregator = KernelEventAggregator(client)

        chunk = {
            "event_type": "process.created",
            "payload": json.dumps({"pid": "p-1", "request_id": "r-1"}),
            "timestamp_ms": 1234567890,
            "source": "kernel",
        }
        event = aggregator._parse_event(chunk)
        assert event is not None
        assert event.event_type == "process.created"
        assert event.pid == "p-1"
        assert event.data["request_id"] == "r-1"

    def test_parse_event_dict_payload(self):
        client = MagicMock()
        aggregator = KernelEventAggregator(client)

        chunk = {
            "event_type": "process.terminated",
            "payload": {"pid": "p-2"},
        }
        event = aggregator._parse_event(chunk)
        assert event is not None
        assert event.pid == "p-2"

    def test_parse_event_invalid_json(self):
        client = MagicMock()
        aggregator = KernelEventAggregator(client)

        chunk = {
            "event_type": "process.created",
            "payload": "not-json{{{",
        }
        event = aggregator._parse_event(chunk)
        assert event is None

    def test_dispatch_calls_callbacks(self):
        client = MagicMock()
        aggregator = KernelEventAggregator(client)

        callback1 = MagicMock()
        callback2 = MagicMock()
        aggregator.subscribe("*", callback1)
        aggregator.subscribe("*", callback2)

        event = KernelEvent("test.event", "pid-1", {"key": "value"})
        aggregator._dispatch(event)

        callback1.assert_called_once_with(event)
        callback2.assert_called_once_with(event)

    def test_dispatch_handles_callback_error(self):
        client = MagicMock()
        aggregator = KernelEventAggregator(client)

        bad_callback = MagicMock(side_effect=ValueError("boom"))
        good_callback = MagicMock()
        aggregator.subscribe("*", bad_callback)
        aggregator.subscribe("*", good_callback)

        event = KernelEvent("test.event", "pid-1", {})
        aggregator._dispatch(event)

        # good_callback should still be called despite bad_callback error
        good_callback.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_start_and_stop(self):
        client = MagicMock()
        aggregator = KernelEventAggregator(client)

        # Mock subscribe_events to be an empty async generator
        async def empty_stream(*args, **kwargs):
            return
            yield  # Make it a generator

        client.subscribe_events = empty_stream

        await aggregator.start()
        assert aggregator._running
        assert aggregator._task is not None

        await aggregator.stop()
        assert not aggregator._running
