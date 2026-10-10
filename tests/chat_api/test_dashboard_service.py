import sys
from pathlib import Path
from types import SimpleNamespace
import types

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.chat_api import dashboard_service


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    def query(self, _model):
        return _FakeQuery(self._rows)

    def close(self):
        return None


class _FakeColumn:
    def __ge__(self, other):
        return (">=", other)

    def desc(self):
        return self


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