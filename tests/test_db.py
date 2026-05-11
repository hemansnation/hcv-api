"""Database layer tests — connection, schema, and append-only enforcement."""
import uuid

import asyncpg
import pytest


@pytest.fixture
async def test_api_key(pool: asyncpg.Pool):
    """Insert a throwaway API key and clean up after the test."""
    async with pool.acquire() as conn:
        key_id = await conn.fetchval(
            "INSERT INTO api_keys (key_hash, client_name, client_email) "
            "VALUES ($1, 'Test Client', 'test@test.com') RETURNING id",
            f"test_hash_{uuid.uuid4().hex}",
        )
    yield key_id
    async with pool.acquire() as conn:
        # TRUNCATE bypasses the no_delete_audit rule; must run before deleting the key
        await conn.execute("TRUNCATE TABLE audit_log")
        await conn.execute("DELETE FROM api_keys WHERE id = $1", key_id)


async def _insert_audit_row(conn: asyncpg.Connection, client_id: uuid.UUID, citation: str) -> int:
    return await conn.fetchval(
        "INSERT INTO audit_log "
        "(request_id, client_id, citation_raw, sources_checked, exists, result_json, audit_hash) "
        "VALUES (gen_random_uuid(), $1, $2, ARRAY['courtlistener'], true, '{}'::jsonb, $3) "
        "RETURNING id",
        client_id,
        citation,
        f"hash_{uuid.uuid4().hex}",
    )


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

async def test_db_connection(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        result = await conn.fetchval("SELECT 1")
    assert result == 1


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

async def test_api_keys_table_exists(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'api_keys')"
        )
    assert exists is True


async def test_audit_log_table_exists(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'audit_log')"
        )
    assert exists is True


# ---------------------------------------------------------------------------
# Append-only enforcement
# ---------------------------------------------------------------------------

async def test_audit_log_update_blocked(pool: asyncpg.Pool, test_api_key: uuid.UUID) -> None:
    """UPDATE on audit_log must silently do nothing (rule: no_update_audit)."""
    async with pool.acquire() as conn:
        audit_id = await _insert_audit_row(conn, test_api_key, "531 U.S. 98")
        await conn.execute(
            "UPDATE audit_log SET citation_raw = 'MODIFIED' WHERE id = $1", audit_id
        )
        stored = await conn.fetchval("SELECT citation_raw FROM audit_log WHERE id = $1", audit_id)
    assert stored == "531 U.S. 98"


async def test_audit_log_delete_blocked(pool: asyncpg.Pool, test_api_key: uuid.UUID) -> None:
    """DELETE on audit_log must silently do nothing (rule: no_delete_audit)."""
    async with pool.acquire() as conn:
        audit_id = await _insert_audit_row(conn, test_api_key, "576 U.S. 644")
        await conn.execute("DELETE FROM audit_log WHERE id = $1", audit_id)
        row_exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM audit_log WHERE id = $1)", audit_id
        )
    assert row_exists is True
