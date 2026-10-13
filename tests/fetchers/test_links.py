"""Apply links copied from tweets are shortener URLs (t.co, ethglob.al).

The dashboard and Slack showed "https://t.co/GNjKqIlDyr" as the place to apply.
They are resolved to the page they lead to before an Event is stored.
"""
import sys
from pathlib import Path

import httpx

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.fetchers.links import expand_short_link


def _client(routes):
    def handler(request):
        target = routes.get(str(request.url))
        if target is None:
            return httpx.Response(200)
        return httpx.Response(301, headers={"location": target})
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_shortener_links_resolve_to_their_destination() -> None:
    client = _client({"https://t.co/GNjKqIlDyr": "https://base.org/builder-grants?utm_source=x"})

    assert expand_short_link("https://t.co/GNjKqIlDyr", client=client) == "https://base.org/builder-grants?utm_source=x"


def test_ordinary_links_are_left_alone_without_a_request() -> None:
    def refuse(request):
        raise AssertionError("no request for non-shortener links")
    client = httpx.Client(transport=httpx.MockTransport(refuse))

    assert expand_short_link("https://ethglobal.com/events/mumbai", client=client) == "https://ethglobal.com/events/mumbai"


def test_an_unreachable_shortener_keeps_the_original_link() -> None:
    def fail(request):
        raise httpx.ConnectError("down")
    client = httpx.Client(transport=httpx.MockTransport(fail))

    assert expand_short_link("https://ethglob.al/VPKQRS6W58", client=client) == "https://ethglob.al/VPKQRS6W58"


def test_empty_links_stay_empty() -> None:
    assert expand_short_link(None) is None
    assert expand_short_link("") == ""
