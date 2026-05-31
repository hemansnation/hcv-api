import logging
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

COVERED_JURISDICTIONS = {
    "us",
    "scotus",
    "ca1",
    "ca2",
    "ca3",
    "ca4",
    "ca5",
    "ca6",
    "ca7",
    "ca8",
    "ca9",
    "ca10",
    "ca11",
    "cadc",
    "cafc",
}

AUTHORITATIVE_SOURCES = {"lexisnexis", "westlaw"}


def calculate_confidence_score(
    verification_results: list[dict],
    case_date: Optional[date] = None,
    jurisdiction: Optional[str] = None,
) -> float:
    if not verification_results:
        return 0.0

    total = len(verification_results)
    confirmed = sum(1 for r in verification_results if r.get("found", False))
    found_in = {
        r.get("source", "").lower()
        for r in verification_results
        if r.get("found", False)
    }

    base_score = confirmed / total

    if found_in & AUTHORITATIVE_SOURCES:
        base_score = min(1.0, base_score + 0.15)

    if case_date is not None and case_date > (date.today() - timedelta(days=30)):
        base_score = max(0.0, base_score - 0.10)

    if jurisdiction is not None and jurisdiction.lower() not in COVERED_JURISDICTIONS:
        base_score = max(0.0, base_score - 0.20)

    return round(base_score, 4)


def get_confidence_label(score: float) -> str:
    if score >= 0.90:
        return "high"
    if score >= 0.70:
        return "medium"
    if score >= 0.50:
        return "low"
    return "not_verified"
