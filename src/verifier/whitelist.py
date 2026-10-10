"""Layer 1: Origin identity anchoring.

Verifies that a claimed event's domain or Twitter handle matches known official sources.
"""
import logging
from typing import Optional
from urllib.parse import urlparse

from .whitelist_data import OFFICIAL_DOMAINS, OFFICIAL_TWITTER_HANDLES

logger = logging.getLogger(__name__)

# Twitter handles are stored with their canonical casing ("ETHGlobal", "EF_ESP")
# while source names are lowercased ("twitter_ethglobal"). Comparing them
# case-sensitively labelled seven legitimate official accounts as degraded
# forever, so both sides are casefolded.
_FOLDED_HANDLES = {h.casefold() for h in OFFICIAL_TWITTER_HANDLES}


def check_domain(url: str) -> tuple[bool, str]:
    """Check if a URL's domain is in the official whitelist.

    Returns (is_verified, reason).
    """
    if not url:
        return False, "no_url_provided"

    try:
        hostname = urlparse(url).hostname
        if not hostname:
            return False, "invalid_url_no_hostname"
    except Exception:
        return False, "invalid_url_parse_error"

    # Exact match
    if hostname in OFFICIAL_DOMAINS:
        return True, f"domain_match:{hostname}"

    # Subdomain match — e.g. blog.ethereum.org → ethereum.org is parent
    parts = hostname.split(".")
    for i in range(1, len(parts)):
        parent = ".".join(parts[i:])
        if parent in OFFICIAL_DOMAINS:
            return True, f"subdomain_match:{parent}"

    return False, f"domain_not_in_whitelist:{hostname}"


def check_twitter_handle(handle: str) -> tuple[bool, str]:
    """Check if a Twitter handle is in the official whitelist.

    Returns (is_verified, reason).
    """
    if not handle:
        return False, "no_handle_provided"

    clean = handle.lstrip("@").strip()
    if clean.casefold() in _FOLDED_HANDLES:
        return True, f"twitter_handle_match:{clean}"

    return False, f"twitter_handle_not_in_whitelist:{clean}"


def origin_check(source_url: str, source_name: str = "") -> dict:
    """Run Layer 1 origin check.

    Returns a dict with `passed`, `reason`, and `detail`.
    """
    result = {
        "layer": "origin_anchor",
        "passed": False,
        "reason": "",
        "detail": {},
    }

    # Check URL domain
    domain_ok, domain_reason = check_domain(source_url)
    result["detail"]["domain_check"] = {"ok": domain_ok, "reason": domain_reason}

    if domain_ok:
        result["passed"] = True
        result["reason"] = domain_reason
        return result

    # If source_name looks like a Twitter handle, check that
    if source_name and source_name.startswith("twitter_"):
        handle = source_name.replace("twitter_", "")
        handle_ok, handle_reason = check_twitter_handle(handle)
        result["detail"]["twitter_check"] = {"ok": handle_ok, "reason": handle_reason}
        if handle_ok:
            result["passed"] = True
            result["reason"] = handle_reason

    if not result["passed"]:
        result["reason"] = domain_reason

    return result
