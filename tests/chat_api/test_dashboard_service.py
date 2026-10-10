import sys
from pathlib import Path
from types import SimpleNamespace
import types

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.chat_api import dashboard_service


class _FakeQuery:
    def __init__(self, events, filter_calls=None):
        self._events = events
        self.filter_calls = filter_calls if filter_calls is not None else []

    def filter(self, *args, **kwargs):
        self.filter_calls.extend(args)
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def all(self):
        return self._events


class _FakeSession:
    def __init__(self, events, filter_calls=None):
        self._events = events
        self.filter_calls = filter_calls if filter_calls is not None else []

    def query(self, _model):
        return _FakeQuery(self._events, self.filter_calls)

    def close(self):
        return None


class _FakeColumn:
    def __ge__(self, other):
        return (">=", other)

    def in_(self, values):
        return ("in", tuple(values))

    def ilike(self, value):
        return ("ilike", value)


def test_list_opportunities_filters_to_official_trust(monkeypatch) -> None:
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    events = [
        SimpleNamespace(
            id=1,
            final_score=8.6,
            event_type="grant",
            title="Base Builder Fund",
            ecosystem="base",
            amount="$50,000",
            deadline=None,
            heat_count=2,
            is_verified=True,
            application_url="https://apply.base.org",
            source_url="https://base.org/grants",
            verification_log={
                "verdict": "verified",
                "source_context": {"source_tier": "official", "official": True},
            },
            created_at=now,
            status="new",
            is_dismissed=False,
        ),
        SimpleNamespace(
            id=2,
            final_score=6.2,
            event_type="hackathon",
            title="Discovery Hackathon",
            ecosystem="newchain",
            amount="$10,000",
            deadline=None,
            heat_count=1,
            is_verified=True,
            application_url="https://ethglobal.com/apply",
            source_url="https://ethglobal.com/events",
            verification_log={
                "verdict": "degraded",
                "source_context": {"source_tier": "discovery", "official": False},
            },
            created_at=now,
            status="new",
            is_dismissed=False,
        ),
    ]

    fake_db_module = types.ModuleType("src.db.database")
    fake_db_module.SessionLocal = lambda: _FakeSession(events)

    fake_models_module = types.ModuleType("src.db.models")
    fake_models_module.Event = SimpleNamespace(
        created_at=_FakeColumn(),
        status=_FakeColumn(),
        final_score=_FakeColumn(),
        event_type=_FakeColumn(),
        ecosystem=_FakeColumn(),
    )

    fake_sqlalchemy_module = types.ModuleType("sqlalchemy")
    fake_sqlalchemy_module.desc = lambda value: value
    fake_sqlalchemy_module.func = SimpleNamespace(coalesce=lambda value, _default: value)

    monkeypatch.setitem(sys.modules, "src.db.database", fake_db_module)
    monkeypatch.setitem(sys.modules, "src.db.models", fake_models_module)
    monkeypatch.setitem(sys.modules, "sqlalchemy", fake_sqlalchemy_module)

    result = dashboard_service.list_opportunities(
        {
            "ecosystem": "",
            "min_score": 5.0,
            "days": 15,
            "source_trust": "official",
        }
    )

    assert result["metrics"]["total_shown"] == 1
    assert result["metrics"]["official"] == 1
    assert result["metrics"]["discovery"] == 0
    assert result["metrics"]["grants"] == 1
    assert result["metrics"]["hackathons"] == 0
    assert "bounties" not in result["metrics"]
    assert len(result["items"]) == 1
    assert result["items"][0]["id"] == 1
    assert result["items"][0]["source_trust"] == "official"
    assert result["items"][0]["verification_verdict"] == "verified"


def test_list_opportunities_without_min_score_keeps_low_and_unscored_events(monkeypatch) -> None:
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)

    def _event(event_id, score):
        return SimpleNamespace(
            id=event_id,
            final_score=score,
            event_type="grant",
            title=f"Event {event_id}",
            ecosystem="base",
            amount="-",
            deadline=None,
            heat_count=1,
            is_verified=False,
            application_url="",
            source_url="",
            verification_log={},
            created_at=now,
            status="new",
            is_dismissed=False,
        )

    events = [_event(1, 8.6), _event(2, 2.1), _event(3, None)]
    filter_calls = []

    fake_db_module = types.ModuleType("src.db.database")
    fake_db_module.SessionLocal = lambda: _FakeSession(events, filter_calls)

    fake_models_module = types.ModuleType("src.db.models")
    fake_models_module.Event = SimpleNamespace(
        created_at=_FakeColumn(),
        status=_FakeColumn(),
        final_score=_FakeColumn(),
        event_type=_FakeColumn(),
        ecosystem=_FakeColumn(),
    )

    fake_sqlalchemy_module = types.ModuleType("sqlalchemy")
    fake_sqlalchemy_module.desc = lambda value: value
    fake_sqlalchemy_module.func = SimpleNamespace(coalesce=lambda value, _default: value)

    monkeypatch.setitem(sys.modules, "src.db.database", fake_db_module)
    monkeypatch.setitem(sys.modules, "src.db.models", fake_models_module)
    monkeypatch.setitem(sys.modules, "sqlalchemy", fake_sqlalchemy_module)

    result = dashboard_service.list_opportunities({"ecosystem": "", "days": 15})

    # No score predicate is pushed to SQL, so unscored (NULL) events survive too.
    assert not [call for call in filter_calls if call[0] == ">=" and call[1] == 0.0]
    assert [item["id"] for item in result["items"]] == [1, 2, 3]
    assert result["items"][2]["score"] is None
    assert result["metrics"]["total_shown"] == 3


def test_list_opportunities_defaults_to_unbounded_time_window(monkeypatch) -> None:
    filter_calls = []

    fake_db_module = types.ModuleType("src.db.database")
    fake_db_module.SessionLocal = lambda: _FakeSession([], filter_calls)

    fake_models_module = types.ModuleType("src.db.models")
    fake_models_module.Event = SimpleNamespace(
        created_at=_FakeColumn(),
        status=_FakeColumn(),
        final_score=_FakeColumn(),
        event_type=_FakeColumn(),
        ecosystem=_FakeColumn(),
    )

    fake_sqlalchemy_module = types.ModuleType("sqlalchemy")
    fake_sqlalchemy_module.desc = lambda value: value
    fake_sqlalchemy_module.func = SimpleNamespace(coalesce=lambda value, _default: value)

    monkeypatch.setitem(sys.modules, "src.db.database", fake_db_module)
    monkeypatch.setitem(sys.modules, "src.db.models", fake_models_module)
    monkeypatch.setitem(sys.modules, "sqlalchemy", fake_sqlalchemy_module)

    dashboard_service.list_opportunities({})

    # created_at >= cutoff is the only ">=" predicate this query can emit; with no
    # days filter it must be absent entirely.
    assert not [call for call in filter_calls if call[0] == ">="]

    # An explicit days value still applies a cutoff.
    filter_calls.clear()
    dashboard_service.list_opportunities({"days": 15})
    assert [call for call in filter_calls if call[0] == ">="]


def test_delete_opportunity_returns_deleted_payload(monkeypatch) -> None:
    fake_event = SimpleNamespace(id=7)

    class _FakeSessionForDelete:
        def close(self):
            return None

    fake_db_module = types.ModuleType("src.db.database")
    fake_db_module.SessionLocal = lambda: _FakeSessionForDelete()

    fake_queries_module = types.ModuleType("src.db.queries")
    fake_queries_module.delete_event = lambda db, event_id: fake_event if event_id == 7 else None
    # delete_opportunity also cleans up the raw signal + vector traces; the fake
    # module has to provide every name the real one exports for that path.
    fake_queries_module.get_event_signal_ids = lambda db, event_id: [11, 12]
    fake_queries_module.delete_raw_signals_by_ids = lambda db, ids: len(ids)

    monkeypatch.setitem(sys.modules, "src.db.database", fake_db_module)
    monkeypatch.setitem(sys.modules, "src.db.queries", fake_queries_module)

    result = dashboard_service.delete_opportunity(7)

    assert result == {"status": "success", "event_id": 7, "deleted": True}


def test_delete_opportunity_raises_for_missing_event(monkeypatch) -> None:
    class _FakeSessionForDelete:
        def close(self):
            return None

    fake_db_module = types.ModuleType("src.db.database")
    fake_db_module.SessionLocal = lambda: _FakeSessionForDelete()

    fake_queries_module = types.ModuleType("src.db.queries")
    fake_queries_module.delete_event = lambda db, event_id: None
    fake_queries_module.get_event_signal_ids = lambda db, event_id: []
    fake_queries_module.delete_raw_signals_by_ids = lambda db, ids: 0

    monkeypatch.setitem(sys.modules, "src.db.database", fake_db_module)
    monkeypatch.setitem(sys.modules, "src.db.queries", fake_queries_module)

    with __import__("pytest").raises(ValueError, match="event_not_found"):
        dashboard_service.delete_opportunity(99)


def test_list_investigations_returns_summary_and_items(monkeypatch) -> None:
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    missions = [
        SimpleNamespace(
            id=7,
            goal="investigate_event:42",
            event_id=42,
            status="completed",
            mission_type="single_event_investigation",
            max_steps=5,
            conclusion={
                "title": "Base Builder Rewards",
                "verdict": "verified",
                "recommended_action": "promote",
                "similar_events": [{"event_id": 2}],
                "supporting_evidence": {"title": "Base Builder Rewards"},
            },
            error_message="",
            started_at=now,
            finished_at=now,
        ),
        SimpleNamespace(
            id=8,
            goal="investigate_event:99",
            event_id=99,
            status="failed",
            mission_type="single_event_investigation",
            max_steps=5,
            conclusion=None,
            error_message="event_not_found",
            started_at=now,
            finished_at=None,
        ),
    ]

    fake_db_module = types.ModuleType("src.db.database")
    fake_db_module.SessionLocal = lambda: _FakeSession(missions)

    fake_models_module = types.ModuleType("src.db.models")
    fake_models_module.AgentMission = SimpleNamespace(
        started_at=_FakeColumn(),
    )

    fake_sqlalchemy_module = types.ModuleType("sqlalchemy")
    fake_sqlalchemy_module.desc = lambda value: value
    fake_sqlalchemy_module.func = SimpleNamespace(coalesce=lambda value, _default: value)

    monkeypatch.setitem(sys.modules, "src.db.database", fake_db_module)
    monkeypatch.setitem(sys.modules, "src.db.models", fake_models_module)
    monkeypatch.setitem(sys.modules, "sqlalchemy", fake_sqlalchemy_module)

    result = dashboard_service.list_investigations(limit=50)

    assert result["summary"]["total_runs"] == 2
    assert result["summary"]["completed"] == 1
    assert result["summary"]["failed"] == 1
    assert result["items"][0]["mission_id"] == 7
    assert result["items"][0]["recommended_action"] == "promote"
    assert result["items"][0]["similar_count"] == 1
    assert result["items"][0]["has_supporting_evidence"] is True