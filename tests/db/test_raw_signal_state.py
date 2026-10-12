"""Recording the outcome of processing a raw signal."""
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.db.database import Base
from src.db.models import Event, EventSource, RawSignal
from src.db.queries import insert_raw_signal, mark_raw_signal_processed


def _db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        bind=engine, tables=[RawSignal.__table__, Event.__table__, EventSource.__table__]
    )
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def _signal(db, content_hash="h1") -> RawSignal:
    return insert_raw_signal(
        db, source_type="rss", source_name="feed", raw_content="Grant A",
        raw_url="https://example.org/a", canonical_url="https://example.org/a",
        content_hash=content_hash,
    )


def test_new_signal_starts_pending_on_its_first_attempt() -> None:
    db = _db_session()
    try:
        signal = _signal(db)

        assert signal.status == "pending"
        assert signal.attempts == 1
    finally:
        db.close()


def test_processed_signal_is_done_and_keeps_no_error() -> None:
    db = _db_session()
    try:
        signal = _signal(db)

        mark_raw_signal_processed(db, signal.id)

        db.refresh(signal)
        assert signal.status == "done"
        assert signal.last_error is None
        assert signal.processed_at is not None
    finally:
        db.close()


def test_failed_signal_records_the_error() -> None:
    db = _db_session()
    try:
        signal = _signal(db)

        mark_raw_signal_processed(db, signal.id, error="classification_failed: timeout")

        db.refresh(signal)
        assert signal.status == "failed"
        assert signal.last_error == "classification_failed: timeout"
    finally:
        db.close()


def test_failure_after_the_event_was_created_is_not_retried() -> None:
    """Retrying would mint a second Event if L2 missed the first one."""
    db = _db_session()
    try:
        signal = _signal(db)
        event = Event(event_type="grant", title="Grant A")
        db.add(event)
        db.commit()
        db.add(EventSource(event_id=event.id, source_type="rss", source_name="feed",
                           source_url="https://example.org/a", raw_signal_id=signal.id))
        db.commit()

        mark_raw_signal_processed(db, signal.id, error="SlackApiError: boom")

        db.refresh(signal)
        assert signal.status == "done"
        assert signal.last_error == "SlackApiError: boom"
    finally:
        db.close()


def test_duplicate_insert_race_is_reported_as_a_duplicate() -> None:
    db = _db_session()
    try:
        _signal(db)

        assert _signal(db) is None
    finally:
        db.close()


def test_other_insert_errors_are_not_disguised_as_duplicates() -> None:
    """A failed write used to return None and be counted as "deduped"."""
    db = _db_session()
    try:
        with pytest.raises(TypeError):
            insert_raw_signal(db, source_type="rss", not_a_column="x")
    finally:
        db.close()
