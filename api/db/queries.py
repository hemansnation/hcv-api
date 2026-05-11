import logging

import asyncpg

logger = logging.getLogger(__name__)

_CREATE_API_KEYS = """
CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key_hash VARCHAR(64) NOT NULL UNIQUE,
    client_name VARCHAR(255) NOT NULL,
    client_email VARCHAR(255) NOT NULL,
    tier VARCHAR(20) NOT NULL DEFAULT 'starter',
    monthly_limit INTEGER NOT NULL DEFAULT 1000,
    requests_this_month INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_used_at TIMESTAMPTZ
);
"""

_CREATE_AUDIT_LOG = """
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
"""

# Idempotent: only creates rules if they don't already exist
_CREATE_APPEND_ONLY_RULES = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_rules
        WHERE tablename = 'audit_log' AND rulename = 'no_update_audit'
    ) THEN
        CREATE RULE no_update_audit AS ON UPDATE TO audit_log DO INSTEAD NOTHING;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_rules
        WHERE tablename = 'audit_log' AND rulename = 'no_delete_audit'
    ) THEN
        CREATE RULE no_delete_audit AS ON DELETE TO audit_log DO INSTEAD NOTHING;
    END IF;
END $$;
"""

_CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_audit_request  ON audit_log(request_id);
CREATE INDEX IF NOT EXISTS idx_audit_client   ON audit_log(client_id);
CREATE INDEX IF NOT EXISTS idx_audit_document ON audit_log(document_id);
CREATE INDEX IF NOT EXISTS idx_audit_hash     ON audit_log(audit_hash);
CREATE INDEX IF NOT EXISTS idx_audit_created  ON audit_log(created_at DESC);
"""


async def create_tables(pool: asyncpg.Pool) -> None:
    """Create api_keys and audit_log tables with indexes and append-only rules."""
    async with pool.acquire() as conn:
        await conn.execute(_CREATE_API_KEYS)
        await conn.execute(_CREATE_AUDIT_LOG)
        await conn.execute(_CREATE_APPEND_ONLY_RULES)
        await conn.execute(_CREATE_INDEXES)
    logger.info("Database tables verified/created")
