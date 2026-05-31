import asyncio
import logging
from typing import Any

from api.services.cache import get_cached_result, set_cached_result
from api.services.extractor import normalize_citation
from api.services.sources.courtlistener import verify_citation_courtlistener

logger = logging.getLogger(__name__)


async def verify_single_citation(citation: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_citation(citation)
    raw_text = citation.get("raw_text", normalized)

    cached = await get_cached_result(normalized)
    if cached is not None:
        logger.debug("Cache hit for: %r", normalized)
        return {**cached, "cached": True}

    source_results = await asyncio.gather(
        verify_citation_courtlistener(raw_text),
        return_exceptions=True,
    )

    sources_checked = []
    found_in = []
    case_name = ""
    court = ""
    date = ""
    url = ""

    for result in source_results:
        if isinstance(result, BaseException):
            logger.error("Source verification raised unexpectedly: %s", result)
            continue
        sources_checked.append(result["source"])
        if result.get("found"):
            found_in.append(result["source"])
            case_name = case_name or result.get("case_name", "")
            court = court or result.get("court", "")
            date = date or result.get("date", "")
            url = url or result.get("url", "")

    verification = {
        "citation_raw": raw_text,
        "citation_normalized": normalized,
        "exists": bool(found_in),
        "sources_checked": sources_checked,
        "found_in": found_in,
        "case_name": case_name,
        "court": court,
        "date": date,
        "url": url,
        "cached": False,
    }

    await set_cached_result(normalized, verification)
    return verification


async def verify_all_citations(citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results = await asyncio.gather(
        *[verify_single_citation(c) for c in citations],
        return_exceptions=True,
    )

    output = []
    for citation, result in zip(citations, results):
        if isinstance(result, BaseException):
            logger.error("Unhandled exception verifying citation: %s", result)
            output.append(
                {
                    "citation_raw": citation.get("raw_text", ""),
                    "citation_normalized": normalize_citation(citation),
                    "exists": False,
                    "sources_checked": [],
                    "found_in": [],
                    "error": "unexpected",
                    "cached": False,
                }
            )
        else:
            output.append(result)
    return output
