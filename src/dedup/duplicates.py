"""Find and merge stored Events that the current L2 rules treat as one opportunity.

New items are matched by those rules as they arrive. Events created before the
rules existed may still be duplicated; this module finds them with the same
tests and merges each group into one Event.
"""
import logging
from collections import defaultdict
from typing import Iterable, List

from sqlalchemy.orm import Session

from src.db.models import Event, EventSource, PushLog
from .content_dedup import DEADLINE_VETO_TOLERANCE, ContentDeduplicator, title_key

logger = logging.getLogger(__name__)

# web_scraper URLs were whole listing pages before pages were split per card, so
# a shared one says nothing about identity. Every other source URL is per item.
AMBIGUOUS_URL_SOURCE_TYPES = {"web_scraper"}

# Which Event of a group survives: one carrying a team decision first.
_TRIAGE_RANK = {"shortlisted": 2, "dismissed": 1, "new": 0}


def find_duplicate_groups(db: Session) -> List[List[Event]]:
    """Groups (each sorted by id) of Events that are the same opportunity."""
    events = db.query(Event).filter(Event.status.notin_(["fraud"])).order_by(Event.id).all()
    parent = {e.id: e.id for e in events}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        parent[find(a)] = find(b)

    owners = defaultdict(set)
    for event_id, url, source_type in db.query(
        EventSource.event_id, EventSource.source_url, EventSource.source_type
    ):
        if url and source_type not in AMBIGUOUS_URL_SOURCE_TYPES and event_id in parent:
            owners[url].add(event_id)
    for ids in owners.values():
        ids = sorted(ids)
        for other in ids[1:]:
            union(ids[0], other)

    by_id = {e.id: e for e in events}

    def members(root):
        return [by_id[i] for i in parent if find(i) == root]

    def compatible(left, right):
        """No two deadlines a different edition apart, no two different chains.

        Checked across whole groups: unions are transitive, so an undated Event
        would otherwise bridge editions whose deadlines are months apart.
        """
        for a in left:
            for b in right:
                if ContentDeduplicator._ecosystem_conflict(a.ecosystem, b):
                    return False
                if a.deadline and b.deadline and abs(a.deadline - b.deadline) > DEADLINE_VETO_TOLERANCE:
                    return False
        return True

    by_title = defaultdict(list)
    for event in events:
        key = title_key(event.title)
        if key:
            by_title[(event.event_type, key)].append(event)
    for same in by_title.values():
        for i, a in enumerate(same):
            for b in same[i + 1:]:
                ra, rb = find(a.id), find(b.id)
                if ra != rb and compatible(members(ra), members(rb)):
                    union(a.id, b.id)

    groups = defaultdict(list)
    for event in events:
        groups[find(event.id)].append(event)
    return sorted((g for g in groups.values() if len(g) > 1), key=lambda g: g[0].id)


def _source_count(db: Session, event_id: int) -> int:
    return db.query(EventSource).filter(EventSource.event_id == event_id).count()


def choose_survivor(db: Session, group: Iterable[Event]) -> Event:
    """The Event a team decision was made on, else the best-sourced, else the oldest."""
    return max(
        group,
        key=lambda e: (_TRIAGE_RANK.get(e.triage_status or "new", 0), _source_count(db, e.id), -e.id),
    )


def merge_group(db: Session, group: List[Event], vector_store=None) -> Event:
    """Merge every Event of ``group`` into its survivor and return the survivor."""
    keep = choose_survivor(db, group)
    kept_urls = {
        s.source_url for s in db.query(EventSource).filter(EventSource.event_id == keep.id)
    }

    for duplicate in group:
        if duplicate.id == keep.id:
            continue
        for source in db.query(EventSource).filter(EventSource.event_id == duplicate.id).all():
            if source.source_url in kept_urls:
                db.delete(source)
            else:
                source.event_id = keep.id
                kept_urls.add(source.source_url)
        db.query(PushLog).filter(PushLog.event_id == duplicate.id).update({PushLog.event_id: keep.id})
        ContentDeduplicator._backfill(keep, {field: getattr(duplicate, field) for field in
                                             ("deadline", "start_date", "amount", "application_url",
                                              "track", "ecosystem")})
        if _TRIAGE_RANK.get(duplicate.triage_status or "new", 0) > _TRIAGE_RANK.get(keep.triage_status or "new", 0):
            keep.triage_status = duplicate.triage_status
            keep.triaged_at = duplicate.triaged_at
        db.flush()
        duplicate_id = duplicate.id
        db.delete(duplicate)
        db.flush()
        if vector_store is not None:
            try:
                vector_store.delete(f"event_{duplicate_id}")
            except Exception as e:
                logger.warning("Could not delete vector for merged event #%s: %s", duplicate_id, e)
        logger.info("Merged event #%s into #%s", duplicate_id, keep.id)

    keep.heat_count = _source_count(db, keep.id)
    db.commit()
    db.refresh(keep)
    return keep
