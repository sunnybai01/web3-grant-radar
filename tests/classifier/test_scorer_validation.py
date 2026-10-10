"""Scoring must never publish an out-of-range or unusable score.

Production stored a final_score of 48.0 (four dimensions multiplied raw) and
could raise TypeError on a null dimension, aborting the whole run.
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.classifier.scorer import OpportunityScorer, stars_from_score


class StubLLM:
    def __init__(self, response=None):
        self.response = response

    def classify_structured(self, system, user):
        return self.response


def _scorer(response) -> OpportunityScorer:
    return OpportunityScorer(StubLLM(response))


BASE_EVENT = {
    "event_type": "grant",
    "title": "Some Grant",
    "description": "desc",
    "amount": "$25,000",
    "ecosystem": "ethereum",
    "source_tier": "discovery",
    "verification_verdict": "verified",
}


def test_out_of_range_dimensions_are_clamped() -> None:
    scored = _scorer({
        "score_roi": 80, "score_reputation": 70, "score_timeliness": 60, "score_strategy": 50,
    }).score(dict(BASE_EVENT))

    assert scored["score_roi"] == 10.0
    assert scored["score_timeliness"] == 10.0
    assert 1.0 <= scored["final_score"] <= 10.0


def test_negative_dimensions_are_clamped() -> None:
    scored = _scorer({
        "score_roi": -5, "score_reputation": 0, "score_timeliness": -1, "score_strategy": 0,
    }).score(dict(BASE_EVENT))

    for key in ("score_roi", "score_reputation", "score_timeliness", "score_strategy"):
        assert 1.0 <= scored[key] <= 10.0, key
    assert 1.0 <= scored["final_score"] <= 10.0


def test_null_dimension_falls_back_instead_of_raising() -> None:
    scored = _scorer({
        "score_roi": None, "score_reputation": 7, "score_timeliness": 6, "score_strategy": 5,
    }).score(dict(BASE_EVENT))

    assert scored["score_roi"] == 5.0  # neutral midpoint, not a crash
    assert 1.0 <= scored["final_score"] <= 10.0


def test_string_dimension_is_coerced() -> None:
    scored = _scorer({
        "score_roi": "8", "score_reputation": "7", "score_timeliness": "6", "score_strategy": "5",
    }).score(dict(BASE_EVENT))

    assert scored["score_roi"] == 8.0
    assert 1.0 <= scored["final_score"] <= 10.0


def test_missing_dimension_uses_heuristic_fallback() -> None:
    scored = _scorer({"score_roi": 8, "score_reputation": 7}).score(dict(BASE_EVENT))

    assert 1.0 <= scored["final_score"] <= 10.0
    assert scored["score_roi"] is not None


def test_garbage_response_uses_heuristic_fallback() -> None:
    scored = _scorer("not a dict").score(dict(BASE_EVENT))

    assert 1.0 <= scored["final_score"] <= 10.0


def test_heuristic_strategy_branch_is_reachable_for_lowercase_event_type() -> None:
    """event_type is stored lowercase; the old comparison never matched."""
    grant = _scorer(None).score({**BASE_EVENT, "event_type": "grant"})
    hack = _scorer(None).score({**BASE_EVENT, "event_type": "hackathon"})

    assert hack["score_strategy"] > grant["score_strategy"]


def test_official_source_gets_reputation_bonus() -> None:
    response = {"score_roi": 5, "score_reputation": 5, "score_timeliness": 5, "score_strategy": 5}

    discovery = _scorer(response).score({**BASE_EVENT, "source_tier": "discovery", "official": False})
    official = _scorer(response).score({**BASE_EVENT, "source_tier": "official", "official": True})

    assert official["score_reputation"] > discovery["score_reputation"]
    assert official["trust_label"] == "confirmed_official"


def test_stars_from_score_handles_extremes() -> None:
    assert stars_from_score(10) != ""
    assert stars_from_score(1) != ""
