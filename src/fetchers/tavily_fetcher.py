"""Tavily search fetcher — LLM-optimized web search for opportunity discovery.

Unlike the RSS/scraper fetchers that pull from fixed URLs, this fetcher runs
search queries against the Tavily API to discover grants/hackathons/bounties
that are not covered by any pre-configured feed. Tavily returns pre-extracted,
clean article text, which is ideal for downstream LLM classification.
"""
import hashlib
import logging
from typing import List

from config.settings import settings
from .base import BaseFetcher, FetchedItem, FetchError

logger = logging.getLogger(__name__)

try:
    from tavily import TavilyClient
except ImportError:  # pragma: no cover
    TavilyClient = None


class TavilyFetcher(BaseFetcher):
    """Runs a Tavily search query and normalizes results into FetchedItems.

    Config keys:
        query:        the search query string (required)
        max_results:  number of results to return (default 5)
        search_depth: "basic" | "advanced" (default "advanced")
        topic:        "general" | "news" (default "general")
        days:         when topic == "news", limit to the last N days (default 15)
    """

    source_type = "tavily_search"

    _client_instance = None  # shared TavilyClient (current active key)
    _active_key_index: int = -1  # which key index is currently in use

    @classmethod
    def _get_client(cls, force_rotate: bool = False):
        if TavilyClient is None:
            raise FetchError("tavily-python is not installed")

        keys = settings.TAVILY_API_KEYS
        if not keys:
            raise FetchError("TAVILY_API_KEYS not set (comma-separated list)")

        if not force_rotate and cls._client_instance is not None:
            return cls._client_instance

        # Start from next key (round-robin)
        start_idx = (cls._active_key_index + 1) % len(keys)

        for offset in range(len(keys)):
            idx = (start_idx + offset) % len(keys)
            api_key = keys[idx]
            try:
                client = TavilyClient(api_key=api_key)
                cls._client_instance = client
                cls._active_key_index = idx
                logger.info(f"TavilyClient using key #{idx + 1}/{len(keys)}")
                return client
            except Exception as e:
                logger.warning(f"Tavily key #{idx + 1} init failed: {e}")
                continue

        raise FetchError(f"All {len(keys)} Tavily API keys failed to initialize")

    def fetch(self) -> List[FetchedItem]:
        query = self.config.get("query", "")
        if not query:
            raise FetchError(f"Tavily source '{self.source_name}' has no query")

        max_results = int(self.config.get("max_results", 5))
        search_depth = self.config.get("search_depth", "advanced")
        topic = self.config.get("topic", "general")

        search_kwargs = {
            "query": query,
            "max_results": max_results,
            "search_depth": search_depth,
            "topic": topic,
        }
        if topic == "news":
            search_kwargs["days"] = int(self.config.get("days", 15))

        keys = settings.TAVILY_API_KEYS
        max_attempts = len(keys) if keys else 1
        last_error = None

        for attempt in range(max_attempts):
            client = self._get_client(force_rotate=(attempt > 0))
            try:
                response = client.search(**search_kwargs)
                break  # success — exit retry loop
            except Exception as e:
                last_error = e
                logger.warning(
                    f"Tavily search attempt {attempt + 1}/{max_attempts} "
                    f"failed for {self.source_name}: {e}"
                )
                if attempt < max_attempts - 1:
                    continue  # rotate key and retry
        else:
            logger.error(
                f"Tavily search failed after {max_attempts} attempts for {self.source_name}"
            )
            raise FetchError(str(last_error)) from last_error

        items = []
        for result in response.get("results", []):
            title = result.get("title", "")
            content = result.get("content", "") or ""
            raw_url = result.get("url", "")
            if not raw_url or not content:
                continue

            raw_content = f"{title}\n\n{content}"
            canonical = self._canonicalize_url(raw_url)

            items.append(FetchedItem(
                source_type=self.source_type,
                source_name=self.source_name,
                raw_content=raw_content,
                raw_url=raw_url,
                canonical_url=canonical,
                metadata=self._enrich({
                    "title": title,
                    "platform": "tavily",
                    "content_hash": hashlib.sha256(raw_content.encode()).hexdigest(),
                    "ecosystem": self.config.get("ecosystem"),
                    "category": self.config.get("category"),
                    "tavily_score": result.get("score"),
                    "published_date": result.get("published_date"),
                    "query": query,
                }),
            ))

        return items
