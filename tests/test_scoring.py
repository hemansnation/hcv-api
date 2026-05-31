from datetime import date, timedelta

import pytest

from api.services.scorer import (calculate_confidence_score,
                                 get_confidence_label)


def _result(source: str, found: bool) -> dict:
    return {"source": source, "found": found}


def test_full_confidence_single_source():
    results = [_result("courtlistener", True)]
    assert calculate_confidence_score(results) == 1.0


def test_partial_confidence():
    results = [_result("courtlistener", True), _result("justia", False)]
    assert calculate_confidence_score(results) == 0.5


def test_zero_confidence():
    results = [_result("courtlistener", False), _result("justia", False)]
    assert calculate_confidence_score(results) == 0.0


def test_authoritative_bonus_lexisnexis():
    results = [_result("courtlistener", True), _result("lexisnexis", True)]
    score = calculate_confidence_score(results)
    assert score == min(1.0, 1.0 + 0.15)


def test_authoritative_bonus_capped_at_one():
    results = [_result("lexisnexis", True)]
    score = calculate_confidence_score(results)
    assert score == 1.0


def test_authoritative_bonus_westlaw():
    results = [_result("courtlistener", False), _result("westlaw", True)]
    score = calculate_confidence_score(results)
    assert score == round(min(1.0, 0.5 + 0.15), 4)


def test_authoritative_bonus_not_applied_when_not_found():
    results = [_result("lexisnexis", False), _result("courtlistener", False)]
    score = calculate_confidence_score(results)
    assert score == 0.0


def test_recency_penalty():
    recent = date.today() - timedelta(days=10)
    results = [_result("courtlistener", True)]
    score = calculate_confidence_score(results, case_date=recent)
    assert score == round(max(0.0, 1.0 - 0.10), 4)


def test_recency_penalty_not_applied_for_old_case():
    old = date.today() - timedelta(days=31)
    results = [_result("courtlistener", True)]
    score = calculate_confidence_score(results, case_date=old)
    assert score == 1.0


def test_jurisdiction_penalty():
    results = [_result("courtlistener", True)]
    score = calculate_confidence_score(results, jurisdiction="uk")
    assert score == round(max(0.0, 1.0 - 0.20), 4)


def test_jurisdiction_penalty_not_applied_for_covered():
    results = [_result("courtlistener", True)]
    score = calculate_confidence_score(results, jurisdiction="scotus")
    assert score == 1.0


def test_jurisdiction_penalty_floors_at_zero():
    results = [_result("courtlistener", False), _result("justia", False)]
    score = calculate_confidence_score(results, jurisdiction="uk")
    assert score == 0.0


def test_all_penalties_combined():
    recent = date.today() - timedelta(days=5)
    results = [_result("courtlistener", True), _result("justia", False)]
    score = calculate_confidence_score(results, case_date=recent, jurisdiction="uk")
    expected = round(max(0.0, 0.5 - 0.10 - 0.20), 4)
    assert score == expected


def test_empty_results():
    assert calculate_confidence_score([]) == 0.0


def test_all_labels():
    assert get_confidence_label(1.00) == "high"
    assert get_confidence_label(0.90) == "high"
    assert get_confidence_label(0.89) == "medium"
    assert get_confidence_label(0.70) == "medium"
    assert get_confidence_label(0.69) == "low"
    assert get_confidence_label(0.50) == "low"
    assert get_confidence_label(0.49) == "not_verified"
    assert get_confidence_label(0.00) == "not_verified"
