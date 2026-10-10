# Twitter Listening Rollout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the disabled RSSHub Twitter path with a Twikit-backed two-lane social ingestion flow that supports official-account direct ingestion, discovery-source preprocessing, and an isolated `social_watch` scheduler.

**Architecture:** Keep the existing fetch-to-event pipeline in [src/main.py](../../../src/main.py) as the only downstream path for classification, verification, scoring, Slack dispatch, and reporting. Add a Twitter-specific ingestion layer in front of it: direct ingestion for official accounts, preprocessing plus adaptation for discovery accounts and Lists, and a dedicated database-backed cursor state table to avoid destructive changes to existing health tables.

**Tech Stack:** Python, Twikit, SQLAlchemy, APScheduler, pytest, existing repository fetcher and pipeline abstractions.

---

## File Structure

### New files

- `src/fetchers/twitter_client.py`
  Async Twikit wrapper for login, cookie reuse, user lookup, account timeline fetches, and List timeline fetches.
- `src/fetchers/twitter_social.py`
  Social preprocessing and tweet-to-`FetchedItem` adaptation helpers.
- `tests/fetchers/test_twikit_fetcher.py`
  Unit tests for Twikit-backed fetch behavior and metadata normalization.
- `tests/fetchers/test_twitter_social.py`
  Unit tests for social preprocessing and tweet adaptation.
- `tests/db/test_twitter_source_state.py`
  Unit tests for cursor and cooldown persistence helpers.

### Modified files

- `requirements.txt`
  Add the Twikit dependency.
- `.env.example`
  Add Twitter credentials, cookie file, and social schedule configuration.
- `config/settings.py`
  Add Twitter and social-watch settings.
- `config/sources.yaml`
  Replace disabled RSSHub entries with Twikit-compatible source metadata and a `social_watch` schedule.
- `src/fetchers/builder.py`
  Register the new Twitter fetcher and preserve social metadata.
- `src/fetchers/base.py`
  Extend skip logic to support source-managed cooldown where needed.
- `src/fetchers/twitter_fetcher.py`
  Replace RSSHub implementation with a Twikit-backed fetcher that delegates async work to `twitter_client.py` and `twitter_social.py`.
- `src/db/models.py`
  Add a new table for Twitter cursor and auth state.
- `src/db/queries.py`
  Add query helpers for Twitter source state.
- `src/scheduler/jobs.py`
  Register the `social_watch` job.
- `src/main.py`
  Add a `run_social_watch()` entry point and integrate source-mode-aware preprocessing.
- `README.md`
  Document the new Twitter runtime behavior and env vars.
- `tests/config/test_settings.py`
  Validate new settings defaults.
- `tests/fetchers/test_source_metadata_normalization.py`
  Validate social metadata backfill and preservation.
- `tests/fetchers/test_runtime_source_controls.py`
  Validate new fetcher registration and social cooldown behavior.
- `tests/scheduler/test_jobs.py`
  Validate scheduler registration for `social_watch`.

### Existing files to read before starting

- `src/main.py`
- `src/fetchers/base.py`
- `src/fetchers/builder.py`
- `src/verifier/verifier.py`
- `src/db/models.py`
- `src/db/queries.py`
- `config/settings.py`
- `config/sources.yaml`
- `docs/superpowers/specs/2026-07-03-twitter-listening-design.md`

## Task 1: Add Dependency, Settings, and Source Metadata Plumbing

**Files:**

- Modify: `requirements.txt`
- Modify: `.env.example`
- Modify: `config/settings.py`
- Modify: `src/fetchers/builder.py`
- Test: `tests/config/test_settings.py`
- Test: `tests/fetchers/test_source_metadata_normalization.py`

- [ ] **Step 1: Write the failing settings and metadata tests**

```python
def test_twitter_settings_have_safe_defaults(monkeypatch) -> None:
    monkeypatch.delenv("TWITTER_AUTH_INFO_1", raising=False)
    monkeypatch.delenv("TWITTER_AUTH_INFO_2", raising=False)
    monkeypatch.delenv("TWITTER_PASSWORD", raising=False)
    monkeypatch.delenv("TWITTER_TOTP_SECRET", raising=False)
    monkeypatch.delenv("TWITTER_COOKIES_FILE", raising=False)
    monkeypatch.delenv("SOCIAL_WATCH_INTERVAL_MINUTES", raising=False)

    settings = Settings()

    assert settings.TWITTER_AUTH_INFO_1 == ""
    assert settings.TWITTER_AUTH_INFO_2 == ""
    assert settings.TWITTER_PASSWORD == ""
    assert settings.TWITTER_TOTP_SECRET == ""
    assert settings.TWITTER_COOKIES_FILE == ".twitter-cookies.json"
    assert settings.SOCIAL_WATCH_INTERVAL_MINUTES == 15


def test_load_sources_config_backfills_social_metadata(tmp_path: Path) -> None:
    path = tmp_path / "sources.yaml"
    path.write_text(
        "sources:\n"
        "  - name: twitter_base\n"
        "    fetch_method: twitter\n"
        "    category: social\n"
        "    ecosystem: base\n"
        "    schedule: social_watch\n"
        "    enabled: true\n",
        encoding="utf-8",
    )

    config = load_sources_config(str(path))
    source = config["sources"][0]

    assert source["signal_type"] == "social"
    assert source["trust_tier"] == "official"
    assert source["ingestion_mode"] == "direct"
    assert source["source_kind"] == "account"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/config/test_settings.py tests/fetchers/test_source_metadata_normalization.py -v`
Expected: FAIL because the new settings and metadata fields do not exist yet.

- [ ] **Step 3: Add dependency and settings plumbing**

```python
# requirements.txt
twikit>=2.3.0


# config/settings.py
TWITTER_AUTH_INFO_1: str = os.getenv("TWITTER_AUTH_INFO_1", "")
TWITTER_AUTH_INFO_2: str = os.getenv("TWITTER_AUTH_INFO_2", "")
TWITTER_PASSWORD: str = os.getenv("TWITTER_PASSWORD", "")
TWITTER_TOTP_SECRET: str = os.getenv("TWITTER_TOTP_SECRET", "")
TWITTER_COOKIES_FILE: str = os.getenv("TWITTER_COOKIES_FILE", ".twitter-cookies.json")
SOCIAL_WATCH_INTERVAL_MINUTES: int = int(os.getenv("SOCIAL_WATCH_INTERVAL_MINUTES", "15"))
TWITTER_FETCH_COUNT: int = int(os.getenv("TWITTER_FETCH_COUNT", "20"))


# src/fetchers/builder.py
FETCHER_MAP = {
    "rss": ".rss_fetcher:RSSFetcher",
    "github_search": ".github_fetcher:GitHubFetcher",
    "rsshub": ".twitter_fetcher:TwitterFetcher",
    "twitter": ".twitter_fetcher:TwitterFetcher",
    "web_scraper": ".web_scraper:WebScraperFetcher",
    "tavily_search": ".tavily_fetcher:TavilyFetcher",
}


def _normalize_source_metadata(source: dict) -> dict:
    normalized = dict(source)
    fetch_method = normalized.get("fetch_method", "rss")
    source_kind = normalized.get("source_kind") or "account"

    if normalized.get("category") == "social" or fetch_method == "twitter":
        normalized["signal_type"] = normalized.get("signal_type") or "social"
        normalized["trust_tier"] = normalized.get("trust_tier") or (
            "discovery" if normalized.get("source_tier") == "discovery" else "official"
        )
        normalized["ingestion_mode"] = normalized.get("ingestion_mode") or (
            "preprocessed" if normalized["trust_tier"] == "discovery" else "direct"
        )
        normalized["source_kind"] = source_kind
        normalized["watch_priority"] = normalized.get("watch_priority") or "normal"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/config/test_settings.py tests/fetchers/test_source_metadata_normalization.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add requirements.txt .env.example config/settings.py src/fetchers/builder.py tests/config/test_settings.py tests/fetchers/test_source_metadata_normalization.py
git commit -m "feat: add twitter config scaffolding"
```

## Task 2: Add Dedicated Twitter Source State Persistence

**Files:**

- Modify: `src/db/models.py`
- Modify: `src/db/queries.py`
- Test: `tests/db/test_twitter_source_state.py`

- [ ] **Step 1: Write the failing Twitter state tests**

```python
def test_upsert_twitter_source_state_creates_and_updates_record(db_session) -> None:
    state = upsert_twitter_source_state(
        db_session,
        source_name="twitter_base",
        last_tweet_id="123",
        cursor="CURSOR_A",
        auth_profile="primary",
    )

    assert state.source_name == "twitter_base"
    assert state.last_tweet_id == "123"
    assert state.cursor == "CURSOR_A"

    state = upsert_twitter_source_state(
        db_session,
        source_name="twitter_base",
        last_tweet_id="456",
        cursor="CURSOR_B",
        auth_profile="primary",
    )

    assert state.last_tweet_id == "456"
    assert state.cursor == "CURSOR_B"


def test_twitter_source_state_supports_cooldown_window(db_session) -> None:
    cooldown_until = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=20)
    upsert_twitter_source_state(
        db_session,
        source_name="twitter_list_alpha",
        cooldown_until=cooldown_until,
    )

    state = get_twitter_source_state(db_session, "twitter_list_alpha")

    assert state.cooldown_until == cooldown_until
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/db/test_twitter_source_state.py -v`
Expected: FAIL because the model and query helpers do not exist.

- [ ] **Step 3: Add the new table and query helpers**

```python
# src/db/models.py
class TwitterSourceState(Base):
    __tablename__ = "twitter_source_state"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_name = Column(String(128), unique=True, nullable=False, index=True)
    last_tweet_id = Column(String(64), nullable=True)
    cursor = Column(Text, nullable=True)
    auth_profile = Column(String(64), nullable=True)
    cooldown_until = Column(DateTime(timezone=True), nullable=True)
    last_fetched_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# src/db/queries.py
def get_twitter_source_state(db: Session, source_name: str) -> Optional[TwitterSourceState]:
    return db.query(TwitterSourceState).filter(TwitterSourceState.source_name == source_name).first()


def upsert_twitter_source_state(db: Session, source_name: str, **kwargs) -> TwitterSourceState:
    state = get_twitter_source_state(db, source_name)
    if state is None:
        state = TwitterSourceState(source_name=source_name)
        db.add(state)
    for key, value in kwargs.items():
        setattr(state, key, value)
    db.commit()
    db.refresh(state)
    return state
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/db/test_twitter_source_state.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/db/models.py src/db/queries.py tests/db/test_twitter_source_state.py
git commit -m "feat: persist twitter source state"
```

## Task 3: Implement Twikit-Backed Official Source Fetching

**Files:**

- Create: `src/fetchers/twitter_client.py`
- Modify: `src/fetchers/twitter_fetcher.py`
- Modify: `src/fetchers/base.py`
- Modify: `tests/fetchers/test_runtime_source_controls.py`
- Test: `tests/fetchers/test_twikit_fetcher.py`

- [ ] **Step 1: Write the failing Twikit fetcher tests**

```python
def test_twitter_fetcher_builds_fetched_items_from_account_timeline(monkeypatch) -> None:
    class FakeTwitterClient:
        def fetch_account_tweets(self, *, screen_name: str, count: int, cursor: str | None):
            return [
                {
                    "id": "1001",
                    "url": "https://x.com/base/status/1001",
                    "text": "Base Builder Rewards is now open. Apply now: https://base.org/apply",
                    "author_screen_name": "base",
                    "quoted_text": "",
                    "link_urls": ["https://base.org/apply"],
                }
            ], "NEXT_CURSOR"

    monkeypatch.setattr("src.fetchers.twitter_fetcher.TwikitTimelineClient", lambda settings: FakeTwitterClient())
    monkeypatch.setattr("src.fetchers.twitter_fetcher._load_twitter_state", lambda *args, **kwargs: None)

    fetcher = TwitterFetcher(
        "twitter_base",
        {
            "screen_name": "base",
            "source_kind": "account",
            "ingestion_mode": "direct",
            "trust_tier": "official",
            "fetch_method": "twitter",
            "category": "social",
            "ecosystem": "base",
        },
    )

    items = fetcher.fetch()

    assert len(items) == 1
    assert items[0].source_type == "twitter"
    assert items[0].metadata["tweet_id"] == "1001"
    assert items[0].metadata["trust_tier"] == "official"


def test_get_fetch_skip_reason_respects_twitter_state_cooldown() -> None:
    now = dt.datetime(2026, 7, 3, 8, 0, tzinfo=dt.timezone.utc)
    health = SimpleNamespace(status="healthy", last_error=None, last_fetch_at=now - dt.timedelta(minutes=5))
    state = SimpleNamespace(cooldown_until=now + dt.timedelta(minutes=10))

    reason = get_fetch_skip_reason(
        {"name": "twitter_base", "fetch_method": "twitter"},
        health,
        now=now,
        source_state=state,
    )

    assert reason == "source_state_cooldown"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/fetchers/test_twikit_fetcher.py tests/fetchers/test_runtime_source_controls.py -v`
Expected: FAIL because the Twikit client wrapper and state-aware skip reason do not exist.

- [ ] **Step 3: Add the Twikit wrapper and official-lane fetcher behavior**

```python
# src/fetchers/twitter_client.py
import asyncio
from twikit import Client


class TwikitTimelineClient:
    def __init__(self, settings):
        self._settings = settings

    async def _build_client(self) -> Client:
        client = Client(language="en-US")
        await client.login(
            auth_info_1=self._settings.TWITTER_AUTH_INFO_1,
            auth_info_2=self._settings.TWITTER_AUTH_INFO_2 or None,
            password=self._settings.TWITTER_PASSWORD,
            totp_secret=self._settings.TWITTER_TOTP_SECRET or None,
            cookies_file=self._settings.TWITTER_COOKIES_FILE,
        )
        return client

    def fetch_account_tweets(self, *, screen_name: str, count: int, cursor: str | None):
        return asyncio.run(self._fetch_account_tweets(screen_name=screen_name, count=count, cursor=cursor))

    async def _fetch_account_tweets(self, *, screen_name: str, count: int, cursor: str | None):
        client = await self._build_client()
        user = await client.get_user_by_screen_name(screen_name)
        tweets = await client.get_user_tweets(user.id, "Tweets", count=count, cursor=cursor)
        rows = [
            {
                "id": tweet.id,
                "url": getattr(tweet, "url", f"https://x.com/{screen_name}/status/{tweet.id}"),
                "text": getattr(tweet, "text", ""),
                "author_screen_name": screen_name,
                "quoted_text": getattr(getattr(tweet, "quote", None), "text", ""),
                "link_urls": [url.get("expanded_url") for url in getattr(tweet, "urls", []) if url.get("expanded_url")],
            }
            for tweet in tweets
        ]
        next_cursor = getattr(tweets, "next_cursor", None)
        return rows, next_cursor


# src/fetchers/base.py
def get_fetch_skip_reason(config, health, now=None, source_state=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    if source_state is not None and getattr(source_state, "cooldown_until", None):
        if now < source_state.cooldown_until:
            return "source_state_cooldown"
    if health is None or health.last_fetch_at is None:
        return None

    last_error = (getattr(health, "last_error", "") or "").lower()
    rate_limit_cooldown = int(config.get("rate_limit_cooldown_minutes", 0) or 0)
    failure_cooldown = int(config.get("failure_cooldown_minutes", 0) or 0)

    if "429" in last_error and rate_limit_cooldown > 0:
        retry_at = health.last_fetch_at + dt.timedelta(minutes=rate_limit_cooldown)
        if now < retry_at:
            return "rate_limited_cooldown"

    if getattr(health, "status", None) == "down" and failure_cooldown > 0:
        retry_at = health.last_fetch_at + dt.timedelta(minutes=failure_cooldown)
        if now < retry_at:
            return "failed_source_cooldown"

    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/fetchers/test_twikit_fetcher.py tests/fetchers/test_runtime_source_controls.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/fetchers/twitter_client.py src/fetchers/twitter_fetcher.py src/fetchers/base.py tests/fetchers/test_twikit_fetcher.py tests/fetchers/test_runtime_source_controls.py
git commit -m "feat: add twikit-backed official twitter fetcher"
```

## Task 4: Implement Discovery-Lane Social Preprocessing and Tweet Adaptation

**Files:**

- Create: `src/fetchers/twitter_social.py`
- Modify: `src/fetchers/twitter_fetcher.py`
- Test: `tests/fetchers/test_twitter_social.py`

- [ ] **Step 1: Write the failing discovery preprocessing tests**

```python
def test_social_preprocessor_drops_market_noise() -> None:
    row = {
        "id": "2001",
        "text": "BTC looks strong today. GM everyone.",
        "quoted_text": "",
        "link_urls": [],
        "author_screen_name": "macro_kol",
    }

    result = preprocess_tweet(row, trust_tier="discovery")

    assert result["verdict"] == "drop"


def test_social_preprocessor_promotes_actionable_opportunity_signal() -> None:
    row = {
        "id": "2002",
        "text": "New Solana builder grant now open. Apply before Aug 1: https://solana.org/grants",
        "quoted_text": "",
        "link_urls": ["https://solana.org/grants"],
        "author_screen_name": "alpha_researcher",
    }

    result = preprocess_tweet(row, trust_tier="discovery")

    assert result["verdict"] == "strong_candidate"
    assert result["has_official_link"] is True


def test_twitter_signal_adapter_builds_classifier_ready_content() -> None:
    row = {
        "id": "2003",
        "text": "Apply for the hackathon here",
        "quoted_text": "Prize pool is $50k",
        "link_urls": ["https://ethglobal.com/events/test"],
        "author_screen_name": "eth_watch",
        "source_kind": "list",
    }

    raw_content = build_tweet_raw_content(row)

    assert "Author: eth_watch" in raw_content
    assert "Quoted tweet: Prize pool is $50k" in raw_content
    assert "Links: https://ethglobal.com/events/test" in raw_content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/fetchers/test_twitter_social.py -v`
Expected: FAIL because the preprocessor and adapter do not exist.

- [ ] **Step 3: Add preprocessing and adaptation helpers**

```python
# src/fetchers/twitter_social.py
OPPORTUNITY_TERMS = {
    "grant", "grants", "hackathon", "buildathon", "bounty", "builder program",
    "rfp", "apply", "application", "deadline", "prize", "prize pool", "security disclosure",
}


def preprocess_tweet(row: dict, trust_tier: str) -> dict:
    text = " ".join(filter(None, [row.get("text", ""), row.get("quoted_text", "")])).lower()
    has_trigger = any(term in text for term in OPPORTUNITY_TERMS)
    has_link = any(url.startswith("https://") for url in row.get("link_urls", []))
    has_official_link = any(
        domain in url for domain in ("foundation", "org", "gitcoin.co", "ethglobal.com", "immunefi.com")
        for url in row.get("link_urls", [])
    )

    if not has_trigger:
        return {"verdict": "drop", "has_official_link": False}
    if has_official_link:
        return {"verdict": "strong_candidate", "has_official_link": True}
    if has_link:
        return {"verdict": "candidate", "has_official_link": False}
    return {"verdict": "drop", "has_official_link": False}


def build_tweet_raw_content(row: dict) -> str:
    lines = [
        f"Author: {row.get('author_screen_name', '')}",
        f"Tweet: {row.get('text', '')}",
        f"Quoted tweet: {row.get('quoted_text', '')}",
        f"Links: {' '.join(row.get('link_urls', []))}",
        f"Source kind: {row.get('source_kind', 'account')}",
    ]
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/fetchers/test_twitter_social.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/fetchers/twitter_social.py src/fetchers/twitter_fetcher.py tests/fetchers/test_twitter_social.py
git commit -m "feat: add twitter discovery preprocessing"
```

## Task 5: Add `social_watch` Scheduling and Pipeline Integration

**Files:**

- Modify: `src/scheduler/jobs.py`
- Modify: `src/main.py`
- Modify: `tests/scheduler/test_jobs.py`
- Test: `tests/test_main_social_watch.py`

- [ ] **Step 1: Write the failing scheduler and pipeline tests**

```python
def test_register_jobs_adds_social_watch(monkeypatch) -> None:
    monkeypatch.setattr(jobs.settings, "HEARTBEAT_INTERVAL_MINUTES", 30)
    monkeypatch.setattr(jobs.settings, "DEFILLAMA_SYNC_ENABLED", False)
    monkeypatch.setattr(jobs.settings, "SOCIAL_WATCH_INTERVAL_MINUTES", 15)

    scheduler = DummyScheduler()
    jobs.register_jobs(scheduler, lambda schedule: None, lambda: None, lambda: None, lambda: None)

    ids = [job["id"] for job in scheduler.jobs]
    assert "pipeline_social_watch" in ids


def test_run_social_watch_calls_pipeline_with_social_schedule(monkeypatch) -> None:
    seen = []
    monkeypatch.setattr("src.main.run_pipeline", lambda schedule: seen.append(schedule) or {"status": "success"})

    from src.main import run_social_watch

    result = run_social_watch()

    assert seen == ["social_watch"]
    assert result["status"] == "success"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/scheduler/test_jobs.py tests/test_main_social_watch.py -v`
Expected: FAIL because `social_watch` is not registered and `run_social_watch()` does not exist.

- [ ] **Step 3: Add the social schedule and pipeline entry point**

```python
# src/scheduler/jobs.py
SOCIAL_WATCH_SCHEDULE_MINUTES = max(1, int(settings.SOCIAL_WATCH_INTERVAL_MINUTES))


def _social_watch_trigger():
    return IntervalTrigger(minutes=SOCIAL_WATCH_SCHEDULE_MINUTES)


def register_jobs(scheduler, pipeline_fn, heartbeat_fn, defillama_sync_fn, social_watch_fn):
    scheduler.add_job(
        lambda: pipeline_fn("grant_hackathon"),
        trigger=CronTrigger.from_crontab(GRANT_HACKATHON_SCHEDULE, timezone="Asia/Shanghai"),
        id="pipeline_grant_hackathon",
        name="Grant & Hackathon Pipeline",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: pipeline_fn("bounty"),
        trigger=CronTrigger.from_crontab(BOUNTY_SCHEDULE, timezone="Asia/Shanghai"),
        id="pipeline_bounty",
        name="Bounty Pipeline",
        replace_existing=True,
    )
    scheduler.add_job(
        social_watch_fn,
        trigger=_social_watch_trigger(),
        id="pipeline_social_watch",
        name="Twitter Social Watch Pipeline",
        replace_existing=True,
    )
    scheduler.add_job(
        heartbeat_fn,
        trigger=_heartbeat_trigger(),
        id="heartbeat",
        name="System Heartbeat & Health Check",
        replace_existing=True,
    )
    if settings.DEFILLAMA_SYNC_ENABLED:
        scheduler.add_job(
            defillama_sync_fn,
            trigger=CronTrigger.from_crontab(DEFILLAMA_SYNC_SCHEDULE, timezone="Asia/Shanghai"),
            id="defillama_candidate_sync",
            name="DefiLlama Candidate Sync",
            replace_existing=True,
        )


# src/main.py
def run_social_watch():
    return run_pipeline("social_watch")


def main():
    init_db()
    scheduler = create_scheduler()
    register_jobs(scheduler, run_pipeline, run_heartbeat, run_defillama_candidate_sync, run_social_watch)
    scheduler.start()
    run_pipeline("grant_hackathon")
    run_pipeline("bounty")
    run_social_watch()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/scheduler/test_jobs.py tests/test_main_social_watch.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/scheduler/jobs.py src/main.py tests/scheduler/test_jobs.py tests/test_main_social_watch.py
git commit -m "feat: schedule social watch pipeline"
```

## Task 6: Wire Runtime Source Config, Docs, and Focused Validation

**Files:**

- Modify: `config/sources.yaml`
- Modify: `README.md`
- Test: `tests/fetchers/test_sources_config_compat.py`
- Test: `tests/fetchers/test_twikit_fetcher.py`
- Test: `tests/fetchers/test_twitter_social.py`
- Test: `tests/scheduler/test_jobs.py`

- [ ] **Step 1: Write the failing source-config compatibility test**

```python
def test_repo_sources_include_social_watch_twitter_sources() -> None:
    config = load_sources_config()
    social_sources = [
        source for source in config["sources"]
        if source.get("schedule") == "social_watch"
    ]

    names = {source["name"] for source in social_sources}

    assert "twitter_gitcoin" in names
    assert "twitter_ethglobal" in names
    assert any(source.get("ingestion_mode") == "preprocessed" for source in social_sources)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/fetchers/test_sources_config_compat.py -v`
Expected: FAIL because the repository config still points at disabled RSSHub entries.

- [ ] **Step 3: Update runtime source config and operator docs**

```yaml
# config/sources.yaml
- name: twitter_gitcoin
  type: twitter
  fetch_method: twitter
  screen_name: gitcoin
  schedule: social_watch
  category: social
  ecosystem: multi
  trust_tier: official
  ingestion_mode: direct
  source_kind: account
  watch_priority: high
  enabled: true

- name: twitter_builder_alpha_list
  type: twitter
  fetch_method: twitter
  list_id: "1888888888888888888"
  schedule: social_watch
  category: social
  ecosystem: multi
  trust_tier: discovery
  ingestion_mode: preprocessed
  source_kind: list
  watch_priority: normal
  enabled: false
```

```markdown
# README.md

- Twitter social watch now uses Twikit rather than RSSHub.
- `social_watch` runs every `SOCIAL_WATCH_INTERVAL_MINUTES` minutes.
- Official Twitter sources enter the main pipeline directly.
- Discovery Twitter sources are preprocessed before classification and Slack.
- Required env vars: `TWITTER_AUTH_INFO_1`, `TWITTER_PASSWORD`, optional `TWITTER_AUTH_INFO_2`, `TWITTER_TOTP_SECRET`, `TWITTER_COOKIES_FILE`.
```

- [ ] **Step 4: Run focused validation**

Run: `pytest tests/config/test_settings.py tests/db/test_twitter_source_state.py tests/fetchers/test_runtime_source_controls.py tests/fetchers/test_source_metadata_normalization.py tests/fetchers/test_sources_config_compat.py tests/fetchers/test_twikit_fetcher.py tests/fetchers/test_twitter_social.py tests/scheduler/test_jobs.py tests/test_main_social_watch.py -v`
Expected: PASS

Run: `docker compose exec -T agent-app python -c "from src.main import run_social_watch; print(run_social_watch())"`
Expected: the command returns a success payload or a controlled auth/config error without breaking non-Twitter schedules.

- [ ] **Step 5: Commit**

```bash
git add config/sources.yaml README.md tests/fetchers/test_sources_config_compat.py tests/fetchers/test_twikit_fetcher.py tests/fetchers/test_twitter_social.py tests/scheduler/test_jobs.py tests/test_main_social_watch.py
git commit -m "feat: enable twitter social watch rollout"
```

## Self-Review Checklist

- Every requirement in [docs/superpowers/specs/2026-07-03-twitter-listening-design.md](../specs/2026-07-03-twitter-listening-design.md) is mapped to at least one task.
- No task requires altering existing `source_health` columns in place; new state lands in a dedicated Twitter table to match the repository's no-migration-structure reality.
- Direct official ingestion, discovery preprocessing, dedicated scheduling, MCP sidecar separation, and Slack throttling are all covered.
- The final validation includes both unit tests and one runtime social-watch smoke check.
