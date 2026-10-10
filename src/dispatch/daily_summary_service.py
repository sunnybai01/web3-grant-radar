"""Aggregate same-day pipeline outcomes for operator-facing Slack summaries."""
from __future__ import annotations

import datetime as dt
from collections import Counter
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.db.models import Event, EventSource, PushLog, ScheduleLog

SUMMARY_JOBS = {
    "pipeline_grant_hackathon",
    "pipeline_bounty",
    "pipeline_social_watch",
}

# Bounty opportunities are out of scope; exclude them from all summary sections.
EXCLUDED_EVENT_TYPES = ("bounty",)

# Statuses that must never be presented as open opportunities. "fraud" rows were
# reaching the Slack summary because only event_type was filtered.
EXCLUDED_EVENT_STATUSES = ("fraud", "expired", "archived")


def _active_events(db: Session):
    """Base query for events the summary is allowed to report on.

    Operator-dismissed events are invalid data: they must never reach Slack in
    any section. Deleted events are hard-removed from the table, so they drop
    out here for free. Fraud-flagged and expired rows are excluded too. Every
    summary query must start from this helper.
    """
    return db.query(Event).filter(
        Event.event_type.notin_(EXCLUDED_EVENT_TYPES),
        Event.status.notin_(EXCLUDED_EVENT_STATUSES),
        # IS NOT TRUE, not "= false": the column is nullable, so rows predating
        # it hold NULL and must still count as not-dismissed.
        Event.is_dismissed.is_not(True),
    )


def _day_bounds(summary_date: dt.date) -> tuple[dt.datetime, dt.datetime]:
    tz = ZoneInfo("Asia/Shanghai")
    start_local = dt.datetime.combine(summary_date, dt.time.min, tzinfo=tz)
    end_local = start_local + dt.timedelta(days=1)
    start = start_local.astimezone(dt.timezone.utc)
    end = end_local.astimezone(dt.timezone.utc)
    return start, end


def _primary_sources_by_event_id(event_sources: list[EventSource]) -> dict[int, EventSource]:
    primary_sources = {}
    for source in event_sources:
        primary_sources.setdefault(source.event_id, source)
    return primary_sources


def _counter_dict(values: list[str]) -> dict[str, int]:
    return dict(sorted(Counter(value for value in values if value).items()))


def _serialize_event(event: Event, primary_source: EventSource | None) -> dict:
    return {
        "id": event.id,
        "event_type": event.event_type,
        "title": event.title,
        "ecosystem": event.ecosystem,
        "final_score": event.final_score,
        "status": event.status,
        # Amount and deadline drive the actual go/no-go call, so the summary needs
        # them inline rather than making the operator open every link.
        "amount": event.amount or "",
        "deadline": event.deadline.date().isoformat() if event.deadline else "",
        "source_type": primary_source.source_type if primary_source is not None else "",
        "source_name": primary_source.source_name if primary_source is not None else "",
        "source_url": (
            primary_source.source_url or event.source_url or ""
            if primary_source is not None else (event.source_url or "")
        ),
        "application_url": event.application_url,
    }


def build_daily_summary(db: Session, *, summary_date: dt.date) -> dict:
    start, end = _day_bounds(summary_date)

    logs = (
        db.query(ScheduleLog)
        .filter(
            ScheduleLog.job_name.in_(SUMMARY_JOBS),
            ScheduleLog.started_at >= start,
            ScheduleLog.started_at < end,
        )
        .all()
    )

    totals = {
        "fetched": sum(log.items_fetched or 0 for log in logs),
        "new": sum(log.items_new or 0 for log in logs),
        "deduped": sum(log.items_deduped or 0 for log in logs),
        "classified": sum(log.items_classified or 0 for log in logs),
        "verified": sum(log.items_verified or 0 for log in logs),
        "pushed": db.query(PushLog)
        .filter(PushLog.pushed_at >= start, PushLog.pushed_at < end, PushLog.success == True)
        .count(),
    }

    events = (
        _active_events(db)
        .filter(
            Event.created_at >= start,
            Event.created_at < end,
        )
        .order_by(Event.created_at.asc())
        .all()
    )

    event_ids = [event.id for event in events]
    event_sources = []
    if event_ids:
        event_sources = (
            db.query(EventSource)
            .filter(EventSource.event_id.in_(event_ids))
            .order_by(EventSource.event_id.asc(), EventSource.fetched_at.asc(), EventSource.id.asc())
            .all()
        )

    source_names = sorted({source.source_name for source in event_sources if source.source_name})
    primary_sources_by_event_id = _primary_sources_by_event_id(event_sources)

    today_scan_stats = {
        "total_new_events": len(events),
        "by_event_type": _counter_dict([str(event.event_type or "") for event in events]),
        "by_source_type": _counter_dict([
            str(primary_sources_by_event_id[event.id].source_type or "")
            for event in events
            if event.id in primary_sources_by_event_id
        ]),
    }

    historical_events = (
        _active_events(db)
        .order_by(
            func.coalesce(Event.final_score, 0).desc(),
            Event.created_at.desc(),
            Event.id.desc(),
        )
        .all()
    )
    historical_event_ids = [event.id for event in historical_events]
    historical_sources = []
    if historical_event_ids:
        historical_sources = (
            db.query(EventSource)
            .filter(EventSource.event_id.in_(historical_event_ids))
            .order_by(EventSource.event_id.asc(), EventSource.fetched_at.asc(), EventSource.id.asc())
            .all()
        )
    historical_primary_sources_by_event_id = _primary_sources_by_event_id(historical_sources)

    historical_high_score = {
        "total_count": len(historical_events),
        "by_event_type": _counter_dict([
            str(event.event_type or "") for event in historical_events
        ]),
        "recent_events": [
            _serialize_event(event, historical_primary_sources_by_event_id.get(event.id))
            for event in historical_events
        ],
    }

    return {
        "summary_date": summary_date.isoformat(),
        "totals": totals,
        "today_scan_stats": today_scan_stats,
        "historical_high_score": historical_high_score,
        "new_events_count": len(events),
        "new_event_sources": source_names,
        "new_events": [
            _serialize_event(event, primary_sources_by_event_id.get(event.id))
            for event in events
        ],
    }