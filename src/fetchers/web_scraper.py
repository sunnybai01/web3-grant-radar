"""HTML web scraper — fallback for sites without RSS/API."""
import logging
import re
from typing import List, Optional
from urllib.parse import urljoin, urlparse
import hashlib

import httpx
from bs4 import BeautifulSoup

from .base import BaseFetcher, FetchedItem, FetchError

logger = logging.getLogger(__name__)

LISTING_HEADINGS = ("h2", "h3", "h4")
MIN_LISTING_CARDS = 3
MAX_ITEMS = 30

_ONCLICK_URL_RE = re.compile(r"""location(?:\.href)?\s*=\s*['"]([^'"]+)['"]""")
_APPLY_TEXT_RE = re.compile(r"\b(apply|register|registration|submit|sign up|join)\b", re.IGNORECASE)
MAX_APPLY_LINKS = 3


def _absolute(href: Optional[str], page_url: str) -> Optional[str]:
    href = (href or "").strip()
    if not href or href == "#" or href.startswith(("javascript:", "mailto:", "tel:")):
        return None
    return urljoin(page_url, href)


def _same_page(url: str, page_url: str) -> bool:
    return url.split("#")[0].rstrip("/") == page_url.split("#")[0].rstrip("/")


def _site(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return ".".join(host.split(".")[-2:])


def _same_site(url: str, page_url: str) -> bool:
    """Same registrable domain, subdomains included (hydropower.sui.io is sui.io)."""
    return _site(url) == _site(page_url)


def _card_of(heading, container, level: str):
    """The largest ancestor of ``heading`` that holds no other heading of its level."""
    card = heading
    while card.parent is not None and card.parent is not container and len(card.parent.find_all(level)) == 1:
        card = card.parent
    return card


def _heading_link(heading, card, page_url: str) -> Optional[str]:
    """Where the heading links to: an enclosing <a> or onclick element (within its card), or a link inside it."""
    element = heading
    while element is not None:
        if element.name == "a" and element.get("href"):
            return _absolute(element["href"], page_url)
        match = _ONCLICK_URL_RE.search(element.get("onclick") or "")
        if match:
            return _absolute(match.group(1), page_url)
        if element is card:
            break
        element = element.parent
    inner = heading.find("a", href=True)
    return _absolute(inner["href"], page_url) if inner else None


def _card_link(heading, card, page_url: str) -> Optional[str]:
    """The heading's own link, else the card's first link that stays on the site."""
    link = _heading_link(heading, card, page_url)
    if link:
        return link
    for anchor in card.find_all("a", href=True):
        url = _absolute(anchor["href"], page_url)
        if url and _same_site(url, page_url):
            return url
    return None


def _signature(card) -> tuple:
    return card.name, tuple(sorted(card.get("class") or []))


def _apply_links(container, page_url: str) -> List[str]:
    """'Apply now: <url>' lines for the page's apply/register links."""
    lines, seen = [], set()
    for anchor in container.find_all("a", href=True):
        label = anchor.get_text(" ", strip=True)
        url = _absolute(anchor["href"], page_url)
        if not url or url in seen or not _APPLY_TEXT_RE.search(label):
            continue
        seen.add(url)
        lines.append(f"{label[:60]}: {url}")
        if len(lines) >= MAX_APPLY_LINKS:
            break
    return lines


class WebScraperFetcher(BaseFetcher):
    """Scrapes web pages directly for grant/hackathon/bounty information.

    Used only when no RSS or API is available. Extracts text content
    from <article>, <main>, or <body> tags and splits into blocks.
    """

    source_type = "web_scraper"

    def _build_item(self, entry, source_url: str, fallback_url: str, title: str = None,
                    url: str = None, extra_lines: List[str] = ()):
        text = entry.get_text(separator="\n", strip=True)
        if not text or len(text) < 50:
            return None
        if extra_lines:
            text = text + "\n\n" + "\n".join(extra_lines)

        heading = entry.find(["h1", "h2", "h3"])
        if title:
            title = title[:200]
        elif heading:
            title = heading.get_text(separator=" ", strip=True)[:200]
        else:
            title = next(
                (line[:200] for line in text.split("\n") if len(line.strip()) > 3),
                text[:200],
            )

        if url:
            raw_url = url
        else:
            link_tag = entry.find("a", href=True)
            raw_url = _absolute(link_tag["href"], source_url) if link_tag else None
            raw_url = raw_url or fallback_url

        canonical = self._canonicalize_url(raw_url)

        return FetchedItem(
            source_type=self.source_type,
            source_name=self.source_name,
            raw_content=text,
            raw_url=raw_url,
            canonical_url=canonical,
            metadata=self._enrich({
                "title": title,
                "content_hash": hashlib.sha256(text.encode()).hexdigest(),
                "ecosystem": self.config.get("ecosystem"),
                "category": self.config.get("category"),
            }),
        )

    def fetch(self) -> List[FetchedItem]:
        url = self.config.get("url", "")
        if not url:
            raise FetchError(f"Web scraper '{self.source_name}' has no URL")

        try:
            resp = self._client.get(url, timeout=30.0)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.error(f"Web scrape failed for {self.source_name}: {e}")
            raise FetchError(str(e)) from e

        soup = BeautifulSoup(resp.text, "lxml")

        # Prefer semantic containers. A lone <article> is the page's content; several
        # are the cards of a listing and must stay together under <main>.
        articles = soup.find_all("article")
        container = (
            (articles[0] if len(articles) == 1 else None)
            or soup.find("main")
            or soup.find("div", class_="content")
            or soup.body
        )
        if not container:
            return []

        # Remove scripting and styling
        for tag in container.find_all(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        cards = self._listing_cards(container, url)
        if cards:
            items = [self._build_item(card, url, url, title=title, url=link) for card, title, link in cards]
            return [item for item in items if item is not None][:MAX_ITEMS]

        # Not a listing: the page describes one program. The page is the source;
        # its first link is arbitrary (nav leftovers, llms.txt), so apply links go
        # into the text for the classifier instead.
        item = self._build_item(container, url, url, url=url, extra_lines=_apply_links(container, url))
        return [item] if item is not None else []

    @staticmethod
    def _listing_cards(container, page_url: str):
        """(card, title, url) per opportunity when the page is a listing, else [].

        A listing repeats identically built cards, each with a heading and a link
        to its own page on the same site. Matching class-name substrings ("item",
        "row") hit Tailwind layout classes such as items-center and cut pages into
        overlapping fragments; cards linking off-site are a portfolio of projects;
        differently built sections with CTA links are one program page.
        """
        best = []
        for level in LISTING_HEADINGS:
            groups, seen = {}, set()
            for heading in container.find_all(level):
                card = _card_of(heading, container, level)
                link = _card_link(heading, card, page_url)
                title = heading.get_text(" ", strip=True)
                if (not link or link in seen or len(title) < 3
                        or _same_page(link, page_url) or not _same_site(link, page_url)):
                    continue
                seen.add(link)
                groups.setdefault(_signature(card), []).append((card, title, link))
            largest = max(groups.values(), key=len, default=[])
            if len(largest) > len(best):
                best = largest
        return best if len(best) >= MIN_LISTING_CARDS else []
