"""add_event_source must be idempotent on (event_id, source_url).

Regression guard for the production crash where two sources surfaced the same
article URL in one run, the second INSERT violated uq_event_source_url, and the
resulting IntegrityError aborted the whole pipeline — permanently losing every
remaining item of that batch.
"""
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.db.database import Base
from src.db.models import Event, EventSource
from src.db.queries import add_event_source


def _db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine, tables=[Event.__table__, EventSource.__table__])
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def _make_event(db) -> Event:
    event = Event(event_type="grant", title="Solana Mobile CLOCK IN Hackathon")
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def test_same_url_twice_returns_existing_row_without_raising() -> None:
    db = _db_session()
    try:
        event = _make_event(db)
        url = "https://ua.news/en/ukraine/solana-colosseum"

        first = add_event_source(
            db, event_id=event.id, source_type="tavily_search",
            source_name="tavily_solana_grants", source_url=url, raw_signal_id=None,
        )
        second = add_event_source(
            db, event_id=event.id, source_type="tavily_search",
            source_name="tavily_base_grants", source_url=url, raw_signal_id=None,
        )

        assert first.id == second.id
        assert db.query(EventSource).count() == 1
    finally:
        db.close()


def test_distinct_urls_and_names_are_all_recorded() -> None:
    db = _db_session()
    try:
        event = _make_event(db)
        add_event_source(db, event_id=event.id, source_type="rss",
                         source_name="avalanche_blog", source_url="https://a.example/1")
        add_event_source(db, event_id=event.id, source_type="rss",
                         source_name="avalanche_blog", source_url="https://a.example/2")

        assert db.query(EventSource).count() == 2
    finally:
        db.close()


def test_null_urls_are_deduplicated_per_event() -> None:
    """Postgres treats NULLs as distinct; we still want one source row per event."""
    db = _db_session()
    try:
        event = _make_event(db)
        first = add_event_source(db, event_id=event.id, source_type="twitter",
                                 source_name="twitter_base", source_url=None)
        second = add_event_source(db, event_id=event.id, source_type="twitter",
                                  source_name="twitter_base", source_url=None)

        assert first.id == second.id
        assert db.query(EventSource).count() == 1
    finally:
        db.close()


def test_concurrent_insert_race_falls_back_to_existing_row(monkeypatch) -> None:
    """If the pre-check misses (raced), the IntegrityError path must recover."""
    from src.db import queries

    db = _db_session()
    try:
        event = _make_event(db)
        url = "https://example.org/apply"

        # Another writer wins the race between our pre-check and our commit.
        db.add(EventSource(event_id=event.id, source_type="rss",
                           source_name="other_source", source_url=url))
        db.commit()

        real_find = queries._find_event_source
        calls = {"n": 0}

        def race_miss(db_session, event_id, source_url):
            calls["n"] += 1
            if calls["n"] == 1:
                return None  # the raced pre-check sees nothing
            return real_find(db_session, event_id, source_url)

        monkeypatch.setattr(queries, "_find_event_source", race_miss)

        row = add_event_source(db, event_id=event.id, source_type="tavily_search",
                               source_name="tavily_base_grants", source_url=url)

        assert row.source_name == "other_source"
        assert db.query(EventSource).count() == 1
        assert calls["n"] == 2, "recovery must re-query after the IntegrityError"
    finally:
        db.close()
