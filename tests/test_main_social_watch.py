import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.classifier.classifier import Classification
from src.fetchers.base import FetchedItem
from src.main import _parse_datetime, _persistable_event_data, _staleness_reason, run_pipeline


@pytest.fixture(autouse=True)
def signal_outcomes(monkeypatch):
    """Record mark_raw_signal_processed calls instead of writing to a database."""
    recorded = []
    monkeypatch.setattr(
        "src.main.mark_raw_signal_processed",
        lambda db, signal_id, error=None: recorded.append((signal_id, error)),
        raising=False,
    )
    return recorded


def _iso(days_from_now: int) -> str:
    """ISO timestamp relative to now.

    run_pipeline reads the real clock, so hardcoded dates turn these tests into time
    bombs — a literal "future" deadline silently becomes expired and the pipeline
    starts dropping the fixture as stale.
    """
    return (datetime.now(timezone.utc) + timedelta(days=days_from_now)).isoformat()


def test_main_declares_run_social_watch_wrapper() -> None:
    source = Path("src/main.py").read_text(encoding="utf-8")
    module = ast.parse(source)

    function = next(
        node for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "run_social_watch"
    )

    assert len(function.body) == 2
    assert isinstance(function.body[1], ast.Return)

    call = function.body[1].value
    assert isinstance(call, ast.Call)
    assert isinstance(call.func, ast.Name)
    assert call.func.id == "run_pipeline"
    assert len(call.args) == 1
    assert isinstance(call.args[0], ast.Constant)
    assert call.args[0].value == "social_watch"


def test_persistable_event_data_strips_non_event_model_fields() -> None:
    event_data = {
        "event_type": "grant",
        "title": "ESP Grants",
        "description": "Support for ecosystem teams",
        "ecosystem": "ethereum",
        "application_url": "https://esp.ethereum.foundation/apply",
        "source_url": "https://x.com/EF_ESP/status/1",
        "source_platform": "twitter_ef_esp",
        "chain": "ethereum",
        "source_tier": "official",
        "official": True,
        "signal_type": "social",
    }

    persisted = _persistable_event_data(event_data)

    assert persisted["event_type"] == "grant"
    assert persisted["ecosystem"] == "ethereum"
    assert "chain" not in persisted
    assert "source_tier" not in persisted
    assert "official" not in persisted
    assert "signal_type" not in persisted


def test_staleness_reason_keeps_recent_discovery_item_with_deadline() -> None:
    """Discovery item with a future deadline should be kept (not stale)."""
    now = datetime(2026, 7, 3, tzinfo=timezone.utc)
    item = FetchedItem(
        source_type="twitter",
        source_name="twitter_gitcoin",
        raw_content="grant round open",
        raw_url="https://x.com/gitcoin/status/1",
        canonical_url="https://x.com/gitcoin/status/1",
        metadata={
            "created_at": (now - timedelta(days=8)).isoformat(),
        },
    )

    assert _staleness_reason(
        item,
        {
            "start_date": "2026-06-01T00:00:00+00:00",
            "deadline": "2026-07-20T00:00:00+00:00",
        },
        source_tier="discovery",
        now=now,
    ) is None


def test_staleness_reason_marks_items_with_past_deadline() -> None:
    now = datetime(2026, 7, 3, tzinfo=timezone.utc)
    item = FetchedItem(
        source_type="twitter",
        source_name="twitter_gitcoin",
        raw_content="grant round open",
        raw_url="https://x.com/gitcoin/status/1",
        canonical_url="https://x.com/gitcoin/status/1",
        metadata={
            "created_at": "2026-07-02T00:00:00+00:00",
        },
    )

    assert _staleness_reason(
        item,
        {
            "start_date": "2026-06-20T00:00:00+00:00",
            "deadline": "2026-07-01T00:00:00+00:00",
        },
        source_tier="discovery",
        now=now,
    ) == "deadline_expired"


def test_staleness_reason_keeps_item_with_deadline_but_no_published_at() -> None:
    """Even without published_at, a future deadline indicates a valid opportunity."""
    now = datetime(2026, 7, 3, tzinfo=timezone.utc)
    item = FetchedItem(
        source_type="twitter",
        source_name="twitter_gitcoin",
        raw_content="grant round open",
        raw_url="https://x.com/gitcoin/status/1",
        canonical_url="https://x.com/gitcoin/status/1",
        metadata={},
    )

    assert _staleness_reason(
        item,
        {
            "start_date": "2026-07-01T00:00:00+00:00",
            "deadline": "2026-07-20T00:00:00+00:00",
        },
        source_tier="discovery",
        now=now,
    ) is None


def test_staleness_reason_keeps_item_without_start_date() -> None:
    """start_date is no longer required — only deadline matters for expiry."""
    now = datetime(2026, 7, 3, tzinfo=timezone.utc)
    item = FetchedItem(
        source_type="twitter",
        source_name="twitter_gitcoin",
        raw_content="grant round open",
        raw_url="https://x.com/gitcoin/status/1",
        canonical_url="https://x.com/gitcoin/status/1",
        metadata={
            "created_at": now.isoformat(),
        },
    )

    assert _staleness_reason(
        item,
        {"deadline": "2026-07-20T00:00:00+00:00"},
        source_tier="discovery",
        now=now,
    ) is None


def test_staleness_reason_drops_discovery_with_no_time_info() -> None:
    """Discovery source with neither published_at nor deadline — too uncertain."""
    now = datetime(2026, 7, 3, tzinfo=timezone.utc)
    item = FetchedItem(
        source_type="twitter",
        source_name="twitter_gitcoin",
        raw_content="grant round open",
        raw_url="https://x.com/gitcoin/status/1",
        canonical_url="https://x.com/gitcoin/status/1",
        metadata={},
    )

    assert _staleness_reason(
        item,
        {"start_date": "2026-07-01T00:00:00+00:00"},
        source_tier="discovery",
        now=now,
    ) == "missing_published_at"


def test_staleness_reason_keeps_official_source_even_with_no_time_info() -> None:
    """Official sources are always kept (assumed rolling opportunities)."""
    now = datetime(2026, 7, 3, tzinfo=timezone.utc)
    item = FetchedItem(
        source_type="rss",
        source_name="ethereum_foundation_esp",
        raw_content="grant round open",
        raw_url="https://blog.ethereum.org/esp",
        canonical_url="https://blog.ethereum.org/esp",
        metadata={},
    )

    assert _staleness_reason(
        item,
        {"start_date": "2026-07-01T00:00:00+00:00"},
        source_tier="official",
        now=now,
    ) is None


def test_run_pipeline_keeps_valid_official_item(monkeypatch) -> None:
    fake_db = SimpleNamespace(close=lambda: None)
    finished = {}

    fake_fetcher = SimpleNamespace(config={"fetch_method": "twitter"})

    class FakeRegistry:
        _fetchers = {"twitter_gitcoin": fake_fetcher}

        def fetch_all_with_status(self, schedule, should_skip=None):
            item = FetchedItem(
                source_type="twitter",
                source_name="twitter_gitcoin",
                raw_content="grant round open",
                raw_url="https://x.com/gitcoin/status/1",
                canonical_url="https://x.com/gitcoin/status/1",
                metadata={
                    "created_at": _iso(-14),
                    "chain": "multi",
                    "source_tier": "official",
                    "official": True,
                    "signal_type": "social",
                },
            )
            return [item], {"twitter_gitcoin": {"success": True, "error": None, "skipped": None}}

    class FakeClassifier:
        def classify(self, item):
            return "GRANT", {
                "title": "Gitcoin Grants",
                "description": "Open round",
                "ecosystem": "multi",
                "application_url": "https://gitcoin.co",
                "start_date": _iso(-3),
                "deadline": _iso(17),
            }

    class PassThroughDeduplicator:
        def check_and_process(self, *args, **kwargs):
            return 1, True  # event_id=1, is_new=True

    monkeypatch.setattr("src.main.SessionLocal", lambda: fake_db)
    monkeypatch.setattr("src.main.create_schedule_log", lambda db, name: SimpleNamespace(id=999))
    monkeypatch.setattr(
        "src.main.finish_schedule_log",
        lambda db, log_id, **kwargs: finished.update({"log_id": log_id, **kwargs}),
    )
    monkeypatch.setattr("src.main.upsert_source_health", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.main.get_source_health", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.main.process_item_l1", lambda db, item: 123)
    monkeypatch.setattr("src.main.increment_stat", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.main.verify_opportunity",
                        lambda **kw: {"verdict": "verified", "verification_log": {}})
    monkeypatch.setattr("src.main.update_event", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.main._try_extract_dates_from_url", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.main._init_components", lambda: None)
    monkeypatch.setattr("src.main._fetcher_registry", FakeRegistry())
    monkeypatch.setattr("src.main._classifier", FakeClassifier())
    monkeypatch.setattr("src.main._deduplicator", PassThroughDeduplicator())
    monkeypatch.setattr("src.main._scorer", SimpleNamespace(score=lambda d: d))
    monkeypatch.setattr("src.main._slack", SimpleNamespace(is_configured=False, push_new_event=lambda e: None))

    result = run_pipeline("social_watch")

    assert result["status"] == "success"
    assert result["fetched"] == 1
    assert result["classified"] == 1
    assert result["new"] == 1
    assert result["verified"] == 1
    assert finished["log_id"] == 999
    assert finished["items_fetched"] == 1
    assert finished["items_new"] == 1


def _discovery_item(now: datetime) -> FetchedItem:
    return FetchedItem(
        source_type="tavily_search",
        source_name="tavily_sui_grants",
        raw_content="hackathon",
        raw_url="https://example.com/a",
        canonical_url="https://example.com/a",
        metadata={"created_at": (now - timedelta(days=2)).isoformat()},
    )


def _official_tweet(published: datetime) -> FetchedItem:
    return FetchedItem(
        source_type="twitter",
        source_name="twitter_optimism_grants",
        raw_content="RetroPGF Round 2 nominations are open",
        raw_url="https://x.com/OptimismGov/status/1615456050391683073",
        canonical_url="https://x.com/OptimismGov/status/1615456050391683073",
        metadata={"created_at": published},
    )


def test_staleness_reason_drops_old_official_post_without_deadline() -> None:
    """#165 'Optimism RetroPGF Round 2 Nomination Window' (tweeted 2023-01-17) was
    pushed as new on 2026-10-10: official sources skipped every age rule."""
    now = datetime(2026, 10, 10, tzinfo=timezone.utc)

    assert _staleness_reason(
        _official_tweet(datetime(2023, 1, 17, tzinfo=timezone.utc)),
        {"title": "Optimism RetroPGF Round 2 Nomination Window"},
        source_tier="official",
        now=now,
    ) == "published_too_old"


@pytest.mark.parametrize("rolling", [True, "true"])
def test_staleness_reason_keeps_old_official_post_for_a_rolling_program(rolling) -> None:
    now = datetime(2026, 10, 10, tzinfo=timezone.utc)

    assert _staleness_reason(
        _official_tweet(datetime(2026, 5, 1, tzinfo=timezone.utc)),
        {"title": "Ecosystem Grants", "is_rolling": rolling},
        source_tier="official",
        now=now,
    ) is None


def test_staleness_reason_keeps_old_official_post_with_a_future_deadline() -> None:
    now = datetime(2026, 10, 10, tzinfo=timezone.utc)

    assert _staleness_reason(
        _official_tweet(datetime(2026, 5, 1, tzinfo=timezone.utc)),
        {"title": "Season 9 Missions", "deadline": "2026-11-30T00:00:00+00:00"},
        source_tier="official",
        now=now,
    ) is None


def test_staleness_reason_keeps_recent_official_post_without_deadline() -> None:
    now = datetime(2026, 10, 10, tzinfo=timezone.utc)

    assert _staleness_reason(
        _official_tweet(datetime(2026, 10, 1, tzinfo=timezone.utc)),
        {"title": "Builder Grants"},
        source_tier="official",
        now=now,
    ) is None


def test_staleness_reason_drops_title_whose_only_year_is_past() -> None:
    """'ETHIndiaVilla 2025' seen in 2026 is last year's event, even if recently crawled."""
    now = datetime(2026, 8, 4, tzinfo=timezone.utc)

    assert _staleness_reason(
        _discovery_item(now),
        {"title": "ETHIndiaVilla 2025"},
        source_tier="discovery",
        now=now,
    ) == "title_year_past"


def test_staleness_reason_keeps_title_with_current_year() -> None:
    now = datetime(2026, 8, 4, tzinfo=timezone.utc)

    assert _staleness_reason(
        _discovery_item(now),
        {"title": "ETHGlobal New York 2026 Hackathon"},
        source_tier="discovery",
        now=now,
    ) is None


def test_staleness_reason_title_year_does_not_veto_a_future_deadline() -> None:
    """An explicit open window outranks a stale-looking title."""
    now = datetime(2026, 8, 4, tzinfo=timezone.utc)

    assert _staleness_reason(
        _discovery_item(now),
        {"title": "2025 Builder Program", "deadline": "2026-09-01T00:00:00+00:00"},
        source_tier="discovery",
        now=now,
    ) is None


def test_staleness_reason_title_year_rule_applies_to_official_sources() -> None:
    now = datetime(2026, 8, 4, tzinfo=timezone.utc)

    assert _staleness_reason(
        _discovery_item(now),
        {"title": "ETHIndiaVilla 2025"},
        source_tier="official",
        now=now,
    ) == "title_year_past"


def test_staleness_reason_ignores_titles_without_years() -> None:
    now = datetime(2026, 8, 4, tzinfo=timezone.utc)

    assert _staleness_reason(
        _discovery_item(now),
        {"title": "Sui Overflow Hackathon"},
        source_tier="discovery",
        now=now,
    ) is None


def test_staleness_reason_drops_start_date_past_grace_without_deadline() -> None:
    """ETHToronto 'running from July 26' with no deadline, seen 20 days later."""
    now = datetime(2026, 8, 15, tzinfo=timezone.utc)

    assert _staleness_reason(
        _discovery_item(now),
        {"title": "ETHToronto Hackathon", "start_date": "2026-07-26T00:00:00+00:00"},
        source_tier="discovery",
        now=now,
    ) == "start_date_passed"


def test_staleness_reason_keeps_recently_started_program() -> None:
    """Inside the grace window a started program may still accept entries."""
    now = datetime(2026, 8, 4, tzinfo=timezone.utc)

    assert _staleness_reason(
        _discovery_item(now),
        {"title": "ETHToronto Hackathon", "start_date": "2026-07-31T00:00:00+00:00"},
        source_tier="discovery",
        now=now,
    ) is None


def test_run_pipeline_drops_results_announced_item(monkeypatch) -> None:
    """A grant already awarded to a named project is not an actionable opportunity."""
    fake_db = SimpleNamespace(close=lambda: None)
    finished = {}
    scraped = []

    fake_fetcher = SimpleNamespace(config={"fetch_method": "twitter"})

    class FakeRegistry:
        _fetchers = {"twitter_gitcoin": fake_fetcher}

        def fetch_all_with_status(self, schedule, should_skip=None):
            item = FetchedItem(
                source_type="twitter",
                source_name="twitter_gitcoin",
                raw_content="grant approved",
                raw_url="https://x.com/avax/status/1",
                canonical_url="https://x.com/avax/status/1",
                metadata={
                    "created_at": _iso(-1),
                    "source_tier": "official",
                    "official": True,
                },
            )
            return [item], {"twitter_gitcoin": {"success": True, "error": None, "skipped": None}}

    class FakeClassifier:
        def classify(self, item):
            return "GRANT", {
                "title": "Avalanche Team1 Accelerator Grant for YourGrails",
                "description": "The committee has approved a $30,000 grant for YourGrails.",
                "opportunity_stage": "results_announced",
                # Deliberately open: the gate must drop this on stage alone.
                "deadline": _iso(120),
            }

    def _fail_if_called(*args, **kwargs):
        scraped.append(args)
        return None

    monkeypatch.setattr("src.main.SessionLocal", lambda: fake_db)
    monkeypatch.setattr("src.main.create_schedule_log", lambda db, name: SimpleNamespace(id=999))
    monkeypatch.setattr(
        "src.main.finish_schedule_log",
        lambda db, log_id, **kwargs: finished.update({"log_id": log_id, **kwargs}),
    )
    monkeypatch.setattr("src.main.upsert_source_health", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.main.get_source_health", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.main.process_item_l1", lambda db, item: 123)
    monkeypatch.setattr("src.main.increment_stat", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.main._try_extract_dates_from_url", _fail_if_called)
    monkeypatch.setattr("src.main._init_components", lambda: None)
    monkeypatch.setattr("src.main._fetcher_registry", FakeRegistry())
    monkeypatch.setattr("src.main._classifier", FakeClassifier())
    monkeypatch.setattr("src.main._slack", SimpleNamespace(is_configured=False, push_new_event=lambda e: None))

    result = run_pipeline("social_watch")

    assert result["status"] == "success"
    assert result["classified"] == 1
    assert result["unactionable"] == 1
    # Dropped before dedup/verify/score, so nothing was created or pushed.
    assert result["new"] == 0
    assert result["verified"] == 0
    assert result["pushed"] == 0
    # The gate runs before the secondary date scrape, so no network call happened.
    assert scraped == []


def test_run_pipeline_keeps_official_item_even_without_start_date(monkeypatch) -> None:
    fake_db = SimpleNamespace(close=lambda: None)
    finished = {}

    fake_fetcher = SimpleNamespace(config={"fetch_method": "twitter"})

    class FakeRegistry:
        _fetchers = {"twitter_gitcoin": fake_fetcher}

        def fetch_all_with_status(self, schedule, should_skip=None):
            item = FetchedItem(
                source_type="twitter",
                source_name="twitter_gitcoin",
                raw_content="grant round open",
                raw_url="https://x.com/gitcoin/status/1",
                canonical_url="https://x.com/gitcoin/status/1",
                metadata={
                    "created_at": _iso(-2),
                    "chain": "multi",
                    "source_tier": "official",
                    "official": True,
                    "signal_type": "social",
                },
            )
            return [item], {"twitter_gitcoin": {"success": True, "error": None, "skipped": None}}

    class FakeClassifier:
        def classify(self, item):
            return "GRANT", {
                "title": "Gitcoin Grants",
                "description": "Open round",
                "ecosystem": "multi",
                "application_url": "https://gitcoin.co",
                "deadline": _iso(17),
            }

    class PassThroughDeduplicator:
        def check_and_process(self, *args, **kwargs):
            return 1, True  # event_id=1, is_new=True

    monkeypatch.setattr("src.main.SessionLocal", lambda: fake_db)
    monkeypatch.setattr("src.main.create_schedule_log", lambda db, name: SimpleNamespace(id=999))
    monkeypatch.setattr(
        "src.main.finish_schedule_log",
        lambda db, log_id, **kwargs: finished.update({"log_id": log_id, **kwargs}),
    )
    monkeypatch.setattr("src.main.upsert_source_health", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.main.get_source_health", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.main.process_item_l1", lambda db, item: 123)
    monkeypatch.setattr("src.main.increment_stat", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.main.verify_opportunity",
                        lambda **kw: {"verdict": "verified", "verification_log": {}})
    monkeypatch.setattr("src.main.update_event", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.main._try_extract_dates_from_url", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.main._init_components", lambda: None)
    monkeypatch.setattr("src.main._fetcher_registry", FakeRegistry())
    monkeypatch.setattr("src.main._classifier", FakeClassifier())
    monkeypatch.setattr("src.main._deduplicator", PassThroughDeduplicator())
    monkeypatch.setattr("src.main._scorer", SimpleNamespace(score=lambda d: d))
    monkeypatch.setattr("src.main._slack", SimpleNamespace(is_configured=False, push_new_event=lambda e: None))

    result = run_pipeline("social_watch")

    assert result["status"] == "success"
    assert result["fetched"] == 1
    assert result["classified"] == 1
    assert result["new"] == 1
    assert result["verified"] == 1
    assert finished["log_id"] == 999
    assert finished["items_fetched"] == 1
    assert finished["items_new"] == 1


def test_main_does_not_bootstrap_bounty_pipeline() -> None:
    source = Path("src/main.py").read_text(encoding="utf-8")
    module = ast.parse(source)

    function = next(
        node for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "main"
    )

    pipeline_calls = [
        call for call in ast.walk(function)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == "run_pipeline"
    ]

    assert all(
        not call.args
        or not isinstance(call.args[0], ast.Constant)
        or call.args[0].value != "bounty"
        for call in pipeline_calls
    )


def test_run_pipeline_failure_finishes_schedule_log_with_error(monkeypatch, signal_outcomes) -> None:
    rollbacks = []
    fake_db = SimpleNamespace(close=lambda: None, rollback=lambda: rollbacks.append(True))
    finished = {}

    fake_fetcher = SimpleNamespace(config={"fetch_method": "twitter"})

    class FakeRegistry:
        _fetchers = {"twitter_gitcoin": fake_fetcher}

        def fetch_all_with_status(self, schedule, should_skip=None):
            item = FetchedItem(
                source_type="twitter",
                source_name="twitter_gitcoin",
                raw_content="grant round open",
                raw_url="https://x.com/gitcoin/status/1",
                canonical_url="https://x.com/gitcoin/status/1",
                metadata={
                    "created_at": _iso(-1),
                    "chain": "multi",
                    "source_tier": "official",
                    "official": True,
                    "signal_type": "social",
                },
            )
            return [item], {"twitter_gitcoin": {"success": True, "error": None, "skipped": None}}

    class FakeClassifier:
        def classify(self, item):
            return "GRANT", {
                "title": "Gitcoin Grants",
                "description": "Open round",
                "ecosystem": "multi",
                "application_url": "https://gitcoin.co",
                "start_date": _iso(-3),
                "deadline": _iso(17),
            }

    class FailingDeduplicator:
        def check_and_process(self, *args, **kwargs):
            raise TypeError("'chain' is an invalid keyword argument for Event")

    monkeypatch.setattr("src.main.SessionLocal", lambda: fake_db)
    monkeypatch.setattr("src.main.create_schedule_log", lambda db, name: SimpleNamespace(id=999))
    monkeypatch.setattr(
        "src.main.finish_schedule_log",
        lambda db, log_id, **kwargs: finished.update({"log_id": log_id, **kwargs}),
    )
    monkeypatch.setattr("src.main.upsert_source_health", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.main.get_source_health", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.main.process_item_l1", lambda db, item: 123)
    monkeypatch.setattr("src.main.increment_stat", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.main._init_components", lambda: None)
    monkeypatch.setattr("src.main._fetcher_registry", FakeRegistry())
    monkeypatch.setattr("src.main._classifier", FakeClassifier())
    monkeypatch.setattr("src.main._deduplicator", FailingDeduplicator())
    monkeypatch.setattr("src.main._scorer", None)
    monkeypatch.setattr("src.main._slack", SimpleNamespace(is_configured=False))

    result = run_pipeline("social_watch")

    # A failure inside one item is isolated: the run still succeeds, the item is
    # counted as an error (so a systematic breakage is visible), and the rest of
    # the batch is processed.
    assert result["status"] == "success"
    assert result["item_errors"] == 1
    assert result["new"] == 0
    assert finished["log_id"] == 999
    assert "error" not in finished
    # The failed item is retried on its next fetch, and the session is usable again.
    assert signal_outcomes == [(123, "TypeError: 'chain' is an invalid keyword argument for Event")]
    assert rollbacks == [True]


def test_run_pipeline_reports_run_level_failure(monkeypatch) -> None:
    """Infrastructure failures (not per-item ones) still fail the run."""
    fake_db = SimpleNamespace(close=lambda: None)
    finished = {}

    class ExplodingRegistry:
        _fetchers = {"twitter_gitcoin": SimpleNamespace(config={"fetch_method": "twitter"})}

        def fetch_all_with_status(self, schedule, should_skip=None):
            raise RuntimeError("fetcher registry unavailable")

    monkeypatch.setattr("src.main.SessionLocal", lambda: fake_db)
    monkeypatch.setattr("src.main.create_schedule_log", lambda db, name: SimpleNamespace(id=999))
    monkeypatch.setattr(
        "src.main.finish_schedule_log",
        lambda db, log_id, **kwargs: finished.update({"log_id": log_id, **kwargs}),
    )
    monkeypatch.setattr("src.main.get_source_health", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.main.select_budgeted_sources", lambda *args, **kwargs: set())
    monkeypatch.setattr("src.main.increment_stat", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.main._init_components", lambda: None)
    monkeypatch.setattr("src.main._reconcile_vector_index_once", lambda: None)
    monkeypatch.setattr("src.main._fetcher_registry", ExplodingRegistry())
    monkeypatch.setattr("src.main._slack", SimpleNamespace(is_configured=False))

    result = run_pipeline("social_watch")

    assert result["status"] == "failed"
    assert "fetcher registry unavailable" in result["error"]
    assert finished["log_id"] == 999
    assert finished["error"] == result["error"]


def test_run_daily_summary_resends_even_if_today_already_succeeded(monkeypatch) -> None:
    fake_db = SimpleNamespace(close=lambda: None)
    sent = {}

    class FakeSlack:
        def send_daily_summary(self, payload):
            sent["payload"] = payload
            return "999.888"

    monkeypatch.setattr("src.main._init_slack", lambda: None)
    monkeypatch.setattr("src.main.SessionLocal", lambda: fake_db)
    monkeypatch.setattr("src.main._slack", FakeSlack())
    monkeypatch.setattr(
        "src.main.get_daily_summary_log",
        lambda db, summary_date, channel: SimpleNamespace(id=7, status="success"),
    )
    monkeypatch.setattr(
        "src.main.create_daily_summary_log",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should reuse existing daily summary log")),
    )
    monkeypatch.setattr(
        "src.main.build_daily_summary",
        lambda db, summary_date: {
            "summary_date": summary_date.isoformat(),
            "totals": {},
            "today_scan_stats": {},
            "historical_high_score": {},
            "new_event_sources": [],
            "new_events": [],
        },
    )
    monkeypatch.setattr(
        "src.main.mark_daily_summary_sent",
        lambda db, row_id, slack_ts: sent.update({"row_id": row_id, "slack_ts": slack_ts}),
    )
    monkeypatch.setattr(
        "src.main.mark_daily_summary_failed",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("send should not fail")),
    )

    from src.main import run_daily_summary

    result = run_daily_summary()

    assert result["status"] == "success"
    assert result["slack_ts"] == "999.888"
    assert sent["row_id"] == 7
    assert sent["slack_ts"] == "999.888"
    assert sent["payload"]["summary_date"] == result["summary_date"]

def _run_single_undated_item(monkeypatch, source_tier: str, scraped_dates: dict) -> dict:
    """Run one undated web_scraper item through run_pipeline with a fixed scrape result."""
    fake_db = SimpleNamespace(close=lambda: None)

    class FakeRegistry:
        _fetchers = {"solana_grants": SimpleNamespace(config={"fetch_method": "web_scraper"})}

        def fetch_all_with_status(self, schedule, should_skip=None):
            item = FetchedItem(
                source_type="web_scraper",
                source_name="solana_grants",
                raw_content="Solana Foundation grants program",
                raw_url="https://solana.org/grants",
                canonical_url="https://solana.org/grants",
                metadata={"source_tier": source_tier, "official": source_tier == "official"},
            )
            return [item], {"solana_grants": {"success": True, "error": None, "skipped": None}}

    class FakeClassifier:
        llm = None

        def classify(self, item):
            return "GRANT", {"title": "Solana Foundation Grants", "description": "Grants for builders"}

    monkeypatch.setattr("src.main.SessionLocal", lambda: fake_db)
    monkeypatch.setattr("src.main.create_schedule_log", lambda db, name: SimpleNamespace(id=1))
    monkeypatch.setattr("src.main.finish_schedule_log", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.main.upsert_source_health", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.main.get_source_health", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.main.process_item_l1", lambda db, item: 1)
    monkeypatch.setattr("src.main.increment_stat", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.main.verify_opportunity",
                        lambda **kw: {"verdict": "unchecked", "verification_log": {}})
    monkeypatch.setattr("src.main.update_event", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.main._try_extract_dates_from_url", lambda *args, **kwargs: dict(scraped_dates))
    monkeypatch.setattr("src.main._init_components", lambda: None)
    monkeypatch.setattr("src.main._reconcile_vector_index_once", lambda: None)
    monkeypatch.setattr("src.main._fetcher_registry", FakeRegistry())
    monkeypatch.setattr("src.main._classifier", FakeClassifier())
    monkeypatch.setattr("src.main._deduplicator",
                        SimpleNamespace(check_and_process=lambda *args, **kwargs: (1, True)))
    monkeypatch.setattr("src.main._scorer", SimpleNamespace(score=lambda d: d))
    monkeypatch.setattr("src.main._slack", SimpleNamespace(is_configured=False, push_new_event=lambda e: None))

    return run_pipeline("grant_hackathon")


def test_scraped_page_date_does_not_age_out_an_undated_official_program_page(monkeypatch) -> None:
    """Official program pages carry no publication date. A date the secondary scrape
    guessed from the page ("© 2023", an old blog sidebar) must not drop them; only a
    date the source itself stamped (feed entry, tweet) ages official content out."""
    result = _run_single_undated_item(
        monkeypatch, "official", {"published_date": "2023-03-01T00:00:00+00:00"}
    )

    assert result["stale"] == 0
    assert result["new"] == 1


def test_scraped_page_date_still_ages_out_discovery_items(monkeypatch) -> None:
    result = _run_single_undated_item(
        monkeypatch, "discovery", {"published_date": "2023-03-01T00:00:00+00:00"}
    )

    assert result["stale"] == 1
    assert result["new"] == 0


def _tavily_item(published_date: str) -> FetchedItem:
    """A Tavily news result; published_date is copied verbatim from the API."""
    return FetchedItem(
        source_type="tavily_search",
        source_name="tavily_starknet_grants",
        raw_content="Starknet Foundation Seed Grants Program",
        raw_url="https://example.com/starknet-seed-grants",
        canonical_url="https://example.com/starknet-seed-grants",
        metadata={"published_date": published_date, "source_tier": "discovery"},
    )


def test_tavily_rfc2822_publication_date_is_understood() -> None:
    """Tavily news returns 'Fri, 09 Oct 2026 08:44:57 GMT'. Read as ISO only, every
    result looked undated, and live programs (Starknet Foundation Grants, Stellar
    Community Fund) were dropped as missing_published_at on 2026-10-12."""
    now = datetime(2026, 10, 12, 6, 46, tzinfo=timezone.utc)

    assert _staleness_reason(
        _tavily_item("Fri, 09 Oct 2026 08:44:57 GMT"),
        {"title": "Starknet Foundation Seed Grants Program"},
        source_tier="discovery",
        now=now,
    ) is None


def test_old_tavily_rfc2822_publication_date_still_ages_out() -> None:
    now = datetime(2026, 10, 12, 6, 46, tzinfo=timezone.utc)

    assert _staleness_reason(
        _tavily_item("Mon, 03 Mar 2025 10:00:00 GMT"),
        {"title": "Starknet Foundation Seed Grants Program"},
        source_tier="discovery",
        now=now,
    ) == "published_too_old"


@pytest.mark.parametrize(
    "value, expected",
    [
        ("Fri, 09 Oct 2026 08:44:57 GMT", datetime(2026, 10, 9, 8, 44, 57, tzinfo=timezone.utc)),
        ("Fri, 09 Oct 2026 16:44:57 +0800", datetime(2026, 10, 9, 8, 44, 57, tzinfo=timezone.utc)),
        ("Fri, 09 Oct 2026 08:44:57 -0000", datetime(2026, 10, 9, 8, 44, 57, tzinfo=timezone.utc)),
        ("2026-10-09T08:44:57Z", datetime(2026, 10, 9, 8, 44, 57, tzinfo=timezone.utc)),
        ("next Friday", None),
        ("", None),
    ],
)
def test_parse_datetime_accepts_iso_and_rfc2822(value, expected) -> None:
    assert _parse_datetime(value) == expected



def _run_items(monkeypatch, items, classify, process_item_l1=None):
    """run_pipeline over fixed items with a stub classifier; returns the result."""
    fake_db = SimpleNamespace(close=lambda: None, rollback=lambda: None)

    class FakeRegistry:
        _fetchers = {"feed": SimpleNamespace(config={"fetch_method": "rss"})}

        def fetch_all_with_status(self, schedule, should_skip=None):
            return list(items), {"feed": {"success": True, "error": None, "skipped": None}}

    monkeypatch.setattr("src.main.SessionLocal", lambda: fake_db)
    monkeypatch.setattr("src.main.create_schedule_log", lambda db, name: SimpleNamespace(id=1))
    monkeypatch.setattr("src.main.finish_schedule_log", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.main.upsert_source_health", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.main.get_source_health", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.main.process_item_l1", process_item_l1 or (lambda db, item: 7))
    monkeypatch.setattr("src.main.increment_stat", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.main._init_components", lambda: None)
    monkeypatch.setattr("src.main._reconcile_vector_index_once", lambda: None)
    monkeypatch.setattr("src.main._fetcher_registry", FakeRegistry())
    monkeypatch.setattr("src.main._classifier", SimpleNamespace(classify=classify, llm=None))
    monkeypatch.setattr("src.main._slack", SimpleNamespace(is_configured=False))
    return run_pipeline("grant_hackathon")


def _feed_item(content: str = "Grant round open") -> FetchedItem:
    return FetchedItem(
        source_type="rss", source_name="feed", raw_content=content,
        raw_url=f"https://example.org/{abs(hash(content))}",
        canonical_url=f"https://example.org/{abs(hash(content))}",
        metadata={"source_tier": "official"},
    )


def test_a_signal_whose_classification_failed_is_marked_for_retry(monkeypatch, signal_outcomes) -> None:
    """An LLM outage must not make the content "already seen" forever."""
    result = _run_items(
        monkeypatch, [_feed_item()], classify=lambda item: Classification(llm_error="timeout")
    )

    assert result["llm_errors"] == 1
    assert signal_outcomes == [(7, "classification_failed")]


def test_a_judged_signal_is_marked_done(monkeypatch, signal_outcomes) -> None:
    _run_items(monkeypatch, [_feed_item()], classify=lambda item: Classification(category="NOISE"))

    assert signal_outcomes == [(7, None)]


def test_an_l1_write_error_skips_only_that_item(monkeypatch, signal_outcomes) -> None:
    """A failed raw_signals write used to be counted as a duplicate, or abort the run."""
    def flaky_l1(db, item):
        if item.raw_content == "first":
            raise RuntimeError("could not write raw_signals")
        return 8

    result = _run_items(
        monkeypatch,
        [_feed_item("first"), _feed_item("second")],
        classify=lambda item: Classification(category="NOISE"),
        process_item_l1=flaky_l1,
    )

    assert result["status"] == "success"
    assert result["item_errors"] == 1
    assert result["deduped"] == 0
    assert signal_outcomes == [(8, None)]


def test_llm_judged_noise_is_counted(monkeypatch, signal_outcomes) -> None:
    """"classified" only counts opportunities; noise needs its own number to audit precision."""
    result = _run_items(
        monkeypatch, [_feed_item()],
        classify=lambda item: Classification(category="NOISE", data={"noise_reason": "roundup"}),
    )

    assert result["noise"] == 1
    assert result["classified"] == 0


def test_keyword_filter_rejections_are_not_counted_as_llm_noise(monkeypatch, signal_outcomes) -> None:
    result = _run_items(monkeypatch, [_feed_item()], classify=lambda item: Classification(category="NOISE"))

    assert result["noise"] == 0
