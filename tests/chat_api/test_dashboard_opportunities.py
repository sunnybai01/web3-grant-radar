import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.chat_api.app import app


def test_dashboard_opportunity_delete_endpoint_removes_event(monkeypatch) -> None:
    client = TestClient(app)

    monkeypatch.setattr(
        "src.chat_api.dashboard_service.delete_opportunity",
        lambda event_id: {"status": "success", "event_id": event_id, "deleted": True},
    )

    resp = client.delete("/api/v1/dashboard/opportunities/101")

    assert resp.status_code == 200
    assert resp.json() == {"status": "success", "event_id": 101, "deleted": True}

def test_manual_scan_status_carries_the_error_field(monkeypatch) -> None:
    """A failed scan must be able to say why; the field was missing from the model."""
    from src.chat_api import app as chat_app
    from src.chat_api import manual_scan_service

    monkeypatch.setattr(
        manual_scan_service,
        "get_manual_scan_status",
        lambda: {
            "job_id": "job-1", "status": "failed", "triggered": True,
            "started_at": "2026-10-10T05:50:08+00:00", "finished_at": "2026-10-10T05:51:00+00:00",
            "current_stage": "", "schedules": [], "error": "llm unavailable",
        },
    )

    payload = chat_app.manual_scan_status()

    assert payload.status == "failed"
    assert payload.error == "llm unavailable"
