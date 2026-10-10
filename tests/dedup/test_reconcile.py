"""Vector index reconciliation: Postgres Events are the source of truth.

Regression guard for the production state where a stale docker volume mount left
only 14 of 40 Events indexed, so L2 dedup could not match the other 26.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.db.database import Base
from src.db.models import Event, EventSource
from src.dedup.reconcile import reconcile_vector_index

NOW = datetime.now(timezone.utc)


class FakeVectorStore:
    def __init__(self, indexed_ids=()):
        self._ids = set(indexed_ids)
        self.added = []

    def existing_ids(self):
        return set(self._ids)

    def add(self, doc_id, text, metadata=None):
        self.added.append((doc_id, text, metadata))
        self._ids.add(doc_id)


class FakeVectorStoreThatCannotList:
    def existing_ids(self):
        raise RuntimeError("chroma unreachable")


def _db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine, tables=[Event.__table__, EventSource.__table__])
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def _event(db, title, **kwargs) -> Event:
    kwargs.setdefault("event_type", "grant")
    kwargs.setdefault("created_at", NOW - timedelta(days=1))
    event = Event(title=title, **kwargs)
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def test_missing_events_are_reindexed() -> None:
    db = _db_session()
    try:
        indexed = _event(db, "Already indexed")
        missing_a = _event(db, "Missing A")
        missing_b = _event(db, "Missing B")

        store = FakeVectorStore(indexed_ids=[f"event_{indexed.id}"])

        summary = reconcile_vector_index(db, store)

        assert summary == {"candidates": 3, "missing": 2, "indexed": 2, "failed": 0}
        assert {doc_id for doc_id, _, _ in store.added} == {
            f"event_{missing_a.id}", f"event_{missing_b.id}"
        }
    finally:
        db.close()


def test_fully_indexed_corpus_is_a_no_op() -> None:
    db = _db_session()
    try:
        event = _event(db, "Only event")
        store = FakeVectorStore(indexed_ids=[f"event_{event.id}"])

        summary = reconcile_vector_index(db, store)

        assert summary["missing"] == 0
        assert store.added == []
    finally:
        db.close()


def test_open_opportunity_older_than_the_window_is_still_reconciled() -> None:
    """Deadline in the future keeps an Event dedup-relevant regardless of age."""
    db = _db_session()
    try:
        old_open = _event(
            db, "Long running program",
            created_at=NOW - timedelta(days=120),
            deadline=NOW + timedelta(days=30),
        )
        store = FakeVectorStore()

        summary = reconcile_vector_index(db, store)

        assert summary["indexed"] == 1
        assert store.added[0][0] == f"event_{old_open.id}"
    finally:
        db.close()


def test_stale_closed_event_is_not_reconciled() -> None:
    db = _db_session()
    try:
        _event(
            db, "Long dead program",
            created_at=NOW - timedelta(days=120),
            deadline=NOW - timedelta(days=100),
        )
        store = FakeVectorStore()

        summary = reconcile_vector_index(db, store)

        assert summary["candidates"] == 0
        assert store.added == []
    finally:
        db.close()


def test_unreachable_index_degrades_without_raising() -> None:
    db = _db_session()
    try:
        _event(db, "Something")
        summary = reconcile_vector_index(
            db, FakeVectorStoreThatCannotList()
        )

        assert summary["candidates"] == 1
        assert summary["failed"] == 1
        assert summary["indexed"] == 0
    finally:
        db.close()
