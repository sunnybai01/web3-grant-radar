"""When a stated deadline has passed.

The classifier writes most deadlines as a bare date ("2026-10-25"), stored as
00:00 UTC. Compared as an instant, that closed an opportunity at 08:00 Beijing
time on the deadline day itself. A date-only deadline lasts through the end of
that day anywhere on earth (UTC-12), the convention many calls use, so an
opportunity is never closed early.
"""
from datetime import datetime, time, timedelta, timezone
from typing import Optional

# End of a calendar day at UTC-12, measured from that day's 00:00 UTC.
_END_OF_DAY_ANYWHERE = timedelta(days=1, hours=12)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def deadline_end(deadline: datetime) -> datetime:
    """The last instant the opportunity is open."""
    deadline = _as_utc(deadline)
    if deadline.astimezone(timezone.utc).timetz().replace(tzinfo=None) == time(0, 0):
        return deadline + _END_OF_DAY_ANYWHERE
    return deadline


def deadline_passed(deadline: Optional[datetime], now: Optional[datetime] = None) -> bool:
    if deadline is None:
        return False
    return deadline_end(deadline) < (now or datetime.now(timezone.utc))
