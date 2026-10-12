"""Web3 Grant Radar — Main Entry Point.

Wires together the full V1 pipeline:
  Fetcher → L1 Dedup → L2 Dedup → LLM Classify → Zero-trust Verify → Score → Slack Push
"""
import email.utils
import logging
import re
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from config.settings import settings
from src.db.database import init_db, SessionLocal
from src.db.models import Event
from src.fetchers.builder import load_sources_config, build_registry
from src.fetchers.base import get_fetch_skip_reason, select_budgeted_sources
from src.dedup.url_dedup import process_item_l1
from src.dedup.content_dedup import ContentDeduplicator
from src.dedup.vector_store import VectorStore
from src.classifier.amount_filter import parse_amount_usd
from src.classifier.keyword_filter import KeywordFilter
from src.classifier.llm_gateway import LLMGateway
from src.classifier.classifier import Classification, OpportunityClassifier
from src.classifier.prompts import current_date_label
from src.classifier.scorer import OpportunityScorer
from src.verifier.verifier import verify_opportunity
from src.dispatch.slack_client import SlackDispatcher
from src.dispatch.daily_summary_service import build_daily_summary
from src.dispatch.report_writer import generate_report
from src.dispatch.heartbeat import heartbeat, increment_stat, reset_daily_stats
from src.scheduler.jobs import create_scheduler, register_jobs
from src.db.queries import (
    upsert_source_health,
    get_source_health,
    create_schedule_log,
    finish_schedule_log,
    update_event,
    get_push_log_for_event,
    create_push_log,
    get_daily_summary_log,
    create_daily_summary_log,
    mark_daily_summary_sent,
    mark_daily_summary_failed,
    unlock_tavily_cooldown,
    mark_raw_signal_processed,
)

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pipeline components (initialized once)
# ---------------------------------------------------------------------------
_fetcher_registry = None
_deduplicator = None
_classifier = None
_scorer = None
_slack = None
_index_reconciled = False
_stats_reset_day = datetime.now(ZoneInfo("Asia/Shanghai")).date()
STALE_EVENT_MAX_AGE = timedelta(days=settings.STALE_MAX_AGE_DAYS)
DATE_SCRAPE_TIMEOUT = settings.DATE_SCRAPE_TIMEOUT_SECONDS
DATE_SCRAPE_MAX_CHARS = settings.DATE_SCRAPE_MAX_CHARS

EVENT_MODEL_FIELDS = {
    "event_type",
    "title",
    "description",
    "start_date",
    "deadline",
    "amount",
    "track",
    "ecosystem",
    "application_url",
    "source_url",
    "source_platform",
}

# Stages a reader can no longer act on. "results_announced" covers the common
# false positive: a post that is genuinely about a grant/hackathon but reports an
# outcome (winners, finalists, a grant already awarded) rather than a call to apply.
UNACTIONABLE_STAGES = {"closed", "results_announced"}

# A hackathon/program whose start date passed this long ago is almost certainly no
# longer joinable, even when no explicit deadline was ever published.
STALE_START_DATE_GRACE = timedelta(days=settings.STALE_START_DATE_GRACE_DAYS)

# A prize/funding pool below this (in USD) isn't worth an operator's time.
MIN_AMOUNT_USD = settings.MIN_AMOUNT_USD

# Outcomes that also feed the in-process heartbeat counters. The rest are
# pipeline bookkeeping only.
STAT_INCREMENT_OUTCOMES = {"new", "deduped", "verified", "fraud", "pushed"}


def _init_components():
    global _fetcher_registry, _deduplicator, _classifier, _scorer, _slack

    if _fetcher_registry is None:
        config = load_sources_config()
        _fetcher_registry = build_registry(config)

    if _deduplicator is None:
        vs = VectorStore()
        _deduplicator = ContentDeduplicator(vs)

    if _classifier is None:
        kw = KeywordFilter()
        llm = LLMGateway()
        _classifier = OpportunityClassifier(kw, llm)
        _scorer = OpportunityScorer(llm)

    if _slack is None:
        _slack = SlackDispatcher()


def _init_slack():
    global _slack

    if _slack is None:
        _slack = SlackDispatcher()


def _reconcile_vector_index_once():
    """Make sure every live Event has a vector.

    The vector index is derived state. A wiped or stale Chroma volume used to
    leave pre-existing Events unindexed, so semantic dedup could not match them
    and duplicates were created for opportunities already in the database.

    Normally a single pass per process is enough, but the index can also be
    cleared from outside the process (POST /api/v1/admin/reset-dedup). The flag
    therefore only records that we have run once; whenever the collection no
    longer covers the candidate Events we re-run, which makes the reset
    self-healing instead of leaving the process matching against an empty index.
    """
    global _index_reconciled

    if _deduplicator is None:
        return

    from src.dedup.reconcile import reconcile_vector_index

    if _index_reconciled:
        try:
            candidate_ids = _reconcile_candidate_ids()
            if _deduplicator.vs.existing_ids() >= candidate_ids:
                return
            logger.warning(
                "Vector index lost %d Event(s) — re-indexing before matching",
                len(candidate_ids - _deduplicator.vs.existing_ids()),
            )
        except Exception as e:
            # Cannot confirm coverage: fall through and reconcile, which is the
            # safe direction for dedup accuracy.
            logger.warning("Could not verify vector index coverage: %s", e)

    db = SessionLocal()
    try:
        reconcile_vector_index(db, _deduplicator.vs)
    except Exception as e:
        logger.error("Vector index reconciliation failed (dedup will be partial): %s", e)
    finally:
        db.close()

    _index_reconciled = True


def _reconcile_candidate_ids() -> set[str]:
    """Doc ids of the Events the reconciler would index."""
    from src.dedup.reconcile import _candidate_events

    db = SessionLocal()
    try:
        return {f"event_{event.id}" for event in _candidate_events(db)}
    finally:
        db.close()


def _persistable_event_data(event_data: dict) -> dict:
    return {
        key: value
        for key, value in event_data.items()
        if key in EVENT_MODEL_FIELDS
    }


def _parse_datetime(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            # Tavily news returns RFC 2822 ("Fri, 09 Oct 2026 08:44:57 GMT"). Read
            # as ISO only, every Tavily result looked undated and was dropped as
            # missing_published_at.
            try:
                parsed = email.utils.parsedate_to_datetime(value)
            except (TypeError, ValueError):
                return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


# Where the secondary page scrape records the publication date it extracted. Kept
# apart from the dates fetchers stamp so official sources can ignore a guess.
SCRAPED_PUBLISHED_KEY = "scraped_published_date"


def _published_at(item, include_scraped: bool = True) -> datetime | None:
    metadata = item.metadata or {}
    keys = ("created_at", "published_at", "published_date", "published")
    if include_scraped:
        keys += (SCRAPED_PUBLISHED_KEY,)
    for key in keys:
        published_at = _parse_datetime(metadata.get(key))
        if published_at is not None:
            return published_at
    return None


_TITLE_YEAR_RE = re.compile(r"\b(20\d{2})\b")


def _title_years_all_past(title: str | None, now: datetime) -> bool:
    """True when the title carries year labels and every one of them is a past year.

    Deliberately title-only: descriptions routinely mention unrelated years ("building
    on Ethereum since 2017") that would cause false drops. A title mixing a past and a
    current year ("2025 recap, 2026 edition") is kept — any non-past year vetoes.
    """
    if not title:
        return False

    years = [int(match) for match in _TITLE_YEAR_RE.findall(title)]
    if not years:
        return False

    return all(year < now.year for year in years)


def _is_rolling(structured: dict) -> bool:
    """The classifier's is_rolling flag, tolerating a stringly-typed value."""
    value = structured.get("is_rolling")
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1"}
    return value is True


def _staleness_reason(
    item, structured: dict | None, source_tier: str = "discovery", now: datetime | None = None
) -> str | None:
    """Check if an opportunity is *definitely* expired and should be dropped.

    Strategy (relaxed):
    - deadline present AND in the past → definitely expired, drop
    - no deadline AND every year in the title is a past year → drop
    - published >60 days ago with no deadline → likely stale, drop. Official
      sources are exempt only when the content says the program is rolling.
    - discovery source whose start date passed >grace ago with no deadline → drop
    - discovery source with no published date AND no deadline → too uncertain, drop
    - official source without a published date → kept (program pages are undated)

    A future deadline short-circuits every weaker rule below it: an explicitly stated
    open window outranks any inference drawn from a title or a publication date.
    """
    now = now or datetime.now(timezone.utc)
    structured = structured or {}
    tier = (source_tier or "discovery").lower()

    # If we have a deadline and it's in the past → definitely expired
    deadline = _parse_datetime(structured.get("deadline"))
    if deadline is not None and deadline < now:
        return "deadline_expired"

    # A past year in the title is about as strong as a past deadline ("ETHIndiaVilla
    # 2025" seen in 2026), so this applies to official sources too — but only when no
    # deadline was found, which keeps rolling programs safe.
    if deadline is None and _title_years_all_past(structured.get("title"), now):
        return "title_year_past"

    # Official sources are trusted, not fresh: a 2023 official tweet about "Round 2"
    # was pushed as a new opportunity in 2026 when official sources skipped this
    # rule. Only a program the content itself calls rolling survives its age. The
    # date must be one the source stamped (feed entry, tweet): official program
    # pages are undated, and a date scraped off such a page is only a guess.
    if tier == "official":
        stamped_at = _published_at(item, include_scraped=False)
        if (
            deadline is None
            and stamped_at is not None
            and now - stamped_at > STALE_EVENT_MAX_AGE
            and not _is_rolling(structured)
        ):
            return "published_too_old"
        return None

    published_at = _published_at(item)
    start_date = _parse_datetime(structured.get("start_date"))

    # The program already started a while ago and no deadline ever surfaced. Checked
    # before the rules below so it can catch items that would otherwise pass.
    if deadline is None and start_date is not None:
        if now - start_date > STALE_START_DATE_GRACE:
            return "start_date_passed"

    # Discovery source with zero time information → too uncertain. A start_date alone
    # does not rescue an item here: without a publication date there is no way to tell
    # whether the stated window is this year's or a rerun of an old announcement.
    if published_at is None and deadline is None:
        return "missing_published_at"

    # Discovery source published long ago and we still can't find a deadline
    if published_at is not None and deadline is None:
        if now - published_at > STALE_EVENT_MAX_AGE:
            return "published_too_old"

    return None


def _try_extract_dates_from_url(url: str, llm: LLMGateway) -> dict | None:
    """Lightweight secondary scrape: fetch a URL and ask LLM to extract dates.

    Used when the initial classification didn't find a deadline but the
    source URL points to a page that likely contains time-window info.
    """
    if not url:
        return None

    try:
        import httpx
        from bs4 import BeautifulSoup

        resp = httpx.get(url, timeout=DATE_SCRAPE_TIMEOUT, follow_redirects=True,
                         headers={"User-Agent": "Web3GrantRadar/1.0"})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        container = soup.find("article") or soup.find("main") or soup.body
        if not container:
            return None
        text = container.get_text(separator="\n", strip=True)[:DATE_SCRAPE_MAX_CHARS]

        prompt = (
            f"Today's date: {current_date_label()}\n"
            "Extract ONLY the dates below from this web page. "
            "Return JSON with no extra text:\n"
            '{"published_date": "ISO 8601 or null", "deadline": "ISO 8601 or null", '
            '"start_date": "ISO 8601 or null"}\n'
            "start_date is when the program, event, or application window opens. "
            "A date written without a year refers to its nearest occurrence after the "
            "page's publication date (or after today when that is unknown).\n\n"
            f"Page text:\n{text}"
        )
        result = llm.classify_structured(
            "You extract dates from web pages. Only output JSON.",
            prompt,
        )
        return result if isinstance(result, dict) else None
    except Exception:
        logger.debug("Secondary date extraction skipped or failed for %s", url)
        return None


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

def _process_item(db, item, signal_id, schedule: str):
    """Run one already-deduped item through gates → dedup → verify → score → push.

    Returns (full_event, outcomes). ``outcomes`` names every stat counter to bump;
    the original counters were cumulative (a brand-new pushed opportunity counted
    in new *and* verified *and* pushed), and ``llm_errors``/``item_errors`` stay
    distinct from "no opportunity found" so an outage is never a quiet day.
    This function does not mutate stats itself.
    """
    classification = _classifier.classify(item)

    # Accept both the Classification object and the legacy (category, data) tuple.
    if isinstance(classification, tuple):
        classification = Classification(category=classification[0], data=classification[1])

    if classification.failed:
        logger.error(
            "[%s] Classification failed for %s signal #%s (%s): %s",
            schedule, item.source_name, signal_id, classification.llm_error,
            (item.metadata or {}).get("title", "")[:80],
        )
        return None, ["llm_errors"]

    if not classification.is_opportunity:
        return None, []

    structured = classification.data or {}
    category = classification.category
    outcomes = ["classified"]

    # --- Phase 3.1: Actionability gate ---
    # Drop outcome reports and closed windows before the expensive date scrape
    # below — there is nothing left to apply to.
    stage = str(structured.get("opportunity_stage") or "").strip().lower().replace(" ", "_")
    if stage in UNACTIONABLE_STAGES:
        logger.info(
            "[%s] Skip %s item from %s: %s",
            schedule, stage, item.source_name, structured.get("title", "")[:80],
        )
        return None, outcomes + ["unactionable"]

    # --- Phase 3.2: Minimum reward gate ---
    # Drop anything whose stated prize/funding reads as below the floor. Runs
    # before the date scrape below so a small prize never costs a fetch + LLM
    # call. A missing or unreadable amount is NOT a small amount: those pass
    # through and are judged by the scorer instead.
    amount_usd = parse_amount_usd(structured.get("amount"))
    if amount_usd is not None and amount_usd < MIN_AMOUNT_USD:
        logger.info(
            "[%s] Skip low-amount item from %s (~$%.0f < $%.0f): %s",
            schedule, item.source_name, amount_usd, MIN_AMOUNT_USD,
            structured.get("title", "")[:80],
        )
        return None, outcomes + ["low_amount"]

    metadata = item.metadata or {}
    source_tier = str(metadata.get("source_tier") or "discovery")

    # --- Phase 3.5: Secondary date extraction ---
    # When the initial classification couldn't find a deadline, try scraping the
    # source URL to extract time-window information.
    if not _parse_datetime(structured.get("deadline")) and item.raw_url:
        extra_dates = _try_extract_dates_from_url(item.raw_url, _classifier.llm)
        if extra_dates:
            for field in ("published_date", "deadline", "start_date"):
                val = extra_dates.get(field)
                if val and not structured.get(field):
                    structured[field] = val
            # If we got a published date, also feed it into item metadata so
            # _published_at can pick it up.
            pub = extra_dates.get("published_date")
            if pub and not _published_at(item):
                item.metadata[SCRAPED_PUBLISHED_KEY] = pub

    staleness_reason = _staleness_reason(item, structured, source_tier=source_tier)
    if staleness_reason:
        logger.info(
            "[%s] Skip stale item from %s: %s (%s)",
            schedule, item.source_name, staleness_reason, structured.get("title", "")[:60],
        )
        return None, outcomes + ["stale"]

    source_metadata = {
        "chain": metadata.get("chain"),
        "source_tier": metadata.get("source_tier"),
        "official": metadata.get("official"),
        "signal_type": metadata.get("signal_type"),
    }

    # --- Phase 4: L2 Semantic Dedup ---
    event_data = {
        "event_type": category.lower(),
        "title": structured.get("title", ""),
        "description": structured.get("description", ""),
        "start_date": structured.get("start_date"),
        "deadline": structured.get("deadline"),
        "amount": structured.get("amount"),
        "track": structured.get("track"),
        "ecosystem": structured.get("ecosystem"),
        "application_url": structured.get("application_url"),
        "source_url": item.raw_url,
        "source_type": item.source_type,
        "source_platform": structured.get("source_platform") or item.source_name,
        **source_metadata,
    }

    event_id, is_new = _deduplicator.check_and_process(
        db, _persistable_event_data(event_data),
        source_type=item.source_type,
        source_name=item.source_name,
        source_url=item.raw_url,
        raw_signal_id=signal_id,
    )

    if not is_new:
        return None, outcomes + ["deduped"]

    outcomes.append("new")

    # --- Phase 5: Zero-trust Verification ---
    verification = verify_opportunity(
        event_type=category.lower(),
        source_url=item.raw_url,
        application_url=structured.get("application_url", ""),
        source_name=item.source_name,
        metadata=metadata,
    )

    if verification["verdict"] == "fraud":
        from src.db.queries import mark_event_fraud
        mark_event_fraud(db, event_id, verification["verification_log"])
        return None, outcomes + ["fraud"]

    outcomes.append("verified")
    event_data["verification_verdict"] = verification["verdict"]
    event_data["verification_log"] = verification["verification_log"]

    # --- Phase 6: Scoring ---
    scored = _scorer.score(event_data)
    if scored:
        update_event(db, event_id,
                     is_verified=verification["verdict"] == "verified",
                     verification_log=verification["verification_log"],
                     score_roi=scored.get("score_roi"),
                     score_reputation=scored.get("score_reputation"),
                     score_timeliness=scored.get("score_timeliness"),
                     score_strategy=scored.get("score_strategy"),
                     final_score=scored.get("final_score"),
                     )

    # --- Phase 7: Push to Slack (if configured, skip dismissed) ---
    full_event = {**event_data, "id": event_id, **scored} if scored else {**event_data, "id": event_id}

    # The triage decision lives on the Event row, not in event_data: read it back.
    dismissed = full_event.get("triage_status") == "dismissed"
    try:
        event_row = db.query(Event).filter(Event.id == event_id).first()
        if event_row is not None:
            dismissed = event_row.triage_status == "dismissed"
    except Exception as e:
        logger.debug("Could not read triage_status for event #%s: %s", event_id, e)

    if dismissed:
        logger.info("Event #%s is dismissed — skipping Slack push", event_id)
        return full_event, outcomes

    slack_ts = _slack.push_new_event(full_event)

    if slack_ts:
        update_event(db, event_id, status="pushed", slack_ts=slack_ts,
                     slack_channel_id=settings.SLACK_CHANNEL_ID)
        create_push_log(db, event_id, action="create", slack_ts=slack_ts, success=True)
        return full_event, outcomes + ["pushed"]

    if _slack.is_configured:
        # Slack was configured but the push did not land: record the failure
        # instead of pretending it worked (previously nothing was written).
        create_push_log(db, event_id, action="create", slack_ts=None, success=False,
                        error_message="slack_push_failed")
        logger.error("Slack push failed for event #%s — recorded as a failed push", event_id)
    return full_event, outcomes


def _rollback(db) -> None:
    try:
        db.rollback()
    except Exception:
        logger.exception("Session rollback failed")


def _record_signal_outcome(db, signal_id, error=None) -> None:
    try:
        mark_raw_signal_processed(db, signal_id, error=error)
    except Exception:
        _rollback(db)
        logger.exception("Could not record the outcome of raw signal #%s", signal_id)


def run_pipeline(schedule: str):
    """Run the full pipeline for one schedule type."""
    global _stats_reset_day

    _init_components()
    _reconcile_vector_index_once()

    # Reset daily stats if day changed
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    if _stats_reset_day != today:
        reset_daily_stats()
        _stats_reset_day = today

    db = SessionLocal()
    log = create_schedule_log(db, f"pipeline_{schedule}")
    stats = {"fetched": 0, "new": 0, "deduped": 0, "classified": 0,
             "unactionable": 0, "low_amount": 0, "stale": 0, "verified": 0,
             "fraud": 0, "pushed": 0, "llm_errors": 0, "item_errors": 0}
    result = None

    try:
        fetcher_sources = [
            {**fetcher.config, "name": name}
            for name, fetcher in _fetcher_registry._fetchers.items()
        ]
        health_by_source = {
            source["name"]: get_source_health(db, source["name"])
            for source in fetcher_sources
        }
        tavily_allowed = select_budgeted_sources(
            fetcher_sources,
            health_by_source,
            schedule,
            fetch_method="tavily_search",
        )

        # --- Phase 1: Fetch ---
        def _should_skip_fetch(name, fetcher):
            if fetcher.config.get("fetch_method") == "tavily_search" and name not in tavily_allowed:
                return "method_budget"
            health = health_by_source.get(name)
            return get_fetch_skip_reason(fetcher.config, health)

        items, source_status = _fetcher_registry.fetch_all_with_status(
            schedule,
            should_skip=_should_skip_fetch,
        )
        stats["fetched"] = len(items)
        increment_stat("fetched", len(items))
        logger.info(f"[{schedule}] Fetched {len(items)} items from {len(_fetcher_registry._fetchers)} sources")

        # Update source health at source-level granularity
        for name, status in source_status.items():
            if status.get("skipped"):
                continue
            upsert_source_health(
                db,
                name,
                success=status.get("success", False),
                error=status.get("error"),
            )

        # --- Phase 2: L1 URL Dedup ---
        l1_results = []
        for item in items:
            try:
                signal_id = process_item_l1(db, item)
            except Exception as e:
                # A failed raw_signals write is not a duplicate, and must not take
                # the rest of the batch down with it.
                stats["item_errors"] += 1
                _rollback(db)
                logger.exception("[%s] L1 failed for item from %s: %s", schedule, item.source_name, e)
                continue
            if signal_id:
                l1_results.append((item, signal_id))
            else:
                stats["deduped"] += 1
        logger.info(f"[{schedule}] L1 dedup: {len(l1_results)} passed, {stats['deduped']} duplicates")

        # --- Phase 3+4+5+6+7: Classify → Dedup → Verify → Score → Collect ---
        new_events = []  # collected for report generation

        for item, signal_id in l1_results:
            try:
                full_event, outcomes = _process_item(db, item, signal_id, schedule)
            except Exception as e:
                # One bad item (malformed LLM value, transient API error) must not
                # abort the run or be charged against every source's health.
                stats["item_errors"] = stats.get("item_errors", 0) + 1
                logger.exception(
                    "[%s] Item from %s failed and was skipped: %s",
                    schedule, item.source_name, e,
                )
                # A failed DB statement leaves the session unusable for every
                # remaining item until it is rolled back.
                _rollback(db)
                _record_signal_outcome(db, signal_id, error=f"{type(e).__name__}: {e}")
                continue

            # Failed signals are retried on their next fetch instead of being
            # treated as seen; everything else was judged and is done.
            _record_signal_outcome(
                db, signal_id, error="classification_failed" if "llm_errors" in outcomes else None
            )

            for outcome in outcomes:
                stats[outcome] = stats.get(outcome, 0) + 1
                if outcome in STAT_INCREMENT_OUTCOMES:
                    increment_stat(outcome)
            if full_event is not None:
                new_events.append(full_event)

        # --- Generate and send report only when effective opportunities exist ---
        if new_events:
            report_path = None
            try:
                report_path = generate_report(new_events, schedule, stats)
                logger.info(f"Report saved: {report_path}")
            except Exception as e:
                logger.error(f"Report generation failed: {e}")

            if report_path and _slack.is_configured:
                _slack.upload_report(report_path, schedule, stats)
        else:
            logger.info(f"[{schedule}] No effective events found; skip Slack cards/report upload")

        if stats.get("llm_errors"):
            logger.error(
                "[%s] %d item(s) could NOT be classified — LLM unavailable or unusable "
                "output. These are NOT 'no opportunity found'.", schedule, stats["llm_errors"],
            )
        if stats.get("item_errors"):
            logger.error(
                "[%s] %d item(s) failed mid-pipeline and were skipped.", schedule, stats["item_errors"],
            )

        finish_schedule_log(db, log.id, items_fetched=stats["fetched"],
                           items_new=stats["new"], items_deduped=stats["deduped"],
                           items_classified=stats["classified"],
                           items_verified=stats["verified"])
        logger.info(f"[{schedule}] Complete: {stats}")
        result = {"status": "success", **stats}

    except Exception as e:
        logger.exception(f"[{schedule}] Pipeline failed: {e}")
        finish_schedule_log(db, log.id, error=str(e))
        # Per-source health is already recorded from the fetch phase. Marking every
        # registered source as failed here charged one classification/scoring bug
        # against all ~58 sources and pushed healthy ones to "down" after 3 runs.
        result = {"status": "failed", "error": str(e), **stats}

    finally:
        db.close()

    return result


def run_heartbeat():
    """Send heartbeat and check source health."""
    _init_components()

    def _hb_slack(stats_or_msg):
        if isinstance(stats_or_msg, str):
            _slack.send_alert(stats_or_msg)
        else:
            _slack.send_heartbeat(stats_or_msg)

    heartbeat(_hb_slack)


def run_social_watch():
    """Run the dedicated social watch schedule."""
    return run_pipeline("social_watch")


def run_daily_summary():
    """Build and send the once-per-day Slack summary."""
    _init_slack()

    db = SessionLocal()
    try:
        summary_date = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        existing = get_daily_summary_log(db, summary_date=summary_date, channel="slack")
        log_row = existing or create_daily_summary_log(db, summary_date=summary_date, channel="slack")
        payload = build_daily_summary(db, summary_date=summary_date)
        payload["totals"]["pushed"] = payload["totals"].get("pushed", 0)

        slack_ts = _slack.send_daily_summary(payload)
        if not slack_ts:
            mark_daily_summary_failed(db, log_row.id, error_message="slack_send_failed_or_not_configured")
            return {
                "status": "failed",
                "summary_date": summary_date.isoformat(),
                "error": "slack_send_failed_or_not_configured",
            }

        mark_daily_summary_sent(db, log_row.id, slack_ts=slack_ts)
        logger.info("Daily summary sent for %s", summary_date.isoformat())
        return {"status": "success", "summary_date": summary_date.isoformat(), "slack_ts": slack_ts}
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    logger.info("Starting Web3 Grant Radar V1...")

    # Initialize database tables
    init_db()
    logger.info("Database initialized")

    def _tavily_unlock() -> int:
        """Unlock all Tavily cooldowns — called by midnight scheduler job."""
        with SessionLocal() as db:
            count = unlock_tavily_cooldown(db)
            db.commit()
        logger.info("Midnight unlock: reset %d tavily source(s)", count)
        return count

    # Create scheduler
    scheduler = create_scheduler()
    register_jobs(
        scheduler,
        run_pipeline,
        run_heartbeat,
        run_social_watch,
        run_daily_summary,
        tavily_unlock_fn=lambda: _tavily_unlock(),
    )
    scheduler.start()
    logger.info("Scheduler started — waiting for jobs...")

    try:
        # Keep the main thread alive
        import signal
        stop_event = __import__("threading").Event()

        def _shutdown(sig, frame):
            logger.info("Shutdown signal received")
            stop_event.set()

        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)

        # Run once immediately on startup, then wait for cron
        logger.info("Running initial pipeline pass...")
        run_pipeline("grant_hackathon")
        run_social_watch()
        run_heartbeat()

        stop_event.wait()

    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        scheduler.shutdown(wait=False)
        if _fetcher_registry:
            _fetcher_registry.close()
        logger.info("Agent shut down")


if __name__ == "__main__":
    main()
