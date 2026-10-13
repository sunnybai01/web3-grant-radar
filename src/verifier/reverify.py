"""Re-verify stored Events with the current verifier.

Verdicts are recorded once, when an Event is created. When the verifier changes,
stored verdicts keep describing the old logic: until 2026-10-13 missing security
keys counted as "all checks passed", the cross-reference layer never ran and
GoPlus was called at a path that 404s.
"""
import logging
from collections import Counter
from typing import Callable

from sqlalchemy.orm import Session

from src.db.models import Event, EventSource
from .verifier import verify_opportunity

logger = logging.getLogger(__name__)

LIVE_STATUSES = ("new", "pushed")


def reverify_events(db: Session, verify: Callable = verify_opportunity, commit: bool = True) -> dict:
    """Recompute the verdict of every live Event; returns counts by verdict.

    ``commit=False`` rolls the changes back (a dry run that still asks the verifier).
    """
    counts = Counter()
    for event in db.query(Event).filter(Event.status.in_(LIVE_STATUSES)).order_by(Event.id).all():
        log = event.verification_log or {}
        source = (
            db.query(EventSource.source_name)
            .filter(EventSource.event_id == event.id)
            .order_by(EventSource.id)
            .first()
        )
        result = verify(
            event_type=event.event_type or "",
            source_url=event.source_url or "",
            application_url=event.application_url or "",
            source_name=source[0] if source else "",
            metadata=log.get("source_context") or {},
        )
        verdict = result["verdict"]
        event.verification_log = result["verification_log"]
        event.is_verified = verdict == "verified"
        if verdict == "fraud":
            event.status = "fraud"
            logger.warning("Event #%s is now flagged as fraud: %s", event.id, event.source_url)
        counts[verdict] += 1
    if commit:
        db.commit()
    else:
        db.rollback()
    return dict(counts)
