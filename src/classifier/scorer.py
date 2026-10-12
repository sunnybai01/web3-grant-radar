"""4D Scoring Matrix: evaluates commercial value of verified opportunities.

S_total = (S_ROI * 0.40) + (S_Reputation * 0.30) + (S_Timeliness * 0.20) + (S_Strategy * 0.10)

Scoring is done via LLM since it requires nuanced judgment about
funding amounts, reputation, and strategic context.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from config.settings import settings
from .llm_gateway import LLMGateway
from .prompts import SCORE_SYSTEM, SCORE_USER_TEMPLATE, current_date_label

logger = logging.getLogger(__name__)


class OpportunityScorer:
    """Scores verified opportunities across 4 dimensions using LLM + inline heuristics."""

    WEIGHTS = settings.SCORE_WEIGHTS  # {"roi": 0.40, "reputation": 0.30, "timeliness": 0.20, "strategy": 0.10}
    OFFICIAL_REPUTATION_BONUS = 1.0
    DISCOVERY_REPUTATION_PENALTY = 0.5
    DEGRADED_STRATEGY_PENALTY = 0.5

    def __init__(self, llm_gateway: LLMGateway):
        self.llm = llm_gateway

    def score(self, event_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Score an opportunity. Returns merged event_data with scoring fields.

        Falls back to heuristic scoring if LLM fails.
        """
        # Prepare prompt data
        deadline = event_data.get("deadline")
        deadline_str = str(deadline) if deadline else "not specified"

        prompt = SCORE_USER_TEMPLATE.format(
            today=current_date_label(),
            category=event_data.get("event_type", ""),
            title=event_data.get("title", ""),
            description=event_data.get("description", "")[:1000],
            deadline=deadline_str,
            amount=event_data.get("amount", "not specified"),
            ecosystem=event_data.get("ecosystem", ""),
            track=event_data.get("track", ""),
            platform=event_data.get("source_platform", ""),
            source_tier=event_data.get("source_tier", "unknown"),
            official=event_data.get("official", False),
            verification_verdict=event_data.get("verification_verdict", "unknown"),
        )

        result = self.llm.classify_structured(SCORE_SYSTEM, prompt)

        dimensions = self._extract_dimensions(result)
        if dimensions is not None:
            event_data.update(dimensions)
            event_data["final_score"] = self._weighted_total(dimensions)
            return self._apply_trust_adjustments(event_data)

        # Fallback: heuristic scoring
        logger.warning("LLM scoring failed, using heuristic fallback")
        return self._heuristic_score(event_data)

    @staticmethod
    def _coerce_score(value) -> Optional[float]:
        """Parse one model-supplied dimension score, or None when unusable."""
        if isinstance(value, bool) or value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value.strip())
            except ValueError:
                return None
        return None

    def _extract_dimensions(self, result) -> Optional[Dict[str, float]]:
        """Validate and clamp all four dimensions, or return None to fall back.

        The old check only tested key presence and then multiplied, so a null or
        string score raised a TypeError that aborted the whole run, and an
        out-of-range value (80) was stored as-is and produced a final_score of
        48.0 while the dashboard still rendered it as a normal score.
        """
        if not isinstance(result, dict) or not result:
            return None

        mapping = {
            "score_roi": "score_roi",
            "score_reputation": "score_reputation",
            "score_timeliness": "score_timeliness",
            "score_strategy": "score_strategy",
        }
        dimensions: Dict[str, float] = {}
        for key in mapping:
            if key not in result:
                logger.warning("Scoring response missing %s — using heuristic fallback", key)
                return None
            raw = self._coerce_score(result[key])
            if raw is None:
                logger.warning("Scoring response has unusable %s=%r — clamped out", key, result[key])
                continue
            if raw < 1.0 or raw > 10.0:
                logger.warning("Scoring response %s=%s outside 1-10 — clamped", key, raw)
            dimensions[key] = round(self._clamp_score(raw), 1)

        # A dimension we could not read at all falls back to the neutral midpoint
        # rather than dropping the whole scoring result.
        for key in mapping:
            dimensions.setdefault(key, 5.0)

        return dimensions

    def _weighted_total(self, dimensions: Dict[str, float]) -> float:
        total = (
            dimensions["score_roi"] * self.WEIGHTS["roi"]
            + dimensions["score_reputation"] * self.WEIGHTS["reputation"]
            + dimensions["score_timeliness"] * self.WEIGHTS["timeliness"]
            + dimensions["score_strategy"] * self.WEIGHTS["strategy"]
        )
        return round(total, 2)

    def _heuristic_score(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """Basic heuristic scoring when LLM fails."""
        amount = event_data.get("amount", "") or ""
        # event_type is stored lowercase ("grant"); compare case-insensitively so
        # these branches are actually reachable.
        event_type = str(event_data.get("event_type") or "").upper()
        ecosystem = event_data.get("ecosystem", "") or ""

        # ROI heuristic: try to parse amount
        score_roi = 5.0
        try:
            amount_lower = amount.lower().replace(",", "")
            # Extract numbers
            import re
            nums = re.findall(r'[\d,]+', amount_lower)
            if nums:
                max_val = max(int(n.replace(",", "")) for n in nums)
                if "eth" in amount_lower or "btc" in amount_lower:
                    max_val *= 3000  # rough conversion
                if max_val >= 100000:
                    score_roi = 9.0
                elif max_val >= 50000:
                    score_roi = 8.0
                elif max_val >= 20000:
                    score_roi = 7.0
                elif max_val >= 5000:
                    score_roi = 6.0
                elif max_val >= 1000:
                    score_roi = 5.0
                else:
                    score_roi = 3.0
        except Exception:
            pass

        # Reputation heuristic: known ecosystems score higher
        tier1 = {"ethereum", "solana", "sui", "base", "arbitrum", "optimism", "polygon", "stellar"}
        score_reputation = 8.0 if ecosystem.lower() in tier1 else 5.0

        # Timeliness heuristic: check deadline proximity
        score_timeliness = 7.0
        deadline = event_data.get("deadline")
        if deadline:
            try:
                if isinstance(deadline, str):
                    deadline = datetime.fromisoformat(deadline.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                days_left = (deadline - now).days
                if days_left <= 0:
                    score_timeliness = 1.0
                elif days_left <= 1:
                    score_timeliness = 3.0
                elif days_left <= 7:
                    score_timeliness = 5.0
                elif 14 <= days_left <= 30:
                    score_timeliness = 9.0
                else:
                    score_timeliness = 7.0
            except Exception:
                pass
        else:
            # No deadline — could be rolling, modest score
            score_timeliness = 5.0

        # Strategy heuristic: grants and hackathons tend to have more ecosystem value
        score_strategy = 6.0
        if event_type == "GRANT":
            score_strategy = 7.0
        elif event_type == "HACKATHON":
            score_strategy = 7.5

        final = (
            score_roi * self.WEIGHTS["roi"]
            + score_reputation * self.WEIGHTS["reputation"]
            + score_timeliness * self.WEIGHTS["timeliness"]
            + score_strategy * self.WEIGHTS["strategy"]
        )

        event_data["score_roi"] = round(score_roi, 1)
        event_data["score_reputation"] = round(score_reputation, 1)
        event_data["score_timeliness"] = round(score_timeliness, 1)
        event_data["score_strategy"] = round(score_strategy, 1)
        event_data["final_score"] = round(final, 2)
        return self._apply_trust_adjustments(event_data)

    def _apply_trust_adjustments(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply small source-trust adjustments after base scoring."""
        source_tier = str(event_data.get("source_tier") or "").lower()
        official = bool(event_data.get("official", source_tier == "official"))
        verification_verdict = str(event_data.get("verification_verdict") or "").lower()

        reputation = float(event_data.get("score_reputation") or 0.0)
        strategy = float(event_data.get("score_strategy") or 0.0)

        if official or source_tier == "official":
            reputation += self.OFFICIAL_REPUTATION_BONUS
        elif source_tier == "discovery":
            reputation -= self.DISCOVERY_REPUTATION_PENALTY

        if verification_verdict == "degraded":
            strategy -= self.DEGRADED_STRATEGY_PENALTY

        event_data["score_roi"] = round(self._clamp_score(float(event_data.get("score_roi") or 0.0)), 1)
        event_data["score_timeliness"] = round(
            self._clamp_score(float(event_data.get("score_timeliness") or 0.0)), 1
        )
        event_data["score_reputation"] = round(self._clamp_score(reputation), 1)
        event_data["score_strategy"] = round(self._clamp_score(strategy), 1)
        event_data["official"] = official
        event_data["trust_label"] = self._trust_label(source_tier, official, verification_verdict)

        final = (
            event_data["score_roi"] * self.WEIGHTS["roi"]
            + event_data["score_reputation"] * self.WEIGHTS["reputation"]
            + event_data["score_timeliness"] * self.WEIGHTS["timeliness"]
            + event_data["score_strategy"] * self.WEIGHTS["strategy"]
        )
        event_data["final_score"] = round(self._clamp_score(final), 2)
        return event_data

    @staticmethod
    def _clamp_score(value: float) -> float:
        return max(1.0, min(10.0, value))

    @staticmethod
    def _trust_label(source_tier: str, official: bool, verification_verdict: str) -> str:
        if (official or source_tier == "official") and verification_verdict == "verified":
            return "confirmed_official"
        if source_tier == "discovery" or verification_verdict == "degraded":
            return "discovery_review"
        return "verified_review"


def stars_from_score(score: float) -> str:
    """Convert a 1-10 score to star rating."""
    if score >= 9:
        return "⭐⭐⭐⭐⭐"
    elif score >= 8:
        return "⭐⭐⭐⭐"
    elif score >= 7:
        return "⭐⭐⭐"
    elif score >= 5:
        return "⭐⭐"
    else:
        return "⭐"
