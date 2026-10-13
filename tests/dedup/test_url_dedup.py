import datetime
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.db.database import Base
from src.db.models import Event, EventSource, RawSignal
from src.db.queries import mark_raw_signal_processed
from src.dedup.url_dedup import generate_content_hash, normalize_url, process_item_l1
from src.fetchers.base import FetchedItem


def _db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        bind=engine, tables=[RawSignal.__table__, Event.__table__, EventSource.__table__]
    )
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def _item(content: str, url: str = "https://sui.io/grants") -> FetchedItem:
    return FetchedItem(
        source_type="web_scraper",
        source_name="sui_grants_page",
        raw_content=content,
        raw_url=url,
        canonical_url=url,
        metadata={},
    )


def test_l1_treats_identical_url_and_content_as_duplicate() -> None:
    db = _db_session()
    try:
        first = process_item_l1(db, _item("Grant A is open"))
        second = process_item_l1(db, _item("Grant A is open"))

        assert first is not None
        assert second is None
    finally:
        db.close()


def test_l1_lets_a_stable_url_through_when_content_changed() -> None:
    """A listing page keeps its URL while opportunities roll over — not a duplicate."""
    db = _db_session()
    try:
        first = process_item_l1(db, _item("Grant A is open"))
        second = process_item_l1(db, _item("Grant A is open. Grant B is open too."))

        assert first is not None
        assert second is not None
        assert first != second
        assert db.query(RawSignal).count() == 2
    finally:
        db.close()


def test_l1_still_dedupes_the_same_content_across_tracking_params() -> None:
    """normalize_url strips tracking params, so these collapse to one signal."""
    db = _db_session()
    try:
        first = process_item_l1(db, _item("Grant A", url="https://sui.io/grants?utm_source=x"))
        second = process_item_l1(db, _item("Grant A", url="https://sui.io/grants"))

        assert first is not None
        assert second is None
    finally:
        db.close()


def test_content_hash_differs_for_changed_content() -> None:
    assert generate_content_hash("a") != generate_content_hash("b")
    assert generate_content_hash("a") == generate_content_hash("a")


def test_normalize_url_strips_tracking_and_trailing_slash() -> None:
    assert normalize_url("https://Sui.io/grants/?utm_source=tw&page=2") == (
        "https://sui.io/grants?page=2"
    )


# --- processing state -------------------------------------------------------
# L1 used to record a signal before it was judged, so an LLM outage or a crash
# mid-item made that content "already seen" forever. A signal now counts as seen
# only once it was processed; failed ones are retried when they are fetched again.


def test_l1_retries_a_signal_whose_processing_failed() -> None:
    db = _db_session()
    try:
        first = process_item_l1(db, _item("Grant A is open"))
        mark_raw_signal_processed(db, first, error="classification_failed")

        again = process_item_l1(db, _item("Grant A is open"))

        assert again == first
        signal = db.get(RawSignal, first)
        assert signal.status == "pending"
        assert signal.attempts == 2
        assert db.query(RawSignal).count() == 1
    finally:
        db.close()


def test_l1_skips_a_signal_that_was_processed() -> None:
    db = _db_session()
    try:
        first = process_item_l1(db, _item("Grant A is open"))
        mark_raw_signal_processed(db, first)

        assert process_item_l1(db, _item("Grant A is open")) is None
    finally:
        db.close()


def test_l1_gives_up_after_the_attempt_limit() -> None:
    db = _db_session()
    try:
        signal_id = process_item_l1(db, _item("Grant A is open"))
        mark_raw_signal_processed(db, signal_id, error="timeout")
        assert process_item_l1(db, _item("Grant A is open")) == signal_id
        mark_raw_signal_processed(db, signal_id, error="timeout")
        assert process_item_l1(db, _item("Grant A is open")) == signal_id
        mark_raw_signal_processed(db, signal_id, error="timeout")

        assert process_item_l1(db, _item("Grant A is open")) is None
        assert db.get(RawSignal, signal_id).status == "failed"
    finally:
        db.close()


def test_l1_retries_a_signal_abandoned_mid_run() -> None:
    """A crash or container restart mid-run leaves the signal pending forever."""
    db = _db_session()
    try:
        signal_id = process_item_l1(db, _item("Grant A is open"))
        signal = db.get(RawSignal, signal_id)
        signal.fetched_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=3)
        db.commit()

        assert process_item_l1(db, _item("Grant A is open")) == signal_id
    finally:
        db.close()


def test_l1_leaves_a_signal_that_is_still_being_processed_alone() -> None:
    db = _db_session()
    try:
        process_item_l1(db, _item("Grant A is open"))

        assert process_item_l1(db, _item("Grant A is open")) is None
    finally:
        db.close()
