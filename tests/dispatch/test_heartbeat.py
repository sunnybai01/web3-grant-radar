import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.dispatch import heartbeat as heartbeat_module


class DummySession:
    def close(self):
        pass


NOW = datetime(2026, 10, 12, 3, 4, tzinfo=timezone.utc)


def _patch(monkeypatch, last_success, unhealthy=()):
    monkeypatch.setattr(heartbeat_module, "SessionLocal", lambda: DummySession())
    monkeypatch.setattr(heartbeat_module, "get_unhealthy_sources", lambda db: list(unhealthy))
    monkeypatch.setattr(
        heartbeat_module, "get_last_successful_run_at", lambda db, job_name: last_success
    )
    monkeypatch.setattr(heartbeat_module, "_stale_alerted_for", {})
    monkeypatch.setattr(heartbeat_module, "_down_alerted", set(), raising=False)


def _source(name, status="down", failures=3, error="Client error '404 Not Found'"):
    return type("Source", (), {
        "source_name": name, "status": status,
        "consecutive_failures": failures, "last_error": error,
    })()


def test_heartbeat_returns_stats_without_sending_slack(monkeypatch) -> None:
    sent = []
    _patch(
        monkeypatch,
        last_success=NOW - timedelta(hours=3),
        unhealthy=[type("Source", (), {"source_name": "foo", "status": "down", "consecutive_failures": 3, "last_error": "404"})()],
    )
    monkeypatch.setattr(
        heartbeat_module,
        "_daily_stats",
        {"fetched": 10, "new": 0, "deduped": 9, "pushed": 0, "verified": 0, "fraud": 0},
    )

    stats = heartbeat_module.heartbeat(lambda payload: sent.append(payload), now=NOW)

    assert stats["fetched"] == 10
    assert stats["unhealthy"] == 1
    assert sent == []


def test_heartbeat_alerts_when_main_pipeline_has_not_succeeded_for_too_long(monkeypatch) -> None:
    """10-10 16:28 -> 10-12 11:04 CST: the host slept and nobody was told."""
    sent = []
    _patch(monkeypatch, last_success=datetime(2026, 10, 10, 8, 28, tzinfo=timezone.utc))

    stats = heartbeat_module.heartbeat(sent.append, now=NOW)

    assert len(sent) == 1
    assert "pipeline_grant_hackathon" in sent[0]
    assert "42.6h" in sent[0]
    assert "2026-10-10 16:28" in sent[0]  # last success, Asia/Shanghai
    assert stats["pipeline_stale_hours"] == 42.6


def test_heartbeat_alerts_once_per_outage(monkeypatch) -> None:
    sent = []
    _patch(monkeypatch, last_success=datetime(2026, 10, 10, 8, 28, tzinfo=timezone.utc))

    heartbeat_module.heartbeat(sent.append, now=NOW)
    heartbeat_module.heartbeat(sent.append, now=NOW + timedelta(hours=4))

    assert len(sent) == 1


def test_heartbeat_alerts_again_for_a_new_outage(monkeypatch) -> None:
    sent = []
    _patch(monkeypatch, last_success=datetime(2026, 10, 10, 8, 28, tzinfo=timezone.utc))
    heartbeat_module.heartbeat(sent.append, now=NOW)

    monkeypatch.setattr(
        heartbeat_module,
        "get_last_successful_run_at",
        lambda db, job_name: datetime(2026, 10, 12, 4, 0, tzinfo=timezone.utc),
    )
    heartbeat_module.heartbeat(sent.append, now=datetime(2026, 10, 13, 4, 0, tzinfo=timezone.utc))

    assert len(sent) == 2


def test_heartbeat_alerts_when_main_pipeline_never_succeeded(monkeypatch) -> None:
    sent = []
    _patch(monkeypatch, last_success=None)

    heartbeat_module.heartbeat(sent.append, now=NOW)

    assert len(sent) == 1
    assert "never" in sent[0]


def test_heartbeat_treats_naive_timestamps_as_utc(monkeypatch) -> None:
    sent = []
    _patch(monkeypatch, last_success=(NOW - timedelta(hours=3)).replace(tzinfo=None))

    heartbeat_module.heartbeat(sent.append, now=NOW)

    assert sent == []


# --- dead sources -------------------------------------------------------------
# ETHGlobal, DoraHacks, Gitcoin and EF ESP sat "down" from 07-01 for three months
# and nobody was told: the heartbeat never sent anything.

FRESH = NOW - timedelta(hours=1)


def test_heartbeat_alerts_when_an_enabled_source_goes_down(monkeypatch) -> None:
    sent = []
    _patch(monkeypatch, last_success=FRESH, unhealthy=[_source("optimism_grants", error="401 Unauthorized")])

    heartbeat_module.heartbeat(sent.append, now=NOW, active_sources={"optimism_grants"})

    assert len(sent) == 1
    assert "optimism_grants" in sent[0]
    assert "401 Unauthorized" in sent[0]


def test_heartbeat_ignores_sources_that_are_disabled(monkeypatch) -> None:
    sent = []
    _patch(monkeypatch, last_success=FRESH, unhealthy=[_source("ethglobal")])

    heartbeat_module.heartbeat(sent.append, now=NOW, active_sources={"optimism_rpgf"})

    assert sent == []


def test_heartbeat_does_not_alert_on_degraded_sources(monkeypatch) -> None:
    sent = []
    _patch(monkeypatch, last_success=FRESH, unhealthy=[_source("feed", status="degraded", failures=1)])

    heartbeat_module.heartbeat(sent.append, now=NOW, active_sources={"feed"})

    assert sent == []


def test_heartbeat_alerts_once_per_source_outage(monkeypatch) -> None:
    sent = []
    _patch(monkeypatch, last_success=FRESH, unhealthy=[_source("feed")])
    heartbeat_module.heartbeat(sent.append, now=NOW, active_sources={"feed"})
    heartbeat_module.heartbeat(sent.append, now=NOW, active_sources={"feed"})
    assert len(sent) == 1

    monkeypatch.setattr(heartbeat_module, "get_unhealthy_sources", lambda db: [])
    heartbeat_module.heartbeat(sent.append, now=NOW, active_sources={"feed"})  # recovered
    monkeypatch.setattr(heartbeat_module, "get_unhealthy_sources", lambda db: [_source("feed")])
    heartbeat_module.heartbeat(sent.append, now=NOW, active_sources={"feed"})  # down again

    assert len(sent) == 2
