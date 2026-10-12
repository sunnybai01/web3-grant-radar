"""Environment-backed runtime configuration.

Values are resolved when Settings() is constructed, not when the class body is
executed. Class-body evaluation froze whatever the process environment happened
to contain at import time, which made the documented defaults untestable and
silently pinned stale .env values.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _str(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return default if value is None else value


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except (TypeError, ValueError):
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "") or default)
    except (TypeError, ValueError):
        return default


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    """Runtime settings snapshot."""

    def __init__(self) -> None:
        # PostgreSQL
        self.POSTGRES_USER: str = _str("POSTGRES_USER", "web3agent")
        self.POSTGRES_PASSWORD: str = _str("POSTGRES_PASSWORD", "web3agent")
        self.POSTGRES_DB: str = _str("POSTGRES_DB", "web3agent")
        self.POSTGRES_HOST: str = _str("POSTGRES_HOST", "localhost")
        self.POSTGRES_PORT: str = _str("POSTGRES_PORT", "5432")

        # ChromaDB
        self.CHROMA_HOST: str = _str("CHROMA_HOST", "localhost")
        self.CHROMA_PORT: str = _str("CHROMA_PORT", "8000")

        # LLM
        self.DEEPSEEK_API_KEY: str = _str("DEEPSEEK_API_KEY")
        self.DEEPSEEK_BASE_URL: str = _str("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        self.QWEN_API_KEY: str = _str("QWEN_API_KEY")
        self.QWEN_BASE_URL: str = _str(
            "QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        self.GEMINI_API_KEY: str = _str("GEMINI_API_KEY")
        self.GEMINI_BASE_URL: str = _str(
            "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"
        )
        self.LLM_PROVIDER_PRIORITY: str = _str("LLM_PROVIDER_PRIORITY", "deepseek,qwen,gemini")
        # Pinned model ids. Provider fallback silently switched models mid-run, so
        # the choice is now explicit and recorded per call.
        self.DEEPSEEK_MODEL: str = _str("DEEPSEEK_MODEL", "deepseek-chat")
        self.QWEN_MODEL: str = _str("QWEN_MODEL", "qwen-turbo-latest")
        self.GEMINI_MODEL: str = _str("GEMINI_MODEL", "gemini-2.0-flash-lite")
        # Backoff applied to a source whose health is "down". Grows with
        # consecutive failures so a permanently dead feed stops being retried on
        # every run.
        self.FAILURE_COOLDOWN_MINUTES: int = _int("FAILURE_COOLDOWN_MINUTES", 720)
        self.FAILURE_COOLDOWN_MAX_MINUTES: int = _int("FAILURE_COOLDOWN_MAX_MINUTES", 10080)

        # Per-request LLM timeout / SDK retry budget.
        self.LLM_TIMEOUT_SECONDS: float = _float("LLM_TIMEOUT_SECONDS", 60.0)
        self.LLM_MAX_RETRIES: int = _int("LLM_MAX_RETRIES", 1)

        # Tavily budget controls.
        #
        # The two knobs together decide the per-source search frequency:
        #   runs/day x sources fetched per run  ==  searches/day per source
        # grant_hackathon runs twice a day (09:00 and 21:00), so the cooldown must
        # be strictly SHORTER than that 12h gap: at exactly 720 minutes the 21:00
        # run lands on the cooldown boundary and every source is skipped, halving
        # coverage to once a day. 660 minutes (11h) leaves an hour of margin, and
        # with the budget covering every enabled source each source is searched
        # exactly twice per day. Lengthen the cooldown to search less often.
        self.TAVILY_SUCCESS_COOLDOWN_MINUTES: int = _int("TAVILY_SUCCESS_COOLDOWN_MINUTES", 660)
        self.TAVILY_MAX_SOURCES_PER_RUN: int = _int("TAVILY_MAX_SOURCES_PER_RUN", 14)

        # Slack
        self.SLACK_BOT_TOKEN: str = _str("SLACK_BOT_TOKEN")
        self.SLACK_CHANNEL_ID: str = _str("SLACK_CHANNEL_ID")

        # Security APIs
        self.GOPLUS_API_KEY: str = _str("GOPLUS_API_KEY")
        self.CERTIK_API_KEY: str = _str("CERTIK_API_KEY")
        self.SCAMSNIFFER_API_KEY: str = _str("SCAMSNIFFER_API_KEY")

        # Search / discovery
        self.GITHUB_TOKEN: str = _str("GITHUB_TOKEN")
        self.TAVILY_API_KEYS: list[str] = [
            k.strip()
            for k in _str("TAVILY_API_KEYS", _str("TAVILY_API_KEY")).split(",")
            if k.strip()
        ]

        # Twitter (Twikit)
        self.TWITTER_AUTH_INFO_1: str = _str("TWITTER_AUTH_INFO_1")
        self.TWITTER_AUTH_INFO_2: str = _str("TWITTER_AUTH_INFO_2")
        self.TWITTER_PASSWORD: str = _str("TWITTER_PASSWORD")
        self.TWITTER_TOTP_SECRET: str = _str("TWITTER_TOTP_SECRET")
        self.TWITTER_COOKIES_FILE: str = _str("TWITTER_COOKIES_FILE", ".twitter-cookies.json")
        self.SOCIAL_WATCH_INTERVAL_MINUTES: int = _int("SOCIAL_WATCH_INTERVAL_MINUTES", 15)
        self.TWITTER_FETCH_COUNT: int = _int("TWITTER_FETCH_COUNT", 20)
        # Tweets older than this are dropped at fetch time. Official accounts are
        # trusted sources, not fresh ones: a 2023 tweet about "Round 2" is history.
        self.TWITTER_MAX_TWEET_AGE_DAYS: int = _int("TWITTER_MAX_TWEET_AGE_DAYS", 30)
        # Only the newest entries of a feed are read. Some feeds carry their whole
        # archive (the EF blog: 642 entries) and would classify years of posts.
        self.RSS_MAX_ENTRIES: int = _int("RSS_MAX_ENTRIES", 30)

        # App
        self.LOG_LEVEL: str = _str("LOG_LEVEL", "INFO")
        self.HEARTBEAT_INTERVAL_MINUTES: int = _int("HEARTBEAT_INTERVAL_MINUTES", 30)
        self.DAILY_SUMMARY_ENABLED: bool = _bool("DAILY_SUMMARY_ENABLED", True)
        self.DAILY_SUMMARY_CRON: str = _str("DAILY_SUMMARY_CRON", "55 23 * * *")
        # How late a scheduled run may still fire, e.g. after the host wakes from
        # sleep. 12h covers one full grant_hackathon cycle; with coalescing a
        # backlog of missed runs fires once.
        self.SCHEDULER_MISFIRE_GRACE_MINUTES: int = _int("SCHEDULER_MISFIRE_GRACE_MINUTES", 720)
        # The heartbeat alerts when grant_hackathon has not completed successfully
        # for this long: its 12h cadence plus a 2h margin for a slow run.
        self.PIPELINE_STALE_ALERT_HOURS: int = _int("PIPELINE_STALE_ALERT_HOURS", 14)
        # A raw signal whose processing failed (LLM outage, crash mid-item) is
        # retried when it is fetched again, up to this many attempts in total.
        self.RAW_SIGNAL_MAX_ATTEMPTS: int = _int("RAW_SIGNAL_MAX_ATTEMPTS", 3)
        # A signal still "pending" after this long was abandoned by a crashed run.
        self.RAW_SIGNAL_PENDING_TIMEOUT_MINUTES: int = _int("RAW_SIGNAL_PENDING_TIMEOUT_MINUTES", 120)
        self.SLIDING_WINDOW_DAYS: int = 14
        self.SIMILARITY_THRESHOLD: float = 0.75

        # Staleness / time-window enforcement
        # Items published more than this many days ago without ANY deadline are
        # dropped. Official sources are judged only on the date the source itself
        # stamped, and are kept when the content says the program is rolling.
        self.STALE_MAX_AGE_DAYS: int = _int("STALE_MAX_AGE_DAYS", 60)
        # Items whose start date passed more than this many days ago, with no
        # deadline, are dropped (discovery sources only).
        self.STALE_START_DATE_GRACE_DAYS: int = _int("STALE_START_DATE_GRACE_DAYS", 14)
        # Secondary date extraction timeout when scraping a source URL.
        self.DATE_SCRAPE_TIMEOUT_SECONDS: int = _int("DATE_SCRAPE_TIMEOUT_SECONDS", 15)
        # Max chars sent to LLM for lightweight date extraction from a scraped page.
        self.DATE_SCRAPE_MAX_CHARS: int = _int("DATE_SCRAPE_MAX_CHARS", 4000)

        # Minimum reward floor: opportunities whose prize/funding reads as less
        # than this many USD are dropped. Amounts that can't be parsed are always
        # kept — the floor only rejects numbers we could actually read.
        self.MIN_AMOUNT_USD: float = _float("MIN_AMOUNT_USD", 5000.0)

        # Scoring weights
        self.SCORE_WEIGHTS: dict = {
            "roi": 0.40,
            "reputation": 0.30,
            "timeliness": 0.20,
            "strategy": 0.10,
        }

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


settings = Settings()
