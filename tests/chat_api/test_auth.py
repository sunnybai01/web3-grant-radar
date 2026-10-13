"""Internal-key auth must fail closed.

An empty CHAT_API_INTERNAL_KEY used to switch auth off entirely: the running
chat-api had no key configured, so DELETE, reset-dedup (truncates raw_signals,
clears the vector index) and manual scans answered anyone who could reach it.
"""
import sys
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.chat_api.app import app
from src.chat_api.auth import verify_internal_key

pytestmark = pytest.mark.real_auth

GOOD_KEY = "k" * 32


def _fake_verify(_target_ids):
    return {
        "score": 78,
        "level": "medium",
        "verdict": "caution",
        "evidence": [],
        "unknowns": [],
        "conflicts": [],
    }


def test_verify_requires_internal_key_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("CHAT_API_INTERNAL_KEY", GOOD_KEY)
    monkeypatch.setattr("src.chat_api.verify_service.verify_targets", _fake_verify)
    client = TestClient(app)

    resp = client.post("/api/v1/chat/verify", json={"target_event_ids": [1]})

    assert resp.status_code == 401


def test_correct_internal_key_is_accepted(monkeypatch) -> None:
    monkeypatch.setenv("CHAT_API_INTERNAL_KEY", GOOD_KEY)
    monkeypatch.setattr("src.chat_api.verify_service.verify_targets", _fake_verify)
    client = TestClient(app)

    resp = client.post(
        "/api/v1/chat/verify",
        json={"target_event_ids": [1]},
        headers={"X-Internal-Key": GOOD_KEY},
    )

    assert resp.status_code == 200


def test_requests_are_rejected_when_no_key_is_configured(monkeypatch) -> None:
    monkeypatch.delenv("CHAT_API_INTERNAL_KEY", raising=False)
    monkeypatch.setattr("src.chat_api.verify_service.verify_targets", _fake_verify)
    client = TestClient(app)

    resp = client.post("/api/v1/chat/verify", json={"target_event_ids": [1]})

    assert resp.status_code == 503


def test_select_targets_requires_internal_key_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("CHAT_API_INTERNAL_KEY", GOOD_KEY)

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


def test_health_needs_no_key(monkeypatch) -> None:
    monkeypatch.setenv("CHAT_API_INTERNAL_KEY", GOOD_KEY)

    assert TestClient(app).get("/api/v1/chat/health").status_code == 200


@pytest.mark.parametrize("key", [None, "", "   ", "short-key"])
def test_startup_refuses_without_a_usable_key(monkeypatch, key) -> None:
    if key is None:
        monkeypatch.delenv("CHAT_API_INTERNAL_KEY", raising=False)
    else:
        monkeypatch.setenv("CHAT_API_INTERNAL_KEY", key)

    with pytest.raises(RuntimeError, match="CHAT_API_INTERNAL_KEY"):
        with TestClient(app):
            pass


def test_startup_succeeds_with_a_usable_key(monkeypatch) -> None:
    monkeypatch.setenv("CHAT_API_INTERNAL_KEY", GOOD_KEY)

    with TestClient(app) as client:
        assert client.get("/api/v1/chat/health").status_code == 200


def test_every_route_except_health_requires_the_key() -> None:
    """select-targets once shipped without the dependency; keep the table honest."""
    unprotected = [
        route.path
        for route in app.routes
        if isinstance(route, APIRoute)
        and route.path != "/api/v1/chat/health"
        and not any(dep.call is verify_internal_key for dep in route.dependant.dependencies)
    ]

    assert unprotected == []
