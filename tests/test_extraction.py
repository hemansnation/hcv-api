from pathlib import Path

import pytest

from api.services.extractor import extract_citations, normalize_citation

FIXTURES = Path(__file__).parent / "fixtures"


def test_extracts_standard_citations() -> None:
    text = (FIXTURES / "sample_brief_1.txt").read_text()
    citations = extract_citations(text)
    assert len(citations) == 5


def test_extracts_correct_reporters() -> None:
    text = (FIXTURES / "sample_brief_1.txt").read_text()
    citations = extract_citations(text)
    for cite in citations:
        assert cite["reporter"] == "U.S."


def test_handles_empty_text() -> None:
    citations = extract_citations("")
    assert citations == []


def test_handles_text_without_citations() -> None:
    citations = extract_citations("The weather today is sunny and warm.")
    assert citations == []


def test_normalize_citation() -> None:
    citation_dict = {"volume": "576", "reporter": "U.S.", "page": "644", "year": "2015"}
    result = normalize_citation(citation_dict)
    assert result == "576 U.S. 644 (2015)"
