"""System heartbeat and source health monitoring."""
import logging
from datetime import datetime, timezone
from typing import Dict, Iterable, Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from config.settings import settings
from src.db.queries import get_last_successful_run_at, get_unhealthy_sources
from src.db.database import SessionLocal

logger = logging.getLogger(__name__)

# The main discovery stream; when it stops succeeding nothing new is found.
STALE_WATCHED_JOB = "pipeline_grant_hackathon"

# Track daily stats in memory (per-process)
_daily_stats: Dict[str, int] = {
    "fetched": 0,
    "new": 0,
    "deduped": 0,
    "pushed": 0,
    "verified": 0,
    "fraud": 0,
}

# job name -> the last-success timestamp an alert was already sent for, so one
# outage produces one alert instead of one per heartbeat.
_stale_alerted_for: Dict[str, Optional[datetime]] = {}

# Sources already reported as down; cleared when a source recovers so its next
# outage is reported again.
_down_alerted: set = set()


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _stale_pipeline_alert(db: Session, now: datetime) -> tuple[Optional[float], Optional[str]]:
    """(hours since the watched job last succeeded, alert text) — text is None
    while the job is fresh or the outage was already reported."""
    last_success = _as_utc(get_last_successful_run_at(db, STALE_WATCHED_JOB))
    threshold = settings.PIPELINE_STALE_ALERT_HOURS

    if last_success is None:
        hours = None
        detail = "has never completed successfully"
    else:
        hours = round((now - last_success).total_seconds() / 3600, 1)
        if hours < threshold:
            return hours, None
        local = last_success.astimezone(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M")
        detail = f"has not completed successfully for {hours}h (last success {local} Asia/Shanghai)"

    if STALE_WATCHED_JOB in _stale_alerted_for and _stale_alerted_for[STALE_WATCHED_JOB] == last_success:
        return hours, None
    _stale_alerted_for[STALE_WATCHED_JOB] = last_success

    message = (
        f"{STALE_WATCHED_JOB} {detail}; alert threshold {threshold}h. "
        "No new opportunities are being discovered. Check that the host stays awake "
        "and the pipeline container is running; missed runs are caught up on wake-up."
    )
    return hours, message


def _down_sources_alert(unhealthy, active_sources: Optional[Iterable[str]]) -> Optional[str]:
    """Alert text for enabled sources that went down since the last report.

    Only enabled sources count: disabled ones keep their old "down" rows and would
    otherwise be reported forever.
    """
    if active_sources is None:
        return None
    active = set(active_sources)
    down = {s.source_name: s for s in unhealthy if s.status == "down" and s.source_name in active}

    _down_alerted.intersection_update(down)  # recovered sources may alert again
    newly_down = [down[name] for name in sorted(down) if name not in _down_alerted]
    if not newly_down:
        return None
    _down_alerted.update(s.source_name for s in newly_down)

    lines = [
        f"• {s.source_name}: {s.consecutive_failures} consecutive failures, "
        f"{(s.last_error or 'no error recorded').splitlines()[0][:160]}"
        for s in newly_down
    ]
    return (
        f"{len(newly_down)} source(s) went down and are no longer being fetched on "
        "every run (retries back off):\n" + "\n".join(lines)
    )


def heartbeat(
    slack_send_fn,
    now: Optional[datetime] = None,
    active_sources: Optional[Iterable[str]] = None,
) -> dict:
    """Run heartbeat: check source health, compile stats, alert on failures.

    Routine stats are only returned. Slack hears from the heartbeat only when the
    main pipeline has stopped succeeding, or when an enabled source goes down.
    """
    now = now or datetime.now(timezone.utc)
    db: Session = SessionLocal()
    try:
        unhealthy = get_unhealthy_sources(db)
        stale_hours, alert = _stale_pipeline_alert(db, now)
        stats = {
            **_daily_stats,
            "unhealthy": len(unhealthy),
            "unhealthy_names": [s.source_name for s in unhealthy],
            "pipeline_stale_hours": stale_hours,
        }

        if alert:
            logger.error("Stale pipeline: %s", alert)
            slack_send_fn(alert)

        sources_alert = _down_sources_alert(unhealthy, active_sources)
        if sources_alert:
            logger.error("Sources down: %s", sources_alert)
            slack_send_fn(sources_alert)

        return stats
    finally:
        db.close()


def increment_stat(key: str, amount: int = 1):
    if key in _daily_stats:
        _daily_stats[key] += amount


def reset_daily_stats():
    for key in _daily_stats:
        _daily_stats[key] = 0
