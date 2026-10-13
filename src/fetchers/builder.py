"""Builds the FetcherRegistry from sources.yaml configuration."""
import logging
import yaml
from pathlib import Path

from config.settings import settings
from .base import FetcherRegistry

logger = logging.getLogger(__name__)


def _repo_config_path(filename: str) -> Path:
    return Path(__file__).resolve().parent.parent.parent / "config" / filename

FETCHER_MAP = {
    "rss": ".rss_fetcher:RSSFetcher",
    "github_search": ".github_fetcher:GitHubFetcher",
    "rsshub": ".twitter_fetcher:TwitterFetcher",
    "twitter": ".twitter_fetcher:TwitterFetcher",
    "web_scraper": ".web_scraper:WebScraperFetcher",
    "tavily_search": ".tavily_fetcher:TavilyFetcher",
    "devpost_api": ".devpost_fetcher:DevpostFetcher",
    "ethglobal_events": ".ethglobal_fetcher:ETHGlobalFetcher",
    "superteam_grants": ".superteam_fetcher:SuperteamGrantsFetcher",
}

DISCOVERY_FETCH_METHODS = {"github_search", "tavily_search"}
DISABLED_SCHEDULES = {"bounty"}


def _resolve_fetcher_class(fetch_method: str):
    target = FETCHER_MAP.get(fetch_method)
    if target is None:
        return None

    module_path, class_name = target.split(":", 1)
    module = __import__(f"{__package__}{module_path}", fromlist=[class_name])
    return getattr(module, class_name)


def _normalize_source_metadata(source: dict) -> dict:
    normalized = dict(source)

    fetch_method = normalized.get("fetch_method", "rss")
    ecosystem = normalized.get("ecosystem") or normalized.get("chain") or "multi"
    source_tier = normalized.get("source_tier")

    if source_tier is None:
        source_tier = "discovery" if fetch_method in DISCOVERY_FETCH_METHODS else "official"

    normalized["chain"] = normalized.get("chain") or ecosystem
    normalized["source_tier"] = source_tier
    normalized["official"] = bool(
        normalized.get("official", source_tier == "official")
    )

    is_social_source = fetch_method in {"twitter", "rsshub"} or normalized.get("category") == "social"

    if "signal_type" not in normalized:
        if is_social_source:
            normalized["signal_type"] = "social"
        elif source_tier == "discovery":
            normalized["signal_type"] = "discovery"
        else:
            normalized["signal_type"] = normalized.get("category", "discovery")

    if is_social_source:
        normalized["trust_tier"] = normalized.get("trust_tier") or (
            "discovery" if source_tier == "discovery" else "official"
        )
        normalized["ingestion_mode"] = normalized.get("ingestion_mode") or (
            "preprocessed" if normalized["trust_tier"] == "discovery" else "direct"
        )
        normalized["source_kind"] = normalized.get("source_kind") or "account"
        normalized["watch_priority"] = normalized.get("watch_priority") or "normal"

    if fetch_method == "tavily_search":
        normalized["success_cooldown_minutes"] = int(
            normalized.get("success_cooldown_minutes")
            or settings.TAVILY_SUCCESS_COOLDOWN_MINUTES
        )
        normalized["max_sources_per_run"] = int(
            normalized.get("max_sources_per_run")
            or settings.TAVILY_MAX_SOURCES_PER_RUN
        )

    # Backoff for sources that keep failing. With no default, the skip rules never
    # matched (`failure_cooldown_minutes` was absent from every source), so a
    # permanently dead source was retried on every single run.
    normalized["failure_cooldown_minutes"] = int(
        normalized.get("failure_cooldown_minutes")
        or settings.FAILURE_COOLDOWN_MINUTES
    )

    return normalized


def _load_yaml_config(path: str | Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _exclude_disabled_schedules(sources: list[dict]) -> list[dict]:
    return [
        source for source in sources
        if source.get("schedule") not in DISABLED_SCHEDULES
    ]


def load_sources_config(path: str = None) -> dict:
    if path is None:
        path = _repo_config_path("sources.yaml")
    config = _load_yaml_config(path)

    if "sources" not in config:
        raise ValueError("sources config must contain 'sources'")

    config["sources"] = [
        _normalize_source_metadata(source)
        for source in _exclude_disabled_schedules(config["sources"])
    ]

    return config


def load_chain_registry_config(path: str = None) -> dict:
    if path is None:
        path = _repo_config_path("chains.yaml")
    config = _load_yaml_config(path)

    if "chains" not in config:
        raise ValueError("chain registry config must contain 'chains'")

    return config


def build_registry(config: dict = None) -> FetcherRegistry:
    """Build and return a FetcherRegistry with all enabled sources."""
    if config is None:
        config = load_sources_config()

    registry = FetcherRegistry()
    sources = config.get("sources", [])

    for src in sources:
        name = src["name"]
        if src.get("enabled", True) is False:
            logger.debug(f"Source '{name}' is disabled, skipping registration")
            continue

        fetch_method = src.get("fetch_method", "rss")
        fetcher_cls = _resolve_fetcher_class(fetch_method)

        if fetcher_cls is None:
            logger.warning(f"No fetcher for method '{fetch_method}' (source '{name}'), skipping")
            continue

        try:
            fetcher = fetcher_cls(source_name=name, config=src,
                                  http_client=registry._http_client)
            registry.register(name, fetcher)
            logger.debug(f"Registered fetcher: {name} ({fetch_method})")
        except Exception as e:
            logger.error(f"Failed to create fetcher for '{name}': {e}")

    logger.info(f"Built registry with {len(registry._fetchers)} fetchers")
    return registry
