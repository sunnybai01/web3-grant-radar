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


def test_llm_calls_have_a_finite_timeout_and_retry_budget(isolated_defaults) -> None:
    """An unbounded SDK default let one hung provider stall the item loop."""
    settings = Settings()

    assert settings.LLM_TIMEOUT_SECONDS > 0
    assert settings.LLM_MAX_RETRIES >= 0


def test_scoring_weights_sum_to_one(isolated_defaults) -> None:
    settings = Settings()

    assert abs(sum(settings.SCORE_WEIGHTS.values()) - 1.0) < 1e-9
