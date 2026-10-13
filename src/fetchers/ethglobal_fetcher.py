"""ETHGlobal hackathons from the server-rendered events page.

The page has no feed (ethglobal.com/events/rss 404s). Its event list ships as
React Server Components data: JSON split across ``self.__next_f.push([1, "..."])``
script chunks. The chunks are joined and the ``{"events": [...]}`` object decoded.
"""
import json
import logging
import re
from typing import List

import httpx

from .base import BaseFetcher, FetchedItem, FetchError

logger = logging.getLogger(__name__)

EVENTS_URL = "https://ethglobal.com/events"
INACTIVE_STATUSES = {"finished", "cancelled"}

_PUSH_RE = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)')
_EVENTS_RE = re.compile(r'\{\s*"events"\s*:\s*\[')


def _events_from_page(html: str) -> list:
    flight = "".join(json.loads(f'"{chunk}"') for chunk in _PUSH_RE.findall(html))
    match = _EVENTS_RE.search(flight)
    if not match:
        raise FetchError("ETHGlobal events page has no event data (page format changed?)")
    try:
        payload, _ = json.JSONDecoder().raw_decode(flight[match.start():])
    except ValueError as e:
        raise FetchError(f"ETHGlobal event data could not be decoded: {e}") from e
    return payload.get("events") or []


def _day(timestamp: str) -> str:
    return (timestamp or "")[:10] or "unknown"


class ETHGlobalFetcher(BaseFetcher):
    """Upcoming and running ETHGlobal hackathons (meetups, cafes and summits are skipped)."""

    source_type = "ethglobal_events"

    def fetch(self) -> List[FetchedItem]:
        try:
            resp = self._client.get(EVENTS_URL, timeout=30.0)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise FetchError(f"ETHGlobal events page failed: {e}") from e

        events = _events_from_page(resp.text)
        return [
            self._item(event) for event in events
            if event.get("type") == "hackathon"
            and event.get("status") not in INACTIVE_STATUSES
            and event.get("slug")
        ]

    def _item(self, event: dict) -> FetchedItem:
        name = (event.get("name") or "").strip()
        url = f"https://ethglobal.com/events/{event['slug']}"
        city = (event.get("city") or {}).get("name") if isinstance(event.get("city"), dict) else event.get("city")
        where = event.get("medium") or "unknown format"
        if city:
            where = f"{where}, {city}"

        lines = [
            name,
            f"ETHGlobal hackathon ({where})",
            f"Event dates: {_day(event.get('startTime'))} to {_day(event.get('endTime'))} (UTC)",
            f"Application deadline: {_day(event.get('signupDeadline'))}",
            f"Status: {event.get('status', 'unknown')}",
        ]
        if event.get("tagline"):
            lines.append(event["tagline"])
        lines += [
            "Sponsor prizes are listed on the event's prizes page.",
            f"Apply: {url}",
            f"Prizes: {url}/prizes",
        ]
        return FetchedItem(
            source_type=self.source_type,
            source_name=self.source_name,
            raw_content="\n".join(lines),
            raw_url=url,
            canonical_url=url,
            metadata=self._enrich({"title": name, "platform": "ethglobal"}),
        )
