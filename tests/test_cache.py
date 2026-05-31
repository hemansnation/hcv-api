"""Unit tests for the Redis caching layer."""

import json
from unittest.mock import AsyncMock, patch

import pytest

import api.services.cache as cache_module
from api.config import settings
from api.services.cache import _cache_key, get_cached_result, set_cached_result


def test_cache_key_format() -> None:
    key = _cache_key("576 U.S. 644 (2015)")
    assert key.startswith("verify:")
    assert len(key) == len("verify:") + 64  # SHA-256 = 64 hex chars


def test_cache_key_deterministic() -> None:
    assert _cache_key("576 U.S. 644") == _cache_key("576 U.S. 644")


def test_cache_key_different_citations_differ() -> None:
    assert _cache_key("576 U.S. 644") != _cache_key("531 U.S. 98")


def test_get_client_creates_from_settings() -> None:
    old = cache_module._redis_client
    cache_module._redis_client = None
    try:
        mock_client = AsyncMock()
        with patch(
            "api.services.cache.aioredis.from_url", return_value=mock_client
        ) as mock_from:
            client = cache_module._get_client()
        mock_from.assert_called_once_with(settings.redis_url, decode_responses=True)
        assert client is mock_client
    finally:
        cache_module._redis_client = old


async def test_get_cached_result_miss() -> None:
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None

    with patch("api.services.cache._get_client", return_value=mock_redis):
        result = await get_cached_result("576 U.S. 644 (2015)")

    assert result is None
    mock_redis.get.assert_called_once()


async def test_get_cached_result_hit() -> None:
    cached = {"citation_raw": "576 U.S. 644", "exists": True, "cached": False}
    mock_redis = AsyncMock()
    mock_redis.get.return_value = json.dumps(cached)

    with patch("api.services.cache._get_client", return_value=mock_redis):
        result = await get_cached_result("576 U.S. 644 (2015)")

    assert result == cached


async def test_set_cached_result_calls_setex() -> None:
    mock_redis = AsyncMock()
    data = {"citation_raw": "576 U.S. 644", "exists": True}

    with patch("api.services.cache._get_client", return_value=mock_redis):
        await set_cached_result("576 U.S. 644 (2015)", data)

    mock_redis.setex.assert_called_once()
    key, ttl, payload = mock_redis.setex.call_args[0]
    assert key.startswith("verify:")
    assert ttl == 86400
    assert json.loads(payload) == data


async def test_get_cached_result_error_returns_none() -> None:
    mock_redis = AsyncMock()
    mock_redis.get.side_effect = Exception("Redis down")

    with patch("api.services.cache._get_client", return_value=mock_redis):
        result = await get_cached_result("576 U.S. 644 (2015)")

    assert result is None


async def test_set_cached_result_error_silently_fails() -> None:
    mock_redis = AsyncMock()
    mock_redis.setex.side_effect = Exception("Redis down")

    with patch("api.services.cache._get_client", return_value=mock_redis):
        await set_cached_result("576 U.S. 644 (2015)", {"exists": True})
