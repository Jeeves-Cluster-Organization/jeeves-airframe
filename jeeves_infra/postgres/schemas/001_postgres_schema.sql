-- =====================================================================
-- CODE ANALYSIS AGENT - POSTGRESQL SCHEMA WITH PGVECTOR
-- =====================================================================
-- Schema for Code Analysis Agent v3.0
-- Dependencies: PostgreSQL 14+, pgvector extension
--
-- Constitution v3.0 Compliance:
--   REMOVED: tasks, journal_entries, kv_store, open_loops tables
--   These features were permanently deleted in the v3.0 pivot.
-- =====================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";  -- UUID generation
CREATE EXTENSION IF NOT EXISTS vector;       -- pgvector for embeddings

-- =====================================================================
-- CORE TABLES
-- =====================================================================

-- User sessions
CREATE TABLE IF NOT EXISTS sessions (
    session_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_activity TIMESTAMPTZ DEFAULT NOW(),
    title TEXT,
    deleted_at TIMESTAMPTZ,
    archived_at TIMESTAMPTZ,
    message_count INTEGER DEFAULT 0
);

-- All user requests (Agent 1: Perception)
CREATE TABLE IF NOT EXISTS requests (
    request_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT NOT NULL,
    session_id UUID NOT NULL,
    user_message TEXT NOT NULL,
    received_at TIMESTAMPTZ DEFAULT NOW(),
    status TEXT DEFAULT 'pending',  -- pending, processing, completed, failed
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

-- Execution plans (Agent 2: Intent → Agent 3: Planner)
CREATE TABLE IF NOT EXISTS execution_plans (
    plan_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    request_id UUID NOT NULL,
    intent TEXT NOT NULL,
    confidence REAL NOT NULL,
    requires_context BOOLEAN DEFAULT FALSE,
    context_query TEXT,
    clarification_needed BOOLEAN DEFAULT FALSE,
    clarification_question TEXT,
    plan_json JSONB NOT NULL,  -- Use JSONB for better query performance
    created_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (request_id) REFERENCES requests(request_id) ON DELETE CASCADE
);

-- Tool executions (Agent 4: Traverser)
CREATE TABLE IF NOT EXISTS tool_executions (
    execution_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    request_id UUID NOT NULL,
    plan_id UUID NOT NULL,
    tool_index INTEGER NOT NULL,
    tool_name TEXT NOT NULL,
    parameters JSONB NOT NULL,
    status TEXT NOT NULL,  -- success, error
    result_data JSONB,
    error_details JSONB,
    execution_time_ms INTEGER,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    executed_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (request_id) REFERENCES requests(request_id) ON DELETE CASCADE,
    FOREIGN KEY (plan_id) REFERENCES execution_plans(plan_id) ON DELETE CASCADE
);

-- Responses (Agent 5: Critic → Agent 6: Integration)
CREATE TABLE IF NOT EXISTS responses (
    response_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    request_id UUID NOT NULL,
    plan_id UUID NOT NULL,
    response_text TEXT NOT NULL,
    generated_at TIMESTAMPTZ DEFAULT NOW(),
    validation_status TEXT DEFAULT 'pending',  -- pending, approved, rejected
    validation_report JSONB,
    validated_at TIMESTAMPTZ,
    FOREIGN KEY (request_id) REFERENCES requests(request_id) ON DELETE CASCADE,
    FOREIGN KEY (plan_id) REFERENCES execution_plans(plan_id) ON DELETE CASCADE
);

-- Memory context retrievals
CREATE TABLE IF NOT EXISTS memory_retrievals (
    retrieval_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    request_id UUID NOT NULL,
    context_query TEXT NOT NULL,
    structured_facts JSONB,
    rag_results JSONB,
    retrieved_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (request_id) REFERENCES requests(request_id) ON DELETE CASCADE
);

-- Knowledge facts with embeddings
CREATE TABLE IF NOT EXISTS knowledge_facts (
    fact_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT NOT NULL,
    domain TEXT NOT NULL,  -- preferences, habits, constraints
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    source_request_id UUID,
    embedding vector(384),  -- pgvector column for semantic search
    UNIQUE(user_id, domain, key),
    FOREIGN KEY (source_request_id) REFERENCES requests(request_id) ON DELETE SET NULL
);

-- Response corrections
CREATE TABLE IF NOT EXISTS response_corrections (
    correction_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    response_id UUID NOT NULL,
    request_id UUID NOT NULL,
    original_response TEXT NOT NULL,
    corrected_response TEXT NOT NULL,
    issues_json JSONB NOT NULL,
    sent_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (response_id) REFERENCES responses(response_id) ON DELETE CASCADE,
    FOREIGN KEY (request_id) REFERENCES requests(request_id) ON DELETE CASCADE
);

-- =====================================================================
-- DATA TABLES WITH VECTOR SUPPORT
-- =====================================================================

-- Memory index for unified memory system
CREATE TABLE IF NOT EXISTS memory_index (
    item_id TEXT PRIMARY KEY,
    item_type TEXT NOT NULL,  -- fact, message, code_chunk
    user_id TEXT NOT NULL,
    content_summary TEXT,  -- First 200 chars of content
    has_embedding INTEGER DEFAULT 0,  -- 1 if vector embedding exists
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_memory_index_user ON memory_index(user_id);
CREATE INDEX IF NOT EXISTS idx_memory_index_type ON memory_index(item_type);

-- Memory cross-references for linking related items
CREATE TABLE IF NOT EXISTS memory_cross_refs (
    ref_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_id TEXT NOT NULL,
    source_type TEXT NOT NULL,  -- message, fact, code_chunk
    target_id TEXT NOT NULL,
    target_type TEXT NOT NULL,  -- message, fact, code_chunk
    relationship TEXT DEFAULT 'references',
    confidence REAL DEFAULT 1.0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(source_id, target_id, relationship)
);

CREATE INDEX IF NOT EXISTS idx_memory_cross_refs_source ON memory_cross_refs(source_id);
CREATE INDEX IF NOT EXISTS idx_memory_cross_refs_target ON memory_cross_refs(target_id);
CREATE INDEX IF NOT EXISTS idx_memory_cross_refs_source_type ON memory_cross_refs(source_type);
CREATE INDEX IF NOT EXISTS idx_memory_cross_refs_target_type ON memory_cross_refs(target_type);

-- Conversation messages with embeddings
CREATE TABLE IF NOT EXISTS messages (
    message_id SERIAL PRIMARY KEY,
    session_id UUID NOT NULL,
    role TEXT NOT NULL,  -- user, assistant, system
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,
    edited_at TIMESTAMPTZ,
    original_content TEXT,
    embedding vector(384),  -- pgvector column for semantic conversation search
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

-- Agent scratchpads for internal state
CREATE TABLE IF NOT EXISTS agent_scratchpads (
    agent_id TEXT NOT NULL,
    session_id UUID NOT NULL,
    content TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (agent_id, session_id)
);

-- Intent macros for fast-path NLP
CREATE TABLE IF NOT EXISTS intent_macros (
    macro_id SERIAL PRIMARY KEY,
    pattern TEXT NOT NULL UNIQUE,
    action_json JSONB NOT NULL,
    examples_json JSONB,
    synonyms_json JSONB
);

-- NOTE: pending_confirmations table has been removed.
-- All interrupt handling now uses the unified flow_interrupts table
-- defined in 002_unified_interrupts.sql

-- =====================================================================
-- VECTOR SIMILARITY SEARCH INDEXES (pgvector)
-- =====================================================================

-- Knowledge facts vector index (for semantic fact retrieval)
CREATE INDEX IF NOT EXISTS idx_knowledge_facts_embedding_cosine
ON knowledge_facts USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Messages vector index (for semantic conversation search)
CREATE INDEX IF NOT EXISTS idx_messages_embedding_cosine
ON messages USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- =====================================================================
-- STANDARD B-TREE INDEXES FOR PERFORMANCE
-- =====================================================================

-- Sessions
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_last_activity ON sessions(last_activity);

-- Requests
CREATE INDEX IF NOT EXISTS idx_requests_user_session ON requests(user_id, session_id);
CREATE INDEX IF NOT EXISTS idx_requests_status ON requests(status);
CREATE INDEX IF NOT EXISTS idx_requests_received_at ON requests(received_at);

-- Execution plans
CREATE INDEX IF NOT EXISTS idx_execution_plans_request ON execution_plans(request_id);
CREATE INDEX IF NOT EXISTS idx_execution_plans_created_at ON execution_plans(created_at);

-- Tool executions
CREATE INDEX IF NOT EXISTS idx_tool_executions_request ON tool_executions(request_id);
CREATE INDEX IF NOT EXISTS idx_tool_executions_plan ON tool_executions(plan_id);
CREATE INDEX IF NOT EXISTS idx_tool_executions_status ON tool_executions(status);

-- Responses
CREATE INDEX IF NOT EXISTS idx_responses_request ON responses(request_id);
CREATE INDEX IF NOT EXISTS idx_responses_validation_status ON responses(validation_status);

-- Knowledge facts
CREATE INDEX IF NOT EXISTS idx_knowledge_facts_user_domain ON knowledge_facts(user_id, domain);
CREATE INDEX IF NOT EXISTS idx_knowledge_facts_last_updated ON knowledge_facts(last_updated);

-- Response corrections
CREATE INDEX IF NOT EXISTS idx_corrections_response ON response_corrections(response_id);
CREATE INDEX IF NOT EXISTS idx_corrections_request ON response_corrections(request_id);

-- Messages
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);
CREATE INDEX IF NOT EXISTS idx_messages_role ON messages(role);

-- NOTE: pending_confirmations indexes removed - see 002_unified_interrupts.sql

-- =====================================================================
-- TRIGGERS FOR AUTO-UPDATING TIMESTAMPS
-- =====================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply trigger to sessions table (for last_activity)
CREATE OR REPLACE FUNCTION update_session_last_activity()
RETURNS TRIGGER AS $$
BEGIN
    NEW.last_activity = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_sessions_last_activity ON sessions;
CREATE TRIGGER update_sessions_last_activity
    BEFORE UPDATE ON sessions
    FOR EACH ROW
    EXECUTE FUNCTION update_session_last_activity();

-- =====================================================================
-- HELPER FUNCTIONS FOR VECTOR SEARCH
-- =====================================================================

-- Function to search knowledge facts by semantic similarity
CREATE OR REPLACE FUNCTION search_facts_by_embedding(
    query_embedding vector(384),
    user_filter TEXT DEFAULT NULL,
    domain_filter TEXT DEFAULT NULL,
    result_limit INTEGER DEFAULT 10,
    min_similarity REAL DEFAULT 0.7
)
RETURNS TABLE (
    fact_id UUID,
    domain TEXT,
    key TEXT,
    value TEXT,
    confidence REAL,
    similarity REAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        k.fact_id,
        k.domain,
        k.key,
        k.value,
        k.confidence,
        (1 - (k.embedding <=> query_embedding))::REAL AS similarity
    FROM knowledge_facts k
    WHERE
        k.embedding IS NOT NULL
        AND (user_filter IS NULL OR k.user_id = user_filter)
        AND (domain_filter IS NULL OR k.domain = domain_filter)
        AND (1 - (k.embedding <=> query_embedding)) >= min_similarity
    ORDER BY k.embedding <=> query_embedding
    LIMIT result_limit;
END;
$$ LANGUAGE plpgsql;

-- =====================================================================
-- COMMENTS FOR DOCUMENTATION
-- =====================================================================

COMMENT ON EXTENSION vector IS 'pgvector extension for vector similarity search';
COMMENT ON TABLE knowledge_facts IS 'Knowledge facts with semantic search via embeddings';
COMMENT ON TABLE messages IS 'Conversation messages with semantic search via embeddings';
COMMENT ON FUNCTION search_facts_by_embedding IS 'Semantic search for knowledge facts using cosine similarity';

-- =====================================================================
-- V2 MEMORY INFRASTRUCTURE (L2-L7)
-- =====================================================================

-- =========================
-- L2: Domain Events & Traces
-- =========================
CREATE TABLE IF NOT EXISTS domain_events (
    event_id TEXT PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1,
    payload JSONB NOT NULL DEFAULT '{}',
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

-- ============================================================
-- Memory Contract M2: Enforce Event Immutability
-- ============================================================

CREATE OR REPLACE FUNCTION prevent_event_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Memory Contract M2 violation: domain_events are immutable (no UPDATE/DELETE allowed)';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS enforce_event_immutability_update ON domain_events;
CREATE TRIGGER enforce_event_immutability_update
BEFORE UPDATE ON domain_events
FOR EACH ROW
EXECUTE FUNCTION prevent_event_mutation();

DROP TRIGGER IF EXISTS enforce_event_immutability_delete ON domain_events;
CREATE TRIGGER enforce_event_immutability_delete
BEFORE DELETE ON domain_events
FOR EACH ROW
EXECUTE FUNCTION prevent_event_mutation();

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
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    user_id TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_traces_correlation ON agent_traces(correlation_id);
CREATE INDEX IF NOT EXISTS idx_traces_request ON agent_traces(request_id);
CREATE INDEX IF NOT EXISTS idx_traces_agent ON agent_traces(agent_name);
CREATE INDEX IF NOT EXISTS idx_traces_status ON agent_traces(status);
CREATE INDEX IF NOT EXISTS idx_traces_started_at ON agent_traces(started_at);
CREATE INDEX IF NOT EXISTS idx_traces_user ON agent_traces(user_id);

-- Unified timeline view
DROP VIEW IF EXISTS timeline_view;
CREATE VIEW timeline_view AS
SELECT
    e.occurred_at AS timestamp,
    'domain_event' AS entry_type,
    e.event_id AS entry_id,
    e.event_type AS label,
    e.aggregate_type,
    e.aggregate_id,
    e.correlation_id,
    e.user_id,
    e.payload::TEXT AS details
FROM domain_events e
UNION ALL
SELECT
    t.started_at AS timestamp,
    'agent_trace' AS entry_type,
    t.trace_id AS entry_id,
    t.agent_name || ':' || t.stage AS label,
    NULL AS aggregate_type,
    NULL AS aggregate_id,
    t.correlation_id,
    t.user_id,
    '{"status": "' || COALESCE(t.status, '') ||
    '", "latency_ms": ' || COALESCE(CAST(t.latency_ms AS TEXT), 'null') ||
    ', "confidence": ' || COALESCE(CAST(t.confidence AS TEXT), 'null') ||
    ', "llm_model": "' || COALESCE(t.llm_model, '') || '"}' AS details
FROM agent_traces t;

CREATE TABLE IF NOT EXISTS event_type_registry (
    event_type TEXT PRIMARY KEY,
    aggregate_type TEXT NOT NULL,
    description TEXT,
    payload_schema TEXT,
    introduced_version TEXT,
    deprecated_version TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Event types for Code Analysis Agent
INSERT INTO event_type_registry (event_type, aggregate_type, description, introduced_version) VALUES
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
    ('code_searched', 'code', 'Code search was performed', '3.0.0')
ON CONFLICT (event_type) DO NOTHING;

-- =========================
-- L3: Semantic Chunks
-- =========================
-- For code analysis: stores code chunks with embeddings
CREATE TABLE IF NOT EXISTS semantic_chunks (
    chunk_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_type TEXT NOT NULL CHECK (source_type IN ('fact', 'message', 'code')),
    source_id UUID NOT NULL,
    chunk_index INTEGER DEFAULT 0,
    secondary_source_type TEXT,
    secondary_source_id UUID,
    chunk_text TEXT NOT NULL,
    content_hash TEXT NOT NULL DEFAULT '',
    embedding_status TEXT NOT NULL DEFAULT 'pending',
    embedding_model TEXT,
    embedding vector(384),
    vector_store_id TEXT,
    importance REAL DEFAULT 0.5,
    tags TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_id TEXT NOT NULL,
    UNIQUE(source_type, source_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_chunks_source ON semantic_chunks(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_chunks_status ON semantic_chunks(embedding_status);
CREATE INDEX IF NOT EXISTS idx_chunks_user ON semantic_chunks(user_id);
CREATE INDEX IF NOT EXISTS idx_chunks_content_hash ON semantic_chunks(content_hash);
CREATE INDEX IF NOT EXISTS idx_chunks_updated ON semantic_chunks(updated_at);

-- Vector index for semantic chunks
CREATE INDEX IF NOT EXISTS idx_semantic_chunks_embedding_cosine
ON semantic_chunks USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- M1 Contract Enforcement: Trigger to validate source exists on INSERT
CREATE OR REPLACE FUNCTION check_semantic_chunk_source() RETURNS TRIGGER AS $$
DECLARE
    source_exists BOOLEAN;
BEGIN
    CASE NEW.source_type
        WHEN 'fact' THEN
            SELECT EXISTS(SELECT 1 FROM knowledge_facts WHERE fact_id = NEW.source_id) INTO source_exists;
        WHEN 'message' THEN
            SELECT EXISTS(SELECT 1 FROM messages WHERE message_id = NEW.source_id::INTEGER) INTO source_exists;
        WHEN 'code' THEN
            -- Code chunks can exist without FK validation (external files)
            source_exists := TRUE;
        ELSE
            RAISE EXCEPTION 'Invalid source_type: %', NEW.source_type;
    END CASE;

    IF NOT source_exists THEN
        RAISE EXCEPTION 'Foreign key constraint violation: source_id % does not exist in % table',
            NEW.source_id, NEW.source_type
            USING ERRCODE = '23503';  -- foreign_key_violation
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_check_semantic_chunk_source ON semantic_chunks;
CREATE TRIGGER trg_check_semantic_chunk_source
    BEFORE INSERT OR UPDATE ON semantic_chunks
    FOR EACH ROW EXECUTE FUNCTION check_semantic_chunk_source();

-- Cascade for knowledge_facts
CREATE OR REPLACE FUNCTION cascade_delete_fact_chunks() RETURNS TRIGGER AS $$
BEGIN
    DELETE FROM semantic_chunks
    WHERE source_id = OLD.fact_id AND source_type = 'fact';
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_cascade_delete_fact_chunks ON knowledge_facts;
CREATE TRIGGER trg_cascade_delete_fact_chunks
    BEFORE DELETE ON knowledge_facts
    FOR EACH ROW EXECUTE FUNCTION cascade_delete_fact_chunks();

-- =========================
-- L4: Working Memory
-- =========================
CREATE TABLE IF NOT EXISTS session_state (
    session_id UUID PRIMARY KEY,
    user_id TEXT NOT NULL,
    focus_type TEXT,
    focus_id TEXT,
    focus_context TEXT,
    referenced_entities TEXT,
    short_term_memory TEXT,
    turn_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_session_state_user ON session_state(user_id);

CREATE TABLE IF NOT EXISTS summarization_config (
    config_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    turn_count_threshold INTEGER DEFAULT 8,
    token_budget_threshold INTEGER DEFAULT 6000,
    idle_timeout_minutes INTEGER DEFAULT 30,
    topic_shift_threshold REAL DEFAULT 0.7,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id)
);

INSERT INTO summarization_config (
    config_id, user_id, turn_count_threshold, token_budget_threshold, idle_timeout_minutes, topic_shift_threshold
) VALUES ('default', 'system', 8, 6000, 30, 0.7)
ON CONFLICT (config_id) DO NOTHING;

-- =========================
-- L5: Graph
-- =========================
CREATE TABLE IF NOT EXISTS graph_nodes (
    node_id TEXT PRIMARY KEY,
    node_type TEXT NOT NULL,
    ref_table TEXT,
    ref_id TEXT,
    label TEXT,
    description TEXT,
    user_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_nodes_type ON graph_nodes(node_type);
CREATE INDEX IF NOT EXISTS idx_nodes_ref ON graph_nodes(ref_table, ref_id);
CREATE INDEX IF NOT EXISTS idx_nodes_user ON graph_nodes(user_id);
CREATE INDEX IF NOT EXISTS idx_nodes_label ON graph_nodes(label);

CREATE TABLE IF NOT EXISTS graph_edges (
    edge_id TEXT PRIMARY KEY,
    from_node_id TEXT NOT NULL,
    to_node_id TEXT NOT NULL,
    edge_type TEXT NOT NULL,
    weight REAL DEFAULT 1.0,
    confidence REAL DEFAULT 1.0,
    auto_generated BOOLEAN DEFAULT FALSE,
    source_agent TEXT,
    source_event_id TEXT,
    valid_from TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_until TIMESTAMPTZ,
    metadata_json TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(from_node_id, to_node_id, edge_type, valid_from),
    FOREIGN KEY (from_node_id) REFERENCES graph_nodes(node_id),
    FOREIGN KEY (to_node_id) REFERENCES graph_nodes(node_id)
);

CREATE INDEX IF NOT EXISTS idx_edges_from ON graph_edges(from_node_id);
CREATE INDEX IF NOT EXISTS idx_edges_to ON graph_edges(to_node_id);
CREATE INDEX IF NOT EXISTS idx_edges_type ON graph_edges(edge_type);
CREATE INDEX IF NOT EXISTS idx_edges_valid ON graph_edges(valid_from, valid_until);
CREATE INDEX IF NOT EXISTS idx_edges_auto ON graph_edges(auto_generated);

CREATE TABLE IF NOT EXISTS edge_type_registry (
    edge_type TEXT PRIMARY KEY,
    inverse_type TEXT,
    description TEXT NOT NULL,
    is_symmetric BOOLEAN DEFAULT FALSE,
    transitive BOOLEAN DEFAULT FALSE,
    introduced_version TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Edge types for Code Analysis Agent
INSERT INTO edge_type_registry (edge_type, inverse_type, description, is_symmetric, transitive, introduced_version) VALUES
    ('mentions', 'mentioned_by', 'Text reference (A mentions B)', FALSE, FALSE, '3.0.0'),
    ('mentioned_by', 'mentions', 'Inverse of mentions', FALSE, FALSE, '3.0.0'),
    ('related_to', 'related_to', 'Weak semantic link', TRUE, FALSE, '3.0.0'),
    ('depends_on', 'depended_on_by', 'Code dependency (A imports B)', FALSE, TRUE, '3.0.0'),
    ('depended_on_by', 'depends_on', 'Inverse of depends_on', FALSE, FALSE, '3.0.0'),
    ('calls', 'called_by', 'Function call (A calls B)', FALSE, FALSE, '3.0.0'),
    ('called_by', 'calls', 'Inverse of calls', FALSE, FALSE, '3.0.0'),
    ('defines', 'defined_in', 'Symbol definition (file A defines symbol B)', FALSE, FALSE, '3.0.0'),
    ('defined_in', 'defines', 'Inverse of defines', FALSE, FALSE, '3.0.0'),
    ('references', 'referenced_by', 'Symbol reference (A references B)', FALSE, FALSE, '3.0.0'),
    ('referenced_by', 'references', 'Inverse of references', FALSE, FALSE, '3.0.0'),
    ('parent_of', 'child_of', 'Hierarchy (A contains B)', FALSE, FALSE, '3.0.0'),
    ('child_of', 'parent_of', 'Inverse of parent_of', FALSE, FALSE, '3.0.0')
ON CONFLICT (edge_type) DO NOTHING;

-- =========================
-- L7: Governance/Observability
-- =========================
CREATE TABLE IF NOT EXISTS tool_metrics (
    metric_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tool_name TEXT NOT NULL,
    user_id TEXT NOT NULL,
    session_id UUID,
    request_id UUID,
    status TEXT NOT NULL DEFAULT 'success',
    execution_time_ms INTEGER DEFAULT 0,
    error_type TEXT,
    error_message TEXT,
    parameters_hash TEXT,
    input_size INTEGER DEFAULT 0,
    output_size INTEGER DEFAULT 0,
    metadata TEXT,
    recorded_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tool_metrics_tool_name ON tool_metrics(tool_name);
CREATE INDEX IF NOT EXISTS idx_tool_metrics_status ON tool_metrics(status);
CREATE INDEX IF NOT EXISTS idx_tool_metrics_recorded_at ON tool_metrics(recorded_at);
CREATE INDEX IF NOT EXISTS idx_tool_metrics_tool_time ON tool_metrics(tool_name, recorded_at);

CREATE TABLE IF NOT EXISTS prompt_versions (
    version_id TEXT PRIMARY KEY,
    prompt_name TEXT NOT NULL,
    version INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    content TEXT NOT NULL,
    breaking_change BOOLEAN DEFAULT FALSE,
    change_summary TEXT,
    author TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    traffic_percentage REAL DEFAULT 100.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deprecated_at TIMESTAMPTZ,
    UNIQUE(prompt_name, version)
);

CREATE INDEX IF NOT EXISTS idx_prompts_name ON prompt_versions(prompt_name);
CREATE INDEX IF NOT EXISTS idx_prompts_active ON prompt_versions(prompt_name, is_active);

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
    feedback_incorporated BOOLEAN DEFAULT FALSE,
    incorporated_in_prompt_version TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_evaluations_evaluated ON agent_evaluations(evaluated_agent);
CREATE INDEX IF NOT EXISTS idx_evaluations_evaluator ON agent_evaluations(evaluator_agent);
CREATE INDEX IF NOT EXISTS idx_evaluations_type ON agent_evaluations(evaluation_type);
CREATE INDEX IF NOT EXISTS idx_evaluations_decision ON agent_evaluations(decision);
CREATE INDEX IF NOT EXISTS idx_evaluations_correlation ON agent_evaluations(correlation_id);

CREATE TABLE IF NOT EXISTS governance_policies (
    policy_id TEXT PRIMARY KEY,
    policy_type TEXT NOT NULL,
    config_json TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO governance_policies (policy_id, policy_type, config_json) VALUES
    ('tool_auto_quarantine', 'tool_governance', '{"enabled": true, "min_invocations": 20, "error_rate_threshold": 0.35, "destructive_tools_threshold": 0.20, "quarantine_duration_hours": 24}'),
    ('tool_degraded_mode', 'tool_governance', '{"enabled": true, "error_rate_threshold": 0.15, "actions": ["log_warning", "reduce_priority_in_planner"]}'),
    ('prompt_change_tracking', 'prompt_governance', '{"emit_domain_event": true, "require_change_summary": true, "breaking_change_requires_review": true}')
ON CONFLICT (policy_id) DO NOTHING;

-- =====================================================================
-- NOTE: CLARIFICATION/CONFIRMATION TABLES REMOVED
-- =====================================================================
-- The pending_clarifications and pending_confirmations tables have been
-- replaced by the unified flow_interrupts table. See migration file:
-- 002_unified_interrupts.sql

-- =====================================================================
-- NOTE: Capability-specific tables moved to capability schemas
-- =====================================================================
-- The following tables are owned by capabilities (per Infrastructure R3/R4):
-- - code_index: See jeeves-capability-code-analyser/database/schemas/
-- - code_analysis_events: See jeeves-capability-code-analyser/database/schemas/
--
-- Capabilities register their schemas via CapabilityResourceRegistry.register_schema()

-- =====================================================================
-- WORKFLOW STATE PERSISTENCE (pure Jeeves runtime)
-- =====================================================================

-- Simple state storage for workflow persistence (replaces LangGraph checkpoints)
CREATE TABLE IF NOT EXISTS jeeves_runtime_state (
    thread_id TEXT PRIMARY KEY,
    state_data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_runtime_state_updated
    ON jeeves_runtime_state (updated_at);

COMMENT ON TABLE jeeves_runtime_state IS 'Workflow state persistence for pure Jeeves runtime';
