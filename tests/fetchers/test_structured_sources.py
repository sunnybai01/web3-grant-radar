"""Structured opportunity sources: one FetchedItem per opportunity.

The generic scraper turned listing pages into one blob (or dozens of overlapping
fragments), and the JS-rendered hackathon pages yielded nothing. These platforms
publish their listings as data, so each fetcher emits one item per hackathon or
grant with the fields the classifier needs written out explicitly, and leaves
out volatile counters (registrations, "13 days left") so L1 does not see a
"new" item on every run.
"""
import json
import sys
from datetime import date
from pathlib import Path

import httpx
import pytest

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.fetchers.base import FetchError
from src.fetchers.builder import FETCHER_MAP, load_sources_config
from src.fetchers.devpost_fetcher import DevpostFetcher, submission_deadline
from src.fetchers.ethglobal_fetcher import ETHGlobalFetcher
from src.fetchers.superteam_fetcher import SuperteamGrantsFetcher


class _FakeClient:
    """Answers GETs from a function of (url, params); records every request."""

    def __init__(self, respond):
        self._respond = respond
        self.requests = []

    def get(self, url, params=None, timeout=None, **kwargs):
        self.requests.append((url, params))
        status, body = self._respond(url, params or {})
        kwargs = {"json": body} if not isinstance(body, str) else {"text": body}
        return httpx.Response(status, request=httpx.Request("GET", url), **kwargs)

    def head(self, url, follow_redirects=True, timeout=None):
        raise AssertionError("structured sources must not resolve URLs one by one")

    def close(self):
        return None


# --- Devpost ------------------------------------------------------------------


def _hackathon(hid, title, state="open", period="Oct 05 - 25, 2026", prize="3,000", **extra):
    return {
        "id": hid,
        "title": title,
        "displayed_location": {"icon": "globe", "location": "Online"},
        "open_state": state,
        "url": f"https://h{hid}.devpost.com/",
        "time_left_to_submission": "13 days left",
        "submission_period_dates": period,
        "themes": [{"id": 1, "name": "Blockchain"}, {"id": 6, "name": "Machine Learning/AI"}],
        "prize_amount": f"$<span data-currency-value>{prize}</span>",
        "prizes_counts": {"cash": 3, "other": 1},
        "registrations_count": 727,
        "organization_name": "IEEE Turkey",
        "invite_only": False,
        **extra,
    }


def _devpost(pages):
    def respond(url, params):
        return 200, {"hackathons": pages[int(params.get("page", 1)) - 1],
                     "meta": {"total_count": sum(len(p) for p in pages), "per_page": 9}}
    return DevpostFetcher(
        "devpost_blockchain",
        {"fetch_method": "devpost_api", "source_tier": "discovery", "signal_type": "hackathon"},
        http_client=_FakeClient(respond),
    )


@pytest.mark.parametrize(
    "period, expected",
    [
        ("Oct 05 - 25, 2026", date(2026, 10, 25)),
        ("Oct 27 - Nov 02, 2026", date(2026, 11, 2)),
        ("Dec 15, 2026 - Jan 10, 2027", date(2027, 1, 10)),
        ("Oct 12, 2026", date(2026, 10, 12)),
        ("Rolling", None),
    ],
)
def test_devpost_submission_period_yields_the_deadline(period, expected) -> None:
    assert submission_deadline(period) == expected


def test_devpost_emits_one_item_per_open_hackathon_with_explicit_fields() -> None:
    fetcher = _devpost([[_hackathon(29114, "IEEE ClimateChain Global Hackathon")]])

    [item] = fetcher.fetch()

    assert item.raw_url == "https://h29114.devpost.com/"
    assert item.metadata["title"] == "IEEE ClimateChain Global Hackathon"
    assert item.metadata["source_tier"] == "discovery"
    assert "Prize pool: $3,000" in item.raw_content
    assert "<span" not in item.raw_content
    assert "Submission deadline: 2026-10-25" in item.raw_content
    assert "Blockchain" in item.raw_content


def test_devpost_content_ignores_volatile_counters() -> None:
    first = _devpost([[_hackathon(1, "A")]]).fetch()[0].raw_content
    later = _devpost([[_hackathon(1, "A", registrations_count=900,
                                  time_left_to_submission="2 days left")]]).fetch()[0].raw_content

    assert first == later
    assert "727" not in first and "days left" not in first


def test_devpost_reads_every_page_and_skips_invite_only_events() -> None:
    pages = [[_hackathon(n, f"H{n}") for n in range(9)],
             [_hackathon(9, "H9"), _hackathon(10, "Private", invite_only=True)]]

    items = _devpost(pages).fetch()

    assert sorted(i.metadata["title"] for i in items) == sorted(f"H{n}" for n in range(10))


# --- ETHGlobal ----------------------------------------------------------------


def _event(eid, name, etype="hackathon", status="future", **extra):
    return {
        "id": eid, "name": name, "slug": name.lower().replace(" ", "-"), "type": etype,
        "medium": "physical", "city": {"name": "Mumbai"},
        "startTime": "2026-11-05T03:30:00.000Z", "endTime": "2026-11-07T12:30:00.000Z",
        "signupDeadline": "2026-11-03T18:00:00.000Z", "status": status,
        "website": None, "tagline": None, "flags": {}, "meta": {"x": 1},
        **extra,
    }


def _ethglobal_page(events) -> str:
    flight = '6:["$","$L27",null,' + json.dumps({"events": events}) + "]\n"
    half = len(flight) // 2
    chunks = [flight[:half], flight[half:]]  # the live page splits the payload
    pushes = "".join(f"<script>self.__next_f.push([1,{json.dumps(c)}])</script>" for c in chunks)
    return f"<!doctype html><html><body><script>self.__next_f.push([0])</script>{pushes}</body></html>"


def _ethglobal(page: str) -> ETHGlobalFetcher:
    return ETHGlobalFetcher(
        "ethglobal_events",
        {"fetch_method": "ethglobal_events", "source_tier": "official", "signal_type": "hackathon"},
        http_client=_FakeClient(lambda url, params: (200, page)),
    )


def test_ethglobal_emits_only_upcoming_hackathons() -> None:
    page = _ethglobal_page([
        _event(1, "ETHGlobal Mumbai"),
        _event(2, "ETHGlobal Tokyo 2026", status="finished"),
        _event(3, "Pragma Mumbai", etype="summit"),
        _event(4, "Cowork with ETHGlobal in Jaipur", etype="cafe"),
        _event(5, "ETHGlobal Lisbon", status="cancelled"),
    ])

    items = _ethglobal(page).fetch()

    assert [i.metadata["title"] for i in items] == ["ETHGlobal Mumbai"]
    [item] = items
    assert item.raw_url == "https://ethglobal.com/events/ethglobal-mumbai"
    assert "Application deadline: 2026-11-03" in item.raw_content
    assert "2026-11-05" in item.raw_content and "2026-11-07" in item.raw_content
    assert "Mumbai" in item.raw_content


def test_ethglobal_page_without_event_data_is_a_fetch_error() -> None:
    """A redesign must show up as a failing source, not as a quiet zero."""
    with pytest.raises(FetchError, match="event data"):
        _ethglobal("<html><body>Events</body></html>").fetch()


# --- Superteam Earn -----------------------------------------------------------


def _grant(slug, title, lo=0, hi=10000, token="USDG", sponsor="DD.xyz by Webacy"):
    return {
        "slug": slug, "title": title, "minReward": lo, "maxReward": hi, "token": token,
        "sponsor": {"name": sponsor, "slug": "s", "isVerified": True},
        "totalApplications": 128, "historicalApplications": 40, "totalPaid": 52000,
        "approvedAmountTotal": 61000, "isPro": False, "isST": True,
    }


def _superteam(grants, **config):
    return SuperteamGrantsFetcher(
        "superteam_grants",
        {"fetch_method": "superteam_grants", "source_tier": "official", "signal_type": "grant", **config},
        http_client=_FakeClient(lambda url, params: (200, grants)),
    )


def test_superteam_emits_one_item_per_live_grant() -> None:
    [item] = _superteam([_grant("korea-grants", "Solana Foundation Korea Grants")]).fetch()

    assert item.raw_url == "https://superteam.fun/earn/grants/korea-grants"
    assert item.metadata["title"] == "Solana Foundation Korea Grants"
    assert "Reward: up to 10,000 USDG per project" in item.raw_content
    assert "DD.xyz by Webacy" in item.raw_content
    assert "rolling basis" in item.raw_content


def test_superteam_shows_a_reward_range_when_there_is_a_floor() -> None:
    [item] = _superteam([_grant("g", "Startup Accelerator Grant", lo=2000, hi=10000, token="USDC")]).fetch()

    assert "Reward: 2,000-10,000 USDC per project" in item.raw_content


def test_superteam_content_ignores_application_counters() -> None:
    first = _superteam([_grant("g", "G")]).fetch()[0].raw_content
    busier = dict(_grant("g", "G"), totalApplications=999, totalPaid=1)

    assert _superteam([busier]).fetch()[0].raw_content == first
    assert "128" not in first


def test_superteam_skips_grants_of_regional_chapters_by_default() -> None:
    """21 of the 22 live grants >= $5K are country-chapter grants for local teams only."""
    grants = [
        _grant("korea-grants", "Solana Foundation Korea Grants", sponsor="Superteam Korea"),
        _grant("spain-grants", "La Familia Spain Grants", sponsor="La Familia"),
        _grant("startup-accelerator-grant", "Startup Accelerator Grant", sponsor="DD.xyz by Webacy"),
        _grant("agentic-engineering", "Agentic Engineering Grants", sponsor="Superteam"),
    ]

    items = _superteam(grants, regional_sponsors=["La Familia"]).fetch()

    assert sorted(i.metadata["title"] for i in items) == ["Agentic Engineering Grants", "Startup Accelerator Grant"]


def test_superteam_keeps_grants_of_allowed_regions() -> None:
    grants = [
        _grant("sg", "Solana Foundation Singapore Grants", sponsor="Superteam Singapore"),
        _grant("korea", "Solana Foundation Korea Grants", sponsor="Superteam Korea"),
    ]

    items = _superteam(grants, allowed_regions=["singapore"]).fetch()

    assert [i.metadata["title"] for i in items] == ["Solana Foundation Singapore Grants"]


def test_superteam_can_include_every_region() -> None:
    grants = [_grant("korea", "Solana Foundation Korea Grants", sponsor="Superteam Korea")]

    assert len(_superteam(grants, exclude_regional=False).fetch()) == 1


def test_superteam_empty_response_is_a_fetch_error() -> None:
    with pytest.raises(FetchError):
        _superteam([]).fetch()


# --- wiring -------------------------------------------------------------------


def test_structured_sources_are_registered_and_enabled() -> None:
    sources = {s["name"]: s for s in load_sources_config()["sources"]}
    expected = {
        "devpost_blockchain": ("devpost_api", "discovery", "hackathon"),
        "ethglobal_events": ("ethglobal_events", "official", "hackathon"),
        "superteam_grants": ("superteam_grants", "official", "grant"),
    }
    for name, (method, tier, signal) in expected.items():
        assert method in FETCHER_MAP, method
        src = sources[name]
        assert src["fetch_method"] == method
        assert src["enabled"] is True
        assert src["schedule"] == "grant_hackathon"
        assert src["source_tier"] == tier
        assert src["signal_type"] == signal
