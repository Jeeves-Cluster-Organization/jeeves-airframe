"""Async TCP transport for kernel IPC.

Manages a persistent TCP connection with msgpack framing.
"""

from __future__ import annotations

import asyncio
import logging
import struct
import uuid
from typing import Any, AsyncIterator, Dict, Optional

from jeeves_infra.ipc.protocol import (
    MSG_REQUEST,
    MSG_RESPONSE,
    MSG_STREAM_CHUNK,
    MSG_STREAM_END,
    MSG_ERROR,
    LENGTH_PREFIX_SIZE,
    MAX_FRAME_SIZE,
    IpcError,
    encode_frame,
    decode_frame,
)

logger = logging.getLogger(__name__)


class IpcTransport:
    """Async TCP transport with length-prefixed msgpack framing.

    Usage:
        transport = IpcTransport("127.0.0.1", 50051)
        await transport.connect()
        result = await transport.request("kernel", "CreateProcess", {...})
        await transport.close()
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 50051):
        self._host = host
        self._port = port
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._closed = False
        self._lock = asyncio.Lock()
        # Pending request futures keyed by request ID
        self._pending: Dict[str, asyncio.Future] = {}
        # Pending stream queues keyed by request ID
        self._stream_queues: Dict[str, asyncio.Queue] = {}
        self._reader_task: Optional[asyncio.Task] = None

    async def connect(self) -> None:
        """Open TCP connection and start background reader."""
        self._reader, self._writer = await asyncio.open_connection(
            self._host, self._port,
        )
        self._closed = False
        self._reader_task = asyncio.create_task(self._read_loop())
        logger.info("ipc_connected", extra={"host": self._host, "port": self._port})

    async def close(self) -> None:
        """Close the TCP connection."""
        if self._closed:
            return
        self._closed = True
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
        # Fail all pending requests
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(IpcError("UNAVAILABLE", "Connection closed"))
        self._pending.clear()
        for q in self._stream_queues.values():
            await q.put(None)  # Sentinel
        self._stream_queues.clear()
        logger.info("ipc_closed")

    @property
    def connected(self) -> bool:
        return not self._closed and self._writer is not None

    async def request(
        self,
        service: str,
        method: str,
        body: Dict[str, Any],
        *,
        timeout: float = 30.0,
    ) -> Dict[str, Any]:
        """Send a request and wait for a response.

        Args:
            service: Service name (kernel, engine, orchestration, commbus).
            method: Method name (e.g. CreateProcess).
            body: Request payload dict.
            timeout: Timeout in seconds.

        Returns:
            Response body dict.

        Raises:
            IpcError: On protocol/connection errors.
        """
        request_id = str(uuid.uuid4())
        payload = {
            "id": request_id,
            "service": service,
            "method": method,
            "body": body,
        }

        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[request_id] = future

        try:
            await self._send_frame(MSG_REQUEST, payload)
            result = await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(request_id, None)
            raise IpcError("TIMEOUT", f"Request {service}.{method} timed out after {timeout}s")
        except Exception:
            self._pending.pop(request_id, None)
            raise

        if not result.get("ok", False):
            error = result.get("error", {})
            raise IpcError(
                error.get("code", "INTERNAL"),
                error.get("message", "Unknown error"),
            )
        return result.get("body", {})

    async def request_stream(
        self,
        service: str,
        method: str,
        body: Dict[str, Any],
        *,
        timeout: float = 300.0,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Send a request and yield streaming response chunks.

        Args:
            service: Service name.
            method: Method name.
            body: Request payload dict.
            timeout: Total stream timeout in seconds.

        Yields:
            Response chunk dicts.
        """
        request_id = str(uuid.uuid4())
        payload = {
            "id": request_id,
            "service": service,
            "method": method,
            "body": body,
        }

        queue: asyncio.Queue = asyncio.Queue()
        self._stream_queues[request_id] = queue

        try:
            await self._send_frame(MSG_REQUEST, payload)
            deadline = asyncio.get_event_loop().time() + timeout
            while True:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    raise IpcError("TIMEOUT", f"Stream {service}.{method} timed out")
                item = await asyncio.wait_for(queue.get(), timeout=remaining)
                if item is None:
                    # Stream end sentinel
                    break
                if isinstance(item, Exception):
                    raise item
                yield item
        finally:
            self._stream_queues.pop(request_id, None)

    async def _send_frame(self, msg_type: int, payload: Dict[str, Any]) -> None:
        """Encode and send a frame over the wire."""
        if self._closed or self._writer is None:
            raise IpcError("UNAVAILABLE", "Not connected")
        frame = encode_frame(msg_type, payload)
        async with self._lock:
            self._writer.write(frame)
            await self._writer.drain()

    async def _read_loop(self) -> None:
        """Background task that reads frames and dispatches to pending futures/queues."""
        try:
            while not self._closed and self._reader is not None:
                # Read 4-byte length prefix
                length_data = await self._reader.readexactly(LENGTH_PREFIX_SIZE)
                frame_len = struct.unpack(">I", length_data)[0]

                if frame_len > MAX_FRAME_SIZE:
                    logger.error("ipc_frame_too_large", extra={"size": frame_len})
                    break

                # Read the rest of the frame
                frame_data = await self._reader.readexactly(frame_len)
                msg_type, payload = decode_frame(frame_data)

                request_id = payload.get("id", "")

                if msg_type == MSG_RESPONSE:
                    fut = self._pending.pop(request_id, None)
                    if fut and not fut.done():
                        fut.set_result(payload)

                elif msg_type == MSG_STREAM_CHUNK:
                    queue = self._stream_queues.get(request_id)
                    if queue:
                        await queue.put(payload.get("body", {}))

                elif msg_type == MSG_STREAM_END:
                    queue = self._stream_queues.get(request_id)
                    if queue:
                        await queue.put(None)  # Sentinel

                elif msg_type == MSG_ERROR:
                    error = payload.get("error", {})
                    exc = IpcError(
                        error.get("code", "INTERNAL"),
                        error.get("message", "Unknown error"),
                    )
                    # Dispatch to either pending future or stream queue
                    fut = self._pending.pop(request_id, None)
                    if fut and not fut.done():
                        fut.set_exception(exc)
                    queue = self._stream_queues.get(request_id)
                    if queue:
                        await queue.put(exc)

        except asyncio.IncompleteReadError:
            logger.warning("ipc_connection_lost")
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.error("ipc_read_error", extra={"error": str(e)})
        finally:
            # Connection lost — fail all pending
            if not self._closed:
                self._closed = True
                for fut in self._pending.values():
                    if not fut.done():
                        fut.set_exception(IpcError("UNAVAILABLE", "Connection lost"))
                self._pending.clear()
                for q in self._stream_queues.values():
                    await q.put(None)
                self._stream_queues.clear()
