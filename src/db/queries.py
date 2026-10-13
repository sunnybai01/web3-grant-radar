"""Common database queries."""
import datetime
import logging
from typing import Optional, List

from sqlalchemy import and_, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import (
    RawSignal,
    Event,
    EventSource,
    SourceHealth,
    TwitterSourceState,
    ScheduleLog,
    PushLog,
    AgentMission,
    AgentTrajectory,
    DailySummaryLog,
)


# --- RawSignal ---

def insert_raw_signal(db: Session, **kwargs) -> Optional[RawSignal]:
    """Insert a signal on its first processing attempt.

    Returns None only when the (canonical_url, content_hash) pair already exists
    (a concurrent run won the race). Any other failure is raised: swallowing it
    used to report a failed write as a successful dedup.
    """
    signal = RawSignal(status="pending", attempts=1, **kwargs)
    db.add(signal)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return None
    db.refresh(signal)
    return signal


def find_raw_signal(db: Session, canonical_url: str, content_hash: str) -> Optional[RawSignal]:
    return (
        db.query(RawSignal)
        .filter(RawSignal.canonical_url == canonical_url, RawSignal.content_hash == content_hash)
        .first()
    )


def claim_raw_signal_retry(db: Session, signal: RawSignal) -> RawSignal:
    """Start another processing attempt for a failed or abandoned signal."""
    signal.status = "pending"
    signal.attempts = (signal.attempts or 1) + 1
    signal.fetched_at = datetime.datetime.now(datetime.timezone.utc)
    db.commit()
    db.refresh(signal)
    return signal


def mark_raw_signal_processed(db: Session, signal_id: int, error: Optional[str] = None) -> None:
    """Record how processing a signal ended.

    A failure is only retried when no Event uses the signal yet: once an Event
    was created from it, retrying could mint a duplicate if L2 missed the first.
    """
    signal = db.get(RawSignal, signal_id)
    if signal is None:
        return
    linked = error is not None and db.query(
        db.query(EventSource).filter(EventSource.raw_signal_id == signal_id).exists()
    ).scalar()
    signal.status = "failed" if error is not None and not linked else "done"
    signal.last_error = error[:2000] if error else None
    signal.processed_at = datetime.datetime.now(datetime.timezone.utc)
    db.commit()


def canonical_url_exists(db: Session, canonical_url: str) -> bool:
    return db.query(
        db.query(RawSignal).filter(RawSignal.canonical_url == canonical_url).exists()
    ).scalar()


# --- Event ---

def insert_event(db: Session, **kwargs) -> Event:
    event = Event(**kwargs)
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def update_event(db: Session, event_id: int, **kwargs) -> Optional[Event]:
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        return None
    for key, value in kwargs.items():
        setattr(event, key, value)
    db.commit()
    db.refresh(event)
    return event


def get_event_by_id(db: Session, event_id: int) -> Optional[Event]:
    return db.query(Event).filter(Event.id == event_id).first()


def delete_event(db: Session, event_id: int) -> Optional[Event]:
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        return None
    db.delete(event)
    db.commit()
    return event


TRIAGE_STATUSES = ("new", "shortlisted", "dismissed")


def set_triage_status(db: Session, event_id: int, status: str) -> Optional[Event]:
    """Record the dashboard's triage decision for an event."""
    if status not in TRIAGE_STATUSES:
        raise ValueError(f"invalid triage status: {status}")
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        return None
    event.triage_status = status
    event.triaged_at = datetime.datetime.now(datetime.timezone.utc)
    event.is_dismissed = status == "dismissed"
    db.commit()
    db.refresh(event)
    return event


def get_recent_events(
    db: Session,
    event_type: Optional[str] = None,
    ecosystem: Optional[str] = None,
    min_score: Optional[float] = None,
    limit: int = 50,
) -> List[Event]:
    q = db.query(Event)
    if event_type:
        q = q.filter(Event.event_type == event_type)
    if ecosystem:
        q = q.filter(Event.ecosystem == ecosystem)
    if min_score is not None:
        q = q.filter(Event.final_score >= min_score)
    return q.order_by(Event.created_at.desc()).limit(limit).all()


def get_events_in_window(
    db: Session,
    window_days: int = 14,
) -> List[Event]:
    """Get events within the sliding window for dedup comparison."""
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=window_days)
    return db.query(Event).filter(Event.created_at >= cutoff).all()


def expire_event(db: Session, event_id: int) -> Optional[Event]:
    return update_event(db, event_id, status="expired")


def expire_past_deadline_events(db: Session, now: Optional[datetime.datetime] = None) -> int:
    """Mark live opportunities whose deadline has passed as expired.

    Shortlisted ones are left alone: the team may still be finishing an
    application, and the decision is theirs.
    """
    from src.deadlines import deadline_passed

    now = now or datetime.datetime.now(datetime.timezone.utc)
    candidates = (
        db.query(Event)
        .filter(
            Event.status.in_(["new", "pushed"]),
            Event.triage_status != "shortlisted",
            Event.deadline.isnot(None),
            Event.deadline < now,
        )
        .all()
    )
    expired = [e for e in candidates if deadline_passed(e.deadline, now=now)]
    for event in expired:
        event.status = "expired"
    if expired:
        db.commit()
    return len(expired)


def mark_event_fraud(db: Session, event_id: int, log: dict) -> Optional[Event]:
    return update_event(db, event_id, status="fraud", verification_log=log, is_verified=False)


# --- EventSource ---

def _find_event_source(db: Session, event_id: int, source_url: Optional[str]):
    """Look up one source trace by its uniqueness key.

    NULL is compared with IS NULL because SQL `= NULL` never matches.
    """
    return (
        db.query(EventSource)
        .filter(
            EventSource.event_id == event_id,
            EventSource.source_url.is_(None)
            if source_url is None
            else EventSource.source_url == source_url,
        )
        .first()
    )


def add_event_source(db: Session, event_id: int, source_type: str,
                     source_name: str, source_url: Optional[str] = None,
                     raw_signal_id: Optional[int] = None) -> EventSource:
    """Attach a source trace to an event. Idempotent on (event_id, source_url).

    Two different sources can legitimately surface the *same* article URL within
    one run (four Tavily configs hitting a single aggregator post, for example).
    The (event_id, source_url) unique constraint used to turn that into an
    IntegrityError which aborted the whole pipeline — and because the offending
    items were already committed to raw_signals, L1 then blocked them forever
    and they were never classified. A repeat now returns the existing row.
    """
    existing = _find_event_source(db, event_id, source_url)
    if existing is not None:
        return existing

    es = EventSource(
        event_id=event_id,
        source_type=source_type,
        source_name=source_name,
        source_url=source_url,
        raw_signal_id=raw_signal_id,
    )
    db.add(es)
    try:
        db.commit()
    except IntegrityError:
        # Lost a race on the unique constraint — the row exists, so use it.
        db.rollback()
        es = _find_event_source(db, event_id, source_url)
        if es is None:
            raise
    db.refresh(es)
    return es


def get_event_source_count(db: Session, event_id: int) -> int:
    return db.query(EventSource).filter(EventSource.event_id == event_id).count()


# --- SourceHealth ---

def upsert_source_health(db: Session, source_name: str, success: bool = True,
                         error: Optional[str] = None):
    sh = db.query(SourceHealth).filter(SourceHealth.source_name == source_name).first()
    now = datetime.datetime.now(datetime.timezone.utc)
    if not sh:
        sh = SourceHealth(source_name=source_name)
        db.add(sh)

    sh.last_fetch_at = now
    if success:
        sh.last_success_at = now
        sh.consecutive_failures = 0
        sh.status = "healthy"
        sh.last_error = None
    else:
        sh.consecutive_failures = (sh.consecutive_failures or 0) + 1
        sh.last_error = error
        if sh.consecutive_failures >= 3:
            sh.status = "down"
        elif sh.consecutive_failures >= 1:
            sh.status = "degraded"
    db.commit()


def get_source_health(db: Session, source_name: str) -> Optional[SourceHealth]:
    return db.query(SourceHealth).filter(SourceHealth.source_name == source_name).first()


def unlock_tavily_cooldown(db: Session) -> int:
    """Reset last_success_at for all Tavily sources so they can fetch again.

    Returns the number of sources unlocked.
    """
    count = (
        db.query(SourceHealth)
        .filter(SourceHealth.source_name.like("tavily_%"))
        .update({"last_success_at": None}, synchronize_session="fetch")
    )
    db.commit()
    logger = logging.getLogger(__name__)
    logger.info(f"Unlocked {count} Tavily sources (cooldown reset)")
    return count


def get_unhealthy_sources(db: Session) -> List[SourceHealth]:
    return db.query(SourceHealth).filter(SourceHealth.status != "healthy").all()


def get_twitter_source_state(db: Session, source_name: str) -> Optional[TwitterSourceState]:
    return db.query(TwitterSourceState).filter(
        TwitterSourceState.source_name == source_name
    ).first()


def upsert_twitter_source_state(
    db: Session,
    source_name: str,
    **kwargs,
) -> TwitterSourceState:
    state = get_twitter_source_state(db, source_name)
    if state is None:
        state = TwitterSourceState(source_name=source_name)
        db.add(state)

    for key, value in kwargs.items():
        setattr(state, key, value)

    db.commit()
    db.refresh(state)
    return state


# --- ScheduleLog ---

def create_schedule_log(db: Session, job_name: str) -> ScheduleLog:
    log = ScheduleLog(job_name=job_name, status="running")
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def finish_schedule_log(db: Session, log_id: int, items_fetched: int = 0,
                        items_new: int = 0, items_deduped: int = 0,
                        items_classified: int = 0, items_verified: int = 0,
                        error: Optional[str] = None):
    log = db.query(ScheduleLog).filter(ScheduleLog.id == log_id).first()
    if log:
        log.status = "failed" if error else "success"
        log.error_message = error
        log.items_fetched = items_fetched
        log.items_new = items_new
        log.items_deduped = items_deduped
        log.items_classified = items_classified
        log.items_verified = items_verified
        log.finished_at = datetime.datetime.now(datetime.timezone.utc)
        db.commit()


def get_last_successful_run_at(db: Session, job_name: str) -> Optional[datetime.datetime]:
    """When ``job_name`` last finished successfully, or None if it never has."""
    return (
        db.query(func.max(ScheduleLog.finished_at))
        .filter(ScheduleLog.job_name == job_name, ScheduleLog.status == "success")
        .scalar()
    )


# --- PushLog ---

def create_push_log(db: Session, event_id: int, action: str = "create",
                    slack_ts: Optional[str] = None, success: bool = True,
                    error_message: Optional[str] = None) -> PushLog:
    pl = PushLog(
        event_id=event_id,
        action=action,
        slack_ts=slack_ts,
        success=success,
        error_message=error_message,
    )
    db.add(pl)
    db.commit()
    db.refresh(pl)
    return pl


def get_push_log_for_event(db: Session, event_id: int) -> Optional[PushLog]:
    return db.query(PushLog).filter(
        PushLog.event_id == event_id,
        PushLog.action == "create",
        PushLog.success == True,
    ).first()


# --- Agent Missions ---

def create_agent_mission(
    db: Session,
    *,
    goal: str,
    event_id: int,
    mission_type: str = "single_event_investigation",
    max_steps: int = 3,
) -> AgentMission:
    mission = AgentMission(
        goal=goal,
        event_id=event_id,
        mission_type=mission_type,
        max_steps=max_steps,
        status="running",
    )
    db.add(mission)
    db.commit()
    db.refresh(mission)
    return mission


def add_agent_trajectory(
    db: Session,
    *,
    mission_id: int,
    step_index: int,
    action: str,
    thought: str = "",
    action_input: Optional[dict] = None,
    observation: Optional[dict] = None,
) -> AgentTrajectory:
    trajectory = AgentTrajectory(
        mission_id=mission_id,
        step_index=step_index,
        action=action,
        thought=thought,
        action_input=action_input,
        observation=observation,
    )
    db.add(trajectory)
    db.commit()
    db.refresh(trajectory)
    return trajectory


def finish_agent_mission(
    db: Session,
    mission_id: int,
    *,
    status: str,
    conclusion: Optional[dict] = None,
    error_message: Optional[str] = None,
) -> Optional[AgentMission]:
    mission = db.query(AgentMission).filter(AgentMission.id == mission_id).first()
    if mission is None:
        return None

    mission.status = status
    mission.conclusion = conclusion
    mission.error_message = error_message
    mission.finished_at = datetime.datetime.now(datetime.timezone.utc)
    db.commit()
    db.refresh(mission)
    return mission


# --- Daily Summary Log ---

def create_daily_summary_log(
    db: Session,
    *,
    summary_date: datetime.date,
    channel: str = "slack",
) -> DailySummaryLog:
    row = DailySummaryLog(
        summary_date=summary_date,
        channel=channel,
        status="running",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_daily_summary_log(
    db: Session,
    *,
    summary_date: datetime.date,
    channel: str = "slack",
) -> Optional[DailySummaryLog]:
    return db.query(DailySummaryLog).filter(
        DailySummaryLog.summary_date == summary_date,
        DailySummaryLog.channel == channel,
    ).first()


def mark_daily_summary_sent(
    db: Session,
    row_id: int,
    *,
    slack_ts: str,
) -> Optional[DailySummaryLog]:
    row = db.query(DailySummaryLog).filter(DailySummaryLog.id == row_id).first()
    if row is None:
        return None
    row.status = "success"
    row.slack_ts = slack_ts
    row.error_message = None
    db.commit()
    db.refresh(row)
    return row


def mark_daily_summary_failed(
    db: Session,
    row_id: int,
    *,
    error_message: str,
) -> Optional[DailySummaryLog]:
    row = db.query(DailySummaryLog).filter(DailySummaryLog.id == row_id).first()
    if row is None:
        return None
    row.status = "failed"
    row.error_message = error_message
    db.commit()
    db.refresh(row)
    return row


# --- Dedup Reset ---

def get_event_signal_ids(db: Session, event_id: int) -> list[int]:
    """Return all raw_signal IDs linked to an event."""
    rows = db.query(EventSource.raw_signal_id).filter(
        EventSource.event_id == event_id,
        EventSource.raw_signal_id.isnot(None),
    ).all()
    return [r[0] for r in rows if r[0] is not None]


def delete_raw_signals_by_ids(db: Session, signal_ids: list[int]) -> int:
    """Delete raw_signals by their IDs. Returns count."""
    if not signal_ids:
        return 0
    count = db.query(RawSignal).filter(RawSignal.id.in_(signal_ids)).delete(synchronize_session="fetch")
    db.commit()
    return count


def purge_orphan_raw_signals(db: Session) -> int:
    """Delete raw_signals that have no related event_sources.

    Returns the number of raw_signals purged.
    """
    subquery = db.query(EventSource.raw_signal_id).filter(
        EventSource.raw_signal_id.isnot(None)
    ).distinct()
    count = db.query(RawSignal).filter(
        ~RawSignal.id.in_(subquery)
    ).delete(synchronize_session="fetch")
    db.commit()
    return count


def truncate_raw_signals(db: Session) -> int:
    """Delete ALL raw_signals. Use with caution — needed for full rescan.

    Returns the number of rows deleted.
    """
    count = db.query(RawSignal).count()
    db.query(RawSignal).delete()
    db.commit()
    return count

