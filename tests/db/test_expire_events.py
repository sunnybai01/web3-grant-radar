"""Opportunities whose deadline has passed leave the dashboard and the summary.

Nothing ever set status "expired": five opportunities past their deadline were
still in To review on 2026-10-12 (#98, #118, #121, #131, #124).
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.db.database import Base
from src.db.models import Event
from src.db.queries import expire_past_deadline_events

NOW = datetime(2026, 10, 13, 2, 0, tzinfo=timezone.utc)


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine, tables=[Event.__table__])
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def _event(db, title, **kwargs):
    kwargs.setdefault("event_type", "hackathon")
    kwargs.setdefault("status", "pushed")
    event = Event(title=title, **kwargs)
    db.add(event)
    db.commit()
    return event


def test_past_deadlines_expire_and_everything_else_stays() -> None:
    db = _db()
    try:
        _event(db, "closed last week", deadline=NOW - timedelta(days=7))
        _event(db, "closes today (date only)", deadline=datetime(2026, 10, 13, tzinfo=timezone.utc))
        _event(db, "open", deadline=NOW + timedelta(days=5))
        _event(db, "rolling", deadline=None)
        _event(db, "shortlisted, past", deadline=NOW - timedelta(days=7), triage_status="shortlisted")
        _event(db, "archived, past", deadline=NOW - timedelta(days=7), status="archived")

        count = expire_past_deadline_events(db, now=NOW)

        statuses = {e.title: e.status for e in db.query(Event)}
        assert count == 1
        assert statuses == {
            "closed last week": "expired",
            "closes today (date only)": "pushed",
            "open": "pushed",
            "rolling": "pushed",
            "shortlisted, past": "pushed",   # the team may still be applying
            "archived, past": "archived",
        }
    finally:
        db.close()
