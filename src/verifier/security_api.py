"""Layer 3: Third-party security API checks.

Integrates with GoPlus Security, CertiK Skynet, and ScamSniffer for domain
threat intelligence.

Result model — this used to be a binary ``passed`` flag that defaulted to True on
every failure path, which meant an unconfigured, rate-limited or timing-out
provider reported "all security checks passed" and the pipeline stamped the event
as verified. Each check now returns one of:

    clean     - the provider answered and found nothing
    malicious - the provider flagged the domain
    unknown   - no key, no answer, or an unusable answer

Only ``malicious`` blocks an opportunity. ``unknown`` never counts as a pass.
"""
import logging
from typing import Optional

import httpx

from config.settings import settings

logger = logging.getLogger(__name__)

RESULT_CLEAN = "clean"
RESULT_MALICIOUS = "malicious"
RESULT_UNKNOWN = "unknown"


def _result(status: str, detail, risk_level: str = "unknown") -> dict:
    return {
        "result": status,
        # `passed` is retained for callers that still read it, but it is now
        # strictly "not malicious" rather than "everything is fine".
        "passed": status != RESULT_MALICIOUS,
        "risk_level": risk_level,
        "detail": detail,
    }


GOPLUS_PHISHING_SITE_URL = "https://api.gopluslabs.io/api/v1/phishing_site"


def check_goplus_domain(domain: str) -> dict:
    """Check a domain against GoPlus Security's phishing-site API.

    The endpoint answers without a key (rate-limited); a configured key is sent
    for higher limits. The code used to call /api/v1/phishing/site (404) and only
    with a key, so no event was ever checked.
    """
    api_key = settings.GOPLUS_API_KEY
    headers = {"Authorization": api_key} if api_key else {}
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(GOPLUS_PHISHING_SITE_URL, params={"url": domain}, headers=headers)
            if resp.status_code != 200:
                return _result(RESULT_UNKNOWN, f"api_error_{resp.status_code}")
            data = resp.json()
            result = data.get("result", {})
            is_phishing = result.get("phishing_site", False) or result.get("malicious_address", False)

            if is_phishing:
                return _result(RESULT_MALICIOUS,
                               result.get("phishing_site_detail", "marked_as_phishing"),
                               risk_level="high")
            return _result(RESULT_CLEAN, result, risk_level="low")
    except Exception as e:
        logger.error(f"GoPlus API error: {e}")
        return _result(RESULT_UNKNOWN, f"api_error:{e}")


def check_cerik_domain(domain: str) -> dict:
    """Check a domain against CertiK Skynet."""
    api_key = settings.CERTIK_API_KEY
    if not api_key:
        return _result(RESULT_UNKNOWN, "certik_not_configured")

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(
                "https://api.certik.com/v1/skynet/domain",
                params={"domain": domain},
                headers={"X-API-KEY": api_key},
            )
            if resp.status_code != 200:
                return _result(RESULT_UNKNOWN, f"api_error_{resp.status_code}")
            data = resp.json()
            risk = data.get("risk_level", "unknown")
            if risk in ("critical", "high"):
                return _result(RESULT_MALICIOUS, data, risk_level=risk)
            if risk == "unknown":
                return _result(RESULT_UNKNOWN, data)
            return _result(RESULT_CLEAN, data, risk_level=risk)
    except Exception as e:
        logger.error(f"CertiK API error: {e}")
        return _result(RESULT_UNKNOWN, f"api_error:{e}")


def check_scamsniffer(domain: str) -> dict:
    """Check domain age / scam reputation via ScamSniffer."""
    api_key = settings.SCAMSNIFFER_API_KEY
    if not api_key:
        return _result(RESULT_UNKNOWN, "scamsniffer_not_configured")

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                "https://api.scamsniffer.io/v1/check",
                json={"url": f"https://{domain}"},
                headers={"X-API-KEY": api_key},
            )
            if resp.status_code != 200:
                return _result(RESULT_UNKNOWN, f"api_error_{resp.status_code}")
            data = resp.json()
            is_scam = data.get("scam", False)
            days_old = data.get("domain_age_days", None)

            if is_scam:
                return _result(RESULT_MALICIOUS, "marked_as_scam", risk_level="high")
            if days_old is not None and days_old < 7:
                # A brand-new domain is a review signal, not proof of fraud: a
                # legitimate new program can launch on a fresh domain. It must not
                # become a permanent fraud verdict.
                return _result(RESULT_UNKNOWN, f"domain_too_new:{days_old}d", risk_level="elevated")
            return _result(RESULT_CLEAN, data, risk_level="low")
    except Exception as e:
        logger.error(f"ScamSniffer API error: {e}")
        return _result(RESULT_UNKNOWN, f"api_error:{e}")


def security_api_check(url: str) -> dict:
    """Run all security API checks on a URL's domain.

    Returns {passed, result, reason, checks: [...], configured: bool}.
    ``configured`` is True when at least one provider can be consulted. GoPlus
    needs no key, so it always is.
    """
    checks: list[dict] = []
    outcome = {
        "layer": "security_api",
        "passed": True,
        "result": RESULT_UNKNOWN,
        "configured": True,
        "checks": checks,
    }

    if not url:
        outcome["reason"] = "no_url_to_check"
        return outcome

    from urllib.parse import urlparse
    try:
        domain = urlparse(url).hostname
    except Exception:
        outcome["reason"] = "invalid_url"
        return outcome

    if not domain:
        outcome["reason"] = "no_hostname"
        return outcome

    goplus = check_goplus_domain(domain)
    checks.append({"api": "goplus", **goplus})

    certik = check_cerik_domain(domain)
    checks.append({"api": "certik", **certik})

    ss = check_scamsniffer(domain)
    checks.append({"api": "scamsniffer", **ss})

    malicious = [c for c in checks if c.get("result") == RESULT_MALICIOUS]
    if malicious:
        outcome["passed"] = False
        outcome["result"] = RESULT_MALICIOUS
        outcome["reason"] = f"{malicious[0]['api']}:{malicious[0].get('detail', 'unknown')}"
        return outcome

    answered = [c for c in checks if c.get("result") == RESULT_CLEAN]
    if answered:
        outcome["result"] = RESULT_CLEAN
        outcome["reason"] = "clean_by:" + ",".join(c["api"] for c in answered)
    else:
        outcome["result"] = RESULT_UNKNOWN
        outcome["reason"] = "no_security_provider_answered"

    return outcome
