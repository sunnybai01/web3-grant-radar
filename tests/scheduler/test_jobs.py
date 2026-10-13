import sys
from pathlib import Path

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.scheduler import jobs


class DummyScheduler:
    def __init__(self) -> None:
        self.jobs = []

    def add_job(self, func, trigger, id, name, replace_existing, **options):
        self.jobs.append(
            {
                "func": func,
                "trigger": trigger,
                "id": id,
                "name": name,
                "replace_existing": replace_existing,
                **options,
            }
        )


def _register_on_paused_scheduler(monkeypatch):
    """Register the real jobs on a real (paused) scheduler so job defaults apply."""
    monkeypatch.setattr(jobs.settings, "DAILY_SUMMARY_ENABLED", True)
    monkeypatch.setattr(jobs.settings, "DAILY_SUMMARY_CRON", "55 23 * * *")
    scheduler = jobs.create_scheduler()
    scheduler.start(paused=True)
    jobs.register_jobs(
        scheduler, lambda schedule: None, lambda: None, lambda: None, lambda: None,
        tavily_unlock_fn=lambda: 0,
    )
    return scheduler


def test_missed_runs_are_caught_up_once_instead_of_dropped(monkeypatch) -> None:
    """APScheduler's default 1s misfire grace dropped every run that fell inside a
    host sleep: four grant_hackathon runs were lost between 10-10 and 10-12. A
    missed run must fire on wake-up, and a backlog must collapse into one run."""
    scheduler = _register_on_paused_scheduler(monkeypatch)
    try:
        for job_id in ("pipeline_grant_hackathon", "pipeline_social_watch", "heartbeat"):
            job = scheduler.get_job(job_id)
            assert job.misfire_grace_time == 720 * 60, job_id
            assert job.coalesce is True, job_id
            assert job.max_instances == 1, job_id
    finally:
        scheduler.shutdown(wait=False)


def test_late_daily_summary_is_dropped_rather_than_sent_the_next_morning(monkeypatch) -> None:
    """The summary is dated when it is sent, so a 23:55 run fired at 09:00 the next
    day would report the wrong day. Only a short delay is caught up."""
    scheduler = _register_on_paused_scheduler(monkeypatch)
    try:
        assert scheduler.get_job("daily_slack_summary").misfire_grace_time == 3600
    finally:
        scheduler.shutdown(wait=False)


def test_register_jobs_supports_large_heartbeat_interval(monkeypatch) -> None:
    monkeypatch.setattr(jobs.settings, "HEARTBEAT_INTERVAL_MINUTES", 240)
    monkeypatch.setattr(jobs.settings, "SOCIAL_WATCH_INTERVAL_MINUTES", 15)
    monkeypatch.setattr(jobs.settings, "DAILY_SUMMARY_ENABLED", True)
    monkeypatch.setattr(jobs.settings, "DAILY_SUMMARY_CRON", "55 23 * * *")

    scheduler = DummyScheduler()
    jobs.register_jobs(
        scheduler, lambda schedule: None, lambda: None, lambda: None, lambda: None,
        tavily_unlock_fn=lambda: 0,
    )

    # grant_hackathon, social_watch, heartbeat, daily_summary, tavily_unlock
    assert len(scheduler.jobs) == 5
    assert isinstance(scheduler.jobs[0]["trigger"], CronTrigger)
    assert scheduler.jobs[0]["id"] == "pipeline_grant_hackathon"
    assert isinstance(scheduler.jobs[1]["trigger"], IntervalTrigger)
    assert scheduler.jobs[1]["trigger"].interval.total_seconds() == 15 * 60
    assert scheduler.jobs[1]["id"] == "pipeline_social_watch"
    assert isinstance(scheduler.jobs[2]["trigger"], IntervalTrigger)
    assert scheduler.jobs[2]["trigger"].interval.total_seconds() == 240 * 60
    assert scheduler.jobs[2]["id"] == "heartbeat"
    assert isinstance(scheduler.jobs[3]["trigger"], CronTrigger)
    assert scheduler.jobs[3]["id"] == "daily_slack_summary"
    assert all(job["id"] != "pipeline_bounty" for job in scheduler.jobs)
    assert all(job["id"] != "defillama_candidate_sync" for job in scheduler.jobs)
    assert any(job["id"] == "tavily_unlock" for job in scheduler.jobs)


def test_grant_hackathon_runs_twice_a_day(monkeypatch) -> None:
    """config/sources.yaml and the README both document 09:00 and 21:00."""
    monkeypatch.setattr(jobs.settings, "HEARTBEAT_INTERVAL_MINUTES", 240)
    monkeypatch.setattr(jobs.settings, "SOCIAL_WATCH_INTERVAL_MINUTES", 15)
    monkeypatch.setattr(jobs.settings, "DAILY_SUMMARY_ENABLED", True)
    monkeypatch.setattr(jobs.settings, "DAILY_SUMMARY_CRON", "55 23 * * *")

    scheduler = DummyScheduler()
    jobs.register_jobs(
        scheduler, lambda schedule: None, lambda: None, lambda: None, lambda: None,
        tavily_unlock_fn=lambda: 0,
    )

    grant_job = next(job for job in scheduler.jobs if job["id"] == "pipeline_grant_hackathon")
    trigger = grant_job["trigger"]
    assert str(trigger.fields[5]) == "9,21"  # hour field
    assert str(trigger.timezone) == "Asia/Shanghai"