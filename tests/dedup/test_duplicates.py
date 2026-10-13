"""Finding and merging Events that the current L2 rules treat as one opportunity."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.db.database import Base
from src.db.models import Event, EventSource, PushLog
from src.dedup.duplicates import find_duplicate_groups, merge_group

NOW = datetime.now(timezone.utc)


class FakeVectorStore:
    def __init__(self):
        self.deleted = []

    def delete(self, doc_id):
        self.deleted.append(doc_id)


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine, tables=[Event.__table__, EventSource.__table__, PushLog.__table__])
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def _event(db, title, **kwargs):
    kwargs.setdefault("event_type", "grant")
    event = Event(title=title, **kwargs)
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def _source(db, event, url, source_type="twitter"):
    db.add(EventSource(event_id=event.id, source_type=source_type, source_name="s", source_url=url))
    db.commit()


def _ids(groups):
    return [[e.id for e in g] for g in groups]


def test_events_sharing_a_tweet_are_one_group() -> None:
    db = _db()
    a = _event(db, "BNB Grant DAO Round 3 - Open for Project Submissions")
    b = _event(db, "BNB Grant DAO Round 3 - $30K Grant Pool")
    for e in (a, b):
        _source(db, e, "https://x.com/DoraHacks/status/1622935711409229824")

    assert _ids(find_duplicate_groups(db)) == [[a.id, b.id]]


def test_a_shared_listing_page_url_does_not_group_events() -> None:
    db = _db()
    a = _event(db, "Founder House Singapore")
    b = _event(db, "Arbitrum Open House Buildathon")
    for e in (a, b):
        _source(db, e, "https://blog.arbitrum.foundation/", source_type="web_scraper")

    assert find_duplicate_groups(db) == []


def test_same_titled_events_group_unless_deadline_or_chain_disagree() -> None:
    db = _db()
    a = _event(db, "Base Builder Grant Program", ecosystem="base")
    b = _event(db, "Base Builder Grants", ecosystem="base")
    _event(db, "Base Builder Grants", ecosystem="solana")
    _event(db, "Base Builder Grants", ecosystem="base", deadline=NOW + timedelta(days=200))
    _event(db, "Base Builder Grants", ecosystem="base", deadline=NOW + timedelta(days=20))

    groups = _ids(find_duplicate_groups(db))

    assert [a.id, b.id] in [g[:2] for g in groups]
    assert all(len(g) <= 3 for g in groups)


def test_merge_keeps_the_team_decision_and_moves_everything_over() -> None:
    db = _db()
    store = FakeVectorStore()
    first = _event(db, "Arbitrum Open House Buildathon", amount="$415k", heat_count=4)
    shortlisted = _event(db, "Arbitrum Open House Buildathon", triage_status="shortlisted",
                         deadline=NOW + timedelta(days=12), heat_count=1)
    _source(db, first, "https://x.com/arbitrum/status/1")
    _source(db, first, "https://x.com/arbitrum/status/2")
    _source(db, shortlisted, "https://x.com/arbitrum/status/2")  # same URL on both
    _source(db, shortlisted, "https://example.org/oh")
    db.add(PushLog(event_id=first.id, action="create", success=True))
    db.commit()
    first_id = first.id

    kept = merge_group(db, [first, shortlisted], vector_store=store)

    assert kept.id == shortlisted.id
    assert db.get(Event, first_id) is None
    urls = sorted(s.source_url for s in db.query(EventSource).filter(EventSource.event_id == kept.id))
    assert urls == ["https://example.org/oh", "https://x.com/arbitrum/status/1", "https://x.com/arbitrum/status/2"]
    assert kept.heat_count == 3
    assert kept.amount == "$415k"
    assert db.query(PushLog).filter(PushLog.event_id == kept.id).count() == 1
    assert store.deleted == [f"event_{first_id}"]
