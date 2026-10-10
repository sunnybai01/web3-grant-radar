"""Abstract base fetcher — all fetchers inherit from this."""
import datetime as dt
import logging
import time
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import httpx

from config.settings import settings

logger = logging.getLogger(__name__)

# Shanghai timezone for Tavily midnight-bound cooldown
_SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


@dataclass
class FetchedItem:
    """Normalized item returned by any fetcher."""
    source_type: str          # rss|github_api|twitter|discord|web_scraper|rsshub
    source_name: str          # config source name
    raw_content: str          # full text/HTML/body
    raw_url: str              # original URL
    canonical_url: str        # normalized URL after redirect resolution
    metadata: Dict[str, Any] = field(default_factory=dict)


class FetchError(Exception):
    """Non-retryable fetch error."""


def select_budgeted_sources(
    sources: List[Dict[str, Any]],
    health_by_source: Dict[str, Any],
    schedule: str,
    *,
    fetch_method: str,
    now: Optional[dt.datetime] = None,
) -> set[str]:
    """Select the least-recently-fetched runnable sources under a method budget."""
    now = now or dt.datetime.now(dt.timezone.utc)
    eligible = []
    budgets = []

    for source in sources:
        if source.get("enabled", True) is False:
            continue
        if source.get("schedule") != schedule:
            continue
        if source.get("fetch_method") != fetch_method:
            continue

        budget = int(source.get("max_sources_per_run", 0) or 0)
        if budget > 0:
            budgets.append(budget)

        name = source.get("name")
        health = health_by_source.get(name)
        if get_fetch_skip_reason(source, health, now=now) is not None:
            continue

        last_fetch_at = getattr(health, "last_fetch_at", None) if health is not None else None
        eligible.append((name, last_fetch_at))

    if not eligible:
        return set()

    budget_limit = min(budgets) if budgets else 0
    if budget_limit <= 0 or len(eligible) <= budget_limit:
        return {name for name, _ in eligible}

    eligible.sort(key=lambda row: (row[1] is not None, row[1] or dt.datetime.min.replace(tzinfo=dt.timezone.utc), row[0]))
    return {name for name, _ in eligible[:budget_limit]}


def get_fetch_skip_reason(
    config: Dict[str, Any],
    health: Optional[Any],
    now: Optional[dt.datetime] = None,
    source_state: Optional[Any] = None,
) -> Optional[str]:
    """Return a short skip reason when a source is cooling down.

    Cooldown strategies:
    - any source with `success_cooldown_minutes` set: a successful fetch locks it
      for that long. Tavily sources ship with this configured (default 5760
      minutes), which is what keeps the search budget honest.
    - tavily_search additionally unlocks at midnight (Asia/Shanghai) via the
      midnight job, so a source whose cooldown has elapsed is not held forever
      by a stale last_success_at.
    - rate_limit_cooldown_minutes / failure_cooldown_minutes apply on 429 and
      repeated failures.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    fetch_method = config.get("fetch_method", "")

    if source_state is not None and getattr(source_state, "cooldown_until", None) is not None:
        if now < source_state.cooldown_until:
            return "source_state_cooldown"

    if health is None:
        return None

    last_error = (getattr(health, "last_error", "") or "").lower()
    rate_limit_cooldown = int(config.get("rate_limit_cooldown_minutes", 0) or 0)
    failure_cooldown = int(config.get("failure_cooldown_minutes", 0) or 0)

    # The 429 / down-source checks only need a status plus a reference time, so
    # they must run even when last_fetch_at is NULL (previously the function
    # returned early and a rate-limited source was retried with no throttle).
    reference = getattr(health, "last_fetch_at", None)

    if "429" in last_error and rate_limit_cooldown > 0 and reference is not None:
        retry_at = reference + dt.timedelta(minutes=rate_limit_cooldown)
        if now < retry_at:
            return "rate_limited_cooldown"

    if getattr(health, "status", None) == "down" and failure_cooldown > 0 and reference is not None:
        # Exponential backoff: the longer a source has been failing, the less
        # often it is retried (capped by FAILURE_COOLDOWN_MAX_MINUTES).
        failures = int(getattr(health, "consecutive_failures", 0) or 0)
        exponent = max(0, failures - 3)
        cooldown = failure_cooldown * (2 ** exponent)
        max_cooldown = int(getattr(settings, "FAILURE_COOLDOWN_MAX_MINUTES", 10080) or 0)
        if max_cooldown > 0:
            cooldown = min(cooldown, max_cooldown)
        retry_at = reference + dt.timedelta(minutes=cooldown)
        if now < retry_at:
            return "failed_source_cooldown"

    last_success_at = getattr(health, "last_success_at", None)
    if last_success_at is None:
        return None

    # ---- Time-based success cooldown (Tavily included) ----
    success_cooldown = int(config.get("success_cooldown_minutes", 0) or 0)
    if success_cooldown > 0:
        retry_at = last_success_at + dt.timedelta(minutes=success_cooldown)
        if now < retry_at:
            return "success_cooldown"

    # ---- Tavily: midnight-bound cooldown (fallback only) ----
    # A Tavily source that already fetched successfully today stays locked until
    # the next midnight (Asia/Shanghai), where the midnight job clears
    # last_success_at for every Tavily source.
    #
    # This only applies when the source has NO explicit success cooldown. With one
    # configured, the cooldown above already decides the rate and the midnight rule
    # would silently cap the source at one run per day: a 21:00 run is always before
    # midnight, so every source that succeeded at 09:00 was skipped no matter how
    # short its cooldown was.
    if fetch_method == "tavily_search" and success_cooldown <= 0:
        shanghai_now = now.astimezone(_SHANGHAI_TZ)
        today_midnight_shanghai = shanghai_now.replace(
            hour=0, minute=0, second=0, microsecond=0,
        )
        if last_success_at >= today_midnight_shanghai:
            return "tavily_cooldown_until_midnight"

    return None


class BaseFetcher(ABC):
    """Base class for all data source fetchers.

    Subclasses implement ``fetch`` and return a list of FetchedItem.
    The base class handles retry logic, rate limiting, and health reporting.
    """

    source_type: str = "unknown"

    def __init__(self, source_name: str, config: Dict[str, Any],
                 http_client: Optional[httpx.Client] = None):
        self.source_name = source_name
        self.config = config
        self._client = http_client or httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "Web3GrantRadar/1.0 (+https://github.com)"},
        )

    @abstractmethod
    def fetch(self) -> List[FetchedItem]:
        """Fetch items from the source. Must be implemented by subclasses."""

    def close(self):
        self._client.close()

    def _enrich(self, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Merge this source's chain/tier context into an item's metadata.

        Downstream stages (staleness rules, scoring trust adjustments, zero-trust
        verification) read source_tier/official/chain/signal_type off the *item*.
        When fetchers omitted them, ``main`` fell back to "discovery" for every
        source — which put the 44 official ecosystem sources under the stricter
        discovery staleness rules, docked their reputation score, and left the
        verifier without source context.
        """
        enriched = dict(metadata or {})
        config = self.config or {}

        for key in ("chain", "source_tier", "official", "signal_type"):
            if enriched.get(key) is None and config.get(key) is not None:
                enriched[key] = config[key]

        return enriched

    def _canonicalize_url(self, url: str) -> str:
        """Resolve redirects and strip tracking params.

        The HEAD request is bounded and its failure is logged: this runs once per
        fetched item, so an un-timed request against a slow host used to stall the
        whole run (entries x client timeout) with no diagnostic.
        """
        if not url:
            return ""

        final_url = url
        try:
            resp = self._client.head(url, follow_redirects=True, timeout=5.0)
            final_url = str(resp.url)
        except Exception as e:
            logger.debug("Redirect resolution failed for %s (%s); using the URL as-is", url, e)

        # Strip common marketing/tracking query params
        import re
        final_url = re.sub(
            r'[?&](utm_source|utm_medium|utm_campaign|utm_content|utm_term|ref|referrer|source)=[^&]*',
            '', final_url,
        )
        final_url = re.sub(r'[?&]$', '', final_url)
        return final_url


class FetcherRegistry:
    """Holds all fetcher instances and dispatches by type."""

    def __init__(self):
        self._fetchers: Dict[str, BaseFetcher] = {}
        self._http_client = httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "Web3GrantRadar/1.0"},
        )

    def register(self, name: str, fetcher: BaseFetcher):
        self._fetchers[name] = fetcher

    def get(self, name: str) -> Optional[BaseFetcher]:
        return self._fetchers.get(name)

    def fetch_all(self, schedule: str) -> List[FetchedItem]:
        """Fetch from all sources matching a schedule type."""
        all_items, _ = self.fetch_all_with_status(schedule)
        return all_items

    def fetch_all_with_status(self, schedule: str, should_skip=None):
        """Fetch from all sources matching a schedule and return per-source status.

        Returns:
            tuple[list[FetchedItem], dict[str, dict]] where status dict contains:
            {"success": bool, "items": int, "error": Optional[str]}
        """
        all_items = []
        source_status = {}

        for name, fetcher in self._fetchers.items():
            if fetcher.config.get("enabled", True) is False:
                continue
            if fetcher.config.get("schedule") != schedule:
                continue

            skip_reason = should_skip(name, fetcher) if should_skip else None
            if skip_reason:
                source_status[name] = {
                    "success": None,
                    "items": 0,
                    "error": None,
                    "skipped": skip_reason,
                }
                logger.info(f"  {name}: SKIPPED — {skip_reason}")
                continue

            try:
                logger.info(f"Fetching from {name}...")
                items = fetcher.fetch()
                all_items.extend(items)
                source_status[name] = {
                    "success": True,
                    "items": len(items),
                    "error": None,
                    "skipped": None,
                }
                logger.info(f"  {name}: {len(items)} items")
            except Exception as e:
                source_status[name] = {
                    "success": False,
                    "items": 0,
                    "error": str(e),
                    "skipped": None,
                }
                logger.error(f"  {name}: FAILED — {e}")

        return all_items, source_status

    def all_names(self) -> List[str]:
        return list(self._fetchers.keys())

    def close(self):
        self._http_client.close()
        for f in self._fetchers.values():
            f.close()
