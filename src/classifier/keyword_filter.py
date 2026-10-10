"""Coarse keyword filter — wide recall, passes candidates to LLM for fine classification.

Design notes (these were the source of real false negatives):

* The gate counts *distinct matched terms*, not the number of regex matches.
  Counting non-overlapping matches made a single occurrence of a listed phrase
  score 1, and competing entries shadowed each other ("grant" before
  "grant program"), so "Ethereum Foundation Grant" failed a ">= 2 hits" filter
  even though it contains two listed terms.
* Negative keywords no longer veto unconditionally. "Not an airdrop. Real grants
  for builders." is a genuine opportunity, and one incidental word ("whitelist",
  "token sale") anywhere in a long page used to kill it before the LLM saw it.
  A negative term only rejects when there is no substantive positive signal.
"""
import re
import logging
from typing import List, Optional
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# A negative keyword only rejects when the positive signal is this weak. Two or
# more distinct opportunity terms outvote an incidental "airdrop"/"whitelist".
MIN_POSITIVE_HITS_OVERRIDING_NEGATIVE = 2


class KeywordFilter:
    """Fast text-based filter: checks content against keyword lists.

    Designed for HIGH RECALL (better to pass noise to the LLM than miss a signal).
    """

    def __init__(self, keywords_path: str = None):
        if keywords_path is None:
            keywords_path = Path(__file__).resolve().parent.parent.parent / "config" / "keywords.yaml"
        with open(keywords_path) as f:
            config = yaml.safe_load(f)

        self.keywords = config.get("keywords", {})
        self.flags = config.get("flags", {})
        self.case_sensitive = self.flags.get("case_sensitive", False)
        # Number of DISTINCT terms that must be present.
        self.min_hits = self.flags.get("min_keyword_hits", 1)

        self._compile_patterns()

    def _term_pattern(self, word: str):
        flags = 0 if self.case_sensitive else re.IGNORECASE
        # Word-ish boundaries so "grant" does not match "granted" inside an
        # unrelated word, while multi-word phrases keep working.
        return re.compile(r"(?<![0-9a-z])" + re.escape(word) + r"(?![0-9a-z])", flags)

    def _compile_patterns(self):
        self._term_patterns = {}
        for category, words in self.keywords.items():
            if category == "negative":
                continue
            self._term_patterns[category] = [
                (word, self._term_pattern(word)) for word in words
            ]

        neg_words = self.keywords.get("negative", [])
        flags = 0 if self.case_sensitive else re.IGNORECASE
        self._negative_pattern = re.compile(
            "|".join(re.escape(w) for w in neg_words), flags=flags
        ) if neg_words else None

    def matched_terms(self, text: str) -> List[str]:
        """Distinct listed terms present in the text."""
        if not text:
            return []
        hits: List[str] = []
        for patterns in self._term_patterns.values():
            for word, pattern in patterns:
                if pattern.search(text):
                    hits.append(word)
        return hits

    def has_negative_signal(self, text: str) -> bool:
        return bool(self._negative_pattern and self._negative_pattern.search(text or ""))

    def matches(self, text: str) -> bool:
        """Return True if text should pass to LLM classification."""
        if not text:
            return False

        hits = self.matched_terms(text)
        negative = self.has_negative_signal(text)

        if negative and len(hits) < MIN_POSITIVE_HITS_OVERRIDING_NEGATIVE:
            logger.debug("Rejected by negative keyword match (%d positive terms)", len(hits))
            return False

        passed = len(hits) >= self.min_hits
        if not passed:
            logger.debug(
                "Keyword filter: %d distinct term(s) < %d threshold", len(hits), self.min_hits
            )
        return passed

    def get_matched_categories(self, text: str) -> List[str]:
        """Return which categories were matched (for routing hints)."""
        matched = []
        for category, patterns in self._term_patterns.items():
            if any(pattern.search(text or "") for _word, pattern in patterns):
                matched.append(category)
        return matched
