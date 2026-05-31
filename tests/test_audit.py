"""Audit trail tests — hashing determinism and database round-trips."""

import uuid

import asyncpg
import pytest

from api.db.audit import (get_audit_record, get_document_audit,
                          log_citation_verification)
from api.utils.hashing import generate_document_hash, generate_record_hash

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def test_api_key(pool: asyncpg.Pool):
    async with pool.acquire() as conn:
        key_id = await conn.fetchval(
            "INSERT INTO api_keys (key_hash, client_name, client_email) "
            "VALUES ($1, 'Audit Test Client', 'audittest@test.com') RETURNING id",
            f"audit_test_{uuid.uuid4().hex}",
        )
    yield key_id
    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE TABLE audit_log")
        await conn.execute("DELETE FROM api_keys WHERE id = $1", key_id)


async def _log(pool: asyncpg.Pool, client_id: uuid.UUID, **overrides) -> str:
    defaults = dict(
        request_id=str(uuid.uuid4()),
        client_id=str(client_id),
        document_id="doc-test",
        citation_raw="531 U.S. 98",
        citation_normalized="531 U.S. 98 (2000)",
        verification_result={
            "sources_checked": ["courtlistener"],
            "found_in": ["courtlistener"],
            "exists": True,
        },
        confidence_score=0.97,
    )
    defaults.update(overrides)
    return await log_citation_verification(pool, **defaults)


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------


def test_hash_is_deterministic() -> None:
    record = {"citation": "531 U.S. 98", "exists": True, "confidence": 0.97}
    assert generate_record_hash(record) == generate_record_hash(record)


def test_hash_changes_with_content() -> None:
    record = {"citation": "531 U.S. 98", "exists": True}
    modified = {**record, "citation": "531 U.S. 99"}
    assert generate_record_hash(record) != generate_record_hash(modified)


def test_document_hash_is_deterministic() -> None:
    hashes = ["aaa", "bbb", "ccc"]
    assert generate_document_hash(hashes) == generate_document_hash(hashes)


def test_document_hash_is_order_independent() -> None:
    assert generate_document_hash(["aaa", "bbb"]) == generate_document_hash(
        ["bbb", "aaa"]
    )


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


async def test_log_creates_record(pool: asyncpg.Pool, test_api_key: uuid.UUID) -> None:
    audit_hash = await _log(pool, test_api_key)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT audit_hash FROM audit_log WHERE audit_hash = $1", audit_hash
        )
    assert row is not None
    assert row["audit_hash"] == audit_hash


async def test_append_only(pool: asyncpg.Pool, test_api_key: uuid.UUID) -> None:
    """UPDATE on audit_log must be silently blocked by the no_update_audit rule."""
    audit_hash = await _log(pool, test_api_key, citation_raw="576 U.S. 644")
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE audit_log SET citation_raw = 'MODIFIED' WHERE audit_hash = $1",
            audit_hash,
        )
        stored = await conn.fetchval(
            "SELECT citation_raw FROM audit_log WHERE audit_hash = $1", audit_hash
        )
    assert stored == "576 U.S. 644"


async def test_retrieve_by_hash(pool: asyncpg.Pool, test_api_key: uuid.UUID) -> None:
    audit_hash = await _log(
        pool, test_api_key, citation_raw="42 U.S.C. § 1983", document_id="doc-retrieve"
    )
    record = await get_audit_record(pool, audit_hash)
    assert record is not None
    assert record["citation_raw"] == "42 U.S.C. § 1983"
    assert record["audit_hash"] == audit_hash


async def test_retrieve_returns_none_for_unknown_hash(pool: asyncpg.Pool) -> None:
    record = await get_audit_record(pool, "0" * 64)
    assert record is None


async def test_get_document_audit(pool: asyncpg.Pool, test_api_key: uuid.UUID) -> None:
    doc_id = f"doc-{uuid.uuid4().hex[:8]}"
    await _log(pool, test_api_key, document_id=doc_id, citation_raw="531 U.S. 98")
    await _log(pool, test_api_key, document_id=doc_id, citation_raw="576 U.S. 644")
    records = await get_document_audit(pool, doc_id)
    assert len(records) == 2
    raw_citations = {r["citation_raw"] for r in records}
    assert raw_citations == {"531 U.S. 98", "576 U.S. 644"}
