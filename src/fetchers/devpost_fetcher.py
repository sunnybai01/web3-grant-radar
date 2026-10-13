"""Devpost hackathon listings via the site's public JSON API."""
import logging
import re
from datetime import date, datetime
from typing import List, Optional

import httpx

from .base import BaseFetcher, FetchedItem, FetchError

logger = logging.getLogger(__name__)

DEVPOST_API = "https://devpost.com/api/hackathons"
MAX_PAGES = 5

_TAG_RE = re.compile(r"<[^>]+>")
_END_RE = re.compile(r"(?:(?P<mon>[A-Za-z]{3})\s+)?(?P<day>\d{1,2}),\s*(?P<year>\d{4})\s*$")
_START_MONTH_RE = re.compile(r"^\s*(?P<mon>[A-Za-z]{3})\b")


def submission_deadline(period: Optional[str]) -> Optional[date]:
    """Last day of a Devpost submission period.

    Handles "Oct 05 - 25, 2026", "Oct 27 - Nov 02, 2026",
    "Dec 15, 2026 - Jan 10, 2027" and a single "Oct 12, 2026".
    """
    if not period:
        return None
    end = period.split(" - ")[-1].strip()
    match = _END_RE.search(end)
    if not match:
        return None
    month = match.group("mon")
    if month is None:
        start = _START_MONTH_RE.match(period)
        if not start:
            return None
        month = start.group("mon")
    try:
        return datetime.strptime(f"{month} {match.group('day')} {match.group('year')}", "%b %d %Y").date()
    except ValueError:
        return None


class DevpostFetcher(BaseFetcher):
    """Open and upcoming hackathons for the configured Devpost themes.

    Config keys:
        themes: Devpost theme names (default ["Blockchain"])
    """

    source_type = "devpost_api"

    def fetch(self) -> List[FetchedItem]:
        themes = self.config.get("themes") or ["Blockchain"]
        hackathons = []
        for page in range(1, MAX_PAGES + 1):
            params = {"themes[]": themes, "status[]": ["open", "upcoming"], "page": page}
            try:
                resp = self._client.get(DEVPOST_API, params=params, timeout=20.0)
                resp.raise_for_status()
                payload = resp.json()
            except (httpx.HTTPError, ValueError) as e:
                raise FetchError(f"Devpost API failed: {e}") from e

            batch = payload.get("hackathons") or []
            hackathons.extend(batch)
            total = (payload.get("meta") or {}).get("total_count") or 0
            if not batch or len(hackathons) >= total:
                break

        return [
            self._item(h) for h in hackathons
            if h.get("url") and h.get("title") and not h.get("invite_only")
        ]

    def _item(self, hackathon: dict) -> FetchedItem:
        title = hackathon["title"].strip()
        url = hackathon["url"]
        period = hackathon.get("submission_period_dates") or ""
        deadline = submission_deadline(period)
        prize = _TAG_RE.sub("", hackathon.get("prize_amount") or "").strip()
        cash_prizes = (hackathon.get("prizes_counts") or {}).get("cash")
        location = (hackathon.get("displayed_location") or {}).get("location") or ""
        themes = ", ".join(t.get("name", "") for t in hackathon.get("themes") or [] if t.get("name"))

        # Only fields that describe the opportunity: registrations and "N days
        # left" change on every fetch and would make L1 treat it as new each run.
        lines = [
            title,
            f"Hackathon on Devpost, hosted by {hackathon.get('organization_name') or 'unknown organizer'}",
            f"Prize pool: {prize}"
            + (f" ({cash_prizes} cash prize{'s' if cash_prizes != 1 else ''})" if cash_prizes else ""),
            f"Submission period: {period}",
        ]
        if deadline:
            lines.append(f"Submission deadline: {deadline.isoformat()}")
        lines += [
            f"Status: {hackathon.get('open_state', 'unknown')}",
            f"Location: {location.strip(' ,')}",
            f"Themes: {themes}",
            f"Apply: {url}",
        ]
        return FetchedItem(
            source_type=self.source_type,
            source_name=self.source_name,
            raw_content="\n".join(lines),
            raw_url=url,
            canonical_url=url,
            metadata=self._enrich({"title": title, "platform": "devpost"}),
        )
