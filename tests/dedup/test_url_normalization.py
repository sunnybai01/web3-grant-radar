"""URL canonicalisation and content normalisation for L1 dedup.

Production evidence: http/https, www/no-www, default ports, parameter order and
the x.com/twitter.com pair were all stored as distinct keys (two signals held the
*same* content hash under `http://suilend.fi/` and `https://suilend.fi/`), and
content hashing over raw page text only ever caught byte-identical refetches
(blog.arbitrum.foundation held 20 signals / 20 hashes).
"""
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.dedup.url_dedup import generate_content_hash, normalize_content, normalize_url


def test_url_equivalences_that_used_to_differ() -> None:
    pairs = [
        ("http://example.com/a", "https://example.com/a"),
        ("https://www.example.com/a", "https://example.com/a"),
        ("https://example.com:443/a", "https://example.com/a"),
        ("http://example.com:80/a", "https://example.com/a"),
        ("https://example.com/a?b=2&a=1", "https://example.com/a?a=1&b=2"),
        ("https://example.com/a?utm_source=x&utm_id=9", "https://example.com/a"),
        ("https://example.com/a?FBclid=1", "https://example.com/a"),
        ("https://x.com/i/status/1", "https://twitter.com/i/status/1"),
        ("https://mobile.twitter.com/i/status/1", "https://x.com/i/status/1"),
        ("https://example.com/a/", "https://example.com/a"),
        ("https://example.com/a#section", "https://example.com/a"),
        ("https://example.com//a//b", "https://example.com/a/b"),
        ("https://EXAMPLE.com/A", "https://example.com/A"),
    ]
    for left, right in pairs:
        assert normalize_url(left) == normalize_url(right), f"{left} != {right}"


def test_relevant_query_params_are_preserved() -> None:
    assert normalize_url("https://example.com/apply?round=3") == "https://example.com/apply?round=3"
    assert normalize_url("https://example.com/a?id=7") != normalize_url("https://example.com/a?id=8")


def test_non_web_schemes_are_dropped() -> None:
    for url in ["mailto:hi@example.com", "javascript:void(0)", "data:text/plain,x", "tel:+1234"]:
        assert normalize_url(url) == ""


def test_relative_urls_are_joined_against_the_base() -> None:
    assert normalize_url("/apply", base_url="https://example.com/grants") == "https://example.com/apply"
    assert normalize_url("/", base_url="https://hackathon.monad.xyz/") == "https://hackathon.monad.xyz/"


def test_hash_routed_spa_keeps_its_host() -> None:
    assert normalize_url("https://sui.io/#/hackathon/123") == "https://sui.io/"


def test_empty_input() -> None:
    assert normalize_url("") == ""
    assert normalize_url(None) == ""


# ---------------------------------------------------------------------------
# Content normalisation
# ---------------------------------------------------------------------------

def test_content_hash_ignores_timestamps_and_whitespace() -> None:
    a = normalize_content("Grants open now   2026-10-10 01:04\n\nApply today")
    b = normalize_content("Grants open now 2026-10-11T09:31:00Z\nApply today")

    assert generate_content_hash(a) == generate_content_hash(b)


def test_content_hash_still_separates_real_changes() -> None:
    a = generate_content_hash(normalize_content("Grants open now"))
    b = generate_content_hash(normalize_content("Grants have closed"))

    assert a != b


def test_zero_width_characters_are_stripped() -> None:
    assert normalize_content("gra\u200bnt") == normalize_content("grant")


@pytest.mark.parametrize("value", ["", None])
def test_empty_content_is_empty(value) -> None:
    assert normalize_content(value) == ""
