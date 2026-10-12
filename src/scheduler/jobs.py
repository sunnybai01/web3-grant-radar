"""APScheduler job definitions for grant, hackathon, and social watch pipelines."""
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from config.settings import settings

logger = logging.getLogger(__name__)

# Schedule definitions
# Grant + hackathon discovery runs twice a day. config/sources.yaml and the README
# both document "0 9,21 * * *"; this constant is the only thing that actually
# schedules it, so a mismatch here halves the coverage of the main opportunity
# stream (evening announcements would wait until the next morning).
GRANT_HACKATHON_SCHEDULE = "0 9,21 * * *"   # 09:00 and 21:00 daily (Asia/Shanghai)
HEARTBEAT_SCHEDULE = f"*/{settings.HEARTBEAT_INTERVAL_MINUTES} * * * *"
DAILY_SUMMARY_SCHEDULE = settings.DAILY_SUMMARY_CRON
SOCIAL_WATCH_INTERVAL_MINUTES = max(1, int(settings.SOCIAL_WATCH_INTERVAL_MINUTES))
TAVILY_UNLOCK_SCHEDULE = "0 0 * * *"  # midnight Asia/Shanghai

# The daily summary is dated when it is sent, so it may only run a little late.
DAILY_SUMMARY_MISFIRE_GRACE_SECONDS = 3600


def _heartbeat_trigger():
    """Build a heartbeat trigger that works for any minute interval."""
    minutes = max(1, int(settings.HEARTBEAT_INTERVAL_MINUTES))
    return IntervalTrigger(minutes=minutes)


def _social_watch_trigger():
    """Build the polling trigger for Twitter social watch."""
    return IntervalTrigger(minutes=max(1, int(settings.SOCIAL_WATCH_INTERVAL_MINUTES)))


def create_scheduler() -> BackgroundScheduler:
    # APScheduler's default misfire grace is 1 second: any run that fell inside a
    # host sleep was dropped, which silently stopped discovery for days. Missed
    # runs now fire on wake-up, and coalescing turns a backlog into a single run.
    scheduler = BackgroundScheduler(
        timezone="Asia/Shanghai",
        job_defaults={
            "misfire_grace_time": max(1, int(settings.SCHEDULER_MISFIRE_GRACE_MINUTES)) * 60,
            "coalesce": True,
            "max_instances": 1,
        },
    )
    return scheduler


def register_jobs(scheduler: BackgroundScheduler, pipeline_fn, heartbeat_fn, social_watch_fn, daily_summary_fn, tavily_unlock_fn):
    """Register all scheduled jobs on the given scheduler.

    Args:
        scheduler: APScheduler instance
        pipeline_fn: callable(schedule_name) that runs the full fetch→push pipeline
        heartbeat_fn: callable() that sends heartbeat + checks source health
        social_watch_fn: callable() that runs the social watch pipeline
        daily_summary_fn: callable() that builds and sends the daily summary
        tavily_unlock_fn: callable() that resets Tavily cooldown at midnight
    """
    # Grant + Hackathon — once daily
    scheduler.add_job(
        lambda: pipeline_fn("grant_hackathon"),
        trigger=CronTrigger.from_crontab(GRANT_HACKATHON_SCHEDULE, timezone="Asia/Shanghai"),
        id="pipeline_grant_hackathon",
        name="Grant & Hackathon Pipeline",
        replace_existing=True,
    )

    # Social watch — medium-frequency polling
    scheduler.add_job(
        social_watch_fn,
        trigger=_social_watch_trigger(),
        id="pipeline_social_watch",
        name="Twitter Social Watch Pipeline",
        replace_existing=True,
    )

    # Heartbeat + health check
    scheduler.add_job(
        heartbeat_fn,
        trigger=_heartbeat_trigger(),
        id="heartbeat",
        name="System Heartbeat & Health Check",
        replace_existing=True,
    )

    if settings.DAILY_SUMMARY_ENABLED:
        scheduler.add_job(
            daily_summary_fn,
            trigger=CronTrigger.from_crontab(DAILY_SUMMARY_SCHEDULE, timezone="Asia/Shanghai"),
            id="daily_slack_summary",
            name="Daily Slack Summary",
            replace_existing=True,
            misfire_grace_time=DAILY_SUMMARY_MISFIRE_GRACE_SECONDS,
        )

    # Tavily cooldown unlock — midnight daily
    scheduler.add_job(
        tavily_unlock_fn,
        trigger=CronTrigger.from_crontab(TAVILY_UNLOCK_SCHEDULE, timezone="Asia/Shanghai"),
        id="tavily_unlock",
        name="Tavily Cooldown Unlock (Midnight)",
        replace_existing=True,
    )

    logger.info(
        f"Registered jobs: grant_hackathon({GRANT_HACKATHON_SCHEDULE}), "
        f"heartbeat({HEARTBEAT_SCHEDULE}), "
        f"social_watch({settings.SOCIAL_WATCH_INTERVAL_MINUTES}m), "
        f"tavily_unlock({TAVILY_UNLOCK_SCHEDULE}), "
        f"daily_summary({'disabled' if not settings.DAILY_SUMMARY_ENABLED else DAILY_SUMMARY_SCHEDULE})"
    )
