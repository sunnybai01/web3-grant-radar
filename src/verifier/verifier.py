"""Zero-trust verification orchestrator — runs all three layers sequentially.

Verification strategy (content-first, not domain-whitelist):
- Layer 1 (origin anchor): checks domain/handle against known-good registry.
  Degrades confidence but does NOT reject — domains not in the registry
  are simply unknown, not fraudulent.
- Layer 2 (cross-reference): looks for corroborating evidence on GitHub,
  DoraHacks, Devpost. Degrades confidence on failure.
- Layer 3 (security API): GoPlus / CertiK / ScamSniffer threat intelligence.
  THIS is the only hard rejection gate — actual phishing/scam detection.

A verification is "verified" only when L1 anchors the origin, L2 corroborates the
opportunity, and a security provider actually answered. L1/L2 failures and an
unanswered security layer produce "degraded"/"unverified" — which still reach the
scorer, but are never stored as verified.
"""
import logging
from typing import Dict, Any

from .whitelist import origin_check
from .cross_reference import cross_reference_check
from .security_api import security_api_check

logger = logging.getLogger(__name__)


def _build_source_context(metadata: dict | None) -> Dict[str, Any]:
    metadata = metadata or {}
    source_tier = metadata.get("source_tier")
    official = bool(metadata.get("official", source_tier == "official"))
    return {
        "chain": metadata.get("chain"),
        "source_tier": source_tier,
        "official": official,
        "signal_type": metadata.get("signal_type"),
    }


class Verifier:
    """Runs the three-layer zero-trust verification pipeline.

    Only Layer 3 (security API threat intel) can reject as fraud.
    L1/L2 provide confidence signals but are non-fatal.

    Usage:
        v = Verifier()
        result = v.verify(event_type="BOUNTY", source_url="...", application_url="...")
        if result["verdict"] != "fraud":
            # proceed to scoring (may be "verified" or "degraded")
    """

    def verify(
        self,
        event_type: str,
        source_url: str = "",
        application_url: str = "",
        source_name: str = "",
        metadata: dict = None,
    ) -> Dict[str, Any]:
        """Run the full verification pipeline.

        Returns a dict with:
          - is_verified: bool (true unless L3 flags as fraud)
          - verification_log: dict with per-layer results
          - verdict: "verified" | "degraded" | "fraud"
        """
        verification_log = {
            "layers": {},
            "verdict": "degraded",
        }
        source_context = _build_source_context(metadata)
        verification_log["source_context"] = source_context

        # ---- Layer 1: Origin Identity Anchoring ----
        # Non-fatal: only degrades confidence, never rejects.
        l1 = origin_check(source_url, source_name)
        verification_log["layers"]["origin_anchor"] = l1

        # ---- Layer 2: Cross-Reference ----
        l2 = cross_reference_check(
            event_type, application_url, source_url, metadata
        )
        verification_log["layers"]["cross_reference"] = l2
        # L2 failure is non-fatal — it degrades confidence but doesn't reject

        # ---- Layer 3: Security API Checks (THE ONLY HARD GATE) ----
        # GoPlus / CertiK / ScamSniffer — actual phishing/scam detection.
        # A provider that is unconfigured, rate-limited or broken reports
        # "unknown", which is never treated as a pass.
        check_url = application_url or source_url
        l3 = security_api_check(check_url)
        verification_log["layers"]["security_api"] = l3

        if l3.get("result") == "malicious" or not l3["passed"]:
            verification_log["verdict"] = "fraud"
            return {
                "is_verified": False,
                "verification_log": verification_log,
                "verdict": "fraud",
            }

        # L3 found nothing wrong. Confidence depends on L1/L2 and on whether a
        # security provider actually answered.
        security_answered = l3.get("result") == "clean"
        if l1["passed"] and l2.get("passed", False) and security_answered:
            verdict = "verified"
        elif not security_answered:
            # No provider was consulted (no keys configured) or none answered.
            # That is "we did not check" and must stay distinct from "we checked
            # and have doubts" so operators can act on the right one.
            verdict = "unchecked"
        else:
            verdict = "degraded"
        verification_log["verdict"] = verdict

        return {
            # Only a fully corroborated item is persisted as verified. "degraded"
            # and "unchecked" still flow to scoring, but the dashboard/DB must not
            # present them as verified.
            "is_verified": verdict == "verified",
            "verification_log": verification_log,
            "verdict": verdict,
        }


# Module-level singleton
_verifier = Verifier()


def verify_opportunity(
    event_type: str,
    source_url: str = "",
    application_url: str = "",
    source_name: str = "",
    metadata: dict = None,
) -> Dict[str, Any]:
    return _verifier.verify(
        event_type=event_type,
        source_url=source_url,
        application_url=application_url,
        source_name=source_name,
        metadata=metadata,
    )
