-- Initial schema: api_keys and audit_log tables
-- Source of truth: docs/architecture.md

CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key_hash VARCHAR(64) NOT NULL UNIQUE,  -- SHA-256 of the actual key
    client_name VARCHAR(255) NOT NULL,
    client_email VARCHAR(255) NOT NULL,
    tier VARCHAR(20) NOT NULL DEFAULT 'starter',  -- starter | professional | enterprise
    monthly_limit INTEGER NOT NULL DEFAULT 1000,
    requests_this_month INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_used_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    request_id UUID NOT NULL,
    client_id UUID NOT NULL REFERENCES api_keys(id),
    document_id VARCHAR(500),
    citation_raw TEXT NOT NULL,
    citation_normalized TEXT,
    sources_checked TEXT[] NOT NULL,
    found_in TEXT[],
    exists BOOLEAN NOT NULL,
    confidence_score NUMERIC(5,4),
    argument_flag VARCHAR(10),
    result_json JSONB NOT NULL,
    audit_hash VARCHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Make audit_log append-only via rules
CREATE RULE no_update_audit AS ON UPDATE TO audit_log DO INSTEAD NOTHING;
CREATE RULE no_delete_audit AS ON DELETE TO audit_log DO INSTEAD NOTHING;

-- Indexes for fast retrieval
CREATE INDEX IF NOT EXISTS idx_audit_request  ON audit_log(request_id);
CREATE INDEX IF NOT EXISTS idx_audit_client   ON audit_log(client_id);
CREATE INDEX IF NOT EXISTS idx_audit_document ON audit_log(document_id);
CREATE INDEX IF NOT EXISTS idx_audit_hash     ON audit_log(audit_hash);
CREATE INDEX IF NOT EXISTS idx_audit_created  ON audit_log(created_at DESC);
