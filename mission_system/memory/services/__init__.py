"""Memory management services.

This module provides infrastructure implementations for Core's memory protocols.
Services here are the "how" - they handle persistence, embedding generation, etc.
Core's protocols define the "what" - the contracts these services must satisfy.

Protocol Implementations:
- SessionStateAdapter: Implements Core's SessionStateProtocol

Infrastructure Services:
- ChunkService: L3 semantic memory chunking
- SessionStateService: L4 session state persistence
- EventEmitter: L2 event log
- TraceRecorder: Agent trace recording
- ToolHealthService: L7 tool metrics
EmbeddingService is owned by capabilities (concrete DB concern).
CodeIndexer has moved to jeeves_capability_hello_world.database.services.code_indexer.
"""

from mission_system.memory.services.xref_manager import CrossRefManager
from mission_system.memory.services.event_emitter import EventEmitter
from mission_system.memory.services.trace_recorder import TraceRecorder
from mission_system.memory.services.session_state_service import SessionStateService
from mission_system.memory.services.session_state_adapter import SessionStateAdapter
from mission_system.memory.services.chunk_service import ChunkService
from mission_system.memory.services.tool_health_service import ToolHealthService

__all__ = [
    # Protocol Adapters (implements Core protocols)
    "SessionStateAdapter",
    # Infrastructure Services
    "CrossRefManager",
    "EventEmitter",
    "TraceRecorder",
    "SessionStateService",
    "ChunkService",
    "ToolHealthService",
]
