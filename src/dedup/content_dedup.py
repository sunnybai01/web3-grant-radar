"""L2 semantic deduplication — ChromaDB vector similarity + sliding window.

Uses LLM-extracted structured summaries for embedding (cleaner signal than raw
text). Falls back to raw title+description if LLM is unavailable.

Matching rules, in order:

1. An indexed Event stays matchable while it carries a future deadline, not only
   while it is younger than the window. Using `created_at` alone minted a second
   Event for the same opportunity when the repost landed seconds after the
   cutoff (observed in production: event #132 arrived 50s late and duplicated
   #120).
2. A differing stated deadline vetoes the match: it is a different edition of
   the program, not the same opportunity.
3. A differing ecosystem vetoes the match: same-named programs on different
   chains are different opportunities.
4. An exact normalized-title match merges without consulting the embedding
   threshold, which cannot separate "Base Builder Grant Program" reposts from
   each other but can score 0.75 on genuinely different programs.
5. The same source URL is always the same Event (the same tweet, feed entry or
   listing produced two Events before: #159/#168). Platform listings
   (LISTING_SOURCE_TYPES) also publish one entry per opportunity, so an Event
   that already holds a different listing from the same source is never a match:
   templated listing texts embed as near-duplicates of each other (47 Superteam
   grants collapsed into four Events on their first run).
6. Incoming items and stored Events are embedded from the same text (title +
   description). Incoming items used an LLM summary with a "| deadline:… |
   ecosystem:…" suffix while stored Events used title + description, so the two
   sides never compared like with like.
7. An Event without a future deadline stays matchable while it keeps being seen:
   the window runs from its latest source, not its creation, so a program
   re-posted every few weeks is not minted again (Base Builder Grant ×3).
8. A merge fills the Event's empty deadline, start date, amount, apply link,
   track and ecosystem from the incoming item; stated values are never replaced.
"""
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from config.settings import settings
from src.classifier.ecosystem import MULTI, normalize_ecosystem
from src.db.models import Event, EventSource
from src.db.queries import add_event_source, insert_event
from src.fetchers.base import LISTING_SOURCE_TYPES
from .vector_store import VectorStore
from .llm_summary import raw_embedding_text

logger = logging.getLogger(__name__)

# Deadline differences below this are not evidence of a different edition: one
# source states the application deadline, another the event's last day
# (ETHGlobal Mumbai: 11-03 vs 11-07). Editions of a program are weeks apart.
DEADLINE_VETO_TOLERANCE = timedelta(days=6)

# Extra days added to the sliding window when deciding whether a stored Event can
# still be matched. See ContentDeduplicator.is_matchable.
MATCH_WINDOW_SLACK_DAYS = 7

# Event fields a merge may fill in when the stored Event has none.
BACKFILL_FIELDS = ("deadline", "start_date", "amount", "application_url", "track", "ecosystem")
_DATETIME_FIELDS = {"deadline", "start_date"}

_TITLE_NOISE_RE = re.compile(r"[^0-9a-z\u4e00-\u9fff]+")

# Words that do not tell two programs apart ("ETHGlobal Mumbai Hackathon" is
# "ETHGlobal Mumbai"). Years and numbers are kept: they separate editions.
_GENERIC_TITLE_WORDS = {"the", "hackathon", "grant", "grants", "program", "programs", "programme"}


def match_window() -> timedelta:
    """How long after its latest sighting an Event without a future deadline stays matchable."""
    return timedelta(days=settings.SLIDING_WINDOW_DAYS + MATCH_WINDOW_SLACK_DAYS)


def normalize_title(title: Optional[str]) -> str:
    """Casefold and strip punctuation/emoji so repost titles compare equal."""
    if not title:
        return ""
    return _TITLE_NOISE_RE.sub(" ", str(title).casefold()).strip()


def title_key(title: Optional[str]) -> str:
    """normalize_title without words that every program title shares."""
    words = [w for w in normalize_title(title).split() if w not in _GENERIC_TITLE_WORDS]
    return " ".join(words)


def _as_utc(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


class ContentDeduplicator:
    """L2 semantic dedup using ChromaDB cosine similarity.

    For each candidate event:
    1. Compute the embedding text for the event
    2. Search ChromaDB for similar events
    3. Merge when a candidate is inside the match window, agrees on deadline and
       ecosystem, and is either a normalized-title twin or scores above the
       similarity threshold
    4. Otherwise insert a new Event and index it
    """

    def __init__(self, vector_store: VectorStore):
        self.vs = vector_store
        self.threshold = settings.SIMILARITY_THRESHOLD  # default: 0.75

    # -- embedding text -----------------------------------------------------

    @staticmethod
    def embedding_text(title: str, description: str) -> str:
        """Text embedded for incoming items and stored Events alike.

        No LLM: re-indexing every live Event must not wait on a summary call per
        Event, and both sides of a comparison must be built the same way.
        """
        return raw_embedding_text(title or "", description or "")

    def embedding_text_for_event(self, event: Event) -> str:
        return self.embedding_text(event.title, event.description)

    # -- match window -------------------------------------------------------

    def is_matchable(self, event: Event, now: Optional[datetime] = None,
                     last_seen: Optional[datetime] = None) -> bool:
        """Can this stored Event still represent a live opportunity?

        True while its deadline is ahead, or while it was last seen (created or
        re-sourced) within the match window. MATCH_WINDOW_SLACK absorbs a repost
        landing just after the cutoff (#120 vs #132, 50 seconds apart).
        """
        now = now or datetime.now(timezone.utc)
        deadline = _as_utc(event.deadline)
        if deadline is not None and deadline >= now:
            return True

        seen = [t for t in (_as_utc(event.created_at), _as_utc(last_seen)) if t is not None]
        if not seen:
            return True
        return max(seen) >= now - match_window()

    def _is_matchable(self, db: Session, event: Event, now: Optional[datetime] = None) -> bool:
        last_seen = (
            db.query(func.max(EventSource.fetched_at))
            .filter(EventSource.event_id == event.id)
            .scalar()
        )
        return self.is_matchable(event, now=now, last_seen=last_seen)

    def _deadline_conflict(self, incoming, candidate: Event) -> bool:
        """True when both sides state a deadline and they describe different editions."""
        left = _as_utc(incoming)
        right = _as_utc(candidate.deadline)
        if left is None or right is None:
            return False
        return abs(left - right) > DEADLINE_VETO_TOLERANCE

    @staticmethod
    def _ecosystem_conflict(incoming: Optional[str], candidate: Event) -> bool:
        left = normalize_ecosystem(incoming)
        right = normalize_ecosystem(candidate.ecosystem)
        if left in (None, MULTI) or right in (None, MULTI):
            return False
        return left != right

    # -- main entry point ---------------------------------------------------

    def check_and_process(
        self,
        db: Session,
        event_data: dict,
        source_type: str,
        source_name: str,
        source_url: Optional[str] = None,
        raw_signal_id: Optional[int] = None,
    ) -> Tuple[Optional[int], bool]:
        """
        Returns (event_id, is_new).
        - is_new=True: event was inserted as a new entity.
        - is_new=False: event was identified as a duplicate; its source was appended
          and heat_count incremented. event_id is the existing event's ID.
        """
        title = event_data.get("title", "")
        description = event_data.get("description", "")
        query_text = self.embedding_text(title, description)

        matched_event_id = self._find_match(
            db,
            query_text=query_text,
            incoming_title=title,
            incoming_deadline=event_data.get("deadline"),
            incoming_ecosystem=event_data.get("ecosystem"),
            source_type=source_type,
            source_name=source_name,
            source_url=source_url,
        )

        if matched_event_id:
            # Duplicate — append source, increment heat, fill what the Event lacked
            add_event_source(
                db,
                event_id=matched_event_id,
                source_type=source_type,
                source_name=source_name,
                source_url=source_url,
                raw_signal_id=raw_signal_id,
            )
            event = db.query(Event).filter(Event.id == matched_event_id).first()
            if event:
                event.heat_count = (event.heat_count or 1) + 1
                self._backfill(event, event_data)
                db.commit()
            return matched_event_id, False

        # New event — insert, index in ChromaDB
        event = insert_event(db, **event_data)

        # Add initial source record
        add_event_source(
            db,
            event_id=event.id,
            source_type=source_type,
            source_name=source_name,
            source_url=source_url,
            raw_signal_id=raw_signal_id,
        )

        self.index_event(event, text=query_text)
        return event.id, True

    def _find_match(
        self,
        db: Session,
        query_text: str,
        incoming_title: str,
        incoming_deadline=None,
        incoming_ecosystem: Optional[str] = None,
        now: Optional[datetime] = None,
        source_type: Optional[str] = None,
        source_name: Optional[str] = None,
        source_url: Optional[str] = None,
    ) -> Optional[int]:
        """Return the id of an existing Event this candidate duplicates."""
        if source_url:
            # A URL is an identity only while it belongs to one Event. Before listing
            # pages were split per card, several Events shared a listing page URL.
            owners = [
                row[0] for row in
                db.query(EventSource.event_id)
                .filter(EventSource.source_url == source_url)
                .distinct()
                .limit(2)
            ]
            if len(owners) == 1:
                return owners[0]
        listing = source_type in LISTING_SOURCE_TYPES and bool(source_url)

        try:
            similar = self.vs.search_similar(query_text, n_results=20)
        except Exception as e:
            # Never treat a broken index as "no duplicate": that is how silent
            # duplicates were created. Fail the item's run loudly instead.
            logger.error("L2 dedup unavailable, refusing to guess: %s", e)
            raise

        now = now or datetime.now(timezone.utc)
        incoming_key = title_key(incoming_title)

        # Candidates are returned nearest-first; the first one that survives the
        # window and veto checks wins. An out-of-window hit must NOT discard the
        # whole candidate list (the old code did, losing real duplicates).
        for doc_id, distance, _meta in similar:
            try:
                candidate_id = int(str(doc_id).replace("event_", ""))
            except ValueError:
                continue

            candidate = db.query(Event).filter(Event.id == candidate_id).first()
            if candidate is None:
                continue
            if not self._is_matchable(db, candidate, now=now):
                continue
            if self._deadline_conflict(incoming_deadline, candidate):
                logger.info(
                    "L2 veto: deadline differs for event #%s (%s vs %s)",
                    candidate_id, incoming_deadline, candidate.deadline,
                )
                continue
            if self._ecosystem_conflict(incoming_ecosystem, candidate):
                continue
            if listing and self._holds_other_listing(db, candidate_id, source_name, source_url):
                continue

            similarity = 1.0 - float(distance)
            title_twin = bool(incoming_key) and incoming_key == title_key(candidate.title)
            if title_twin or similarity >= self.threshold:
                logger.info(
                    "L2 dedup hit: similarity=%.3f title_twin=%s -> event #%s",
                    similarity, title_twin, candidate_id,
                )
                return candidate_id

        return None

    @staticmethod
    def _backfill(event: Event, event_data: dict) -> None:
        for field in BACKFILL_FIELDS:
            value = event_data.get(field)
            if field in _DATETIME_FIELDS:
                value = _as_utc(value)
            if value in (None, "") or getattr(event, field) not in (None, ""):
                continue
            setattr(event, field, value)

    @staticmethod
    def _holds_other_listing(db: Session, event_id: int, source_name: str, source_url: str) -> bool:
        """The Event already carries a different entry from the same listing source."""
        return db.query(
            db.query(EventSource)
            .filter(
                EventSource.event_id == event_id,
                EventSource.source_name == source_name,
                EventSource.source_url != source_url,
            )
            .exists()
        ).scalar()

    def index_event(self, event: Event, text: Optional[str] = None) -> bool:
        """Index (or refresh) an Event in the vector store.

        Returns True when indexed. Failures are logged loudly but do not abort
        the run: the Event row is already committed, and by the time we return
        its raw_signal is recorded, so L1 would never re-process it. Startup
        reconciliation re-indexes anything missing.
        """
        payload = text or self.embedding_text_for_event(event)
        if not payload or not payload.strip():
            return False

        metadata = {
            "event_type": event.event_type or "",
            "ecosystem": event.ecosystem or "",
            "created_at": (
                _as_utc(event.created_at) or datetime.now(timezone.utc)
            ).isoformat(),
        }
        if event.deadline is not None:
            metadata["deadline"] = _as_utc(event.deadline).isoformat()

        try:
            self.vs.add(doc_id=f"event_{event.id}", text=payload, metadata=metadata)
        except Exception as e:
            logger.error(
                "Event #%s created but NOT indexed — semantic dedup will not match "
                "it until reconciliation runs: %s", event.id, e,
            )
            return False
        return True
