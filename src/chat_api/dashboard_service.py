from datetime import datetime, timedelta, timezone


def _source_trust_from_event(event) -> str:
    log = event.verification_log or {}
    source_context = log.get("source_context") or {}
    source_tier = str(source_context.get("source_tier") or "").lower()
    official = bool(source_context.get("official", source_tier == "official"))
    return "official" if official else "discovery"


def _verification_verdict_from_event(event) -> str:
    log = event.verification_log or {}
    return str(log.get("verdict") or "unknown")


TRIAGE_STATUSES = ("new", "shortlisted", "dismissed")
SORT_KEYS = ("score", "deadline", "newest")
CLOSING_SOON_DAYS = 7
SUMMARY_CHARS = 280
# The listing loads every grant/hackathon row and filters in Python: the table
# holds hundreds of rows, and source trust lives inside verification_log JSON,
# so it cannot be filtered in SQL anyway. The cap only guards against runaway growth.
MAX_ROWS = 2000


def _triage_status(event) -> str:
    status = getattr(event, "triage_status", None)
    return status if status in TRIAGE_STATUSES else "new"


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _iso(value: datetime | None) -> str | None:
    value = _as_utc(value)
    return value.isoformat() if value else None


def _round(value) -> float | None:
    return round(value, 1) if value is not None else None


def _summary(text: str | None) -> str:
    text = " ".join((text or "").split())
    if len(text) <= SUMMARY_CHARS:
        return text
    return text[: SUMMARY_CHARS - 1].rstrip() + "…"


def _is_closing_soon(event, now: datetime) -> bool:
    deadline = _as_utc(event.deadline)
    return deadline is not None and now <= deadline <= now + timedelta(days=CLOSING_SOON_DAYS)


def serialize_opportunity(event, source_count: int = 0) -> dict:
    return {
        "id": event.id,
        "score": _round(event.final_score),
        "scores": {
            "roi": _round(event.score_roi),
            "reputation": _round(event.score_reputation),
            "timeliness": _round(event.score_timeliness),
            "strategy": _round(event.score_strategy),
        },
        "type": (event.event_type or "").upper(),
        "title": (event.title or "")[:200],
        "summary": _summary(event.description),
        "ecosystem": event.ecosystem or None,
        "amount": event.amount or None,
        "deadline": _iso(event.deadline),
        "first_seen": _iso(event.created_at),
        "heat": event.heat_count or 1,
        "source_count": source_count,
        "verified": bool(event.is_verified),
        "verification_verdict": _verification_verdict_from_event(event),
        "source_trust": _source_trust_from_event(event),
        "apply_url": event.application_url or event.source_url or "",
        "triage_status": _triage_status(event),
    }


def _matches_filters(event, filters: dict, now: datetime) -> bool:
    types = {t.lower() for t in (filters.get("event_types") or [])}
    if types and (event.event_type or "").lower() not in types:
        return False

    ecosystem = (filters.get("ecosystem") or "").strip().lower()
    if ecosystem and (event.ecosystem or "").lower() != ecosystem:
        return False

    trust = str(filters.get("source_trust") or "all").strip().lower()
    if trust in {"official", "discovery"} and _source_trust_from_event(event) != trust:
        return False

    query = (filters.get("q") or "").strip().lower()
    if query and query not in (event.title or "").lower() and query not in (event.ecosystem or "").lower():
        return False

    if int(filters.get("closing_within_days") or 0) > 0:
        deadline = _as_utc(event.deadline)
        window_end = now + timedelta(days=int(filters["closing_within_days"]))
        if deadline is None or not (now <= deadline <= window_end):
            return False

    return True


def _sort_events(events: list, sort: str) -> list:
    far_future = datetime.max.replace(tzinfo=timezone.utc)
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    if sort == "deadline":
        # Soonest first; open-ended (rolling) items go last.
        return sorted(events, key=lambda e: (_as_utc(e.deadline) or far_future, -e.id))
    if sort == "newest":
        return sorted(events, key=lambda e: (_as_utc(e.created_at) or epoch, e.id), reverse=True)
    # Score: unscored items go last.
    return sorted(
        events,
        key=lambda e: (e.final_score is not None, e.final_score or 0, e.id),
        reverse=True,
    )


def build_opportunity_listing(
    events: list,
    filters: dict,
    source_counts: dict[int, int] | None = None,
    now: datetime | None = None,
) -> dict:
    """Shape the dashboard listing from already-loaded Event rows.

    - metrics describe the whole board and ignore filters, so the header stats
      stay stable while the operator narrows the list;
    - counts apply every filter except status, so each status tab shows how many
      rows it would list;
    - items apply every filter including status.
    """
    now = now or datetime.now(timezone.utc)
    source_counts = source_counts or {}
    status = str(filters.get("status") or "new").lower()
    sort = filters.get("sort") if filters.get("sort") in SORT_KEYS else "score"

    active = [e for e in events if _triage_status(e) != "dismissed"]
    verified_count = sum(1 for e in active if e.is_verified)
    unchecked_count = sum(
        1 for e in active if (e.verification_log or {}).get("verdict") == "unchecked"
    )

    filtered = [e for e in events if _matches_filters(e, filters, now)]
    counts = {key: 0 for key in TRIAGE_STATUSES}
    for event in filtered:
        counts[_triage_status(event)] += 1
    counts["all"] = len(filtered)

    if status in TRIAGE_STATUSES:
        filtered = [e for e in filtered if _triage_status(e) == status]

    return {
        "metrics": {
            "to_review": sum(1 for e in events if _triage_status(e) == "new"),
            "shortlisted": sum(1 for e in events if _triage_status(e) == "shortlisted"),
            "closing_soon": sum(1 for e in active if _is_closing_soon(e, now)),
            "verified_percent": int(round(verified_count / max(len(active), 1) * 100)),
            "verified_count": verified_count,
            "unchecked_count": unchecked_count,
            "total": len(active),
        },
        "counts": counts,
        "ecosystems": sorted({e.ecosystem.lower() for e in events if e.ecosystem}),
        "items": [
            serialize_opportunity(e, source_counts.get(e.id, 0))
            for e in _sort_events(filtered, sort)
        ],
    }


def next_scan_at(now: datetime | None = None) -> str | None:
    """Next scheduled grant/hackathon run, from the scheduler's own cron string."""
    from apscheduler.triggers.cron import CronTrigger

    from src.scheduler.jobs import GRANT_HACKATHON_SCHEDULE

    now = now or datetime.now(timezone.utc)
    trigger = CronTrigger.from_crontab(GRANT_HACKATHON_SCHEDULE, timezone="Asia/Shanghai")
    fire = trigger.get_next_fire_time(None, now)
    return fire.isoformat() if fire else None


def _source_counts(db, event_ids: list[int]) -> dict[int, int]:
    from sqlalchemy import func

    from src.db.models import EventSource

    if not event_ids:
        return {}
    rows = (
        db.query(EventSource.event_id, func.count(EventSource.id))
        .filter(EventSource.event_id.in_(event_ids))
        .group_by(EventSource.event_id)
        .all()
    )
    return {event_id: count for event_id, count in rows}


def list_opportunities(filters: dict) -> dict:
    import logging
    import time

    from src.db.database import SessionLocal
    from src.db.models import Event

    logger = logging.getLogger(__name__)
    db = SessionLocal()
    try:
        t0 = time.monotonic()
        events = (
            db.query(Event)
            .filter(Event.status.in_(["new", "pushed"]))
            .filter(Event.event_type.in_(["grant", "hackathon"]))
            .limit(MAX_ROWS)
            .all()
        )
        listing = build_opportunity_listing(
            events, filters, _source_counts(db, [e.id for e in events])
        )
        logger.info(
            "dashboard query: %d rows, %d listed in %.0f ms (status=%s)",
            len(events), len(listing["items"]), (time.monotonic() - t0) * 1000,
            filters.get("status") or "new",
        )
        listing["next_scan_at"] = next_scan_at()
        return listing
    finally:
        db.close()


def get_opportunity(event_id: int) -> dict:
    from src.db.database import SessionLocal
    from src.db.models import Event, EventSource

    db = SessionLocal()
    try:
        event = db.query(Event).filter(Event.id == event_id).first()
        if event is None:
            raise ValueError("event_not_found")
        sources = (
            db.query(EventSource)
            .filter(EventSource.event_id == event_id)
            .order_by(EventSource.fetched_at.asc())
            .all()
        )
        detail = serialize_opportunity(event, len(sources))
        detail["description"] = event.description or ""
        detail["sources"] = [
            {
                "name": source.source_name,
                "type": source.source_type,
                "url": source.source_url or "",
                "fetched_at": _iso(source.fetched_at),
            }
            for source in sources
        ]
        return detail
    finally:
        db.close()


def delete_opportunity(event_id: int) -> dict:
    import logging

    from src.db.database import SessionLocal
    from src.db.queries import delete_event, get_event_signal_ids, delete_raw_signals_by_ids

    logger = logging.getLogger(__name__)
    db = SessionLocal()
    try:
        # Capture signal IDs before deleting event (cascade deletes event_sources)
        signal_ids = get_event_signal_ids(db, event_id)

        deleted = delete_event(db, event_id)
        if deleted is None:
            raise ValueError("event_not_found")

        # Cleanup dedup traces so re-fetches aren't blocked
        if signal_ids:
            try:
                count = delete_raw_signals_by_ids(db, signal_ids)
                logger.info(
                    f"Cleaned up {count} raw_signals for deleted event #{event_id}"
                )
            except Exception:
                logger.warning(f"Failed to clean raw_signals for event #{event_id}", exc_info=True)

        # Remove ChromaDB vector so semantic dedup doesn't block re-fetch
        try:
            from src.dedup.vector_store import VectorStore

            vs = VectorStore()
            vs.delete(f"event_{event_id}")
            logger.info(f"Cleaned ChromaDB vector for event #{event_id}")
        except Exception:
            logger.warning(f"Failed to clean ChromaDB vector for event #{event_id}", exc_info=True)

        return {"status": "success", "event_id": event_id, "deleted": True}
    finally:
        db.close()


def triage_opportunity(event_id: int, status: str) -> dict:
    """Record a triage decision and return the updated listing row."""
    import logging

    from src.db.database import SessionLocal
    from src.db.queries import set_triage_status

    logger = logging.getLogger(__name__)
    db = SessionLocal()
    try:
        updated = set_triage_status(db, event_id, status)
        if updated is None:
            raise ValueError("event_not_found")
        logger.info("Event #%s triaged as %s", event_id, status)
        return serialize_opportunity(updated, _source_counts(db, [event_id]).get(event_id, 0))
    finally:
        db.close()


def _format_dt(value: datetime | None, fmt: str, fallback: str = "") -> str:
    if not value:
        return fallback
    return value.strftime(fmt)


def list_source_health() -> dict:
    from src.db.database import SessionLocal
    from src.db.models import SourceHealth

    db = SessionLocal()
    try:
        sources = db.query(SourceHealth).order_by(SourceHealth.source_name.asc()).all()

        items = [
            {
                "source": source.source_name,
                "status": source.status or "unknown",
                "last_success": _format_dt(source.last_success_at, "%Y-%m-%d %H:%M", "Never"),
                "last_fetch": _format_dt(source.last_fetch_at, "%Y-%m-%d %H:%M", "Never"),
                "failures": source.consecutive_failures or 0,
                "last_error": (source.last_error or "")[:100],
            }
            for source in sources
        ]

        return {
            "summary": {
                "total_sources": len(sources),
                "healthy": sum(1 for source in sources if source.status == "healthy"),
                "degraded": sum(1 for source in sources if source.status == "degraded"),
                "down": sum(1 for source in sources if source.status == "down"),
            },
            "items": items,
        }
    finally:
        db.close()


def list_schedule_logs(limit: int = 50) -> dict:
    from sqlalchemy import desc

    from src.db.database import SessionLocal
    from src.db.models import ScheduleLog

    db = SessionLocal()
    try:
        logs = db.query(ScheduleLog).order_by(desc(ScheduleLog.started_at)).limit(limit).all()

        items = [
            {
                "id": log.id,
                "job": log.job_name,
                "status": log.status or "unknown",
                "started": _format_dt(log.started_at, "%m-%d %H:%M"),
                "fetched": log.items_fetched or 0,
                "new": log.items_new or 0,
                "deduped": log.items_deduped or 0,
                "classified": log.items_classified or 0,
                "verified": log.items_verified or 0,
                "error": (log.error_message or "")[:80],
            }
            for log in logs
        ]

        return {
            "summary": {
                "total_runs": len(logs),
                "success": sum(1 for log in logs if log.status == "success"),
                "failed": sum(1 for log in logs if log.status == "failed"),
                "running": sum(1 for log in logs if log.status == "running"),
            },
            "items": items,
        }
    finally:
        db.close()


def list_investigations(limit: int = 50) -> dict:
    from sqlalchemy import desc

    from src.db.database import SessionLocal
    from src.db.models import AgentMission

    db = SessionLocal()
    try:
        missions = db.query(AgentMission).order_by(desc(AgentMission.started_at)).limit(limit).all()

        items = []
        for mission in missions:
            conclusion = mission.conclusion or {}
            similar_events = conclusion.get("similar_events") or []
            supporting_evidence = conclusion.get("supporting_evidence") or None
            items.append(
                {
                    "mission_id": mission.id,
                    "event_id": mission.event_id,
                    "status": mission.status or "unknown",
                    "started": _format_dt(mission.started_at, "%m-%d %H:%M"),
                    "finished": _format_dt(mission.finished_at, "%m-%d %H:%M"),
                    "title": str(conclusion.get("title") or ""),
                    "verdict": str(conclusion.get("verdict") or "unknown"),
                    "recommended_action": str(conclusion.get("recommended_action") or ""),
                    "similar_count": len(similar_events),
                    "has_supporting_evidence": bool(supporting_evidence),
                    "error": (mission.error_message or "")[:80],
                }
            )

        return {
            "summary": {
                "total_runs": len(missions),
                "completed": sum(1 for mission in missions if mission.status == "completed"),
                "failed": sum(1 for mission in missions if mission.status == "failed"),
                "running": sum(1 for mission in missions if mission.status == "running"),
            },
            "items": items,
        }
    finally:
        db.close()