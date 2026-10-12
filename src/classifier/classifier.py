"""Classification orchestrator — keyword filter → LLM classify → structured extraction."""
import email.utils
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, Tuple

from src.fetchers.base import FetchedItem
from .keyword_filter import KeywordFilter
from .llm_gateway import LLMGateway
from .prompts import CLASSIFY_SYSTEM, CLASSIFY_USER_TEMPLATE, current_date_label

logger = logging.getLogger(__name__)

# Categories the pipeline accepts. Anything else (including the intentionally
# out-of-scope BOUNTY) is treated as noise, but only after case normalisation.
ACCEPTED_CATEGORIES = {"GRANT", "HACKATHON"}
OUT_OF_SCOPE_CATEGORIES = {"BOUNTY"}

# Metadata keys fetchers use for the content's own publication time.
PUBLISHED_KEYS = ("created_at", "published_at", "published_date", "published")


def published_label(metadata: Optional[Dict[str, Any]]) -> str:
    """The content's publication date as YYYY-MM-DD, the raw value when it cannot
    be parsed, or "unknown". Shown to the model so it can tell a 2023 post from news."""
    for key in PUBLISHED_KEYS:
        value = (metadata or {}).get(key)
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, str) and value.strip():
            text = value.strip()
            try:
                return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
            except ValueError:
                pass
            try:
                return email.utils.parsedate_to_datetime(text).date().isoformat()
            except (TypeError, ValueError):
                return text[:40]
    return "unknown"


@dataclass
class Classification:
    """Outcome of classifying one item.

    ``category`` is "GRANT"/"HACKATHON" for a real opportunity, "NOISE" when the
    content genuinely is not an opportunity, and None only when we could not
    decide (LLM failure, unusable output). Keeping those last two apart matters:
    the old API returned None for both, so a provider outage was indistinguishable
    from "nothing found here" and whole runs silently reported zero opportunities.
    """

    category: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    llm_error: Optional[str] = None

    def __iter__(self):
        """Allow (category, data) unpacking, the shape this API used to return."""
        return iter((self.category, self.data))

    @property
    def is_opportunity(self) -> bool:
        return self.category in ACCEPTED_CATEGORIES and self.data is not None

    @property
    def failed(self) -> bool:
        return self.llm_error is not None


class OpportunityClassifier:
    """Two-stage classifier: keyword coarse filter → LLM fine classification.

    Stage 1 (keyword_filter): fast, cheap, wide recall.
    Stage 2 (llm_gateway): LLM classifies + extracts structured fields.
    """

    CONFIDENCE_THRESHOLD = 0.6

    def __init__(self, keyword_filter: KeywordFilter, llm_gateway: LLMGateway):
        self.keywords = keyword_filter
        self.llm = llm_gateway

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _coerce_confidence(value) -> Optional[float]:
        """Parse a model-supplied confidence defensively.

        The model returns JSON, so confidence occasionally arrives as a string
        or with an unexpected shape; comparing that to a float used to raise and
        abort the entire run.
        """
        if value is None:
            return None
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value.strip())
            except ValueError:
                return None
        return None

    # -- main entry point ---------------------------------------------------

    def classify(self, item: FetchedItem) -> Classification:
        """Classify a single fetched item.

        Returns a Classification. Callers must check ``failed`` before treating a
        non-opportunity as "the content was noise".
        """
        # Stage 1: keyword coarse filter
        if not self.keywords.matches(item.raw_content):
            return Classification(category="NOISE")

        # Stage 2: LLM fine classification + extraction
        user_prompt = CLASSIFY_USER_TEMPLATE.format(
            today=current_date_label(),
            published=published_label(item.metadata),
            title=(item.metadata or {}).get("title", "")[:300],
            content=item.raw_content[:3000],
            source_name=item.source_name,
            source_type=item.source_type,
        )

        try:
            result = self.llm.classify_structured(CLASSIFY_SYSTEM, user_prompt)
        except Exception as e:
            logger.error("Classification call raised for %s: %s", item.source_name, e)
            return Classification(llm_error=f"exception:{e}")

        if not isinstance(result, dict) or not result:
            return Classification(llm_error="empty_or_non_object_response")

        raw_category = result.get("category")
        if not isinstance(raw_category, str) or not raw_category.strip():
            return Classification(llm_error="missing_category", data=result)

        category = raw_category.strip().upper()

        # Bounty opportunities are intentionally out of scope — drop them so no
        # new bounty events are ever created, even if the LLM still emits BOUNTY.
        if category in OUT_OF_SCOPE_CATEGORIES:
            return Classification(category="NOISE")

        if category not in ACCEPTED_CATEGORIES:
            # Includes "NOISE" and any unexpected label such as "FELLOWSHIP".
            return Classification(category="NOISE", data=result)

        confidence = self._coerce_confidence(result.get("confidence"))
        if confidence is None:
            # The schema does not require confidence, and the prompt only asks for
            # it. Treating a missing value as 0.0 silently discarded opportunities,
            # so an absent score is treated as "the model did not object".
            logger.debug("No usable confidence for %s; accepting classification", item.source_name)
            confidence = 1.0

        if confidence < self.CONFIDENCE_THRESHOLD:
            return Classification(category="NOISE", data=result)

        # Merge ecosystem/category hints from source config
        metadata = item.metadata or {}
        if not result.get("ecosystem"):
            result["ecosystem"] = metadata.get("ecosystem")

        result["category"] = category
        result["confidence"] = confidence
        return Classification(category=category, data=result)

    def classify_batch(
        self, items: list[FetchedItem]
    ) -> list[Tuple[FetchedItem, Classification]]:
        """Classify a batch. Returns list of (item, Classification)."""
        return [(item, self.classify(item)) for item in items]
