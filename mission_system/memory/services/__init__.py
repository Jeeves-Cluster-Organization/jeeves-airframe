"""Memory management services.

This module provides infrastructure implementations for Core's memory protocols.
Services here are the "how" - they handle persistence, embedding generation, etc.
Core's protocols define the "what" - the contracts these services must satisfy.

Protocol Implementations:
- SessionStateAdapter: Implements Core's SessionStateProtocol
- EmbeddingService: Infrastructure for semantic search (partial SemanticSearchProtocol)

Infrastructure Services:
- ChunkService: L3 semantic memory chunking
- SessionStateService: L4 session state persistence
- EventEmitter: L2 event log
- TraceRecorder: Agent trace recording
- ToolHealthService: L7 tool metrics
- CodeIndexer: Code indexing for semantic search

Memory Module Audit (2025-12-09):
- Moved from avionics/memory/services/
"""

from mission_system.memory.services.nli_service import NLIService, get_nli_service

# Lazy import: EmbeddingService requires sentence-transformers (1.5GB+ ML dep)
# Import directly when needed: from mission_system.memory.services.embedding_service import EmbeddingService
from mission_system.memory.services.xref_manager import CrossRefManager
from mission_system.memory.services.event_emitter import EventEmitter
from mission_system.memory.services.trace_recorder import TraceRecorder
from mission_system.memory.services.session_state_service import SessionStateService
from mission_system.memory.services.session_state_adapter import SessionStateAdapter
from mission_system.memory.services.chunk_service import ChunkService
from mission_system.memory.services.tool_health_service import ToolHealthService
from mission_system.memory.services.code_indexer import CodeIndexer

__all__ = [
    # Protocol Adapters (implements Core protocols)
    "SessionStateAdapter",
    # Infrastructure Services (EmbeddingService is lazy - import directly when needed)
    "NLIService",
    "get_nli_service",
    "CrossRefManager",
    "EventEmitter",
    "TraceRecorder",
    "SessionStateService",
    "ChunkService",
    "ToolHealthService",
    "CodeIndexer",
]
