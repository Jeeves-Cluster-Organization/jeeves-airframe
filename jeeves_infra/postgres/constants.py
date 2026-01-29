"""Database constants for PostgreSQL client.

Centralizes column type definitions to avoid duplication across
insert, update, and query operations.

Constitutional Alignment:
- P1: Single source of truth for column types
- M5: Consistent data handling
"""

from typing import FrozenSet

# ============================================================================
# UUID Columns
# ============================================================================
# Columns that should be treated as UUIDs and converted to strings
# Used for parameter preparation in queries, inserts, and updates

UUID_COLUMNS: FrozenSet[str] = frozenset({
    # Core identifiers (UUID type in schema)
    'session_id',
    'request_id',
    'task_id',
    'entry_id',
    'plan_id',
    'response_id',
    'source_request_id',
    'fact_id',
    # Memory module identifiers (UUID type in schema)
    'chunk_id',
    'metric_id',
    # Loop and session identifiers
    'loop_id',
    'originating_session_id',
    'resolution_session_id',
    # Correlation
    'correlation_id',
    'envelope_id',
    # Note: The following are TEXT, not UUID in schema - do not include:
    # - user_id: TEXT (human-readable user identifiers)
    # - event_id: TEXT (domain event identifiers)
    # - trace_id: TEXT (trace identifiers)
    # - agent_id: TEXT (agent names)
    # - edge_id: TEXT (knowledge graph edge identifiers)
})

# ============================================================================
# JSONB Columns
# ============================================================================
# Columns that should be serialized as JSON for PostgreSQL JSONB storage

JSONB_COLUMNS: FrozenSet[str] = frozenset({
    # Plan and execution data
    'plan_json',
    'execution_plan_json',
    'action_json',
    # Metadata and configuration
    'metadata',
    'metadata_json',
    'config_json',
    'parameters',
    'payload',
    # Results and reports
    'result_data',
    'error_details',
    'validation_report',
    'issues_json',
    # Session state
    'focus_context',
    'referenced_entities',
    'structured_facts',
    'rag_results',
    # Other
    'tags',
    'examples_json',
    'synonyms_json',
})

# ============================================================================
# Vector Columns
# ============================================================================
# Columns that should be cast to pgvector type

VECTOR_COLUMNS: FrozenSet[str] = frozenset({
    'embedding',
})

# ============================================================================
# All Special Columns
# ============================================================================
# Union of all columns that need special handling

SPECIAL_COLUMNS: FrozenSet[str] = UUID_COLUMNS | JSONB_COLUMNS | VECTOR_COLUMNS


__all__ = [
    'UUID_COLUMNS',
    'JSONB_COLUMNS',
    'VECTOR_COLUMNS',
    'SPECIAL_COLUMNS',
]
