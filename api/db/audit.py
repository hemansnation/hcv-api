import json
import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

import asyncpg

from api.utils.hashing import generate_record_hash

logger = logging.getLogger(__name__)


async def log_citation_verification(
    db_pool: asyncpg.Pool,
    request_id: str,
    client_id: str,
    document_id: str | None,
    citation_raw: str,
    citation_normalized: str | None,
    verification_result: dict,
    confidence_score: float,
) -> str:
    record = {
        "request_id": request_id,
        "client_id": client_id,
        "document_id": document_id,
        "citation_raw": citation_raw,
        "citation_normalized": citation_normalized,
        "sources_checked": verification_result.get("sources_checked", []),
        "found_in": verification_result.get("found_in", []),
        "exists": verification_result.get("exists", False),
        "confidence_score": confidence_score,
        "argument_flag": verification_result.get("argument_flag"),
    }
    audit_hash = generate_record_hash(record)

    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO audit_log "
                "(request_id, client_id, document_id, citation_raw, citation_normalized, "
                "sources_checked, found_in, exists, confidence_score, argument_flag, "
                "result_json, audit_hash) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb, $12)",
                uuid.UUID(request_id),
                uuid.UUID(str(client_id)),
                document_id,
                citation_raw,
                citation_normalized,
                record["sources_checked"],
                record["found_in"] or [],
                record["exists"],
                record["confidence_score"],
                record["argument_flag"],
                json.dumps(verification_result),
                audit_hash,
            )
    except asyncpg.UniqueViolationError:
        logger.warning("Audit record already exists for hash %s", audit_hash)
    except Exception:
        logger.exception("Failed to write audit record for citation %r", citation_raw)
        raise

    return audit_hash


def _row_to_dict(row: asyncpg.Record) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, uuid.UUID):
            result[key] = str(value)
        elif isinstance(value, datetime):
            result[key] = value.isoformat()
        elif isinstance(value, Decimal):
            result[key] = float(value)
        elif key == "result_json" and isinstance(value, str):
            try:
                result[key] = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                result[key] = value
        else:
            result[key] = value
    return result


async def get_audit_record(db_pool: asyncpg.Pool, audit_hash: str) -> dict | None:
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT request_id, client_id, document_id, citation_raw, citation_normalized, "
                "sources_checked, found_in, exists, confidence_score, argument_flag, "
                "result_json, audit_hash, created_at "
                "FROM audit_log WHERE audit_hash = $1",
                audit_hash,
            )
        return _row_to_dict(row) if row else None
    except Exception:
        logger.exception("Failed to retrieve audit record %s", audit_hash)
        return None


async def get_document_audit(db_pool: asyncpg.Pool, document_id: str) -> list[dict]:
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT request_id, client_id, document_id, citation_raw, citation_normalized, "
                "sources_checked, found_in, exists, confidence_score, argument_flag, "
                "result_json, audit_hash, created_at "
                "FROM audit_log WHERE document_id = $1 ORDER BY created_at ASC",
                document_id,
            )
        return [_row_to_dict(row) for row in rows]
    except Exception:
        logger.exception(
            "Failed to retrieve document audit for document_id %s", document_id
        )
        return []
