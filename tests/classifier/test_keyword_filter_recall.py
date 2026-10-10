"""Keyword prefilter must not drop real opportunities.

Production evidence: the old >=2 *non-overlapping regex match* rule returned
False for "Ethereum Foundation Grant" (one hit for two listed terms) and for
"Total prize pool $100,000", while an incidental negative word killed genuine
grants outright.
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.classifier.keyword_filter import KeywordFilter

FILTER = KeywordFilter()


def test_single_strong_term_passes() -> None:
    """A lone "grant"/"hackathon"/"funding" mention is a valid candidate."""
    for text in [
        "Ethereum Foundation Grant",
        "Total prize pool $100,000",
        "Funding available for public goods",
        "Retro funding round 5 is here",
        "Apply for the accelerator",
        "Solana Foundation Grants Program",
        "Starknet Seed Grants",
        "Colosseum Crypto World's Fair Hackathon",
    ]:
        assert FILTER.matches(text) is True, text


def test_unrelated_content_is_rejected() -> None:
    for text in [
        "We are hiring a protocol engineer",
        "The price of ETH rose 4% today",
        "",
        None,
    ]:
        assert FILTER.matches(text) is False, text


def test_listed_phrase_is_not_shadowed_by_a_shorter_entry() -> None:
    """'grant' used to be consumed before 'grant program' could match."""
    hits = FILTER.matched_terms("The grant program is open with funding available")

    assert "grant" in hits
    assert "grant program" in hits or "funding" in hits


def test_negative_word_alone_rejects() -> None:
    assert FILTER.matches("Claim your airdrop now") is False


def test_negative_word_does_not_kill_a_real_grant() -> None:
    """One incidental 'airdrop'/'whitelist' must not veto a genuine call."""
    assert FILTER.matches("Not an airdrop. Real grants for builders.") is True
    assert FILTER.matches(
        "ETHDenver 2026 hackathon: whitelist your team now, $50,000 prize pool"
    ) is True
    assert FILTER.matches(
        "Grants for teams that completed a token sale in 2025: apply now"
    ) is True


def test_two_or_more_positive_terms_override_a_negative() -> None:
    text = "Hackathon grants open for applications — ignore the airdrop rumours"

    assert len(FILTER.matched_terms(text)) >= 2
    assert FILTER.matches(text) is True


def test_term_matching_respects_word_boundaries() -> None:
    """'hack' inside 'hackathon' should not double-count as two terms."""
    hits = FILTER.matched_terms("Hackathon")

    assert "hackathon" in hits
    assert "hack" not in hits


def test_matched_categories_reports_the_right_bucket() -> None:
    assert "hackathon" in FILTER.get_matched_categories("Join the buildathon now")
    assert "grant" in FILTER.get_matched_categories("New funding round announced")
