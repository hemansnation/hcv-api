"""Integration tests for the API endpoints."""

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx

from api.db.connection import get_db_pool
from api.main import app
from api.utils.auth import get_current_client

FIXTURES = Path(__file__).parent / "fixtures"

_CL_URL = "https://www.courtlistener.com/api/rest/v4/citation-lookup/"

_FAKE_CLIENT = {
    "id": "00000000-0000-0000-0000-000000000001",
    "client_name": "Test Client",
    "tier": "starter",
    "key_hash": "testhash",
}

_FOUND_CLUSTER = [
    {
        "case_name": "Obergefell v. Hodges",
        "court": "scotus",
        "date_filed": "2015-06-26",
        "absolute_url": "/opinion/3242193/obergefell-v-hodges/",
    }
]


@pytest.fixture
async def client():
    """AsyncClient with auth dependency overridden to return a fake client."""
    app.dependency_overrides[get_current_client] = lambda: _FAKE_CLIENT
    async with httpx.AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _patch_audit():
    return patch(
        "api.routes.verify.log_citation_verification",
        new=AsyncMock(return_value="abc123"),
    )


@contextmanager
def _patch_cache():
    with patch(
        "api.services.verifier.get_cached_result", new=AsyncMock(return_value=None)
    ), patch("api.services.verifier.set_cached_result", new=AsyncMock()):
        yield


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@respx.mock
async def test_verify_real_citations(client: httpx.AsyncClient) -> None:
    respx.post(_CL_URL).mock(return_value=httpx.Response(200, json=_FOUND_CLUSTER))

    text = (FIXTURES / "sample_brief_1.txt").read_text()
    with _patch_audit(), _patch_cache():
        resp = await client.post(
            "/v1/verify", json={"text": text, "document_id": "doc-001"}
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["citations_found"] == 5
    assert len(data["results"]) == 5
    assert data["document_id"] == "doc-001"
    assert data["request_id"]
    assert data["processing_time_ms"] >= 0


@respx.mock
async def test_verify_hallucinated(client: httpx.AsyncClient) -> None:
    respx.post(_CL_URL).mock(return_value=httpx.Response(200, json=[]))

    text = (FIXTURES / "sample_hallucinated.txt").read_text()
    with _patch_audit(), _patch_cache():
        resp = await client.post("/v1/verify", json={"text": text})

    assert resp.status_code == 200
    data = resp.json()
    assert data["citations_found"] == 3
    for result in data["results"]:
        assert result["confidence_score"] == 0.0
        assert result["exists"] is False


@respx.mock
async def test_verify_no_citations(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/v1/verify",
        json={"text": "The weather today is sunny and pleasant outside."},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["citations_found"] == 0
    assert data["results"] == []


async def test_verify_requires_auth() -> None:
    async with httpx.AsyncClient(app=app, base_url="http://test") as ac:
        resp = await ac.post(
            "/v1/verify", json={"text": "Some text without any citations here."}
        )
    assert resp.status_code == 401


async def test_verify_rate_limit() -> None:
    from fastapi import HTTPException as _HTTPException

    async def _rate_limited():
        raise _HTTPException(
            status_code=429,
            detail={
                "error": "RATE_LIMIT_EXCEEDED",
                "message": "Rate limit exceeded. Upgrade your plan for higher limits.",
                "retry_after": 60,
                "current_tier": "starter",
            },
            headers={"Retry-After": "60"},
        )

    app.dependency_overrides[get_current_client] = _rate_limited
    try:
        async with httpx.AsyncClient(app=app, base_url="http://test") as ac:
            resp = await ac.post(
                "/v1/verify",
                json={"text": "The weather today is sunny and pleasant outside."},
            )
    finally:
        app.dependency_overrides.pop(get_current_client, None)

    assert resp.status_code == 429
    assert resp.headers.get("retry-after") == "60"
    data = resp.json()
    assert data["error"] == "RATE_LIMIT_EXCEEDED"
    assert data["retry_after"] == 60
    assert data["current_tier"] == "starter"


async def test_verify_text_too_long(client: httpx.AsyncClient) -> None:
    resp = await client.post("/v1/verify", json={"text": "x" * 51000})
    assert resp.status_code == 422


@respx.mock
async def test_audit_record_created(client: httpx.AsyncClient) -> None:
    respx.post(_CL_URL).mock(return_value=httpx.Response(200, json=_FOUND_CLUSTER))

    mock_pool = MagicMock()
    app.dependency_overrides[get_db_pool] = lambda: mock_pool

    text = (FIXTURES / "sample_brief_1.txt").read_text()
    mock_log = AsyncMock(return_value="deadbeef" * 8)
    try:
        with patch(
            "api.routes.verify.log_citation_verification", new=mock_log
        ), _patch_cache():
            resp = await client.post("/v1/verify", json={"text": text})
    finally:
        app.dependency_overrides.pop(get_db_pool, None)

    assert resp.status_code == 200
    assert mock_log.call_count == 5
    first_call = mock_log.call_args_list[0]
    assert first_call.kwargs.get("client_id") == _FAKE_CLIENT["id"]


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


async def test_health_degraded() -> None:
    async with httpx.AsyncClient(app=app, base_url="http://test") as ac:
        resp = await ac.get("/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("healthy", "degraded")
    assert data["version"] == "1.0.0"
    assert data["database"] in ("connected", "disconnected")
    assert data["cache"] in ("connected", "disconnected")
    assert "uptime_seconds" in data
    assert "timestamp" in data


async def test_health_connected(client: httpx.AsyncClient) -> None:
    mock_conn = AsyncMock()
    mock_conn.fetchval.return_value = 1
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)
    mock_pool = MagicMock()
    mock_pool.acquire.return_value = mock_ctx

    mock_redis = AsyncMock()
    mock_redis.ping.return_value = True

    app.state.db_pool = mock_pool
    app.state.redis_client = mock_redis
    try:
        resp = await client.get("/health")
    finally:
        app.state.db_pool = None
        app.state.redis_client = None

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert data["cache"] == "connected"


async def test_health_db_error(client: httpx.AsyncClient) -> None:
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(side_effect=Exception("db error"))
    mock_ctx.__aexit__ = AsyncMock(return_value=None)
    mock_pool = MagicMock()
    mock_pool.acquire.return_value = mock_ctx

    mock_redis = AsyncMock()
    mock_redis.ping.return_value = True

    app.state.db_pool = mock_pool
    app.state.redis_client = mock_redis
    try:
        resp = await client.get("/health")
    finally:
        app.state.db_pool = None
        app.state.redis_client = None

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "degraded"
    assert data["database"] == "disconnected"


# ---------------------------------------------------------------------------
# Audit endpoints
# ---------------------------------------------------------------------------


async def test_audit_not_found_returns_404() -> None:
    with patch("api.routes.audit.get_audit_record", new=AsyncMock(return_value=None)):
        async with httpx.AsyncClient(app=app, base_url="http://test") as ac:
            resp = await ac.get("/v1/audit/nonexistent_hash_that_does_not_exist")

    assert resp.status_code == 404
    assert resp.json()["error"] == "AUDIT_RECORD_NOT_FOUND"


async def test_audit_found_returns_record() -> None:
    record = {"audit_hash": "abc123", "citation_raw": "576 U.S. 644"}
    with patch("api.routes.audit.get_audit_record", new=AsyncMock(return_value=record)):
        async with httpx.AsyncClient(app=app, base_url="http://test") as ac:
            resp = await ac.get("/v1/audit/abc123")

    assert resp.status_code == 200
    assert resp.json()["audit_hash"] == "abc123"


async def test_audit_document_returns_list() -> None:
    records = [
        {"audit_hash": "aaa", "citation_raw": "531 U.S. 98"},
        {"audit_hash": "bbb", "citation_raw": "576 U.S. 644"},
    ]
    with patch(
        "api.routes.audit.get_document_audit", new=AsyncMock(return_value=records)
    ):
        async with httpx.AsyncClient(app=app, base_url="http://test") as ac:
            resp = await ac.get("/v1/audit/document/doc-001")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


# ---------------------------------------------------------------------------
# Response headers
# ---------------------------------------------------------------------------


async def test_response_includes_request_id_header(client: httpx.AsyncClient) -> None:
    resp = await client.post("/v1/verify", json={"text": "The weather today is sunny."})
    assert "x-request-id" in resp.headers
    request_id = resp.headers["x-request-id"]
    # Should be a valid UUID
    import uuid

    uuid.UUID(request_id)  # raises if invalid
