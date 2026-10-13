"""L2 dedup for structured platform listings (one item per opportunity).

On its first run, superteam_grants' 47 live grants collapsed into four Events:
the grant texts share one template, so "Solana Foundation Korea Grants" and
"... Malaysia Grants" embedded as near-duplicates, and #178 absorbed 24
unrelated grants. A platform lists each opportunity once under its own URL, so
two listings from the same source with different URLs are different
opportunities, and the same listing URL is always the same opportunity.
"""
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.db.database import Base
from src.db.models import Event, EventSource
from src.dedup.content_dedup import ContentDeduplicator


class FakeVectorStore:
    def __init__(self, results=None):
        self.results = results or []

    def search_similar(self, text, n_results=5, where=None):
        return list(self.results)

    def add(self, doc_id, text, metadata=None):
        pass


class NullSummary:
    def get_embedding_text(self, title, description):
        return f"{title} {description}".strip()


def _db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine, tables=[Event.__table__, EventSource.__table__])
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def _grant(title: str) -> dict:
    return {
        "event_type": "grant",
        "title": title,
        "description": "Grant on Superteam Earn (Solana ecosystem). Reward: up to 10,000 USDG per project.",
        "ecosystem": "solana",
    }


def _process(db, store, title, url, source_type="superteam_grants", source_name="superteam_grants"):
    return ContentDeduplicator(store, llm_extractor=NullSummary()).check_and_process(
        db, _grant(title), source_type=source_type, source_name=source_name, source_url=url,
    )


KOREA = "https://superteam.fun/earn/grants/korea"
MALAYSIA = "https://superteam.fun/earn/grants/malaysia"


def test_distinct_listings_from_one_platform_are_never_merged() -> None:
    db = _db_session()
    try:
        korea_id, _ = _process(db, FakeVectorStore(), "Solana Foundation Korea Grants", KOREA)
        near_identical = FakeVectorStore(results=[(f"event_{korea_id}", 0.02, {})])

        malaysia_id, is_new = _process(db, near_identical, "Solana Foundation Malaysia Grants", MALAYSIA)

        assert is_new is True
        assert malaysia_id != korea_id
    finally:
        db.close()


def test_a_listing_seen_again_with_changed_text_maps_to_its_own_event() -> None:
    db = _db_session()
    try:
        korea_id, _ = _process(db, FakeVectorStore(), "Solana Foundation Korea Grants", KOREA)

        again_id, is_new = _process(db, FakeVectorStore(), "Solana Foundation Korea Grants (round 2 budget)", KOREA)

        assert is_new is False
        assert again_id == korea_id
    finally:
        db.close()


def test_other_sources_still_merge_into_a_listing_event() -> None:
    db = _db_session()
    try:
        korea_id, _ = _process(db, FakeVectorStore(), "Solana Foundation Korea Grants", KOREA)
        similar = FakeVectorStore(results=[(f"event_{korea_id}", 0.05, {})])

        tweet_id, is_new = _process(
            db, similar, "Solana Foundation Korea Grants", "https://x.com/SuperteamKorea/status/1",
            source_type="twitter", source_name="twitter_superteamkorea",
        )

        assert is_new is False
        assert tweet_id == korea_id
    finally:
        db.close()
