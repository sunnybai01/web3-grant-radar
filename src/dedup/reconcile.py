"""Startup reconciliation between the Postgres Event table and the vector index.

The vector index is a derived store: Event rows are the source of truth. When
the index loses vectors (a stale docker volume mount, a reset, or a wiped Chroma
volume) semantic dedup silently stops matching pre-existing Events and
duplicates start appearing — which is exactly what happened in production, where
only 14 of 40 Events had vectors.

This module re-embeds the Events that are missing from the collection.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from config.settings import settings
from src.db.models import Event

logger = logging.getLogger(__name__)

# Chunked so a large reconciliation cannot stall pipeline startup forever.
BACKFILL_LIMIT = 500


def _candidate_events(db: Session, window_days: Optional[int] = None) -> list[Event]:
    """Events that dedup should be able to match against.

    Includes anything created inside the sliding window *or* still carrying a
    future deadline: an open opportunity must stay matchable even when it was
    first seen longer ago than the window.
    """
    now = datetime.now(timezone.utc)
    days = settings.SLIDING_WINDOW_DAYS if window_days is None else window_days
    cutoff = now - timedelta(days=days)
    return (
        db.query(Event)
        .filter((Event.created_at >= cutoff) | (Event.deadline >= now))
        .order_by(Event.created_at.desc())
        .limit(BACKFILL_LIMIT)
        .all()
    )


def reconcile_vector_index(db: Session, vector_store, deduplicator=None, window_days: Optional[int] = None) -> dict:
    """Index any Event missing from the vector collection.

    Returns {"candidates": n, "missing": n, "indexed": n, "failed": n}.
    Never raises for individual failures — the caller decides how loud to be.
    """
    summary = {"candidates": 0, "missing": 0, "indexed": 0, "failed": 0}

    events = _candidate_events(db, window_days=window_days)
    summary["candidates"] = len(events)
    if not events:
        return summary

    try:
        indexed_ids = vector_store.existing_ids()
    except Exception as e:
        logger.error("Vector index reconciliation skipped — cannot list ids: %s", e)
        summary["failed"] = len(events)
        return summary

    if deduplicator is None:
        from src.dedup.content_dedup import ContentDeduplicator

        deduplicator = ContentDeduplicator(vector_store)

    for event in events:
        doc_id = f"event_{event.id}"
        if doc_id in indexed_ids:
            continue

        summary["missing"] += 1
        text = deduplicator.embedding_text_for_event(event)
        if not text:
            continue

        metadata = {
            "event_type": event.event_type or "",
            "ecosystem": event.ecosystem or "",
            "created_at": (
                event.created_at.isoformat()
                if event.created_at
                else datetime.now(timezone.utc).isoformat()
            ),
        }
        if event.deadline is not None:
            metadata["deadline"] = event.deadline.isoformat()

        try:
            vector_store.add(doc_id=doc_id, text=text, metadata=metadata)
            summary["indexed"] += 1
        except Exception as e:
            summary["failed"] += 1
            logger.error("Failed to re-index event #%s: %s", event.id, e)

    if summary["missing"]:
        logger.warning(
            "Vector index reconciliation: %s/%s Events were missing from the index "
            "(%s re-indexed, %s failed) — L2 dedup could not match them before this.",
            summary["missing"], summary["candidates"], summary["indexed"], summary["failed"],
        )
    else:
        logger.info(
            "Vector index reconciliation: all %s candidate Events are indexed",
            summary["candidates"],
        )

    return summary
