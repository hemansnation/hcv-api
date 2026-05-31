import logging
from typing import Any

from eyecite import get_citations
from eyecite.clean import clean_text
from eyecite.models import FullCaseCitation

logger = logging.getLogger(__name__)


def clean_legal_text(text: str) -> str:
    return clean_text(text, ["html", "inline_whitespace", "all_whitespace"])


def extract_citations(text: str) -> list[dict[str, Any]]:
    if not text or not text.strip():
        return []
    cleaned = clean_legal_text(text)
    raw_citations = get_citations(cleaned)

    results = []
    for cite in raw_citations:
        if not isinstance(cite, FullCaseCitation):
            continue
        try:
            span = cite.span()
            results.append(
                {
                    "raw_text": cite.matched_text(),
                    "volume": cite.groups.get("volume"),
                    "reporter": cite.groups.get("reporter"),
                    "page": cite.groups.get("page"),
                    "year": cite.metadata.year,
                    "start_index": span[0],
                    "end_index": span[1],
                    "citation_type": "FullCaseCitation",
                }
            )
        except Exception as e:
            logger.warning("Skipping citation due to parse error: %s", e)

    return results


def normalize_citation(citation_dict: dict[str, Any]) -> str:
    volume = citation_dict.get("volume", "")
    reporter = citation_dict.get("reporter", "")
    page = citation_dict.get("page", "")
    year = citation_dict.get("year")

    base = f"{volume} {reporter} {page}".strip()
    if year:
        return f"{base} ({year})"
    return base
