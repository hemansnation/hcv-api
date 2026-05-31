import hashlib
import json
import logging

import redis.asyncio as aioredis

from api.config import settings

logger = logging.getLogger(__name__)

_redis_client: aioredis.Redis | None = None
_TTL = 86400


def _get_client() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


def _cache_key(normalized_citation: str) -> str:
    digest = hashlib.sha256(normalized_citation.encode()).hexdigest()
    return f"verify:{digest}"


async def get_cached_result(normalized_citation: str) -> dict | None:
    try:
        client = _get_client()
        value = await client.get(_cache_key(normalized_citation))
        if value is None:
            return None
        return json.loads(value)
    except Exception as e:
        logger.warning("Cache read error: %s", e)
        return None


async def set_cached_result(normalized_citation: str, result: dict) -> None:
    try:
        client = _get_client()
        await client.setex(_cache_key(normalized_citation), _TTL, json.dumps(result))
    except Exception as e:
        logger.warning("Cache write error: %s", e)
