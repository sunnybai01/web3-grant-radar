"""LLM summary extraction for improved L2 vector dedup.

Replaces raw title+description text with a structured summary before embedding.
Extracts: canonical_title, deadline, publish_date, location_type, ecosystem, summary.
"""
import json
import logging
from typing import Optional

from src.classifier.llm_gateway import LLMGateway

logger = logging.getLogger(__name__)

SUMMARY_EXTRACTION_PROMPT = """Extract structured metadata from this Web3 opportunity description.

Return ONLY a JSON object (no markdown, no backticks) with these keys:
- "canonical_title": a normalized title (remove emoji, hashtags, handle mentions, merge "by X" suffixes)
- "deadline": ISO 8601 date or null
- "publish_date": ISO 8601 date of when this was published (extract from context if possible) or null
- "location_type": "online" | "offline" | "hybrid" | "unknown"
- "ecosystem": which blockchain/ecosystem (ethereum, solana, arbitrum, etc.) or null
- "summary": one concise sentence (max 140 chars) summarizing the core opportunity

Content:
{content}

JSON:"""


def format_summary_text(s: dict) -> str:
    """Format extracted summary into embedding-friendly text."""
    parts = [
        s.get("canonical_title", ""),
        s.get("summary", ""),
        f"deadline:{s.get('deadline', 'none')}",
        f"location:{s.get('location_type', 'unknown')}",
        f"ecosystem:{s.get('ecosystem', 'unknown')}",
    ]
    return " | ".join(parts)


def raw_embedding_text(title: str, description: str) -> str:
    """Deterministic embedding text with no LLM call.

    Used for bulk re-indexing (startup reconciliation, post-reset backfill) where
    one summary request per Event is not worth the seconds it costs, and where the
    LLM being down must not leave the index empty.
    """
    return f"{title} {description}".strip()[:2000]


class LLMSummaryExtractor:
    """Extract structured summaries for dedup embedding.

    Falls back to raw text on any LLM failure — degrades gracefully.
    """

    def __init__(self):
        try:
            self._llm = LLMGateway()
            self._available = bool(self._llm._clients)
        except Exception as e:
            logger.warning(f"LLM gateway init failed, summary extraction disabled: {e}")
            self._llm = None
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def extract(self, title: str, description: str) -> Optional[dict]:
        """Call LLM to extract structured summary. Returns None on failure."""
        if not self._available or not self._llm:
            return None

        content = f"title: {title}\n\ndescription: {description}"[:3000]

        try:
            raw = self._llm.complete(
                system_prompt="You are a precise metadata extractor. Return ONLY valid JSON.",
                user_prompt=SUMMARY_EXTRACTION_PROMPT.format(content=content),
                json_mode=True,
                temperature=0.1,
                max_tokens=300,
            )
            if raw is None:
                return None
            raw = raw.strip()
            if raw.startswith("```"):
                lines = raw.split("\n")
                raw = "\n".join(lines[1:]) if lines[0].startswith("```") else raw
                if raw.endswith("```"):
                    raw = raw[:-3]
            return json.loads(raw)
        except Exception as e:
            logger.warning(f"LLM summary extraction failed: {e}")
            return None

    def get_embedding_text(self, title: str, description: str) -> str:
        """Get the best available text for embedding.

        Tries LLM summary first, falls back to raw title+description.
        """
        summary = self.extract(title, description)
        if summary:
            text = format_summary_text(summary)
            if text.strip():
                logger.debug(f"Using LLM summary for embedding: {text[:120]}...")
                return text

        # Fallback: raw text
        return raw_embedding_text(title, description)
