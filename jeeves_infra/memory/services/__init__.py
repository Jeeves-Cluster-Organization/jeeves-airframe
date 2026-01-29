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
- Consolidated in jeeves_infra/memory/services/
"""

from jeeves_infra.memory.services.nli_service import NLIService, get_nli_service

# Lazy import: EmbeddingService requires sentence-transformers (1.5GB+ ML dep)
# Import directly when needed: from jeeves_infra.memory.services.embedding_service import EmbeddingService
from jeeves_infra.memory.services.xref_manager import CrossRefManager
from jeeves_infra.memory.services.event_emitter import EventEmitter
from jeeves_infra.memory.services.trace_recorder import TraceRecorder
from jeeves_infra.memory.services.session_state_service import SessionStateService
# SessionStateAdapter removed - depends on capability-specific types not in jeeves_infra
from jeeves_infra.memory.services.chunk_service import ChunkService
from jeeves_infra.memory.services.tool_health_service import ToolHealthService
from jeeves_infra.memory.services.code_indexer import CodeIndexer

__all__ = [
    # Protocol Adapters removed - SessionStateAdapter depends on capability-specific types
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
