import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.chat_api.app import app


def test_verify_requires_internal_key_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("CHAT_API_INTERNAL_KEY", "test-key")

    def fake_verify(_target_ids):
        return {
            "score": 78,
            "level": "medium",
            "verdict": "caution",
            "evidence": [],
            "unknowns": [],
            "conflicts": [],
        }

    monkeypatch.setattr("src.chat_api.verify_service.verify_targets", fake_verify)
    client = TestClient(app)

    resp = client.post("/api/v1/chat/verify", json={"target_event_ids": [1]})

    assert resp.status_code == 401

def test_select_targets_requires_internal_key_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("CHAT_API_INTERNAL_KEY", "test-key")

    def fake_select(_params):
        raise AssertionError("selection must not run without a valid key")

    monkeypatch.setattr("src.chat_api.selection_service.select_target_event_ids", fake_select)
    client = TestClient(app)

    payload = {"mode": "mixed", "event_id": 7, "limit": 20}
    assert client.post("/api/v1/chat/select-targets", json=payload).status_code == 401
    assert (
        client.post(
            "/api/v1/chat/select-targets",
            json=payload,
            headers={"X-Internal-Key": "wrong-key"},
        ).status_code
        == 401
    )
