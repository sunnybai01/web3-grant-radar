"""Documented setting defaults.

These assert the values the README and the operational contract promise. They use
the `isolated_defaults` fixture because config.settings loads the repo .env at
import time, which otherwise leaks developer-specific values into the assertions.
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

from config.settings import Settings


def test_twitter_settings_have_safe_defaults(isolated_defaults) -> None:
    settings = Settings()

    assert settings.TWITTER_AUTH_INFO_1 == ""
    assert settings.TWITTER_AUTH_INFO_2 == ""
    assert settings.TWITTER_PASSWORD == ""
    assert settings.TWITTER_TOTP_SECRET == ""
    assert settings.TWITTER_COOKIES_FILE == ".twitter-cookies.json"
    assert settings.SOCIAL_WATCH_INTERVAL_MINUTES == 15
    assert settings.TWITTER_FETCH_COUNT == 20


def test_tavily_budget_yields_two_searches_per_source_per_day(isolated_defaults) -> None:
    """grant_hackathon runs at 09:00 and 21:00, so the cooldown must be shorter
    than that 12h gap; with the budget covering every enabled source each source
    is searched exactly twice a day."""
    settings = Settings()

    assert settings.TAVILY_SUCCESS_COOLDOWN_MINUTES < 12 * 60
    assert settings.TAVILY_SUCCESS_COOLDOWN_MINUTES == 660
    assert settings.TAVILY_MAX_SOURCES_PER_RUN == 14


def test_daily_summary_settings_have_safe_defaults(isolated_defaults) -> None:
    settings = Settings()

    assert settings.DAILY_SUMMARY_ENABLED is True
    assert settings.DAILY_SUMMARY_CRON == "55 23 * * *"


def test_scheduler_catch_up_and_stale_alert_defaults(isolated_defaults) -> None:
    """A run missed during host sleep is caught up within one 12h cycle, and a
    main pipeline that has not succeeded for 12h + 2h margin is reported."""
    settings = Settings()

    assert settings.SCHEDULER_MISFIRE_GRACE_MINUTES == 720
    assert settings.PIPELINE_STALE_ALERT_HOURS == 14


def test_tweets_older_than_a_month_are_not_ingested_by_default(isolated_defaults) -> None:
    assert Settings().TWITTER_MAX_TWEET_AGE_DAYS == 30


def test_failed_signals_are_retried_a_bounded_number_of_times(isolated_defaults) -> None:
    settings = Settings()

    assert settings.RAW_SIGNAL_MAX_ATTEMPTS == 3
    assert settings.RAW_SIGNAL_PENDING_TIMEOUT_MINUTES == 120


def test_llm_calls_have_a_finite_timeout_and_retry_budget(isolated_defaults) -> None:
    """An unbounded SDK default let one hung provider stall the item loop."""
    settings = Settings()

    assert settings.LLM_TIMEOUT_SECONDS > 0
    assert settings.LLM_MAX_RETRIES >= 0


def test_scoring_weights_sum_to_one(isolated_defaults) -> None:
    settings = Settings()

    assert abs(sum(settings.SCORE_WEIGHTS.values()) - 1.0) < 1e-9
