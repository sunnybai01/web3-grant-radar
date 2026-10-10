"""GitHub API fetcher — searches issues across configured orgs for bounties."""
import logging
from typing import List
import hashlib

import httpx

from .base import BaseFetcher, FetchedItem, FetchError
from config.settings import settings

logger = logging.getLogger(__name__)


class GitHubFetcher(BaseFetcher):
    """Fetches Issues/Discussions from GitHub orgs using the Search API."""

    source_type = "github_api"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "Web3GrantRadar/1.0",
        }
        github_token = settings.GITHUB_TOKEN
        if github_token:
            self._headers["Authorization"] = f"Bearer {github_token}"
        else:
            logger.warning("GITHUB_TOKEN is empty: GitHub fetcher may hit low rate limits")

    def fetch(self) -> List[FetchedItem]:
        items = []
        queries = self.config.get("github_queries", [])
        orgs = self.config.get("orgs", [])
        errors = []

        for org in orgs:
            for query in queries:
                full_query = f"org:{org} {query}"
                try:
                    batch = self._search(full_query, org)
                    items.extend(batch)
                    logger.debug(f"  GitHub search '{org}': {len(batch)} results")
                except FetchError as e:
                    errors.append(f"{org}: {e}")

        if errors:
            raise FetchError("; ".join(errors[:3]))

        return items

    def _search(self, query: str, org: str) -> List[FetchedItem]:
        items = []
        url = "https://api.github.com/search/issues"
        params = {
            "q": query,
            "sort": "updated",
            "order": "desc",
            "per_page": 30,
        }

        try:
            resp = self._client.get(url, headers=self._headers, params=params)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.error(f"GitHub API error for {org}: {e}")
            raise FetchError(str(e)) from e

        for issue in data.get("items", []):
            title = issue.get("title", "")
            body = issue.get("body", "") or ""
            html_url = issue.get("html_url", "")
            raw_content = f"{title}\n\n{body}"

            items.append(FetchedItem(
                source_type=self.source_type,
                source_name=f"{self.source_name}_{org}",
                raw_content=raw_content,
                raw_url=html_url,
                canonical_url=html_url,
                metadata=self._enrich({
                    "title": title,
                    "org": org,
                    "repo": issue.get("repository_url", "").split("/repos/")[-1],
                    "issue_number": issue.get("number"),
                    "state": issue.get("state"),
                    "labels": [l["name"] for l in issue.get("labels", [])],
                    "created_at": issue.get("created_at"),
                    "updated_at": issue.get("updated_at"),
                    "content_hash": hashlib.sha256(raw_content.encode()).hexdigest(),
                    "ecosystem": self.config.get("ecosystem"),
                    "category": self.config.get("category"),
                }),
            ))

        return items
