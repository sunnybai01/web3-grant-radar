"""RSS / Atom feed fetcher."""
import logging
from typing import List, Optional
from datetime import datetime, timezone
import hashlib

import feedparser
import httpx

from config.settings import settings

from .base import BaseFetcher, FetchedItem, FetchError

logger = logging.getLogger(__name__)


class RSSFetcher(BaseFetcher):
    """Fetches items from RSS/Atom feeds."""

    source_type = "rss"

    def fetch(self) -> List[FetchedItem]:
        url = self.config.get("url", "")
        if not url:
            raise FetchError(f"RSS source '{self.source_name}' has no URL configured")

        try:
            resp = self._client.get(url, timeout=20.0)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.error(f"RSS fetch failed for {self.source_name}: {e}")
            raise FetchError(str(e)) from e

        feed = feedparser.parse(resp.text)
        if not feed.entries:
            # feedparser turns an HTML page into zero entries without raising, which
            # recorded broken feeds as healthy for months. An empty result is a failure.
            if not feed.get("version"):
                raise FetchError(
                    f"{url} is not a valid feed "
                    f"(content-type {resp.headers.get('content-type', 'unknown')})"
                )
            raise FetchError(f"feed {url} has no entries")

        items = []

        for entry in _newest_entries(feed.entries, settings.RSS_MAX_ENTRIES):
            raw_url = entry.get("link", "")
            canonical = self._canonicalize_url(raw_url)

            # Use the feed item title + summary as raw content
            title = entry.get("title", "")
            summary = entry.get("summary", entry.get("description", ""))
            raw_content = f"{title}\n\n{summary}"

            content_hash = hashlib.sha256(raw_content.encode()).hexdigest()

            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                except Exception:
                    pass

            items.append(FetchedItem(
                source_type=self.source_type,
                source_name=self.source_name,
                raw_content=raw_content,
                raw_url=raw_url,
                canonical_url=canonical,
                metadata=self._enrich({
                    "title": title,
                    "published": published,
                    "content_hash": content_hash,
                    "ecosystem": self.config.get("ecosystem"),
                    "category": self.config.get("category"),
                }),
            ))

        return items


def _newest_entries(entries, limit: int):
    """The ``limit`` most recent entries; undated ones keep their feed order after dated ones."""
    dated = [e for e in entries if e.get("published_parsed") or e.get("updated_parsed")]
    if not dated:
        return list(entries)[:limit]
    undated = [e for e in entries if not (e.get("published_parsed") or e.get("updated_parsed"))]
    dated.sort(key=lambda e: tuple(e.get("published_parsed") or e.get("updated_parsed")), reverse=True)
    return (dated + undated)[:limit]
