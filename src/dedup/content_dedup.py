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
"""
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Tuple

from sqlalchemy.orm import Session

from config.settings import settings
from src.db.models import Event
from src.db.queries import add_event_source, insert_event
from .vector_store import VectorStore
from .llm_summary import LLMSummaryExtractor

logger = logging.getLogger(__name__)

# Deadline differences below this are noise (a source rounding "Oct 11" to
# "2026-10-11 00:00"), not evidence of a different edition.
DEADLINE_VETO_TOLERANCE = timedelta(days=3)

# Extra days added to the sliding window when deciding whether a stored Event can
# still be matched. See ContentDeduplicator.is_matchable.
MATCH_WINDOW_SLACK_DAYS = 7

_TITLE_NOISE_RE = re.compile(r"[^0-9a-z\u4e00-\u9fff]+")


def normalize_title(title: Optional[str]) -> str:
    """Casefold and strip punctuation/emoji so repost titles compare equal."""
    if not title:
        return ""
    return _TITLE_NOISE_RE.sub(" ", str(title).casefold()).strip()


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

    def __init__(self, vector_store: VectorStore, llm_extractor: Optional[LLMSummaryExtractor] = None):
        self.vs = vector_store
        self.threshold = settings.SIMILARITY_THRESHOLD  # default: 0.75
        self.window_days = settings.SLIDING_WINDOW_DAYS
        self.llm = llm_extractor or LLMSummaryExtractor()

    # -- embedding text -----------------------------------------------------

    def embedding_text(self, title: str, description: str) -> str:
        """Text that gets embedded for an incoming candidate."""
        return self.llm.get_embedding_text(title or "", description or "")

    def embedding_text_for_event(self, event: Event) -> str:
        """Text that gets embedded for an already stored Event (re-indexing).

        Deliberately does NOT call the LLM. Re-indexing is a bulk operation (every
        live Event, on startup and after a vector reset), and one summary call per
        Event turned reconciliation into a multi-minute stall in front of the
        pipeline. Stored Events already carry the classifier's own title and
        description, which is what the LLM summary would have been derived from.
        The matched text stays semantically equivalent; the previous behaviour was
        also inconsistent, since an Event whose summary call failed fell back to
        exactly this text anyway.
        """
        return raw_embedding_text(event.title or "", event.description or "")

    # -- match window -------------------------------------------------------

    def is_matchable(self, event: Event, now: Optional[datetime] = None) -> bool:
        """Can this stored Event still represent a live opportunity?"""
        now = now or datetime.now(timezone.utc)
        deadline = _as_utc(event.deadline)
        if deadline is not None and deadline >= now:
            return True

        created_at = _as_utc(event.created_at)
        if created_at is None:
            return True
        # MATCH_WINDOW_SLACK absorbs the gap between an Event's created_at and the
        # moment the opportunity actually surfaced: a repost of the same item can
        # legitimately arrive just after the cutoff, and treating it as new is what
        # created duplicate Events (#120 vs #132, 50 seconds apart on the boundary).
        window = timedelta(days=self.window_days + MATCH_WINDOW_SLACK_DAYS)
        return created_at >= now - window

    def _deadline_conflict(self, incoming, candidate: Event) -> bool:
        """True when both sides state a deadline and they describe different editions."""
        left = _as_utc(incoming)
        right = _as_utc(candidate.deadline)
        if left is None or right is None:
            return False
        return abs(left - right) > DEADLINE_VETO_TOLERANCE

    @staticmethod
    def _ecosystem_conflict(incoming: Optional[str], candidate: Event) -> bool:
        left = (incoming or "").strip().casefold()
        right = (candidate.ecosystem or "").strip().casefold()
        if not left or not right:
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
        )

        if matched_event_id:
            # Duplicate — append source, increment heat
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
    ) -> Optional[int]:
        """Return the id of an existing Event this candidate duplicates."""
        try:
            similar = self.vs.search_similar(query_text, n_results=20)
        except Exception as e:
            # Never treat a broken index as "no duplicate": that is how silent
            # duplicates were created. Fail the item's run loudly instead.
            logger.error("L2 dedup unavailable, refusing to guess: %s", e)
            raise

        now = now or datetime.now(timezone.utc)
        incoming_norm = normalize_title(incoming_title)

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
            if not self.is_matchable(candidate, now=now):
                continue
            if self._deadline_conflict(incoming_deadline, candidate):
                logger.info(
                    "L2 veto: deadline differs for event #%s (%s vs %s)",
                    candidate_id, incoming_deadline, candidate.deadline,
                )
                continue
            if self._ecosystem_conflict(incoming_ecosystem, candidate):
                continue

            similarity = 1.0 - float(distance)
            title_twin = bool(incoming_norm) and incoming_norm == normalize_title(candidate.title)
            if title_twin or similarity >= self.threshold:
                logger.info(
                    "L2 dedup hit: similarity=%.3f title_twin=%s -> event #%s",
                    similarity, title_twin, candidate_id,
                )
                return candidate_id

        return None

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
