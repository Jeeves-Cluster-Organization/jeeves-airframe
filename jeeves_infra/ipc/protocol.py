"""Wire protocol for kernel IPC.

Frame format:
    ┌──────────┬──────────┬────────────────────────┐
    │ len (4B) │ type(1B) │   msgpack payload      │
    │ u32 BE   │ u8       │                        │
    └──────────┴──────────┴────────────────────────┘

Length is the size of (type byte + payload), NOT including the 4-byte length prefix.
"""

from __future__ import annotations

import struct
from typing import Any, Dict

import msgpack

# Message type constants
MSG_REQUEST: int = 0x01
MSG_RESPONSE: int = 0x02
MSG_STREAM_CHUNK: int = 0x03
MSG_STREAM_END: int = 0x04
MSG_ERROR: int = 0xFF

# Header sizes
LENGTH_PREFIX_SIZE: int = 4
TYPE_BYTE_SIZE: int = 1
HEADER_SIZE: int = LENGTH_PREFIX_SIZE + TYPE_BYTE_SIZE

# Max frame size (50MB, IPC frame size limit)
MAX_FRAME_SIZE: int = 50 * 1024 * 1024


class IpcError(Exception):
    """IPC protocol error."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


def encode_frame(msg_type: int, payload: Dict[str, Any]) -> bytes:
    """Encode a frame for the wire.

    Args:
        msg_type: Message type byte (MSG_REQUEST, MSG_RESPONSE, etc.)
        payload: Dict to msgpack-encode as the frame body.

    Returns:
        Complete frame bytes (length prefix + type byte + msgpack payload).
    """
    body = msgpack.packb(payload, use_bin_type=True)
    frame_len = TYPE_BYTE_SIZE + len(body)
    return struct.pack(">I", frame_len) + struct.pack("B", msg_type) + body


def decode_frame(data: bytes) -> tuple[int, Dict[str, Any]]:
    """Decode a frame from raw bytes (type byte + payload, no length prefix).

    Args:
        data: Raw bytes AFTER the 4-byte length prefix has been stripped.

    Returns:
        Tuple of (msg_type, decoded payload dict).
    """
    if len(data) < TYPE_BYTE_SIZE:
        raise IpcError("PROTOCOL_ERROR", "Frame too short")
    msg_type = data[0]
    payload = msgpack.unpackb(data[TYPE_BYTE_SIZE:], raw=False)
    return msg_type, payload
