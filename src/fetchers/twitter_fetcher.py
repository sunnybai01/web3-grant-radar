"""Twitter/X fetcher via Twikit-backed authenticated timelines."""
import logging
from datetime import datetime, timedelta, timezone
from typing import List
import hashlib

from config.settings import settings

from .base import BaseFetcher, FetchedItem, FetchError
from .twitter_client import TwikitTimelineClient
from .twitter_social import build_tweet_raw_content, preprocess_tweet

logger = logging.getLogger(__name__)


def _tweet_id_value(tweet_id) -> int:
    try:
        return int(tweet_id)
    except (TypeError, ValueError):
        return -1


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _save_twitter_state(source_name: str, **kwargs) -> None:
    from src.db.database import SessionLocal
    from src.db.queries import upsert_twitter_source_state

    db = SessionLocal()
    try:
        upsert_twitter_source_state(db, source_name, **kwargs)
    finally:
        db.close()


class TwitterFetcher(BaseFetcher):
    """Fetches tweets from Twitter accounts or Lists via Twikit."""

    source_type = "twitter"

    def fetch(self) -> List[FetchedItem]:
        # Always read the newest page. The timeline's next cursor points to OLDER
        # tweets; persisting and reusing it walked each account backwards one page
        # per run, so new tweets were never seen and years-old ones were ingested.
        # Already-seen tweets are dropped by L1 dedup.
        cursor = None
        count = int(self.config.get("count") or settings.TWITTER_FETCH_COUNT)
        min_created_at = datetime.now(timezone.utc) - timedelta(
            days=max(1, int(settings.TWITTER_MAX_TWEET_AGE_DAYS))
        )
        source_kind = self.config.get("source_kind", "account")
        client = TwikitTimelineClient(settings)

        try:
            if source_kind == "list":
                list_id = self.config.get("list_id", "")
                if not list_id:
                    raise FetchError(f"Twitter list source '{self.source_name}' has no list_id")
                rows, _older_page_cursor = client.fetch_list_tweets(
                    list_id=list_id,
                    count=count,
                    cursor=cursor,
                )
            else:
                screen_name = self.config.get("screen_name", "")
                if not screen_name:
                    raise FetchError(f"Twitter source '{self.source_name}' has no screen_name")
                rows, _older_page_cursor = client.fetch_account_tweets(
                    screen_name=screen_name,
                    count=count,
                    cursor=cursor,
                )
        except Exception as e:
            logger.error("Twitter fetch failed for %s: %s", self.source_name, e)
            raise FetchError(str(e)) from e

        items = []
        latest_tweet_id = None
        trust_tier = self.config.get("trust_tier") or "official"
        for row in rows:
            tweet_id = row.get("id", "")
            # Track the newest id by value: the pinned tweet comes first in the
            # timeline but is usually older than the rest of the page.
            if _tweet_id_value(tweet_id) > _tweet_id_value(latest_tweet_id):
                latest_tweet_id = tweet_id

            created_at = row.get("created_at")
            if isinstance(created_at, datetime) and _as_utc(created_at) < min_created_at:
                logger.debug(
                    "Skip tweet %s from %s: created %s is older than %d days",
                    tweet_id, self.source_name, created_at.date(),
                    settings.TWITTER_MAX_TWEET_AGE_DAYS,
                )
                continue

            row["source_kind"] = source_kind
            decision = preprocess_tweet(row, trust_tier=trust_tier)
            if self.config.get("ingestion_mode") == "preprocessed" and decision["verdict"] == "drop":
                continue

            raw_url = row.get("url", "")
            raw_content = build_tweet_raw_content(row)
            canonical = self._canonicalize_url(raw_url) if raw_url else ""

            items.append(
                FetchedItem(
                    source_type=self.source_type,
                    source_name=self.source_name,
                    raw_content=raw_content,
                    raw_url=raw_url,
                    canonical_url=canonical,
                    metadata=self._enrich({
                        "title": (row.get("text", "") or "")[:120],
                        "platform": "twitter",
                        "tweet_id": tweet_id,
                        "created_at": row.get("created_at"),
                        "author_screen_name": row.get("author_screen_name", ""),
                        "trust_tier": trust_tier,
                        "ingestion_mode": self.config.get("ingestion_mode"),
                        "source_kind": source_kind,
                        "preprocess_verdict": decision["verdict"],
                        "has_official_link": decision["has_official_link"],
                        "content_hash": hashlib.sha256(raw_content.encode()).hexdigest(),
                        "ecosystem": self.config.get("ecosystem"),
                        "category": self.config.get("category"),
                    }),
                )
            )

        _save_twitter_state(
            self.source_name,
            last_tweet_id=latest_tweet_id,
            cursor=None,
        )

        return items
