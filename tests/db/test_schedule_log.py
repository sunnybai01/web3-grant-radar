import datetime
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.db.database import Base
from src.db.models import ScheduleLog
from src.db.queries import get_last_successful_run_at


def _db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine, tables=[ScheduleLog.__table__])
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def _at(day: int, hour: int) -> datetime.datetime:
    return datetime.datetime(2026, 10, day, hour, 0, tzinfo=datetime.timezone.utc)


def test_last_successful_run_ignores_failed_running_and_other_jobs() -> None:
    db = _db_session()
    try:
        db.add_all([
            ScheduleLog(job_name="pipeline_grant_hackathon", status="success",
                        started_at=_at(10, 8), finished_at=_at(10, 9)),
            ScheduleLog(job_name="pipeline_grant_hackathon", status="failed",
                        started_at=_at(11, 1), finished_at=_at(11, 2)),
            ScheduleLog(job_name="pipeline_grant_hackathon", status="running",
                        started_at=_at(12, 1)),
            ScheduleLog(job_name="pipeline_social_watch", status="success",
                        started_at=_at(12, 3), finished_at=_at(12, 4)),
        ])
        db.commit()

        last = get_last_successful_run_at(db, "pipeline_grant_hackathon")

        assert last.replace(tzinfo=None) == _at(10, 9).replace(tzinfo=None)
    finally:
        db.close()


def test_last_successful_run_is_none_without_history() -> None:
    db = _db_session()
    try:
        assert get_last_successful_run_at(db, "pipeline_grant_hackathon") is None
    finally:
        db.close()
