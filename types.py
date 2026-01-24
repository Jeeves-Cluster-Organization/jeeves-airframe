from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ErrorCategory(str, Enum):
    TIMEOUT = "timeout"
    BACKEND = "backend"
    CONNECTION = "connection"
    PARSE = "parse"
    UNKNOWN = "unknown"


class StreamEventType(str, Enum):
    TOKEN = "token"
    MESSAGE = "message"
    TOOL_CALL = "tool_call"
    ERROR = "error"
    DONE = "done"


@dataclass
class AirframeError(Exception):
    category: ErrorCategory
    message: str
    raw_backend: Optional[Any] = None

    def __str__(self) -> str:
        return f"{self.category}: {self.message}"


@dataclass
class Message:
    role: str
    content: str


@dataclass
class ToolSpec:
    name: str
    description: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None


@dataclass
class InferenceRequest:
    messages: List[Message]
    model: Optional[str] = None
    tools: Optional[List[ToolSpec]] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: bool = True
    extra_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class InferenceStreamEvent:
    """
    Stream-first contract:
      - type: token | message | tool_call | error | done
    """
    type: StreamEventType
    content: Optional[str] = None
    raw: Optional[Any] = None
    error: Optional[AirframeError] = None
    finish_reason: Optional[str] = None
    usage: Optional[Dict[str, Any]] = None


@dataclass
class InferenceResult:
    message: Optional[str]
    finish_reason: Optional[str] = None
    usage: Optional[Dict[str, Any]] = None
    raw: Optional[Any] = None
