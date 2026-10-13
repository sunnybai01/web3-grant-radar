"""L2 semantic dedup matching rules.

Regression guards for three production defects:
  * the window used Event.created_at only, so a repost 50 seconds after the
    cutoff minted a second Event for the same opportunity (#120 vs #132);
  * an out-of-window candidate discarded the whole candidate list instead of
    falling through to the next one;
  * a broken vector index (search raised / returned nothing) was treated as
    "no duplicate", silently creating duplicates.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.db.database import Base
from src.db.models import Event, EventSource
from src.dedup.content_dedup import ContentDeduplicator, normalize_title

NOW = datetime(2026, 9, 22, 1, 5, tzinfo=timezone.utc)


class FakeVectorStore:
    """Returns a scripted candidate list; records what was indexed."""

    def __init__(self, results=None, raise_on_search=False):
        self.results = results or []
        self.raise_on_search = raise_on_search
        self.added = []

    def search_similar(self, text, n_results=5, where=None):
        if self.raise_on_search:
            raise RuntimeError("chroma down")
        return list(self.results)

    def add(self, doc_id, text, metadata=None):
        self.added.append((doc_id, text, metadata))



def _db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine, tables=[Event.__table__, EventSource.__table__])
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def _event(db, **kwargs) -> Event:
    kwargs.setdefault("event_type", "hackathon")
    kwargs.setdefault("title", "Solana Mobile CLOCK IN Hackathon")
    event = Event(**kwargs)
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def _dedup(store) -> ContentDeduplicator:
    return ContentDeduplicator(store)


def test_normalize_title_ignores_case_punctuation_and_emoji() -> None:
    assert normalize_title("Base Builder Grant Program!") == normalize_title("base  builder grant program")
    assert normalize_title("🏆 Base Builder Grant Program") == "base builder grant program"


def test_open_deadline_keeps_event_matchable_past_the_window() -> None:
    """#120 was created 2026-09-08 and duplicated by #132 on 2026-09-22."""
    db = _db_session()
    try:
        old = _event(
            db,
            created_at=NOW - timedelta(days=20),
            deadline=NOW + timedelta(days=10),
        )
        assert _dedup(FakeVectorStore()).is_matchable(old, now=NOW) is True

        # Outside both the window and the deadline: nothing left to match against.
        ancient = _event(
            db,
            title="Closed program",
            created_at=NOW - timedelta(days=60),
            deadline=NOW - timedelta(days=30),
        )
        assert _dedup(FakeVectorStore()).is_matchable(ancient, now=NOW) is False

        # An expired deadline alone does not unmatch a recent Event: the pipeline
        # decides whether the *incoming* item is stale, and a late repost of a
        # just-published listing should merge rather than duplicate.
        expired_recently = _event(
            db,
            title="Just closed",
            created_at=NOW - timedelta(days=2),
            deadline=NOW - timedelta(days=1),
        )
        assert _dedup(FakeVectorStore()).is_matchable(expired_recently, now=NOW) is True
    finally:
        db.close()


def test_repost_fifty_seconds_after_cutoff_merges() -> None:
    db = _db_session()
    try:
        existing = _event(
            db,
            title="Solana Mobile CLOCK IN Hackathon",
            created_at=NOW - timedelta(days=14, seconds=50),
            deadline=NOW + timedelta(days=20),
        )
        store = FakeVectorStore([(f"event_{existing.id}", 1.0 - 0.8837, {})])

        matched = _dedup(store)._find_match(
            db,
            query_text="Solana CLOCK IN Hackathon by RadiantsDAO",
            incoming_title="Solana CLOCK IN Hackathon by RadiantsDAO",
            incoming_deadline=NOW + timedelta(days=20),
            incoming_ecosystem="solana",
            now=NOW,
        )

        assert matched == existing.id
    finally:
        db.close()


def test_out_of_window_candidate_does_not_discard_later_match() -> None:
    """The old loop set matched_event_id = None on an out-of-window hit."""
    db = _db_session()
    try:
        stale = _event(
            db, title="Old unrelated program",
            created_at=NOW - timedelta(days=90), deadline=NOW - timedelta(days=60),
        )
        live = _event(
            db, title="Solana Mobile CLOCK IN Hackathon",
            created_at=NOW - timedelta(days=2), deadline=NOW + timedelta(days=5),
        )
        store = FakeVectorStore([
            (f"event_{stale.id}", 1.0 - 0.99, {}),   # nearest, but out of window
            (f"event_{live.id}", 1.0 - 0.8837, {}),  # real duplicate
        ])

        matched = _dedup(store)._find_match(
            db,
            query_text="Solana CLOCK IN Hackathon",
            incoming_title="Solana CLOCK IN Hackathon",
            incoming_deadline=NOW + timedelta(days=5),
            incoming_ecosystem="solana",
            now=NOW,
        )

        assert matched == live.id
    finally:
        db.close()


def test_differing_deadline_vetoes_a_high_similarity_match() -> None:
    """A new round of the same program is a new opportunity, not a duplicate."""
    db = _db_session()
    try:
        round_one = _event(
            db, title="ETHIndia Hackathon",
            created_at=NOW - timedelta(days=3), deadline=NOW + timedelta(days=7),
        )
        store = FakeVectorStore([(f"event_{round_one.id}", 1.0 - 0.99, {})])

        matched = _dedup(store)._find_match(
            db,
            query_text="ETHIndia Hackathon 2027 edition",
            incoming_title="ETHIndia Hackathon 2027 edition",
            incoming_deadline=NOW + timedelta(days=400),
            incoming_ecosystem=None,
            now=NOW,
        )

        assert matched is None
    finally:
        db.close()


def test_differing_ecosystem_vetoes_the_match() -> None:
    db = _db_session()
    try:
        solana = _event(
            db, title="Builder Grant Program", ecosystem="solana",
            created_at=NOW - timedelta(days=1), deadline=NOW + timedelta(days=30),
        )
        store = FakeVectorStore([(f"event_{solana.id}", 1.0 - 0.97, {})])

        matched = _dedup(store)._find_match(
            db,
            query_text="Builder Grant Program",
            incoming_title="Builder Grant Program",
            incoming_deadline=NOW + timedelta(days=30),
            incoming_ecosystem="ethereum",
            now=NOW,
        )

        assert matched is None
    finally:
        db.close()


def test_exact_title_twin_merges_below_the_similarity_threshold() -> None:
    """Base Builder Grant Program reposts are identical titles far apart in time."""
    db = _db_session()
    try:
        existing = _event(
            db, title="Base Builder Grant Program", event_type="grant",
            created_at=NOW - timedelta(days=1), deadline=None,
        )
        store = FakeVectorStore([(f"event_{existing.id}", 1.0 - 0.40, {})])

        matched = _dedup(store)._find_match(
            db,
            query_text="Base Builder Grant Program",
            incoming_title="Base Builder Grant Program",
            incoming_deadline=None,
            incoming_ecosystem=None,
            now=NOW,
        )

        assert matched == existing.id
    finally:
        db.close()


def test_broken_index_raises_instead_of_reporting_no_duplicate() -> None:
    db = _db_session()
    try:
        store = FakeVectorStore(raise_on_search=True)
        with pytest.raises(RuntimeError):
            _dedup(store)._find_match(
                db,
                query_text="anything",
                incoming_title="anything",
                incoming_deadline=None,
                incoming_ecosystem=None,
                now=NOW,
            )
    finally:
        db.close()


def test_new_event_is_indexed_with_deadline_metadata() -> None:
    db = _db_session()
    try:
        store = FakeVectorStore([])
        dedup = _dedup(store)

        event_id, is_new = dedup.check_and_process(
            db,
            {
                "event_type": "hackathon",
                "title": "Fresh Hackathon",
                "description": "desc",
                "deadline": NOW + timedelta(days=9),
                "ecosystem": "solana",
            },
            source_type="tavily_search",
            source_name="tavily_solana_grants",
            source_url="https://example.org/fresh",
        )

        assert is_new is True
        assert store.added and store.added[0][0] == f"event_{event_id}"
        assert store.added[0][2]["deadline"].startswith("2026-10-01")
    finally:
        db.close()
