import logging
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException

from api.db.audit import get_audit_record, get_document_audit
from api.db.connection import get_db_pool

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/v1/audit/document/{document_id}")
async def get_audit_by_document(
    document_id: str,
    pool: Annotated[asyncpg.Pool, Depends(get_db_pool)],
) -> list[dict]:
    return await get_document_audit(pool, document_id)


@router.get("/v1/audit/{audit_hash}")
async def get_audit(
    audit_hash: str,
    pool: Annotated[asyncpg.Pool, Depends(get_db_pool)],
) -> dict:
    record = await get_audit_record(pool, audit_hash)
    if record is None:
        raise HTTPException(status_code=404, detail="AUDIT_RECORD_NOT_FOUND")
    return record
