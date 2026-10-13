import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.fetchers.twitter_fetcher import TwitterFetcher


# Relative to the real clock: fetch() drops tweets older than the max age.
RECENT = datetime.now(timezone.utc) - timedelta(days=1)


class _FakeClient:
    def head(self, url: str, follow_redirects: bool = True):
        return httpx.Response(200, request=httpx.Request("HEAD", url), url=url)

    def close(self) -> None:
        return None


def test_twitter_fetcher_builds_fetched_items_from_account_timeline(monkeypatch) -> None:
    class FakeTwitterClient:
        def fetch_account_tweets(self, *, screen_name: str, count: int, cursor: str | None):
            assert screen_name == "base"
            assert count == 20
            assert cursor is None
            return [
                {
                    "id": "1001",
                    "url": "https://x.com/base/status/1001",
                    "text": "Base Builder Rewards is now open. Apply now: https://base.org/apply",
                    "author_screen_name": "base",
                    "quoted_text": "",
                    "link_urls": ["https://base.org/apply"],
                    "created_at": RECENT,
                }
            ], "NEXT_CURSOR"

    saved_state = {}

    monkeypatch.setattr("src.fetchers.twitter_fetcher.TwikitTimelineClient", lambda settings: FakeTwitterClient())
    monkeypatch.setattr(
        "src.fetchers.twitter_fetcher._save_twitter_state",
        lambda source_name, **kwargs: saved_state.update({"source_name": source_name, **kwargs}),
    )

    fetcher = TwitterFetcher(
        "twitter_base",
        {
            "screen_name": "base",
            "source_kind": "account",
            "ingestion_mode": "direct",
            "trust_tier": "official",
            "fetch_method": "twitter",
            "category": "social",
            "ecosystem": "base",
        },
        http_client=_FakeClient(),
    )

    items = fetcher.fetch()

    assert len(items) == 1
    assert items[0].source_type == "twitter"
    assert items[0].metadata["tweet_id"] == "1001"
    assert items[0].metadata["created_at"] == RECENT
    assert items[0].metadata["trust_tier"] == "official"
    assert items[0].metadata["preprocess_verdict"] == "strong_candidate"
    assert items[0].canonical_url == "https://x.com/base/status/1001"
    assert saved_state == {
        "source_name": "twitter_base",
        "last_tweet_id": "1001",
        "cursor": None,
    }


def test_twitter_fetcher_drops_discovery_noise_when_preprocessed(monkeypatch) -> None:
    class FakeTwitterClient:
        def fetch_account_tweets(self, *, screen_name: str, count: int, cursor: str | None):
            return [
                {
                    "id": "2001",
                    "url": "https://x.com/alpha/status/2001",
                    "text": "BTC looks strong today. GM everyone.",
                    "author_screen_name": "alpha_watch",
                    "quoted_text": "",
                    "link_urls": [],
                }
            ], None

    monkeypatch.setattr("src.fetchers.twitter_fetcher.TwikitTimelineClient", lambda settings: FakeTwitterClient())
    monkeypatch.setattr("src.fetchers.twitter_fetcher._save_twitter_state", lambda source_name, **kwargs: None)

    fetcher = TwitterFetcher(
        "twitter_alpha",
        {
            "screen_name": "alpha_watch",
            "source_kind": "account",
            "ingestion_mode": "preprocessed",
            "trust_tier": "discovery",
            "fetch_method": "twitter",
            "category": "social",
            "ecosystem": "multi",
        },
        http_client=_FakeClient(),
    )

    items = fetcher.fetch()

    assert items == []

def _row(tweet_id: str, created_at, text: str = "Grants round is open. Apply now.") -> dict:
    return {
        "id": tweet_id,
        "url": f"https://x.com/acct/status/{tweet_id}",
        "text": text,
        "author_screen_name": "acct",
        "quoted_text": "",
        "link_urls": [],
        "created_at": created_at,
    }


def _official_fetcher(source_kind: str = "account") -> TwitterFetcher:
    config = {
        "source_kind": source_kind,
        "ingestion_mode": "direct",
        "trust_tier": "official",
        "fetch_method": "twitter",
        "category": "social",
        "ecosystem": "multi",
    }
    if source_kind == "list":
        config["list_id"] = "123"
    else:
        config["screen_name"] = "acct"
    return TwitterFetcher("twitter_acct", config, http_client=_FakeClient())


def _wire(monkeypatch, rows):
    calls = []
    saved = {}

    class FakeTwitterClient:
        def fetch_account_tweets(self, *, screen_name, count, cursor):
            calls.append(cursor)
            return list(rows), "OLDER_PAGE_CURSOR"

        def fetch_list_tweets(self, *, list_id, count, cursor):
            calls.append(cursor)
            return list(rows), "OLDER_PAGE_CURSOR"

    monkeypatch.setattr("src.fetchers.twitter_fetcher.TwikitTimelineClient", lambda settings: FakeTwitterClient())
    monkeypatch.setattr(
        "src.fetchers.twitter_fetcher._save_twitter_state",
        lambda source_name, **kwargs: saved.update(kwargs),
    )
    return calls, saved


@pytest.mark.parametrize("source_kind", ["account", "list"])
def test_twitter_fetcher_always_reads_the_newest_page(monkeypatch, source_kind) -> None:
    """The stored Bottom cursor pointed one page further into the past on every run,
    so after the first fetch new tweets were never seen and 2022-2023 tweets were
    ingested instead (e.g. DoraHacks' BNB Grant DAO Round 3 from 2023-02)."""
    calls, saved = _wire(monkeypatch, [_row("1001", RECENT)])

    _official_fetcher(source_kind).fetch()

    assert calls == [None]
    assert saved["cursor"] is None


def test_twitter_fetcher_drops_tweets_older_than_the_max_age(monkeypatch) -> None:
    old = datetime(2023, 2, 7, 8, 0, tzinfo=timezone.utc)
    _wire(monkeypatch, [_row("1622935711409229824", old), _row("2109467576455802945", RECENT)])

    items = _official_fetcher().fetch()

    assert [item.metadata["tweet_id"] for item in items] == ["2109467576455802945"]


def test_twitter_fetcher_keeps_tweets_whose_age_is_unknown(monkeypatch) -> None:
    _wire(monkeypatch, [_row("1001", None)])

    items = _official_fetcher().fetch()

    assert [item.metadata["tweet_id"] for item in items] == ["1001"]


def test_twitter_fetcher_records_the_newest_tweet_id_not_the_pinned_one(monkeypatch) -> None:
    """The pinned tweet comes first in the timeline but is usually older."""
    rows = [
        _row("1500", RECENT - timedelta(days=5)),
        _row("2001", RECENT),
        _row("1900", RECENT - timedelta(days=1)),
    ]
    _, saved = _wire(monkeypatch, rows)

    _official_fetcher().fetch()

    assert saved["last_tweet_id"] == "2001"
