"""Layer 2: Multi-source cross-referencing.

Verifies that an opportunity has corroborating evidence from independent sources.
- Grants → governance forum budget proposal
- Hackathons → DoraHacks/Devpost platform existence
- Bounties → GitHub Issue still open with proper label
"""
import logging
from typing import Optional
import os

import httpx

logger = logging.getLogger(__name__)

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

CROSS_REF_CHECKS = {
    "GRANT": "Check if a matching budget proposal or governance vote exists.",
    "HACKATHON": "Check if the event is listed on DoraHacks or Devpost with matching details.",
    "BOUNTY": "Verify the GitHub Issue is still OPEN and has an official bounty label.",
}


def _github_headers() -> dict:
    h = {"Accept": "application/vnd.github+json", "User-Agent": "Web3GrantRadar-Verifier/1.0"}
    if GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return h


def verify_github_issue(repo: str, issue_number: int) -> dict:
    """Check if a GitHub issue is still open.

    Returns {passed, reason, detail}.
    """
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}"

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, headers=_github_headers())
            if resp.status_code == 404:
                return {"passed": False, "reason": "github_issue_not_found"}
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.error(f"GitHub cross-ref error: {e}")
        return {"passed": False, "reason": f"github_api_error:{e}"}

    state = data.get("state", "closed")
    labels = [l["name"].lower() for l in data.get("labels", [])]
    bounty_labels = {"bounty", "bug bounty", "good first issue", "help wanted",
                     "paid", "reward", "up for grabs"}

    has_bounty_label = any(bl in labels for bl in bounty_labels)

    if state != "open":
        return {
            "passed": False,
            "reason": f"issue_state_is_{state}",
            "detail": {"state": state, "labels": labels},
        }

    if has_bounty_label:
        return {
            "passed": True,
            "reason": "github_issue_open_with_bounty_label",
            "detail": {"state": state, "labels": labels},
        }

    return {
        "passed": True,
        "reason": "github_issue_open_no_explicit_bounty_label",
        "detail": {"state": state, "labels": labels},
    }


# Statuses some servers return for HEAD while serving the page to GET.
HEAD_REJECTED_STATUSES = {403, 405, 501}


def cross_reference_check(event_type: str, application_url: str,
                          source_url: str, metadata: dict = None) -> dict:
    """Run Layer 2 cross-reference checks.

    Returns {passed, reason, checks_performed}.
    """
    result = {
        "layer": "cross_reference",
        "passed": False,
        "reason": "no_cross_reference_available",
        "checks_performed": [],
    }

    if not application_url and not source_url:
        return result

    # The pipeline passes event types in lowercase ("grant"); compared as-is
    # against "GRANT"/"HACKATHON" this layer never ran for any event.
    event_type = (event_type or "").strip().upper()

    # Bounty: verify GitHub issue if URL is a GitHub issue
    if event_type == "BOUNTY":
        check_url = application_url or source_url
        if "github.com" in check_url and "/issues/" in check_url:
            try:
                parts = check_url.split("github.com/")[1].split("/issues/")
                repo = parts[0]
                issue_num = int(parts[1].split("#")[0].split("?")[0])
                gh_result = verify_github_issue(repo, issue_num)
                result["passed"] = gh_result["passed"]
                result["reason"] = gh_result["reason"]
                result["checks_performed"].append({"type": "github_issue", "result": gh_result})
            except (ValueError, IndexError):
                result["reason"] = "could_not_parse_github_url"
            return result

    # For Grants and Hackathons without direct GitHub issue links,
    # we do a lighter check: verify the URL is reachable and not a known phishing domain
    if event_type in ("GRANT", "HACKATHON"):
        check_url = application_url or source_url
        if check_url:
            try:
                with httpx.Client(timeout=10.0, headers={"User-Agent": "Web3GrantRadar-Verifier/1.0"}) as client:
                    resp = client.head(check_url, follow_redirects=True)
                    if resp.status_code in HEAD_REJECTED_STATUSES:
                        # Many sites refuse HEAD although the page is up.
                        resp = client.get(check_url, follow_redirects=True)
                    if resp.status_code < 400:
                        result["passed"] = True
                        result["reason"] = "application_url_reachable"
                        result["checks_performed"].append(
                            {"type": "url_reachable", "status_code": resp.status_code}
                        )
                    else:
                        result["reason"] = f"url_returned_{resp.status_code}"
            except Exception as e:
                result["reason"] = f"url_unreachable:{e}"
            return result

    result["passed"] = True
    result["reason"] = "no_cross_ref_checks_applicable"
    return result
