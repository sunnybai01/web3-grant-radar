"""Re-verify stored Events with the current verifier.

Every stored verdict came from logic that has since been fixed: missing
security keys passed as "all checks passed", the cross-reference layer never
ran, and GoPlus was called at a 404 path. 25 "degraded" Events still carried
is_verified=true and showed a green Verified badge.
"""
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.db.database import Base
from src.db.models import Event, EventSource
from src.verifier.reverify import reverify_events


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine, tables=[Event.__table__, EventSource.__table__])
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def _event(db, title, verdict, **kwargs):
    kwargs.setdefault("status", "pushed")
    event = Event(event_type="grant", title=title, source_url=f"https://example.org/{title}",
                  is_verified=True,
                  verification_log={"verdict": verdict, "source_context": {"source_tier": "official", "official": True}},
                  **kwargs)
    db.add(event)
    db.commit()
    db.add(EventSource(event_id=event.id, source_type="rss", source_name="feed", source_url=event.source_url))
    db.commit()
    return event


def test_live_events_get_a_fresh_verdict_and_a_matching_flag() -> None:
    db = _db()
    try:
        _event(db, "legacy-degraded", "degraded")
        _event(db, "legacy-verified", "verified")
        _event(db, "archived", "degraded", status="archived")
        calls = []
        verdicts = {"https://example.org/legacy-degraded": "degraded", "https://example.org/legacy-verified": "verified"}

        def verify(**kwargs):
            calls.append(kwargs)
            verdict = verdicts[kwargs["source_url"]]
            return {"verdict": verdict, "is_verified": verdict == "verified",
                    "verification_log": {"verdict": verdict, "source_context": kwargs["metadata"]}}

        counts = reverify_events(db, verify=verify)

        flags = {e.title: (e.verification_log["verdict"], e.is_verified) for e in db.query(Event)}
        assert counts == {"degraded": 1, "verified": 1}
        assert flags["legacy-degraded"] == ("degraded", False)
        assert flags["legacy-verified"] == ("verified", True)
        assert flags["archived"] == ("degraded", True)  # not live, not touched
        assert calls[0]["metadata"] == {"source_tier": "official", "official": True}
        assert calls[0]["event_type"] == "grant" and calls[0]["source_name"] == "feed"
    finally:
        db.close()


def test_a_newly_flagged_phishing_site_is_marked_fraud() -> None:
    db = _db()
    try:
        _event(db, "phish", "degraded")

        reverify_events(db, verify=lambda **kw: {"verdict": "fraud", "is_verified": False,
                                                 "verification_log": {"verdict": "fraud"}})

        assert db.query(Event).one().status == "fraud"
    finally:
        db.close()
