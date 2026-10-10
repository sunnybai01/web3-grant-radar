"""Classifier robustness: LLM failures must be distinguishable from "noise".

The old API returned (None, None) for both a provider outage and a genuine
non-match, so an entire run could silently report zero opportunities. These
tests pin the tri-state behaviour and the defensive parsing of model output.
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.classifier.classifier import Classification, OpportunityClassifier
from src.fetchers.base import FetchedItem


class StubKeywords:
    def __init__(self, matches=True):
        self._matches = matches

    def matches(self, text):
        return self._matches


class StubLLM:
    def __init__(self, response=None, raises=None):
        self.response = response
        self.raises = raises
        self.calls = 0

    def classify_structured(self, system, user):
        self.calls += 1
        if self.raises:
            raise self.raises
        return self.response


def _item(content="A grant program is open for applications.") -> FetchedItem:
    return FetchedItem(
        source_type="rss",
        source_name="avalanche_blog",
        raw_content=content,
        raw_url="https://example.org/grants",
        canonical_url="https://example.org/grants",
        metadata={"title": "Grants", "ecosystem": "avalanche"},
    )


def _classifier(**kwargs) -> OpportunityClassifier:
    return OpportunityClassifier(StubKeywords(**{k: v for k, v in kwargs.items() if k == "matches"}),
                                 StubLLM(**{k: v for k, v in kwargs.items() if k != "matches"}))


def test_keyword_miss_is_noise_not_failure() -> None:
    result = OpportunityClassifier(StubKeywords(matches=False), StubLLM()).classify(_item())

    assert result.category == "NOISE"
    assert result.failed is False


def test_llm_exception_is_reported_as_failure() -> None:
    cls = _classifier(raises=RuntimeError("connection reset"))

    result = cls.classify(_item())

    assert result.failed is True
    assert result.category is None
    assert "connection reset" in result.llm_error


def test_empty_response_is_reported_as_failure() -> None:
    result = _classifier(response={}).classify(_item())

    assert result.failed is True
    assert result.category is None


def test_string_confidence_does_not_raise() -> None:
    cls = _classifier(response={"category": "GRANT", "title": "X", "confidence": "0.9"})

    result = cls.classify(_item())

    assert result.category == "GRANT"
    assert result.data["confidence"] == 0.9


def test_missing_confidence_is_accepted_not_zeroed() -> None:
    """A response without confidence used to default to 0.0 and become NOISE."""
    cls = _classifier(response={"category": "GRANT", "title": "X"})

    result = cls.classify(_item())

    assert result.category == "GRANT"
    assert result.data["confidence"] == 1.0


def test_low_confidence_is_noise() -> None:
    cls = _classifier(response={"category": "GRANT", "title": "X", "confidence": 0.2})

    assert cls.classify(_item()).category == "NOISE"


def test_category_is_case_normalized() -> None:
    for raw, expected in [("grant", "GRANT"), ("Hackathon", "HACKATHON")]:
        result = _classifier(response={"category": raw, "title": "X", "confidence": 0.9}).classify(_item())
        assert result.category == expected, raw


def test_lowercase_bounty_is_dropped() -> None:
    """`category == "BOUNTY"` only caught the upper-case spelling."""
    result = _classifier(response={"category": "bounty", "title": "X", "confidence": 0.9}).classify(_item())

    assert result.category == "NOISE"
    assert result.failed is False


def test_lowercase_noise_is_not_an_event() -> None:
    result = _classifier(response={"category": "noise", "title": "X", "confidence": 0.9}).classify(_item())

    assert result.category == "NOISE"
    assert result.is_opportunity is False


def test_unknown_category_is_not_an_event() -> None:
    result = _classifier(response={"category": "FELLOWSHIP", "title": "X", "confidence": 0.9}).classify(_item())

    assert result.is_opportunity is False


def test_missing_category_is_a_failure_not_noise() -> None:
    result = _classifier(response={"title": "X", "confidence": 0.9}).classify(_item())

    assert result.failed is True


def test_ecosystem_backfilled_from_source_metadata() -> None:
    cls = _classifier(response={"category": "GRANT", "title": "X", "confidence": 0.9})

    result = cls.classify(_item())

    assert result.data["ecosystem"] == "avalanche"


def test_classification_supports_tuple_unpacking() -> None:
    """Backwards compatibility with the previous (category, data) return shape."""
    category, data = Classification(category="GRANT", data={"title": "X"})

    assert category == "GRANT"
    assert data == {"title": "X"}
