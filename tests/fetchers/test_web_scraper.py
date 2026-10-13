import sys
from pathlib import Path

import httpx

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.fetchers.web_scraper import WebScraperFetcher


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return None


class _FakeClient:
    def __init__(self, html: str) -> None:
        self._html = html

    def get(self, url: str, timeout: float = 30.0):
        return _FakeResponse(self._html)

    def head(self, url: str, follow_redirects: bool = True):
        return httpx.Response(200, request=httpx.Request("HEAD", url), url=url)

    def close(self) -> None:
        return None


def test_web_scraper_falls_back_to_container_when_matched_cards_are_too_small() -> None:
    html = """
    <html>
      <body>
        <main>
          <div class="card">A</div>
          <div class="card">B</div>
          <section>
            <h1>Official Grant Program</h1>
            <p>
              This Avalanche grant program is open now for builders and provides
              application guidance, eligibility details, and funding support.
            </p>
            <a href="/apply">Apply now</a>
          </section>
        </main>
      </body>
    </html>
    """
    fetcher = WebScraperFetcher(
        "official_grants",
        {
            "name": "official_grants",
            "url": "https://example.com/grants",
            "ecosystem": "avalanche",
            "category": "grant",
        },
        http_client=_FakeClient(html),
    )

    items = fetcher.fetch()

    assert len(items) == 1
    assert items[0].metadata["title"] == "Official Grant Program"
    # A program page is its own source; the apply link travels in the text so the
    # classifier can report it as application_url.
    assert items[0].raw_url == "https://example.com/grants"
    assert "https://example.com/apply" in items[0].raw_content

# --- listing pages -------------------------------------------------------------
# Card detection used to match class *substrings* ("item", "row"), so Tailwind's
# items-center / flex-row matched layout divs: arbitrum_grants produced 20
# overlapping fragments, and on blog.arbitrum.foundation no card got its own link.
# A listing is now recognised by repeated headings that each link somewhere else.


def _scrape(html: str, url: str = "https://example.com/programs"):
    return WebScraperFetcher(
        "listing", {"name": "listing", "url": url, "category": "grant"}, http_client=_FakeClient(html)
    ).fetch()


def _page(body: str) -> str:
    return f"<html><body><main>{body}</main></body></html>"


DESC = "<p>Funding and support for teams building on the network, applications reviewed monthly.</p>"


def test_listing_page_yields_one_item_per_linked_card() -> None:
    cards = "".join(
        f'<div class="flex items-center row"><a class="card-link" href="/programs/{slug}">'
        f'<div class="card_headline"><h3>{name}</h3></div>{DESC}</a></div>'
        for slug, name in [("ika", "Ika"), ("bluefin", "Bluefin"), ("momentum", "Momentum")]
    )
    items = _scrape(_page(f'<div class="flex flex-row items-center"><h1>Programs</h1>{cards}</div>'))

    assert [(i.metadata["title"], i.raw_url) for i in items] == [
        ("Ika", "https://example.com/programs/ika"),
        ("Bluefin", "https://example.com/programs/bluefin"),
        ("Momentum", "https://example.com/programs/momentum"),
    ]
    # One card per item: no item's text contains another's.
    texts = [i.raw_content for i in items]
    assert not any(a != b and a in b for a in texts for b in texts)


def test_listing_link_may_sit_inside_the_heading() -> None:
    cards = "".join(
        f'<article><h2><a href="https://example.com/p/{n}">Grant round {n}</a></h2>{DESC}</article>'
        for n in range(3)
    )

    items = _scrape(_page(cards))

    assert [i.raw_url for i in items] == [f"https://example.com/p/{n}" for n in range(3)]


def test_listing_cards_that_navigate_by_onclick_get_their_own_url() -> None:
    """blog.arbitrum.foundation renders cards as <button onclick="window.location='/slug/'">."""
    cards = "".join(
        f'<button class="gh-card post" onclick="window.location=\'/post-{n}/\'">'
        f'<div class="gh-card-wrapper"><h3 class="gh-card-title">Builder\'s Block #{n}</h3>{DESC}</div></button>'
        for n in range(3)
    )

    items = _scrape(_page(cards), url="https://blog.example.org/")

    assert [i.raw_url for i in items] == [f"https://blog.example.org/post-{n}/" for n in range(3)]


def test_program_page_with_sections_stays_one_item() -> None:
    """Sections of one program page are not separate opportunities."""
    sections = "".join(f"<section><h2>{t}</h2>{DESC}</section>" for t in ("Overview", "Eligibility", "How to apply"))

    items = _scrape(_page(f'<h1>Builder Grants</h1>{sections}<a href="/apply">Apply now</a>'))

    assert len(items) == 1
    assert items[0].metadata["title"] == "Builder Grants"
    assert items[0].raw_url == "https://example.com/programs"
    assert "Apply now: https://example.com/apply" in items[0].raw_content
    assert "Eligibility" in items[0].raw_content and "How to apply" in items[0].raw_content


def test_program_page_item_is_not_pointed_at_an_unrelated_first_link() -> None:
    """The Stellar RFP page's first link was llms.txt, so that became the item URL."""
    items = _scrape(_page(f'<a href="/llms.txt">LLMs</a><h1>RFP Track</h1>{DESC}'))

    assert items[0].raw_url == "https://example.com/programs"


def test_cards_linking_to_other_sites_are_a_portfolio_not_a_listing() -> None:
    """sui.io/programs-funding lists ecosystem projects that link to their own sites."""
    cards = "".join(
        f'<div class="project"><h2><a href="https://{name}.xyz/">{name}</a></h2>{DESC}</div>'
        for name in ("ika", "bluefin", "momentum", "suilend")
    )

    items = _scrape(_page(f"<h1>Programs and funding</h1>{cards}"))

    assert len(items) == 1


def test_listing_card_may_carry_its_link_outside_the_heading() -> None:
    """build.avax.network/hackathons: the heading is plain text, the card has a link."""
    cards = "".join(
        f'<div class="event-card"><h2>Team1 Hackathon {n}</h2>{DESC}<a href="/events/{n}">View</a></div>'
        for n in range(3)
    )

    items = _scrape(_page(cards), url="https://build.example.network/hackathons")

    assert [i.raw_url for i in items] == [f"https://build.example.network/events/{n}" for n in range(3)]


def test_differently_built_sections_are_not_mistaken_for_cards() -> None:
    """starknet.io/grants: three sections, each with its own CTA link, are one program page."""
    body = (
        f'<section class="hero"><h2>Supporting builders</h2>{DESC}<a href="/grants/seed">Seed</a></section>'
        f'<div class="types grid"><h2>Types of grants</h2>{DESC}<a href="/grants/growth">Growth</a></div>'
        f'<aside class="cta"><h2>Find the right grant</h2>{DESC}<a href="/grants/apply">Apply</a></aside>'
    )

    assert len(_scrape(_page(f"<h1>Starknet Grants</h1>{body}"))) == 1
