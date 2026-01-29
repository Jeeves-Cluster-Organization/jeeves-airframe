-- Migration: Unified Flow Interrupts
-- Description: Replace separate pending_confirmations and pending_clarifications tables
--              with a single unified flow_interrupts table.
-- Breaking Change: This migration drops legacy tables. No backward compatibility.

-- =============================================================================
-- PART 1: Create Unified flow_interrupts Table
-- =============================================================================

CREATE TABLE IF NOT EXISTS flow_interrupts (
    -- Primary key
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Foreign key references
    request_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    envelope_id TEXT,

    -- Interrupt classification
    kind TEXT NOT NULL CHECK (kind IN (
        'clarification',
        'confirmation',
        'agent_review',
        'checkpoint',
        'resource_exhausted',
        'timeout',
        'system_error'
    )),

    -- Interrupt content
    question TEXT,          -- For clarification
    message TEXT,           -- For confirmation
    data JSONB DEFAULT '{}', -- Extensible payload

    -- Response data (NULL until resolved)
    response JSONB,

    -- Status tracking
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending',
        'resolved',
        'expired',
        'cancelled'
    )),

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Tracing context for OpenTelemetry
    trace_id TEXT,
    span_id TEXT
);

-- =============================================================================
-- PART 2: Indexes for Efficient Querying
-- =============================================================================

-- Primary lookup: Find pending interrupts for a request
CREATE INDEX IF NOT EXISTS idx_flow_interrupts_request
    ON flow_interrupts(request_id, status)
    WHERE status = 'pending';

-- Session-based lookup: Find all interrupts in a session
CREATE INDEX IF NOT EXISTS idx_flow_interrupts_session
    ON flow_interrupts(session_id, created_at DESC);

-- User-based lookup: Find pending interrupts for a user
CREATE INDEX IF NOT EXISTS idx_flow_interrupts_user_pending
    ON flow_interrupts(user_id, status)
    WHERE status = 'pending';

-- Kind-based queries: Find interrupts by type
CREATE INDEX IF NOT EXISTS idx_flow_interrupts_kind
    ON flow_interrupts(kind, status);

-- Expiration tracking: Find expired interrupts for cleanup
CREATE INDEX IF NOT EXISTS idx_flow_interrupts_expires
    ON flow_interrupts(expires_at)
    WHERE expires_at IS NOT NULL AND status = 'pending';

-- Tracing correlation: Find interrupts by trace ID
CREATE INDEX IF NOT EXISTS idx_flow_interrupts_trace
    ON flow_interrupts(trace_id)
    WHERE trace_id IS NOT NULL;

-- =============================================================================
-- PART 3: Update Trigger
-- =============================================================================

DROP TRIGGER IF EXISTS update_flow_interrupts_updated_at ON flow_interrupts;
CREATE TRIGGER update_flow_interrupts_updated_at
    BEFORE UPDATE ON flow_interrupts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- PART 4: Table Comment
-- =============================================================================

COMMENT ON TABLE flow_interrupts IS
    'Unified storage for all flow interrupt types (clarification, confirmation, etc.). '
    'Replaces pending_confirmations and pending_clarifications tables.';

COMMENT ON COLUMN flow_interrupts.kind IS
    'Type of interrupt: clarification, confirmation, agent_review, checkpoint, '
    'resource_exhausted, timeout, system_error';

COMMENT ON COLUMN flow_interrupts.data IS
    'Extensible JSONB payload for interrupt-specific data';

COMMENT ON COLUMN flow_interrupts.response IS
    'Response data: {text?, approved?, decision?, data?, received_at}';

-- =============================================================================
-- PART 5: Drop Legacy Tables (BREAKING CHANGE)
-- =============================================================================

-- Drop indexes first
DROP INDEX IF EXISTS idx_pending_confirmations_user;
DROP INDEX IF EXISTS idx_pending_confirmations_expires;
DROP INDEX IF EXISTS idx_pending_confirmations_request;
DROP INDEX IF EXISTS idx_pending_confirmations_status;
DROP INDEX IF EXISTS idx_pending_clarifications_session;
DROP INDEX IF EXISTS idx_pending_clarifications_status;
DROP INDEX IF EXISTS idx_pending_clarifications_created_at;

-- Drop triggers
DROP TRIGGER IF EXISTS update_pending_confirmations_updated_at ON pending_confirmations;
DROP TRIGGER IF EXISTS update_pending_clarifications_updated_at ON pending_clarifications;

-- Drop legacy tables
DROP TABLE IF EXISTS pending_confirmations CASCADE;
DROP TABLE IF EXISTS pending_clarifications CASCADE;
