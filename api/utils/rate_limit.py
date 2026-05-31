import logging
import time
from typing import Any

from fastapi import Request

logger = logging.getLogger(__name__)

TIER_MINUTE_LIMITS: dict[str, int] = {
    "starter": 10,
    "professional": 60,
    "enterprise": 500,
}


def get_redis_client(request: Request) -> Any:
    """FastAPI dependency — returns the Redis client from app.state."""
    return getattr(request.app.state, "redis_client", None)


async def check_rate_limit(api_key_hash: str, tier: str, redis_client: Any) -> bool:
    """Returns True if the request is within the per-minute limit, False if exceeded."""
    if redis_client is None:
        return True

    limit = TIER_MINUTE_LIMITS.get(tier, TIER_MINUTE_LIMITS["starter"])
    unix_minute = int(time.time() // 60)
    redis_key = f"ratelimit:{api_key_hash}:{unix_minute}"

    try:
        pipe = redis_client.pipeline()
        pipe.incr(redis_key)
        pipe.expire(redis_key, 90)
        results = await pipe.execute()
        return int(results[0]) <= limit
    except Exception as e:
        logger.warning(f"Rate limit check failed (failing open): {e}")
        return True
