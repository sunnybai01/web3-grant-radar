"""RSS fetch results must reflect whether the feed actually delivered anything.

Three enabled "RSS" sources (near_foundation, sui_foundation, sui_overflow)
returned HTML pages. feedparser parsed them into zero entries without raising,
so the sources were recorded as healthy for months while producing nothing.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.fetchers.base import FetchError
from src.fetchers.rss_fetcher import RSSFetcher


class _FakeClient:
    def __init__(self, body: str) -> None:
        self._body = body

    def get(self, url: str, timeout: float = 20.0):
        return httpx.Response(200, text=self._body, request=httpx.Request("GET", url))

    def head(self, url: str, follow_redirects: bool = True):
        return httpx.Response(200, request=httpx.Request("HEAD", url), url=url)

    def close(self) -> None:
        return None


def _fetcher(body: str) -> RSSFetcher:
    return RSSFetcher("feed", {"url": "https://example.org/feed", "fetch_method": "rss"},
                      http_client=_FakeClient(body))


def _rss(items: str) -> str:
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>Blog</title>{items}</channel></rss>'


def _item(n: int, published: datetime) -> str:
    stamp = published.strftime("%a, %d %b %Y %H:%M:%S +0000")
    return (f"<item><title>Post {n}</title><link>https://example.org/p/{n}</link>"
            f"<description>Grant round {n}</description><pubDate>{stamp}</pubDate></item>")


def test_html_page_instead_of_a_feed_is_a_fetch_error() -> None:
    page = "<!doctype html><html><head><title>Blog</title></head><body><h1>Blog</h1></body></html>"

    with pytest.raises(FetchError, match="not a valid feed"):
        _fetcher(page).fetch()


def test_feed_without_entries_is_a_fetch_error() -> None:
    with pytest.raises(FetchError, match="no entries"):
        _fetcher(_rss("")).fetch()


def test_only_the_newest_entries_are_fetched() -> None:
    """The EF blog feed carries 642 entries; reading them all would classify years of posts."""
    newest = datetime(2026, 10, 5, tzinfo=timezone.utc)
    items = "".join(_item(n, newest - timedelta(days=n)) for n in reversed(range(40)))  # oldest first

    fetched = _fetcher(_rss(items)).fetch()

    assert len(fetched) == 30
    assert fetched[0].metadata["title"] == "Post 0"
    assert {item.metadata["title"] for item in fetched} == {f"Post {n}" for n in range(30)}
