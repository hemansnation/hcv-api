import hashlib
import logging
from typing import Annotated, Any

import asyncpg
from fastapi import Depends, Header, HTTPException

from api.db.connection import get_db_pool
from api.utils.rate_limit import check_rate_limit, get_redis_client

logger = logging.getLogger(__name__)

_RATE_LIMIT_DETAIL = {
    "error": "RATE_LIMIT_EXCEEDED",
    "message": "Rate limit exceeded. Upgrade your plan for higher limits.",
    "retry_after": 60,
}
_RATE_LIMIT_HEADERS = {"Retry-After": "60"}


async def get_current_client(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    pool: asyncpg.Pool = Depends(get_db_pool),
    redis_client: Any = Depends(get_redis_client),
) -> dict:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="INVALID_API_KEY")

    key_hash = hashlib.sha256(x_api_key.encode()).hexdigest()

    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, client_name, tier, monthly_limit, requests_this_month, is_active "
                "FROM api_keys WHERE key_hash = $1",
                key_hash,
            )
    except Exception:
        logger.exception("Database error during API key lookup")
        raise HTTPException(status_code=503, detail="SERVICE_UNAVAILABLE")

    if row is None or not row["is_active"]:
        raise HTTPException(status_code=401, detail="INVALID_API_KEY")

    tier = row["tier"]

    if row["requests_this_month"] >= row["monthly_limit"]:
        raise HTTPException(
            status_code=429,
            detail={**_RATE_LIMIT_DETAIL, "current_tier": tier},
            headers=_RATE_LIMIT_HEADERS,
        )

    allowed = await check_rate_limit(key_hash, tier, redis_client)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={**_RATE_LIMIT_DETAIL, "current_tier": tier},
            headers=_RATE_LIMIT_HEADERS,
        )

    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE api_keys SET requests_this_month = requests_this_month + 1, "
                "last_used_at = NOW() WHERE id = $1",
                row["id"],
            )
    except Exception:
        logger.warning("Failed to update usage counters for client %s", row["id"])

    return {
        "id": str(row["id"]),
        "client_name": row["client_name"],
        "tier": tier,
        "key_hash": key_hash,
    }
