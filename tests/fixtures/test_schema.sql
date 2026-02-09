-- =====================================================================
-- SQLITE TEST SCHEMA
-- =====================================================================
-- Converted from PostgreSQL schemas (001, 002, 003) for test fixtures.
-- All types normalized to SQLite: UUID→TEXT, TIMESTAMPTZ→TEXT,
-- JSONB→TEXT, vector→TEXT, SERIAL→INTEGER PRIMARY KEY AUTOINCREMENT.
-- Triggers ported to SQLite syntax for M1/M2 contract enforcement.
-- =====================================================================

-- =====================================================================
-- CORE TABLES (from 001_postgres_schema.sql)
-- =====================================================================

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    last_activity TEXT DEFAULT CURRENT_TIMESTAMP,
    title TEXT,
    deleted_at TEXT,
    archived_at TEXT,
    message_count INTEGER DEFAULT 0,
    state TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS requests (
    request_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    user_message TEXT NOT NULL,
    received_at TEXT DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'pending',
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS execution_plans (
    plan_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    intent TEXT NOT NULL,
    confidence REAL NOT NULL,
    requires_context INTEGER DEFAULT 0,
    context_query TEXT,
    clarification_needed INTEGER DEFAULT 0,
    clarification_question TEXT,
    plan_json TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (request_id) REFERENCES requests(request_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tool_executions (
    execution_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    plan_id TEXT NOT NULL,
    tool_index INTEGER NOT NULL,
    tool_name TEXT NOT NULL,
    parameters TEXT NOT NULL,
    status TEXT NOT NULL,
    result_data TEXT,
    error_details TEXT,
    execution_time_ms INTEGER,
    started_at TEXT,
    completed_at TEXT,
    executed_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (request_id) REFERENCES requests(request_id) ON DELETE CASCADE,
    FOREIGN KEY (plan_id) REFERENCES execution_plans(plan_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS responses (
    response_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    plan_id TEXT NOT NULL,
    response_text TEXT NOT NULL,
    generated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    validation_status TEXT DEFAULT 'pending',
    validation_report TEXT,
    validated_at TEXT,
    FOREIGN KEY (request_id) REFERENCES requests(request_id) ON DELETE CASCADE,
    FOREIGN KEY (plan_id) REFERENCES execution_plans(plan_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS memory_retrievals (
    retrieval_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    context_query TEXT NOT NULL,
    structured_facts TEXT,
    rag_results TEXT,
    retrieved_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (request_id) REFERENCES requests(request_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS knowledge_facts (
    fact_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    domain TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
    source_request_id TEXT,
    embedding TEXT,
    UNIQUE(user_id, domain, key),
    FOREIGN KEY (source_request_id) REFERENCES requests(request_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS response_corrections (
    correction_id TEXT PRIMARY KEY,
    response_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    original_response TEXT NOT NULL,
    corrected_response TEXT NOT NULL,
    issues_json TEXT NOT NULL,
    sent_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (response_id) REFERENCES responses(response_id) ON DELETE CASCADE,
    FOREIGN KEY (request_id) REFERENCES requests(request_id) ON DELETE CASCADE
);

-- =====================================================================
-- DATA TABLES
-- =====================================================================

CREATE TABLE IF NOT EXISTS memory_index (
    item_id TEXT PRIMARY KEY,
    item_type TEXT NOT NULL,
    user_id TEXT NOT NULL,
    content_summary TEXT,
    has_embedding INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_memory_index_user ON memory_index(user_id);
CREATE INDEX IF NOT EXISTS idx_memory_index_type ON memory_index(item_type);

CREATE TABLE IF NOT EXISTS memory_cross_refs (
    ref_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    target_type TEXT NOT NULL,
    relationship TEXT DEFAULT 'references',
    confidence REAL DEFAULT 1.0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_id, target_id, relationship)
);

CREATE INDEX IF NOT EXISTS idx_memory_cross_refs_source ON memory_cross_refs(source_id);
CREATE INDEX IF NOT EXISTS idx_memory_cross_refs_target ON memory_cross_refs(target_id);

CREATE TABLE IF NOT EXISTS messages (
    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,
    edited_at TEXT,
    original_content TEXT,
    embedding TEXT,
    sources TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS agent_scratchpads (
    agent_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    content TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (agent_id, session_id)
);

CREATE TABLE IF NOT EXISTS intent_macros (
    macro_id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern TEXT NOT NULL UNIQUE,
    action_json TEXT NOT NULL,
    examples_json TEXT,
    synonyms_json TEXT
);

-- =====================================================================
-- L2: DOMAIN EVENTS & TRACES
-- =====================================================================

CREATE TABLE IF NOT EXISTS domain_events (
    event_id TEXT PRIMARY KEY,
    occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1,
    payload TEXT NOT NULL DEFAULT '{}',
    causation_id TEXT,
    correlation_id TEXT,
    idempotency_key TEXT UNIQUE,
    user_id TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT 'system'
);

CREATE INDEX IF NOT EXISTS idx_events_aggregate ON domain_events(aggregate_type, aggregate_id);
CREATE INDEX IF NOT EXISTS idx_events_correlation ON domain_events(correlation_id);
CREATE INDEX IF NOT EXISTS idx_events_occurred_at ON domain_events(occurred_at);
CREATE INDEX IF NOT EXISTS idx_events_user ON domain_events(user_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON domain_events(event_type);

-- M2 Contract: Immutability enforcement
CREATE TRIGGER IF NOT EXISTS enforce_event_immutability_update
BEFORE UPDATE ON domain_events
BEGIN
    SELECT RAISE(ABORT, 'Memory Contract M2 violation: domain_events are immutable (no UPDATE allowed)');
END;

CREATE TRIGGER IF NOT EXISTS enforce_event_immutability_delete
BEFORE DELETE ON domain_events
BEGIN
    SELECT RAISE(ABORT, 'Memory Contract M2 violation: domain_events are immutable (no DELETE allowed)');
END;

CREATE TABLE IF NOT EXISTS agent_traces (
    trace_id TEXT PRIMARY KEY,
    span_id TEXT NOT NULL,
    parent_span_id TEXT,
    agent_name TEXT NOT NULL,
    stage TEXT NOT NULL,
    input_json TEXT,
    output_json TEXT,
    llm_model TEXT,
    llm_provider TEXT,
    prompt_version TEXT,
    latency_ms INTEGER,
    token_count_input INTEGER,
    token_count_output INTEGER,
    confidence REAL,
    status TEXT NOT NULL,
    error_details TEXT,
    correlation_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    user_id TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_traces_correlation ON agent_traces(correlation_id);
CREATE INDEX IF NOT EXISTS idx_traces_request ON agent_traces(request_id);

CREATE TABLE IF NOT EXISTS event_type_registry (
    event_type TEXT PRIMARY KEY,
    aggregate_type TEXT NOT NULL,
    description TEXT,
    payload_schema TEXT,
    introduced_version TEXT,
    deprecated_version TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO event_type_registry (event_type, aggregate_type, description, introduced_version) VALUES
    ('session_started', 'session', 'New conversation session started', '3.0.0'),
    ('session_summarized', 'session', 'Session was summarized for working memory', '3.0.0'),
    ('config_changed', 'config', 'Configuration value was changed', '3.0.0'),
    ('tool_quarantined', 'governance', 'Tool was quarantined due to error rate', '3.0.0'),
    ('tool_restored', 'governance', 'Tool was restored from quarantine', '3.0.0'),
    ('prompt_updated', 'governance', 'Agent prompt was updated', '3.0.0'),
    ('fact_created', 'fact', 'New fact/preference was stored', '3.0.0'),
    ('fact_updated', 'fact', 'Fact/preference was updated', '3.0.0'),
    ('message_created', 'message', 'New message was stored', '3.0.0'),
    ('code_indexed', 'code', 'Code file was indexed for analysis', '3.0.0'),
    ('code_searched', 'code', 'Code search was performed', '3.0.0');

-- =====================================================================
-- L3: SEMANTIC CHUNKS
-- =====================================================================

CREATE TABLE IF NOT EXISTS semantic_chunks (
    chunk_id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL CHECK (source_type IN ('fact', 'message', 'code')),
    source_id TEXT NOT NULL,
    chunk_index INTEGER DEFAULT 0,
    secondary_source_type TEXT,
    secondary_source_id TEXT,
    chunk_text TEXT NOT NULL,
    content_hash TEXT NOT NULL DEFAULT '',
    embedding_status TEXT NOT NULL DEFAULT 'pending',
    embedding_model TEXT,
    embedding TEXT,
    vector_store_id TEXT,
    importance REAL DEFAULT 0.5,
    tags TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_id TEXT NOT NULL,
    UNIQUE(source_type, source_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_chunks_source ON semantic_chunks(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_chunks_status ON semantic_chunks(embedding_status);
CREATE INDEX IF NOT EXISTS idx_chunks_user ON semantic_chunks(user_id);

-- M1 Contract: Source validation trigger
CREATE TRIGGER IF NOT EXISTS trg_check_semantic_chunk_source
BEFORE INSERT ON semantic_chunks
BEGIN
    SELECT CASE
        WHEN NEW.source_type = 'fact' AND NOT EXISTS(
            SELECT 1 FROM knowledge_facts WHERE fact_id = NEW.source_id
        ) THEN RAISE(ABORT, 'Foreign key constraint violation: source_id does not exist in knowledge_facts')
        WHEN NEW.source_type = 'message' AND NOT EXISTS(
            SELECT 1 FROM messages WHERE message_id = CAST(NEW.source_id AS INTEGER)
        ) THEN RAISE(ABORT, 'Foreign key constraint violation: source_id does not exist in messages')
    END;
END;

-- M1 Contract: Cascade delete fact→chunks
CREATE TRIGGER IF NOT EXISTS trg_cascade_delete_fact_chunks
BEFORE DELETE ON knowledge_facts
BEGIN
    DELETE FROM semantic_chunks WHERE source_id = OLD.fact_id AND source_type = 'fact';
END;

-- =====================================================================
-- L4: WORKING MEMORY
-- =====================================================================

CREATE TABLE IF NOT EXISTS session_state (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    focus_type TEXT,
    focus_id TEXT,
    focus_context TEXT,
    referenced_entities TEXT,
    short_term_memory TEXT,
    turn_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS summarization_config (
    config_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    turn_count_threshold INTEGER DEFAULT 8,
    token_budget_threshold INTEGER DEFAULT 6000,
    idle_timeout_minutes INTEGER DEFAULT 30,
    topic_shift_threshold REAL DEFAULT 0.7,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id)
);

INSERT OR IGNORE INTO summarization_config (
    config_id, user_id, turn_count_threshold, token_budget_threshold,
    idle_timeout_minutes, topic_shift_threshold
) VALUES ('default', 'system', 8, 6000, 30, 0.7);

-- =====================================================================
-- L5: GRAPH
-- =====================================================================

CREATE TABLE IF NOT EXISTS graph_nodes (
    node_id TEXT PRIMARY KEY,
    node_type TEXT NOT NULL,
    ref_table TEXT,
    ref_id TEXT,
    label TEXT,
    description TEXT,
    user_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT,
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS graph_edges (
    edge_id TEXT PRIMARY KEY,
    from_node_id TEXT NOT NULL,
    to_node_id TEXT NOT NULL,
    edge_type TEXT NOT NULL,
    weight REAL DEFAULT 1.0,
    confidence REAL DEFAULT 1.0,
    auto_generated INTEGER DEFAULT 0,
    source_agent TEXT,
    source_event_id TEXT,
    valid_from TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_until TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(from_node_id, to_node_id, edge_type, valid_from),
    FOREIGN KEY (from_node_id) REFERENCES graph_nodes(node_id),
    FOREIGN KEY (to_node_id) REFERENCES graph_nodes(node_id)
);

CREATE TABLE IF NOT EXISTS edge_type_registry (
    edge_type TEXT PRIMARY KEY,
    inverse_type TEXT,
    description TEXT NOT NULL,
    is_symmetric INTEGER DEFAULT 0,
    transitive INTEGER DEFAULT 0,
    introduced_version TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO edge_type_registry (edge_type, inverse_type, description, is_symmetric, transitive, introduced_version) VALUES
    ('mentions', 'mentioned_by', 'Text reference (A mentions B)', 0, 0, '3.0.0'),
    ('mentioned_by', 'mentions', 'Inverse of mentions', 0, 0, '3.0.0'),
    ('related_to', 'related_to', 'Weak semantic link', 1, 0, '3.0.0'),
    ('depends_on', 'depended_on_by', 'Code dependency (A imports B)', 0, 1, '3.0.0'),
    ('depended_on_by', 'depends_on', 'Inverse of depends_on', 0, 0, '3.0.0'),
    ('calls', 'called_by', 'Function call (A calls B)', 0, 0, '3.0.0'),
    ('called_by', 'calls', 'Inverse of calls', 0, 0, '3.0.0'),
    ('defines', 'defined_in', 'Symbol definition (file A defines symbol B)', 0, 0, '3.0.0'),
    ('defined_in', 'defines', 'Inverse of defines', 0, 0, '3.0.0'),
    ('references', 'referenced_by', 'Symbol reference (A references B)', 0, 0, '3.0.0'),
    ('referenced_by', 'references', 'Inverse of references', 0, 0, '3.0.0'),
    ('parent_of', 'child_of', 'Hierarchy (A contains B)', 0, 0, '3.0.0'),
    ('child_of', 'parent_of', 'Inverse of parent_of', 0, 0, '3.0.0');

-- =====================================================================
-- L7: GOVERNANCE/OBSERVABILITY
-- =====================================================================

CREATE TABLE IF NOT EXISTS tool_metrics (
    metric_id TEXT PRIMARY KEY,
    tool_name TEXT NOT NULL,
    user_id TEXT NOT NULL,
    session_id TEXT,
    request_id TEXT,
    status TEXT NOT NULL DEFAULT 'success',
    execution_time_ms INTEGER DEFAULT 0,
    error_type TEXT,
    error_message TEXT,
    parameters_hash TEXT,
    input_size INTEGER DEFAULT 0,
    output_size INTEGER DEFAULT 0,
    metadata TEXT,
    recorded_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS prompt_versions (
    version_id TEXT PRIMARY KEY,
    prompt_name TEXT NOT NULL,
    version INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    content TEXT NOT NULL,
    breaking_change INTEGER DEFAULT 0,
    change_summary TEXT,
    author TEXT,
    is_active INTEGER DEFAULT 1,
    traffic_percentage REAL DEFAULT 100.0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deprecated_at TEXT,
    UNIQUE(prompt_name, version)
);

CREATE TABLE IF NOT EXISTS agent_evaluations (
    evaluation_id TEXT PRIMARY KEY,
    evaluator_agent TEXT NOT NULL,
    evaluated_agent TEXT NOT NULL,
    request_id TEXT,
    trace_id TEXT,
    correlation_id TEXT,
    evaluation_type TEXT NOT NULL,
    score REAL,
    decision TEXT,
    issues TEXT,
    feedback TEXT,
    feedback_incorporated INTEGER DEFAULT 0,
    incorporated_in_prompt_version TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS governance_policies (
    policy_id TEXT PRIMARY KEY,
    policy_type TEXT NOT NULL,
    config_json TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO governance_policies (policy_id, policy_type, config_json) VALUES
    ('tool_auto_quarantine', 'tool_governance', '{"enabled": true, "min_invocations": 20, "error_rate_threshold": 0.35, "destructive_tools_threshold": 0.20, "quarantine_duration_hours": 24}'),
    ('tool_degraded_mode', 'tool_governance', '{"enabled": true, "error_rate_threshold": 0.15, "actions": ["log_warning", "reduce_priority_in_planner"]}'),
    ('prompt_change_tracking', 'prompt_governance', '{"emit_domain_event": true, "require_change_summary": true, "breaking_change_requires_review": true}');

-- =====================================================================
-- WORKFLOW STATE (from 001)
-- =====================================================================

CREATE TABLE IF NOT EXISTS jeeves_runtime_state (
    thread_id TEXT PRIMARY KEY,
    state_data TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================================
-- UNIFIED FLOW INTERRUPTS (from 002_unified_interrupts.sql)
-- =====================================================================

CREATE TABLE IF NOT EXISTS flow_interrupts (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    envelope_id TEXT,
    kind TEXT NOT NULL CHECK (kind IN (
        'clarification', 'confirmation', 'agent_review',
        'checkpoint', 'resource_exhausted', 'timeout', 'system_error'
    )),
    question TEXT,
    message TEXT,
    data TEXT DEFAULT '{}',
    response TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending', 'resolved', 'expired', 'cancelled'
    )),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TEXT,
    resolved_at TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    trace_id TEXT,
    span_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_flow_interrupts_request ON flow_interrupts(request_id, status);
CREATE INDEX IF NOT EXISTS idx_flow_interrupts_session ON flow_interrupts(session_id);

-- =====================================================================
-- HELLO WORLD CAPABILITY (from 003_hello_world_schema.sql)
-- =====================================================================

CREATE TABLE IF NOT EXISTS hello_world_events (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_hello_world_events_session ON hello_world_events(session_id);

-- =====================================================================
-- STANDARD INDEXES
-- =====================================================================

CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_requests_user_session ON requests(user_id, session_id);
CREATE INDEX IF NOT EXISTS idx_requests_status ON requests(status);
CREATE INDEX IF NOT EXISTS idx_execution_plans_request ON execution_plans(request_id);
CREATE INDEX IF NOT EXISTS idx_tool_executions_request ON tool_executions(request_id);
CREATE INDEX IF NOT EXISTS idx_tool_executions_plan ON tool_executions(plan_id);
CREATE INDEX IF NOT EXISTS idx_responses_request ON responses(request_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_facts_user_domain ON knowledge_facts(user_id, domain);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);
