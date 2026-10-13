"""When a stated deadline has passed.

The classifier writes most deadlines as a bare date ("2026-10-25"), stored as
00:00 UTC. Compared as an instant, that closed the opportunity at 08:00 Beijing
time on the deadline day itself. A date-only deadline now lasts through the end
of that day anywhere on earth (UTC-12).
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.deadlines import deadline_end, deadline_passed

UTC = timezone.utc
DAY = datetime(2026, 10, 25, tzinfo=UTC)


def test_a_date_only_deadline_lasts_through_that_day_everywhere() -> None:
    assert deadline_end(DAY) == datetime(2026, 10, 26, 12, 0, tzinfo=UTC)


def test_a_deadline_with_a_time_is_taken_literally() -> None:
    stated = datetime(2026, 10, 25, 23, 59, tzinfo=UTC)

    assert deadline_end(stated) == stated


def test_a_date_only_deadline_is_open_on_its_own_day_in_beijing() -> None:
    eight_am_beijing = datetime(2026, 10, 25, 0, 0, tzinfo=UTC)

    assert deadline_passed(DAY, now=eight_am_beijing + timedelta(hours=1)) is False
    assert deadline_passed(DAY, now=datetime(2026, 10, 26, 13, 0, tzinfo=UTC)) is True


def test_naive_timestamps_are_utc_and_no_deadline_never_passes() -> None:
    assert deadline_passed(datetime(2026, 10, 25), now=datetime(2026, 10, 25, 9, tzinfo=UTC)) is False
    assert deadline_passed(None, now=datetime(2030, 1, 1, tzinfo=UTC)) is False
