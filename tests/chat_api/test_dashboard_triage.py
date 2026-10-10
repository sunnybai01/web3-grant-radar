"""Dashboard triage: listing shape, detail lookup and triage decisions.

The listing logic is a pure function over Event rows, so it is exercised with real
model instances in an in-memory SQLite database rather than fake query objects.
"""
import datetime as dt
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.chat_api import dashboard_service
from src.chat_api.app import app
from src.db.database import Base
from src.db.models import Event, EventSource
from src.db.queries import set_triage_status

NOW = dt.datetime(2026, 10, 10, 4, 0, tzinfo=dt.timezone.utc)


def _event(id, **overrides):
    values = dict(
        id=id,
        event_type="grant",
        title=f"Event {id}",
        ecosystem="base",
        final_score=5.0,
        is_verified=False,
        verification_log={"verdict": "unchecked", "source_context": {"official": True}},
        created_at=NOW - dt.timedelta(days=id),
        triage_status="new",
        status="new",
        heat_count=1,
    )
    values.update(overrides)
    return Event(**values)


def _ids(listing):
    return [item["id"] for item in listing["items"]]


def test_listing_defaults_to_new_items_sorted_by_score() -> None:
    events = [
        _event(1, final_score=6.0),
        _event(2, final_score=None),
        _event(3, final_score=9.0),
        _event(4, final_score=8.0, triage_status="shortlisted"),
    ]

    listing = dashboard_service.build_opportunity_listing(events, {}, now=NOW)

    # Unscored items sort last; shortlisted items are not on the New tab.
    assert _ids(listing) == [3, 1, 2]


def test_counts_apply_filters_but_metrics_ignore_them() -> None:
    events = [
        _event(1, event_type="grant"),
        _event(2, event_type="hackathon"),
        _event(3, event_type="grant", triage_status="shortlisted"),
        _event(4, event_type="grant", triage_status="dismissed"),
    ]

    listing = dashboard_service.build_opportunity_listing(
        events, {"event_types": ["grant"], "status": "all"}, now=NOW
    )

    assert listing["counts"] == {"new": 1, "shortlisted": 1, "dismissed": 1, "all": 3}
    assert listing["metrics"]["to_review"] == 2
    assert listing["metrics"]["shortlisted"] == 1
    # Dismissed rows are excluded from the board totals.
    assert listing["metrics"]["total"] == 3
    assert _ids(listing) == [4, 3, 1]  # equal scores: newest id first


def test_search_matches_title_or_ecosystem_case_insensitively() -> None:
    events = [
        _event(1, title="Sui Overflow", ecosystem="sui"),
        _event(2, title="Base Builder Grants", ecosystem="base"),
        _event(3, title="Retro rewards", ecosystem="Optimism"),
    ]

    by_title = dashboard_service.build_opportunity_listing(events, {"q": "BUILDER"}, now=NOW)
    by_chain = dashboard_service.build_opportunity_listing(events, {"q": "optim"}, now=NOW)

    assert _ids(by_title) == [2]
    assert _ids(by_chain) == [3]


def test_ecosystem_and_source_trust_filters() -> None:
    discovery = {"verdict": "unchecked", "source_context": {"source_tier": "discovery"}}
    events = [
        _event(1, ecosystem="base"),
        _event(2, ecosystem="Base", verification_log=discovery),
        _event(3, ecosystem="sui"),
    ]

    listing = dashboard_service.build_opportunity_listing(
        events, {"ecosystem": "base", "source_trust": "official"}, now=NOW
    )

    assert _ids(listing) == [1]
    assert listing["ecosystems"] == ["base", "sui"]


def test_closing_soon_metric_and_filter() -> None:
    events = [
        _event(1, deadline=NOW + dt.timedelta(days=3)),
        _event(2, deadline=NOW + dt.timedelta(days=20)),
        _event(3, deadline=NOW - dt.timedelta(days=1)),
        _event(4, deadline=None),
        _event(5, deadline=NOW + dt.timedelta(days=2), triage_status="dismissed"),
    ]

    listing = dashboard_service.build_opportunity_listing(
        events, {"closing_within_days": 7}, now=NOW
    )

    assert listing["metrics"]["closing_soon"] == 1
    assert _ids(listing) == [1]


def test_deadline_and_newest_sorts() -> None:
    events = [
        _event(1, deadline=None, created_at=NOW - dt.timedelta(days=3)),
        _event(2, deadline=NOW + dt.timedelta(days=9), created_at=NOW - dt.timedelta(days=1)),
        _event(3, deadline=NOW + dt.timedelta(days=2), created_at=NOW - dt.timedelta(days=2)),
    ]

    by_deadline = dashboard_service.build_opportunity_listing(events, {"sort": "deadline"}, now=NOW)
    by_newest = dashboard_service.build_opportunity_listing(events, {"sort": "newest"}, now=NOW)

    assert _ids(by_deadline) == [3, 2, 1]
    assert _ids(by_newest) == [2, 3, 1]


def test_item_shape_uses_iso_dates_and_nulls() -> None:
    event = _event(
        7,
        deadline=dt.datetime(2026, 10, 14),
        amount=None,
        description="  Retroactive   grants\nfor apps on Base.  ",
        score_roi=9.04,
    )

    item = dashboard_service.build_opportunity_listing(
        [event], {}, source_counts={7: 3}, now=NOW
    )["items"][0]

    assert item["deadline"] == "2026-10-14T00:00:00+00:00"
    assert item["amount"] is None
    assert item["summary"] == "Retroactive grants for apps on Base."
    assert item["scores"]["roi"] == 9.0
    assert item["source_count"] == 3
    assert item["triage_status"] == "new"


def test_next_scan_at_follows_the_scheduler_cron() -> None:
    # 12:00 Asia/Shanghai -> next run is 21:00 the same day.
    noon_shanghai = dt.datetime(2026, 10, 10, 4, 0, tzinfo=dt.timezone.utc)

    assert dashboard_service.next_scan_at(noon_shanghai) == "2026-10-10T21:00:00+08:00"


# --- persistence -------------------------------------------------------------


@pytest.fixture
def sqlite_session(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine, tables=[Event.__table__, EventSource.__table__])
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr("src.db.database.SessionLocal", factory)
    return factory


def test_set_triage_status_keeps_is_dismissed_in_sync(sqlite_session) -> None:
    db = sqlite_session()
    db.add(_event(1))
    db.commit()

    dismissed = set_triage_status(db, 1, "dismissed")
    assert dismissed.triage_status == "dismissed"
    assert dismissed.is_dismissed is True
    assert dismissed.triaged_at is not None

    restored = set_triage_status(db, 1, "new")
    assert restored.is_dismissed is False

    with pytest.raises(ValueError):
        set_triage_status(db, 1, "archived")
    assert set_triage_status(db, 999, "new") is None


def test_get_opportunity_returns_description_and_sources(sqlite_session) -> None:
    db = sqlite_session()
    db.add(_event(5, description="Full description"))
    db.add_all([
        EventSource(event_id=5, source_type="rss", source_name="base_blog",
                    source_url="https://base.org/blog", fetched_at=NOW),
        EventSource(event_id=5, source_type="tavily", source_name="tavily_base",
                    fetched_at=NOW + dt.timedelta(hours=1)),
    ])
    db.commit()

    detail = dashboard_service.get_opportunity(5)

    assert detail["description"] == "Full description"
    assert detail["source_count"] == 2
    assert [source["name"] for source in detail["sources"]] == ["base_blog", "tavily_base"]
    with pytest.raises(ValueError, match="event_not_found"):
        dashboard_service.get_opportunity(404)


def test_triage_opportunity_returns_the_updated_row(sqlite_session) -> None:
    db = sqlite_session()
    db.add(_event(9))
    db.commit()

    row = dashboard_service.triage_opportunity(9, "shortlisted")

    assert row["id"] == 9
    assert row["triage_status"] == "shortlisted"


# --- routes ------------------------------------------------------------------


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("CHAT_API_INTERNAL_KEY", raising=False)
    return TestClient(app)


def test_triage_route_validates_status_and_maps_missing_event(client, monkeypatch) -> None:
    def fake_triage(event_id, status):
        if event_id == 404:
            raise ValueError("event_not_found")
        return dashboard_service.serialize_opportunity(_event(event_id, triage_status=status))

    monkeypatch.setattr("src.chat_api.dashboard_service.triage_opportunity", fake_triage)

    ok = client.put("/api/v1/dashboard/opportunities/3/triage", json={"status": "shortlisted"})
    bad = client.put("/api/v1/dashboard/opportunities/3/triage", json={"status": "archived"})
    missing = client.put("/api/v1/dashboard/opportunities/404/triage", json={"status": "new"})

    assert ok.status_code == 200
    assert ok.json()["triage_status"] == "shortlisted"
    assert bad.status_code == 422
    assert missing.status_code == 404


def test_listing_route_passes_filters_and_rejects_unknown_status(client, monkeypatch) -> None:
    captured = {}

    def fake_list(filters):
        captured.update(filters)
        return {
            "metrics": {"to_review": 0, "shortlisted": 0, "closing_soon": 0,
                        "verified_percent": 0, "total": 0},
            "counts": {"new": 0, "shortlisted": 0, "dismissed": 0, "all": 0},
            "items": [],
        }

    monkeypatch.setattr("src.chat_api.dashboard_service.list_opportunities", fake_list)

    resp = client.get(
        "/api/v1/dashboard/opportunities",
        params={"status": "shortlisted", "q": "sui", "sort": "deadline", "closing_within_days": 7},
    )
    rejected = client.get("/api/v1/dashboard/opportunities", params={"status": "archived"})

    assert resp.status_code == 200
    assert captured["status"] == "shortlisted"
    assert captured["q"] == "sui"
    assert captured["sort"] == "deadline"
    assert captured["closing_within_days"] == 7
    assert rejected.status_code == 422


def test_detail_route_maps_missing_event_to_404(client, monkeypatch) -> None:
    def fake_get(event_id):
        raise ValueError("event_not_found")

    monkeypatch.setattr("src.chat_api.dashboard_service.get_opportunity", fake_get)

    assert client.get("/api/v1/dashboard/opportunities/1").status_code == 404


def test_listing_route_defaults_the_coverage_split(client, monkeypatch) -> None:
    """verified_percent alone cannot tell "nothing verified" from "nothing checked"."""
    monkeypatch.setattr(
        "src.chat_api.dashboard_service.list_opportunities",
        lambda filters: {
            "metrics": {"to_review": 0, "shortlisted": 0, "closing_soon": 0,
                        "verified_percent": 0, "total": 0},
            "counts": {"new": 0, "shortlisted": 0, "dismissed": 0, "all": 0},
            "items": [],
        },
    )

    metrics = client.get("/api/v1/dashboard/opportunities").json()["metrics"]

    assert metrics["verified_count"] == 0
    assert metrics["unchecked_count"] == 0
