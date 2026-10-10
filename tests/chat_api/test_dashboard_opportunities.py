import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.chat_api.app import app


def test_dashboard_opportunities_returns_metrics_and_items(monkeypatch) -> None:
    client = TestClient(app)

    def fake_list_opportunities(filters):
        assert filters["event_types"] == ["grant", "hackathon"]
        assert filters["days"] == 15
        assert filters["min_score"] == 5.0
        assert filters["source_trust"] == "official"
        return {
            "metrics": {
                "total_shown": 2,
                "avg_score": 7.5,
                "verified_percent": 50,
                "grants": 1,
                "hackathons": 1,
                "official": 1,
                "discovery": 1,
            },
            "items": [
                {
                    "id": 101,
                    "score": 8.4,
                    "type": "GRANT",
                    "title": "Sui Builder Fund",
                    "ecosystem": "sui",
                    "amount": "$10,000",
                    "deadline": "2026-07-20",
                    "heat": 3,
                    "verified": True,
                    "source_trust": "official",
                    "verification_verdict": "verified",
                    "apply_url": "https://example.com/apply",
                }
            ],
        }

    monkeypatch.setattr("src.chat_api.dashboard_service.list_opportunities", fake_list_opportunities)

    resp = client.get(
        "/api/v1/dashboard/opportunities",
        params={
            "ecosystem": "",
            "min_score": 5.0,
            "days": 15,
            "source_trust": "official",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["metrics"]["total_shown"] == 2
    assert body["metrics"]["official"] == 1
    assert "bounties" not in body["metrics"]
    assert body["items"][0]["id"] == 101
    assert body["items"][0]["title"] == "Sui Builder Fund"
    assert body["items"][0]["source_trust"] == "official"
    assert body["items"][0]["verification_verdict"] == "verified"


def test_dashboard_opportunities_defaults_to_no_score_floor(monkeypatch) -> None:
    client = TestClient(app)
    captured = {}

    def fake_list_opportunities(filters):
        captured.update(filters)
        return {
            "metrics": {
                "total_shown": 0,
                "avg_score": 0.0,
                "verified_percent": 0,
                "grants": 0,
                "hackathons": 0,
                "official": 0,
                "discovery": 0,
            },
            "items": [],
        }

    monkeypatch.setattr("src.chat_api.dashboard_service.list_opportunities", fake_list_opportunities)

    resp = client.get("/api/v1/dashboard/opportunities")

    assert resp.status_code == 200
    assert captured["min_score"] == 0.0


def test_dashboard_opportunity_delete_endpoint_removes_event(monkeypatch) -> None:
    client = TestClient(app)

    monkeypatch.setattr(
        "src.chat_api.dashboard_service.delete_opportunity",
        lambda event_id: {"status": "success", "event_id": event_id, "deleted": True},
    )

    resp = client.delete("/api/v1/dashboard/opportunities/101")

    assert resp.status_code == 200
    assert resp.json() == {"status": "success", "event_id": 101, "deleted": True}