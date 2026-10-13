"""L2 dedup: identity, consistent embeddings, last-seen windows, field backfill.

Duplicates still in production on 2026-10-12, by cause:
* the same tweet produced two Events (#159/#168, #157/#161): source URLs were
  never used as an identity key;
* incoming items were embedded as an LLM summary with a
  "| deadline:… | ecosystem:…" suffix, stored Events as title + description, so
  the two sides never compared like with like;
* evergreen programs without a deadline stopped being matchable 21 days after
  their first sighting however often they were re-posted (Base Builder Grant
  #100/#101/#114, Arbitrum Open House #108/#121/#149);
* "ETHGlobal Mumbai Hackathon" (#172, deadline 11-07) and "ETHGlobal Mumbai"
  (#176, application deadline 11-03) were vetoed as different editions;
* a merge kept the first source's empty deadline/amount/apply link even when a
  later source stated them.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.classifier.ecosystem import normalize_ecosystem
from src.db.database import Base
from src.db.models import Event, EventSource
from src.dedup.content_dedup import ContentDeduplicator, raw_embedding_text, title_key
from src.dedup.reconcile import _candidate_events

NOW = datetime.now(timezone.utc)


class RecordingVectorStore:
    def __init__(self, results=None):
        self.results = results or []
        self.queries = []
        self.added = []

    def search_similar(self, text, n_results=5, where=None):
        self.queries.append(text)
        return list(self.results)

    def add(self, doc_id, text, metadata=None):
        self.added.append((doc_id, text))



def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine, tables=[Event.__table__, EventSource.__table__])
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def _dedup(store=None):
    return ContentDeduplicator(store or RecordingVectorStore())


def _event(db, title="Base Builder Grant Program", **kwargs) -> Event:
    kwargs.setdefault("event_type", "grant")
    kwargs.setdefault("created_at", NOW - timedelta(days=1))
    event = Event(title=title, **kwargs)
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def _source(db, event, url, fetched_at=None, name="twitter_dorahacks"):
    db.add(EventSource(event_id=event.id, source_type="twitter", source_name=name,
                       source_url=url, fetched_at=fetched_at or NOW))
    db.commit()


TWEET = "https://x.com/DoraHacks/status/1622935711409229824"


def test_the_same_source_url_is_always_the_same_event() -> None:
    db = _db()
    try:
        first = _event(db, title="BNB Grant DAO Round 3 - Open for Project Submissions")
        _source(db, first, TWEET)

        event_id, is_new = _dedup().check_and_process(
            db, {"event_type": "grant", "title": "BNB Grant DAO Round 3 - $30K Grant Pool"},
            source_type="twitter", source_name="twitter_dorahacks", source_url=TWEET,
        )

        assert (event_id, is_new) == (first.id, False)
    finally:
        db.close()


def test_incoming_items_are_embedded_like_stored_events() -> None:
    db = _db()
    try:
        store = RecordingVectorStore()
        _dedup(store).check_and_process(
            db, {"event_type": "grant", "title": "Starknet Seed Grants", "description": "Up to $25K."},
            source_type="rss", source_name="starknet_blog", source_url="https://example.org/a",
        )

        expected = raw_embedding_text("Starknet Seed Grants", "Up to $25K.")
        assert store.queries == [expected]
        assert store.added[0][1] == expected
    finally:
        db.close()


def test_a_program_seen_again_recently_stays_matchable() -> None:
    db = _db()
    try:
        evergreen = _event(db, created_at=NOW - timedelta(days=60))
        _source(db, evergreen, "https://x.com/base/status/1", fetched_at=NOW - timedelta(days=60))
        _source(db, evergreen, "https://x.com/base/status/2", fetched_at=NOW - timedelta(days=5))

        assert _dedup()._is_matchable(db, evergreen, now=NOW) is True
    finally:
        db.close()


def test_a_program_not_seen_for_longer_than_the_window_is_not_matchable() -> None:
    db = _db()
    try:
        gone = _event(db, created_at=NOW - timedelta(days=90))
        _source(db, gone, "https://x.com/base/status/1", fetched_at=NOW - timedelta(days=40))

        assert _dedup()._is_matchable(db, gone, now=NOW) is False
    finally:
        db.close()


def test_reconciliation_keeps_recently_seen_programs_indexed() -> None:
    db = _db()
    try:
        evergreen = _event(db, created_at=NOW - timedelta(days=60))
        _source(db, evergreen, "https://x.com/base/status/2", fetched_at=NOW - timedelta(days=5))

        assert evergreen.id in {e.id for e in _candidate_events(db)}
    finally:
        db.close()


def test_ecosystem_aliases_name_the_same_chain() -> None:
    assert normalize_ecosystem("BNB Chain") == normalize_ecosystem("binance") == "bnb"
    assert normalize_ecosystem("Sui Network") == "sui"
    assert normalize_ecosystem("arbitrum one") == "arbitrum"
    assert normalize_ecosystem("multi") == normalize_ecosystem("Cross-chain") == "multi"
    assert normalize_ecosystem("ethereum") == "ethereum"
    assert normalize_ecosystem("") is None


def test_a_multichain_item_does_not_veto_a_chain_specific_event() -> None:
    db = _db()
    try:
        eth = _event(db, title="Account Abstraction Grants Round", ecosystem="ethereum")
        store = RecordingVectorStore([(f"event_{eth.id}", 0.05, {})])

        event_id, _ = _dedup(store).check_and_process(
            db, {"event_type": "grant", "title": "Account Abstraction Grants Round", "ecosystem": "multi"},
            source_type="rss", source_name="feed", source_url="https://example.org/aa",
        )

        assert event_id == eth.id
    finally:
        db.close()


def test_ecosystem_aliases_do_not_veto_a_match() -> None:
    db = _db()
    try:
        bnb = _event(db, title="BNB Grant DAO Round 3", ecosystem="binance")
        store = RecordingVectorStore([(f"event_{bnb.id}", 0.05, {})])

        event_id, is_new = _dedup(store).check_and_process(
            db, {"event_type": "grant", "title": "BNB Grant DAO Round 3", "ecosystem": "BNB Chain"},
            source_type="rss", source_name="feed", source_url="https://example.org/bnb",
        )

        assert (event_id, is_new) == (bnb.id, False)
    finally:
        db.close()


def test_a_merge_fills_fields_the_event_was_missing() -> None:
    db = _db()
    try:
        event = _event(db, title="Arbitrum Open House Buildathon", amount="$415k")
        store = RecordingVectorStore([(f"event_{event.id}", 0.05, {})])
        deadline = NOW + timedelta(days=12)

        _dedup(store).check_and_process(
            db,
            {"event_type": "hackathon", "title": "Arbitrum Open House Buildathon", "amount": "$115K",
             "deadline": deadline, "application_url": "https://openhouse.arbitrum.io/apply"},
            source_type="rss", source_name="feed", source_url="https://example.org/oh",
        )

        db.refresh(event)
        assert event.amount == "$415k"  # a stated value is never overwritten
        assert event.application_url == "https://openhouse.arbitrum.io/apply"
        assert event.deadline.replace(tzinfo=timezone.utc) == deadline
    finally:
        db.close()


def test_title_key_ignores_generic_words_but_keeps_what_tells_programs_apart() -> None:
    assert title_key("ETHGlobal Mumbai Hackathon") == title_key("ETHGlobal Mumbai")
    assert title_key("Base Builder Grants") == title_key("Base Builder Grant Program")
    assert title_key("Starknet Seed Grants") != title_key("Starknet Growth Grants")
    assert title_key("ETHGlobal Tokyo 2026") != title_key("ETHGlobal Tokyo 2025")


def test_application_and_event_end_dates_are_not_different_editions() -> None:
    db = _db()
    try:
        tweet = _event(db, title="ETHGlobal Mumbai Hackathon", event_type="hackathon",
                       deadline=datetime(2026, 11, 7, tzinfo=timezone.utc))
        store = RecordingVectorStore([(f"event_{tweet.id}", 0.30, {})])

        event_id, is_new = _dedup(store).check_and_process(
            db, {"event_type": "hackathon", "title": "ETHGlobal Mumbai",
                 "deadline": datetime(2026, 11, 3, tzinfo=timezone.utc)},
            source_type="ethglobal_events", source_name="ethglobal_events",
            source_url="https://ethglobal.com/events/mumbai",
        )

        assert (event_id, is_new) == (tweet.id, False)
    finally:
        db.close()


def test_a_url_shared_by_several_events_is_not_an_identity() -> None:
    """Before listing pages were split per card, #148 "Founder House Singapore" and
    #149 "Arbitrum Open House Buildathon" both carried the blog's front page as
    their source URL. Such a URL says nothing about which opportunity it is."""
    db = _db()
    try:
        listing = "https://blog.arbitrum.foundation/"
        founder = _event(db, title="Founder House Singapore", ecosystem="arbitrum")
        buildathon = _event(db, title="Arbitrum Open House Buildathon", ecosystem="arbitrum")
        _source(db, founder, listing, name="arbitrum_foundation_blog")
        _source(db, buildathon, listing, name="arbitrum_foundation_blog")
        unrelated = RecordingVectorStore([(f"event_{founder.id}", 0.60, {})])

        event_id, is_new = _dedup(unrelated).check_and_process(
            db, {"event_type": "grant", "title": "Arbitrum Audit Program", "ecosystem": "arbitrum"},
            source_type="web_scraper", source_name="arbitrum_foundation_blog", source_url=listing,
        )

        assert is_new is True
        assert event_id not in (founder.id, buildathon.id)
    finally:
        db.close()
