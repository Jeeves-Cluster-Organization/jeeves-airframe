from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional


class BackendKind(str, Enum):
    LLAMA_SERVER = "llama_server"
    OPENAI_CHAT = "openai_chat"
    ANTHROPIC_MESSAGES = "anthropic_messages"


@dataclass
class CapacityHints:
    max_concurrency: Optional[int] = None
    tier: Optional[str] = None  # e.g., "A100-80GB", "consumer-24GB"


@dataclass
class EndpointSpec:
    name: str
    base_url: str
    backend_kind: BackendKind
    api_type: Optional[str] = None  # e.g., "native", "openai"
    tags: Dict[str, str] = field(default_factory=dict)
    capacity: CapacityHints = field(default_factory=CapacityHints)
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class HealthState:
    status: str  # healthy | degraded | unhealthy | unknown
    checked_at: Optional[float] = None
    detail: Optional[str] = None
