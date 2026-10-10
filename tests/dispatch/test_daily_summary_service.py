import datetime
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.db.database import Base
from src.db.models import Event, EventSource, PushLog, ScheduleLog
from src.dispatch.daily_summary_service import build_daily_summary


def _db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        bind=engine,
        tables=[Event.__table__, EventSource.__table__, PushLog.__table__, ScheduleLog.__table__],
    )
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def test_build_daily_summary_includes_totals_and_new_event_sources() -> None:
    db = _db_session()
    try:
        summary_date = datetime.date(2026, 7, 6)

        db.add_all(
            [
                ScheduleLog(
                    job_name="pipeline_grant_hackathon",
                    status="success",
                    started_at=datetime.datetime(2026, 7, 6, 1, 0),
                    items_fetched=10,
                    items_new=1,
                    items_deduped=5,
                    items_classified=3,
                    items_verified=1,
                ),
                ScheduleLog(
                    job_name="pipeline_bounty",
                    status="success",
                    started_at=datetime.datetime(2026, 7, 6, 2, 0),
                    items_fetched=20,
                    items_new=0,
                    items_deduped=12,
                    items_classified=4,
                    items_verified=1,
                ),
                ScheduleLog(
                    job_name="pipeline_social_watch",
                    status="success",
                    started_at=datetime.datetime(2026, 7, 6, 3, 0),
                    items_fetched=30,
                    items_new=1,
                    items_deduped=18,
                    items_classified=6,
                    items_verified=2,
                ),
            ]
        )
        db.commit()

        event = Event(
            event_type="grant",
            title="Base Builder Rewards",
            description="Funding opportunity.",
            ecosystem="base",
            final_score=7.8,
            created_at=datetime.datetime(2026, 7, 6, 4, 0),
        )
        db.add(event)
        db.commit()
        db.refresh(event)

        db.add(
            EventSource(
                event_id=event.id,
                source_type="twitter",
                source_name="twitter_buildonbase",
                source_url="https://x.com/buildonbase/status/1",
            )
        )
        older_event = Event(
            event_type="bounty",
            title="Arbitrum Security Bounty",
            description="Historical high-score event.",
            ecosystem="arbitrum",
            final_score=8.6,
            created_at=datetime.datetime(2026, 7, 1, 4, 0),
        )
        db.add(older_event)
        db.commit()
        db.refresh(older_event)

        db.add(
            EventSource(
                event_id=older_event.id,
                source_type="rss",
                source_name="immunefi_rss",
                source_url="https://immunefi.com/bounty/arb",
            )
        )
        db.commit()

        payload = build_daily_summary(db, summary_date=summary_date)

        assert payload["summary_date"] == "2026-07-06"
        assert payload["totals"]["fetched"] == 60
        assert payload["totals"]["new"] == 2
        assert payload["new_events_count"] == 1
        assert payload["new_event_sources"] == ["twitter_buildonbase"]
        assert payload["new_events"][0]["title"] == "Base Builder Rewards"
        assert payload["new_events"][0]["source_type"] == "twitter"
        assert payload["new_events"][0]["source_url"] == "https://x.com/buildonbase/status/1"
        assert payload["today_scan_stats"] == {
            "total_new_events": 1,
            "by_event_type": {"grant": 1},
            "by_source_type": {"twitter": 1},
        }
        # Bounty events are out of scope and must be excluded from every summary section.
        assert payload["historical_high_score"]["total_count"] == 1
        assert payload["historical_high_score"]["by_event_type"] == {"grant": 1}
        assert payload["historical_high_score"]["recent_events"][0]["title"] == "Base Builder Rewards"
        assert payload["historical_high_score"]["recent_events"][0]["source_type"] == "twitter"
    finally:
        db.close()


def test_build_daily_summary_excludes_dismissed_events_from_every_section() -> None:
    db = _db_session()
    try:
        summary_date = datetime.date(2026, 7, 6)

        kept = Event(
            event_type="grant",
            title="Base Builder Rewards",
            ecosystem="base",
            final_score=7.8,
            created_at=datetime.datetime(2026, 7, 6, 4, 0),
        )
        dismissed_today = Event(
            event_type="grant",
            title="Dismissed Today",
            ecosystem="base",
            final_score=9.5,
            created_at=datetime.datetime(2026, 7, 6, 5, 0),
            is_dismissed=True,
        )
        dismissed_older = Event(
            event_type="hackathon",
            title="Dismissed Earlier",
            ecosystem="arbitrum",
            final_score=9.9,
            created_at=datetime.datetime(2026, 7, 1, 4, 0),
            is_dismissed=True,
        )
        db.add_all([kept, dismissed_today, dismissed_older])
        db.commit()

        payload = build_daily_summary(db, summary_date=summary_date)

        titles = [event["title"] for event in payload["new_events"]]
        historical_titles = [
            event["title"] for event in payload["historical_high_score"]["recent_events"]
        ]

        assert titles == ["Base Builder Rewards"]
        assert historical_titles == ["Base Builder Rewards"]
        assert payload["historical_high_score"]["total_count"] == 1
        assert payload["historical_high_score"]["by_event_type"] == {"grant": 1}
    finally:
        db.close()


def test_build_daily_summary_treats_null_is_dismissed_as_not_dismissed() -> None:
    """is_dismissed is nullable; rows predating the column must stay visible."""
    db = _db_session()
    try:
        summary_date = datetime.date(2026, 7, 6)

        legacy = Event(
            event_type="grant",
            title="Legacy Unflagged Event",
            ecosystem="base",
            final_score=7.0,
            created_at=datetime.datetime(2026, 7, 6, 4, 0),
            is_dismissed=None,
        )
        db.add(legacy)
        db.commit()

        payload = build_daily_summary(db, summary_date=summary_date)

        assert [event["title"] for event in payload["new_events"]] == ["Legacy Unflagged Event"]
        assert [
            event["title"] for event in payload["historical_high_score"]["recent_events"]
        ] == ["Legacy Unflagged Event"]
    finally:
        db.close()


def test_build_daily_summary_handles_empty_new_events() -> None:
    db = _db_session()
    try:
        summary_date = datetime.date(2026, 7, 6)

        db.add(
            ScheduleLog(
                job_name="pipeline_social_watch",
                status="success",
                started_at=datetime.datetime(2026, 7, 6, 3, 0),
                items_fetched=30,
                items_new=0,
                items_deduped=30,
                items_classified=0,
                items_verified=0,
            )
        )
        db.commit()

        payload = build_daily_summary(db, summary_date=summary_date)

        assert payload["totals"]["fetched"] == 30
        assert payload["new_events_count"] == 0
        assert payload["new_event_sources"] == []
        assert payload["new_events"] == []
        assert payload["today_scan_stats"] == {
            "total_new_events": 0,
            "by_event_type": {},
            "by_source_type": {},
        }
        assert payload["historical_high_score"] == {
            "total_count": 0,
            "by_event_type": {},
            "recent_events": [],
        }
    finally:
        db.close()

# ---------------------------------------------------------------------------
# Events the operator must never see as "open opportunities".
# ---------------------------------------------------------------------------

def test_fraud_and_expired_events_are_excluded_from_the_summary() -> None:
    """Only event_type was filtered, so status='fraud' rows reached Slack."""
    db = _db_session()
    try:
        summary_date = datetime.date(2026, 7, 6)
        when = datetime.datetime(2026, 7, 6, 3, 0)

        db.add_all([
            Event(event_type="grant", title="Real Grant", status="new", created_at=when),
            Event(event_type="grant", title="Phishing Grant", status="fraud", created_at=when),
            Event(event_type="hackathon", title="Long Gone Hackathon", status="expired", created_at=when),
            Event(event_type="grant", title="Archived Grant", status="archived", created_at=when),
            Event(event_type="grant", title="Dismissed Grant", status="new",
                  is_dismissed=True, created_at=when),
        ])
        db.commit()

        payload = build_daily_summary(db, summary_date=summary_date)

        titles = [event["title"] for event in payload["new_events"]]
        assert titles == ["Real Grant"]
        assert payload["new_events_count"] == 1
    finally:
        db.close()
