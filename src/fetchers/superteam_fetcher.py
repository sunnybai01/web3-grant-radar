"""Superteam Earn live grants (Solana ecosystem) via the site's public JSON API.

Only grants are fetched: Superteam's other listings are bounties, which are out
of scope for this pipeline.

Most live grants come from Superteam's country chapters ("Superteam Korea",
"La Familia" for Spain) and fund local teams only. They are skipped unless their
region is allowed.

Config keys:
    exclude_regional:   skip country-chapter grants (default true)
    allowed_regions:    regions whose chapter grants are kept, e.g. [Singapore]
    regional_sponsors:  chapter sponsors not named "Superteam <region>", e.g. [La Familia]
"""
import logging
from typing import List

import httpx

from .base import BaseFetcher, FetchedItem, FetchError

logger = logging.getLogger(__name__)

GRANTS_API = "https://superteam.fun/api/grants/live"
GRANT_URL = "https://superteam.fun/earn/grants/{slug}"


CHAPTER_PREFIX = "superteam "


def _amount(value) -> str:
    try:
        return f"{float(value):,.0f}"
    except (TypeError, ValueError):
        return str(value)


class SuperteamGrantsFetcher(BaseFetcher):
    source_type = "superteam_grants"

    def fetch(self) -> List[FetchedItem]:
        try:
            resp = self._client.get(GRANTS_API, timeout=20.0)
            resp.raise_for_status()
            grants = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            raise FetchError(f"Superteam grants API failed: {e}") from e

        if not isinstance(grants, list) or not grants:
            raise FetchError("Superteam grants API returned no live grants")
        return [
            self._item(g) for g in grants
            if g.get("slug") and g.get("title") and not self._restricted_to_another_region(g)
        ]

    def _restricted_to_another_region(self, grant: dict) -> bool:
        if self.config.get("exclude_regional", True) is False:
            return False
        sponsor = grant.get("sponsor") or {}
        name = str((sponsor.get("name") if isinstance(sponsor, dict) else sponsor) or "").strip()
        lowered = name.casefold()
        regional_sponsors = {str(s).casefold() for s in self.config.get("regional_sponsors") or []}
        if lowered.startswith(CHAPTER_PREFIX):
            region = lowered[len(CHAPTER_PREFIX):].strip()
        elif lowered in regional_sponsors:
            region = lowered
        else:
            return False  # a global sponsor ("Superteam", a company)
        allowed = {str(r).casefold() for r in self.config.get("allowed_regions") or []}
        return region not in allowed

    def _item(self, grant: dict) -> FetchedItem:
        title = grant["title"].strip()
        url = GRANT_URL.format(slug=grant["slug"])
        token = grant.get("token") or ""
        low, high = grant.get("minReward") or 0, grant.get("maxReward")
        if high and low and low < high:
            reward = f"{_amount(low)}-{_amount(high)} {token}"
        elif high:
            reward = f"up to {_amount(high)} {token}"
        else:
            reward = "not stated"
        sponsor = grant.get("sponsor") or {}
        sponsor_name = (sponsor.get("name") if isinstance(sponsor, dict) else sponsor) or ""

        # Application counts and totals paid change daily; leave them out so L1
        # does not see a "new" grant on every run.
        lines = [
            title,
            f"Grant on Superteam Earn (Solana ecosystem), offered by {sponsor_name.strip() or 'unknown sponsor'}",
            f"Reward: {reward.strip()} per project",
            "Applications are accepted on a rolling basis while the grant is live.",
            f"Apply: {url}",
        ]
        return FetchedItem(
            source_type=self.source_type,
            source_name=self.source_name,
            raw_content="\n".join(lines),
            raw_url=url,
            canonical_url=url,
            metadata=self._enrich({"title": title, "platform": "superteam", "ecosystem": "solana"}),
        )
