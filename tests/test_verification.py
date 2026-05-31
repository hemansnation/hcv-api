from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from api.services.extractor import extract_citations
from api.services.sources.courtlistener import verify_citation_courtlistener
from api.services.verifier import verify_all_citations, verify_single_citation

FIXTURES = Path(__file__).parent / "fixtures"

_CL_URL = "https://www.courtlistener.com/api/rest/v4/citation-lookup/"

_CLUSTER_RESPONSE = [
    {
        "case_name": "Obergefell v. Hodges",
        "court": "scotus",
        "date_filed": "2015-06-26",
        "absolute_url": "/opinion/3242193/obergefell-v-hodges/",
    }
]


@respx.mock
@pytest.mark.asyncio
async def test_finds_real_citation() -> None:
    respx.post(_CL_URL).mock(return_value=httpx.Response(200, json=_CLUSTER_RESPONSE))

    result = await verify_citation_courtlistener("576 U.S. 644")

    assert result["found"] is True
    assert result["source"] == "courtlistener"
    assert result["case_name"] == "Obergefell v. Hodges"
    assert result["court"] == "scotus"


@respx.mock
@pytest.mark.asyncio
async def test_missing_citation() -> None:
    respx.post(_CL_URL).mock(return_value=httpx.Response(200, json=[]))

    result = await verify_citation_courtlistener("999 U.S. 999")

    assert result["found"] is False
    assert result["source"] == "courtlistener"
    assert "error" not in result


@respx.mock
@pytest.mark.asyncio
async def test_timeout_handled() -> None:
    respx.post(_CL_URL).mock(side_effect=httpx.TimeoutException("timed out"))

    result = await verify_citation_courtlistener("576 U.S. 644")

    assert result["found"] is False
    assert result["source"] == "courtlistener"
    assert result["error"] == "timeout"


@pytest.mark.asyncio
async def test_cache_hit() -> None:
    citation = {
        "raw_text": "576 U.S. 644",
        "volume": "576",
        "reporter": "U.S.",
        "page": "644",
        "year": "2015",
    }
    cached_value = {
        "citation_raw": "576 U.S. 644",
        "citation_normalized": "576 U.S. 644 (2015)",
        "exists": True,
        "sources_checked": ["courtlistener"],
        "found_in": ["courtlistener"],
        "case_name": "Obergefell v. Hodges",
        "court": "scotus",
        "date": "2015-06-26",
        "url": "/opinion/3242193/",
        "cached": False,
    }

    with (
        patch(
            "api.services.verifier.get_cached_result",
            new=AsyncMock(return_value=cached_value),
        ),
        patch(
            "api.services.verifier.verify_citation_courtlistener", new=AsyncMock()
        ) as mock_cl,
    ):
        result = await verify_single_citation(citation)

    mock_cl.assert_not_called()
    assert result["cached"] is True
    assert result["exists"] is True


@respx.mock
@pytest.mark.asyncio
async def test_hallucinated_citations() -> None:
    respx.post(_CL_URL).mock(return_value=httpx.Response(200, json=[]))

    text = (FIXTURES / "sample_hallucinated.txt").read_text()
    citations = extract_citations(text)
    assert len(citations) == 3

    with (
        patch(
            "api.services.verifier.get_cached_result", new=AsyncMock(return_value=None)
        ),
        patch("api.services.verifier.set_cached_result", new=AsyncMock()),
    ):
        results = await verify_all_citations(citations)

    assert len(results) == 3
    for result in results:
        assert (
            result["exists"] is False
        ), f"Expected hallucinated citation to be not found: {result}"
