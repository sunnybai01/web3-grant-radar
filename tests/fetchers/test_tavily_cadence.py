"""Tavily cadence: every enabled source gets searched twice a day.

The requirement is 14 sources x 2 searches/day. Two knobs decide it:

    searches per source per day = (scheduled runs per day)
                                  if cooldown < gap between runs else 0

grant_hackathon runs at 09:00 and 21:00, so a cooldown of exactly 720 minutes
lands *on* the 21:00 boundary and (because the check is `now < last_success +
cooldown`) silently skips every source — halving coverage to once a day with no
error anywhere. These tests pin the arithmetic.
"""
import datetime as dt
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2]))

from config.settings import settings
from src.fetchers.base import get_fetch_skip_reason

SHANGHAI = dt.timezone(dt.timedelta(hours=8))
RUN_HOURS = (9, 21)


def _tavily_config(cooldown_minutes: int) -> dict:
    return {
        "name": "tavily_solana_grants",
        "fetch_method": "tavily_search",
        "success_cooldown_minutes": cooldown_minutes,
        "max_sources_per_run": 14,
    }


def _health_at(moment: dt.datetime, previous_success: dt.datetime):
    return SimpleNamespace(
        status="healthy",
        last_error=None,
        last_fetch_at=previous_success,
        last_success_at=previous_success,
        consecutive_failures=0,
    )


def _daily_run_times(day: dt.date) -> list[dt.datetime]:
    return [dt.datetime.combine(day, dt.time(hour=h), tzinfo=SHANGHAI) for h in RUN_HOURS]


@pytest.mark.parametrize("cooldown", [660, 600, 480])
def test_cooler_than_the_run_gap_searches_every_run(cooldown: int) -> None:
    day = dt.date(2026, 10, 10)
    config = _tavily_config(cooldown)
    previous = _daily_run_times(day)[0]  # the 09:00 run

    evening = _daily_run_times(day)[1]
    assert get_fetch_skip_reason(config, _health_at(evening, previous), now=evening) is None


@pytest.mark.parametrize("cooldown", [721, 1440, 5760])
def test_cooldown_above_the_run_gap_skips_the_evening_run(cooldown: int) -> None:
    """Anything longer than the 12h gap drops the source to one run a day."""
    day = dt.date(2026, 10, 10)
    config = _tavily_config(cooldown)
    previous = _daily_run_times(day)[0]

    evening = _daily_run_times(day)[1]
    assert get_fetch_skip_reason(config, _health_at(evening, previous), now=evening) == "success_cooldown"


def test_cooldown_on_the_exact_boundary_is_not_enough_margin() -> None:
    """At exactly 720 minutes the evening run qualifies only if it starts on the
    very second. Any drift (slow fetch, restart, manual scan) lands before the
    boundary and the whole run is skipped, so real margin is required."""
    day = dt.date(2026, 10, 10)
    config = _tavily_config(720)
    succeeded_at = _daily_run_times(day)[0]  # 09:00

    for a_bit_early in (11 * 60 + 59, 11 * 60 + 30):
        moment = succeeded_at + dt.timedelta(minutes=a_bit_early)
        assert get_fetch_skip_reason(
            config, _health_at(moment, succeeded_at), now=moment
        ) == "success_cooldown"

    on_the_nose = succeeded_at + dt.timedelta(minutes=720)
    assert get_fetch_skip_reason(
        config, _health_at(on_the_nose, succeeded_at), now=on_the_nose
    ) is None


def test_configured_cooldown_is_shorter_than_the_run_gap() -> None:
    """Guard the shipped default against the boundary trap above."""
    assert settings.TAVILY_SUCCESS_COOLDOWN_MINUTES < 12 * 60


def test_configured_budget_covers_every_tavily_source() -> None:
    """If the budget is smaller than the source count, sources rotate and each one
    drops below twice a day even when the cooldown allows it."""
    from src.fetchers.builder import load_sources_config

    config = load_sources_config()
    enabled_tavily = [
        source for source in config["sources"]
        if source.get("fetch_method") == "tavily_search" and source.get("enabled", True)
    ]

    assert enabled_tavily, "expected at least one enabled Tavily source"
    assert settings.TAVILY_MAX_SOURCES_PER_RUN >= len(enabled_tavily)


def test_both_daily_runs_qualify_at_the_shipped_defaults() -> None:
    """End to end over two days: 09:00 and 21:00 both fetch, for 2 searches/day."""
    config = _tavily_config(settings.TAVILY_SUCCESS_COOLDOWN_MINUTES)
    last_success = None
    fetched_at: list[dt.datetime] = []

    for day_offset in (0, 1):
        day = dt.date(2026, 10, 10) + dt.timedelta(days=day_offset)
        for moment in _daily_run_times(day):
            health = _health_at(moment, last_success) if last_success else None
            if get_fetch_skip_reason(config, health, now=moment) is None:
                fetched_at.append(moment)
                last_success = moment

    per_day: dict[dt.date, int] = {}
    for moment in fetched_at:
        per_day[moment.date()] = per_day.get(moment.date(), 0) + 1

    assert per_day == {dt.date(2026, 10, 10): 2, dt.date(2026, 10, 11): 2}
