"""Unit tests for the per-minute Redis rate limiter."""

from unittest.mock import patch

import pytest

from api.utils.rate_limit import TIER_MINUTE_LIMITS, check_rate_limit

# ---------------------------------------------------------------------------
# Fake Redis — in-memory pipeline that mirrors INCR / EXPIRE behaviour
# ---------------------------------------------------------------------------


class _FakePipeline:
    def __init__(self, store: dict) -> None:
        self._store = store
        self._ops: list = []

    def incr(self, key: str) -> "_FakePipeline":
        self._ops.append(("incr", key))
        return self

    def expire(self, key: str, ttl: int) -> "_FakePipeline":
        self._ops.append(("expire", key, ttl))
        return self

    async def execute(self) -> list:
        results = []
        for op in self._ops:
            if op[0] == "incr":
                key = op[1]
                self._store[key] = self._store.get(key, 0) + 1
                results.append(self._store[key])
            else:
                results.append(True)
        return results


class FakeRedis:
    def __init__(self) -> None:
        self._store: dict[str, int] = {}

    def pipeline(self) -> _FakePipeline:
        return _FakePipeline(self._store)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_within_limit() -> None:
    """9 requests for a starter key (limit=10) must all be allowed."""
    redis = FakeRedis()
    limit = TIER_MINUTE_LIMITS["starter"]  # 10

    for i in range(limit - 1):
        result = await check_rate_limit("key_a", "starter", redis)
        assert result is True, f"Request {i + 1} should be allowed"


async def test_exceeds_limit() -> None:
    """The (limit+1)th request for a starter key must be denied."""
    redis = FakeRedis()
    limit = TIER_MINUTE_LIMITS["starter"]  # 10

    for _ in range(limit):
        await check_rate_limit("key_b", "starter", redis)

    result = await check_rate_limit("key_b", "starter", redis)
    assert result is False


async def test_different_keys_independent() -> None:
    """Two distinct API keys must not share their counter bucket."""
    redis = FakeRedis()
    limit = TIER_MINUTE_LIMITS["starter"]  # 10

    for _ in range(limit):
        await check_rate_limit("key_x", "starter", redis)

    # key_x is now at the limit; key_y should be completely fresh
    result = await check_rate_limit("key_y", "starter", redis)
    assert result is True


async def test_limit_resets_after_minute() -> None:
    """After advancing the clock past 60 s, the counter bucket changes and resets."""
    redis = FakeRedis()
    limit = TIER_MINUTE_LIMITS["starter"]  # 10

    # Exhaust the limit at t=0 (unix_minute = 0)
    with patch("api.utils.rate_limit.time") as mock_time:
        mock_time.time.return_value = 0.0
        for _ in range(limit):
            await check_rate_limit("key_c", "starter", redis)
        result_before = await check_rate_limit("key_c", "starter", redis)
    assert result_before is False

    # Advance to t=60 (unix_minute = 1) — fresh bucket
    with patch("api.utils.rate_limit.time") as mock_time:
        mock_time.time.return_value = 60.0
        result_after = await check_rate_limit("key_c", "starter", redis)
    assert result_after is True


async def test_professional_tier_higher_limit() -> None:
    """Professional tier allows 60 req/min; 60 requests must all pass."""
    redis = FakeRedis()
    limit = TIER_MINUTE_LIMITS["professional"]  # 60

    for i in range(limit):
        result = await check_rate_limit("key_pro", "professional", redis)
        assert result is True, f"Request {i + 1} of {limit} should be allowed"

    result = await check_rate_limit("key_pro", "professional", redis)
    assert result is False


async def test_none_redis_fails_open() -> None:
    """If the Redis client is None (unavailable), all requests are allowed."""
    result = await check_rate_limit("key_d", "starter", redis_client=None)
    assert result is True
