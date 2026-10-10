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


def list_opportunities(filters: dict) -> dict:
    import logging
    import time

    from sqlalchemy import desc, func

    from src.db.database import SessionLocal
    from src.db.models import Event

    logger = logging.getLogger(__name__)

    event_types = filters.get("event_types") or ["grant", "hackathon"]
    ecosystem = (filters.get("ecosystem") or "").strip()
    min_score = float(filters.get("min_score", 0.0))
    days = int(filters.get("days", 0))
    source_trust = str(filters.get("source_trust") or "all").strip().lower()

    db = SessionLocal()
    try:
        t0 = time.monotonic()
        query = db.query(Event).filter(Event.status.in_(["new", "pushed"]))

        # days <= 0 means "no time window" — the operator filters by dismiss/delete
        # instead, so the list must not silently hide older opportunities.
        if days > 0:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            query = query.filter(Event.created_at >= cutoff)

        # min_score <= 0 means "show everything" — skip the filter entirely so
        # events that were never scored (final_score IS NULL) stay visible.
        if min_score > 0:
            query = query.filter(Event.final_score >= min_score)

        if event_types:
            query = query.filter(Event.event_type.in_(event_types))
        if ecosystem:
            query = query.filter(Event.ecosystem.ilike(f"%{ecosystem}%"))

        # Postgres sorts NULLs first on DESC; coalesce keeps unscored events at the bottom.
        events = query.order_by(desc(func.coalesce(Event.final_score, 0))).limit(500).all()
        t1 = time.monotonic()
        logger.info(
            "dashboard query: %d rows in %.0f ms (filters: types=%s ecosystem=%s days=%s)",
            len(events), (t1 - t0) * 1000, event_types, ecosystem or "any",
            days if days > 0 else "all",
        )

        if source_trust in {"official", "discovery"}:
            events = [
                event for event in events if _source_trust_from_event(event) == source_trust
            ]

        items = []
        for event in events:
            trust = _source_trust_from_event(event)
            verification_verdict = _verification_verdict_from_event(event)
            items.append(
                {
                    "id": event.id,
                    "score": round(event.final_score, 1) if event.final_score is not None else None,
                    "type": (event.event_type or "").upper(),
                    "title": (event.title or "")[:120],
                    "ecosystem": event.ecosystem or "-",
                    "amount": event.amount or "-",
                    "deadline": event.deadline.strftime("%Y-%m-%d") if event.deadline else "Rolling",
                    "heat": event.heat_count or 1,
                    "verified": bool(event.is_verified),
                    "source_trust": trust,
                    "verification_verdict": verification_verdict,
                    "apply_url": event.application_url or event.source_url or "",
                    "is_dismissed": bool(event.is_dismissed),
                }
            )

        total = len(events)
        avg_score = round(sum((event.final_score or 0) for event in events) / max(total, 1), 1)
        # "unchecked" is a first-class verdict: with no security-provider keys
        # configured nothing is verified, and reporting 0% without saying why is
        # less useful than reporting the coverage split.
        verified_count = sum(1 for event in events if event.is_verified)
        unchecked_count = sum(
            1 for event in events
            if ((event.verification_log or {}).get("verdict") == "unchecked")
        )
        verified_percent = int(round(verified_count / max(total, 1) * 100))

        return {
            "metrics": {
                "total_shown": total,
                "avg_score": avg_score,
                "verified_percent": verified_percent,
                "verified_count": verified_count,
                "unchecked_count": unchecked_count,
                "grants": sum(1 for event in events if event.event_type == "grant"),
                "hackathons": sum(1 for event in events if event.event_type == "hackathon"),
                "official": sum(1 for event in events if _source_trust_from_event(event) == "official"),
                "discovery": sum(1 for event in events if _source_trust_from_event(event) == "discovery"),
            },
            "items": items,
        }
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


def dismiss_opportunity(event_id: int, dismissed: bool = True) -> dict:
    """Mark or unmark an event as dismissed (not matching)."""
    import logging

    from src.db.database import SessionLocal
    from src.db.queries import dismiss_event

    logger = logging.getLogger(__name__)
    db = SessionLocal()
    try:
        updated = dismiss_event(db, event_id, dismissed=dismissed)
        if updated is None:
            raise ValueError("event_not_found")
        logger.info(
            f"Event #{event_id} dismissed={dismissed}"
        )
        return {
            "status": "success",
            "event_id": event_id,
            "is_dismissed": bool(updated.is_dismissed),
        }
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