"""What the classifier must treat as "not an opportunity for the reader".

A labeled sample of real items (2026-10-13) showed 10 of 16 non-opportunities
accepted: other teams' grant proposals on the Optimism forum, a "10+ funding
programs" roundup, a weekly digest, a demo day, a conference week and a credits
promotion. The prompt now names these cases and asks for the reason, so the
decision can be audited from the logs.
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.classifier.prompts import CLASSIFY_SYSTEM, CLASSIFY_USER_TEMPLATE, EXTRACTION_SCHEMA

NOISE_REASONS = {
    "third_party_application", "roundup", "funding_news",
    "non_building_event", "non_cash_reward", "general_news", "other",
}


def test_prompt_names_each_kind_of_non_opportunity() -> None:
    text = CLASSIFY_SYSTEM.lower()

    for phrase in (
        "own application",      # [Builder Grant Proposal] X, Grant Application: X
        "roundup",              # Top 15 grants, 10+ funding programs, weekly digest
        "raised",               # funding / investment news
        "demo day",             # pre-selected teams present
        "credits",              # service credits, not money
    ):
        assert phrase in text, phrase


def test_demo_days_are_no_longer_listed_as_hackathons() -> None:
    hackathon_line = next(line for line in CLASSIFY_SYSTEM.splitlines() if line.startswith('- "HACKATHON"'))

    assert "demo day" not in hackathon_line.lower()


def test_model_reports_why_something_is_noise() -> None:
    assert "noise_reason" in CLASSIFY_USER_TEMPLATE
    enum = set(EXTRACTION_SCHEMA["properties"]["noise_reason"]["enum"])
    assert enum - {None} == NOISE_REASONS  # null for real opportunities
