"""The model must know what day it is.

Without today's date the classifier judged a 2023 tweet about "BNB Grant DAO
Round 3" as an open opportunity, a deadline written as "Nov 30" had to guess
its year, and the timeliness score ("how much time remains?") had no reference.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import httpx

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.classifier.classifier import OpportunityClassifier
from src.classifier.scorer import OpportunityScorer
from src.fetchers.base import FetchedItem
from src.main import _try_extract_dates_from_url


def _today() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()


class AlwaysMatches:
    def matches(self, text):
        return True


class RecordingLLM:
    def __init__(self, response):
        self.response = response
        self.prompts = []

    def classify_structured(self, system, user):
        self.prompts.append((system, user))
        return self.response


def _tweet(metadata: dict) -> FetchedItem:
    return FetchedItem(
        source_type="twitter",
        source_name="twitter_dorahacks",
        raw_content="Keep up with #BNBGrantDAO - Round3 now open for project submission!",
        raw_url="https://x.com/DoraHacks/status/1622935711409229824",
        canonical_url="https://x.com/DoraHacks/status/1622935711409229824",
        metadata=metadata,
    )


def _classify_prompt(metadata: dict) -> str:
    llm = RecordingLLM({"category": "NOISE"})
    OpportunityClassifier(AlwaysMatches(), llm).classify(_tweet(metadata))
    return llm.prompts[0][1]


def test_classifier_prompt_states_today() -> None:
    assert f"Today's date: {_today()}" in _classify_prompt({"title": "BNB Grant DAO"})


def test_classifier_prompt_states_when_the_content_was_published() -> None:
    prompt = _classify_prompt(
        {"title": "BNB Grant DAO", "created_at": datetime(2023, 2, 7, 8, 0, tzinfo=timezone.utc)}
    )

    assert "Published: 2023-02-07" in prompt


def test_classifier_prompt_accepts_iso_string_publication_dates() -> None:
    prompt = _classify_prompt({"title": "Grants", "published": "2026-10-05T09:30:00+00:00"})

    assert "Published: 2026-10-05" in prompt


def test_classifier_prompt_marks_an_unknown_publication_date() -> None:
    assert "Published: unknown" in _classify_prompt({"title": "Grants"})


def test_classifier_asks_whether_the_program_is_rolling() -> None:
    """main._staleness_reason keeps an aged official post only when it is rolling."""
    assert "is_rolling" in _classify_prompt({"title": "Grants"})


def test_scorer_prompt_states_today() -> None:
    llm = RecordingLLM({"score_roi": 5, "score_reputation": 5, "score_timeliness": 5, "score_strategy": 5})

    OpportunityScorer(llm).score({"event_type": "grant", "title": "X", "deadline": "2026-11-01"})

    assert f"Today's date: {_today()}" in llm.prompts[0][1]


def test_secondary_date_extraction_prompt_states_today(monkeypatch) -> None:
    page = SimpleNamespace(
        text="<html><body><main>Applications close Nov 30.</main></body></html>",
        raise_for_status=lambda: None,
    )
    monkeypatch.setattr(httpx, "get", lambda url, **kwargs: page)
    llm = RecordingLLM({"deadline": None})

    _try_extract_dates_from_url("https://example.org/grants", llm)

    assert f"Today's date: {_today()}" in llm.prompts[0][1]
