"""
Server-Sent Events (SSE) utilities.

Provides helpers for streaming events to HTTP clients via SSE.
"""

from __future__ import annotations

import json
import asyncio
from typing import Any, AsyncIterator, Dict, Optional


def format_sse_event(
    data: Any,
    event: Optional[str] = None,
    id: Optional[str] = None,
    retry: Optional[int] = None,
) -> str:
    """
    Format data as an SSE event string.

    Args:
        data: Event data (will be JSON-encoded if not a string)
        event: Optional event type name
        id: Optional event ID for client reconnection
        retry: Optional reconnection time in milliseconds

    Returns:
        Formatted SSE event string
    """
    lines = []

    if id is not None:
        lines.append(f"id: {id}")

    if event is not None:
        lines.append(f"event: {event}")

    if retry is not None:
        lines.append(f"retry: {retry}")

    # Serialize data
    if isinstance(data, str):
        data_str = data
    else:
        data_str = json.dumps(data, default=str)

    # SSE requires each line of data to be prefixed with "data: "
    for line in data_str.split("\n"):
        lines.append(f"data: {line}")

    # End with double newline
    return "\n".join(lines) + "\n\n"


def format_sse_comment(comment: str) -> str:
    """Format a comment (for keepalive)."""
    return f": {comment}\n\n"


async def sse_keepalive(
    interval: float = 15.0,
    comment: str = "keepalive",
) -> AsyncIterator[str]:
    """
    Generate keepalive comments at regular intervals.

    Use with asyncio.create_task and merge with data stream.

    Args:
        interval: Seconds between keepalives
        comment: Comment text to send

    Yields:
        SSE comment strings
    """
    while True:
        await asyncio.sleep(interval)
        yield format_sse_comment(comment)


class SSEStream:
    """
    Helper class for building SSE response streams.

    Usage:
        async def event_generator():
            stream = SSEStream()

            # Send initial event
            yield stream.event({"status": "started"}, event="flow_started")

            # Stream data
            async for data in some_async_source:
                yield stream.event(data)

            # Send done signal
            yield stream.done()

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream"
        )
    """

    def __init__(self, include_keepalive: bool = True, keepalive_interval: float = 15.0):
        self._event_id = 0
        self._include_keepalive = include_keepalive
        self._keepalive_interval = keepalive_interval

    def event(
        self,
        data: Any,
        event: Optional[str] = None,
        include_id: bool = True,
    ) -> str:
        """Format an event with auto-incrementing ID."""
        event_id = None
        if include_id:
            self._event_id += 1
            event_id = str(self._event_id)

        return format_sse_event(data, event=event, id=event_id)

    def done(self, data: Optional[Any] = None) -> str:
        """Send a [DONE] marker (OpenAI-style)."""
        if data is not None:
            return self.event(data, event="done") + format_sse_event("[DONE]")
        return format_sse_event("[DONE]")

    def error(self, message: str, code: Optional[str] = None) -> str:
        """Send an error event."""
        data = {"error": message}
        if code:
            data["code"] = code
        return self.event(data, event="error")

    def keepalive(self) -> str:
        """Send a keepalive comment."""
        return format_sse_comment("keepalive")


async def merge_sse_streams(
    data_stream: AsyncIterator[str],
    keepalive_interval: float = 15.0,
) -> AsyncIterator[str]:
    """
    Merge a data stream with keepalive pings.

    Ensures clients don't timeout during long operations.

    Args:
        data_stream: Primary data stream
        keepalive_interval: Seconds between keepalives if no data

    Yields:
        SSE strings from data stream, with keepalives interspersed
    """
    data_queue: asyncio.Queue = asyncio.Queue()
    done = asyncio.Event()

    async def fill_queue():
        try:
            async for item in data_stream:
                await data_queue.put(item)
        finally:
            done.set()

    # Start data producer
    task = asyncio.create_task(fill_queue())

    try:
        while not done.is_set() or not data_queue.empty():
            try:
                # Wait for data with timeout
                item = await asyncio.wait_for(
                    data_queue.get(),
                    timeout=keepalive_interval
                )
                yield item
            except asyncio.TimeoutError:
                # Send keepalive if no data received
                if not done.is_set():
                    yield format_sse_comment("keepalive")
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
