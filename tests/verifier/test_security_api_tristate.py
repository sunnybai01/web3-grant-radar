"""Security API tri-state behaviour.

Production evidence: with all three provider keys empty, `security_api_check`
returned passed=True / reason="all_security_checks_passed", the fraud branch was
unreachable, and every event was stored as verified.
"""
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.verifier import security_api
from src.verifier.security_api import (
    RESULT_CLEAN,
    RESULT_MALICIOUS,
    RESULT_UNKNOWN,
    security_api_check,
)


def _blank_keys(monkeypatch):
    monkeypatch.setattr(security_api.settings, "GOPLUS_API_KEY", "", raising=False)
    monkeypatch.setattr(security_api.settings, "CERTIK_API_KEY", "", raising=False)
    monkeypatch.setattr(security_api.settings, "SCAMSNIFFER_API_KEY", "", raising=False)


def _forbid_network(monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("no provider should be called")

    monkeypatch.setattr(security_api.httpx, "Client", explode)


@pytest.fixture(autouse=True)
def _no_real_provider_calls(monkeypatch):
    """GoPlus needs no key, so an unstubbed test would call the real API."""
    _forbid_network(monkeypatch)


def test_no_answer_yields_unknown_not_clean(monkeypatch) -> None:
    _blank_keys(monkeypatch)
    _forbid_network(monkeypatch)

    outcome = security_api_check("https://free-eth-airdrop-claim.xyz/apply")

    assert outcome["result"] == RESULT_UNKNOWN
    assert outcome["reason"] == "no_security_provider_answered"
    # `passed` still means "not malicious", but it must never be read as verified.
    assert outcome["passed"] is True


class _GoPlusClient:
    """Stands in for httpx.Client; records the request and answers like GoPlus."""

    calls = []

    def __init__(self, phishing_site=0, **kwargs):
        self.phishing_site = phishing_site

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, params=None, headers=None):
        _GoPlusClient.calls.append((url, params, headers or {}))
        import httpx
        return httpx.Response(200, json={"code": 1, "message": "OK",
                                         "result": {"website_contract_security": [], "phishing_site": self.phishing_site}})


def test_goplus_answers_without_a_key_at_its_phishing_site_endpoint(monkeypatch) -> None:
    """The code called /api/v1/phishing/site (404) and only with a key; the documented
    /api/v1/phishing_site endpoint answers without one, so no event was ever checked."""
    _blank_keys(monkeypatch)
    _GoPlusClient.calls = []
    monkeypatch.setattr(security_api.httpx, "Client", lambda **kw: _GoPlusClient(phishing_site=0))

    outcome = security_api_check("https://ethglobal.com/events/mumbai")

    url, params, headers = _GoPlusClient.calls[0]
    assert url == "https://api.gopluslabs.io/api/v1/phishing_site"
    assert params == {"url": "ethglobal.com"}
    assert "Authorization" not in headers
    assert outcome["result"] == RESULT_CLEAN
    assert outcome["reason"] == "clean_by:goplus"


def test_goplus_flags_a_phishing_site(monkeypatch) -> None:
    _blank_keys(monkeypatch)
    monkeypatch.setattr(security_api.httpx, "Client", lambda **kw: _GoPlusClient(phishing_site=1))

    outcome = security_api_check("https://free-eth-airdrop-claim.xyz/apply")

    assert outcome["result"] == RESULT_MALICIOUS
    assert outcome["passed"] is False


def test_malicious_provider_blocks(monkeypatch) -> None:
    _blank_keys(monkeypatch)
    monkeypatch.setattr(security_api.settings, "SCAMSNIFFER_API_KEY", "k", raising=False)
    monkeypatch.setattr(
        security_api, "check_scamsniffer",
        lambda domain: {"result": RESULT_MALICIOUS, "passed": False, "risk_level": "high",
                        "detail": "marked_as_scam"},
    )

    outcome = security_api_check("https://scam.example/apply")

    assert outcome["result"] == RESULT_MALICIOUS
    assert outcome["passed"] is False
    assert outcome["reason"].startswith("scamsniffer:")


def test_clean_provider_reports_clean(monkeypatch) -> None:
    _blank_keys(monkeypatch)
    monkeypatch.setattr(security_api.settings, "GOPLUS_API_KEY", "k", raising=False)
    monkeypatch.setattr(
        security_api, "check_goplus_domain",
        lambda domain: {"result": RESULT_CLEAN, "passed": True, "risk_level": "low", "detail": {}},
    )

    outcome = security_api_check("https://build.avax.network/grants")

    assert outcome["result"] == RESULT_CLEAN
    assert outcome["reason"] == "clean_by:goplus"


def test_provider_error_is_unknown_not_a_pass(monkeypatch) -> None:
    """A 429/500/timeout must not convert a phishing domain into "clean"."""
    _blank_keys(monkeypatch)
    monkeypatch.setattr(security_api.settings, "GOPLUS_API_KEY", "k", raising=False)
    monkeypatch.setattr(
        security_api, "check_goplus_domain",
        lambda domain: {"result": RESULT_UNKNOWN, "passed": True, "risk_level": "unknown",
                        "detail": "api_error_429"},
    )

    outcome = security_api_check("https://build.avax.network/grants")

    assert outcome["result"] == RESULT_UNKNOWN
    assert outcome["configured"] is True


def test_missing_or_invalid_url_is_unknown(monkeypatch) -> None:
    _blank_keys(monkeypatch)

    assert security_api_check("")["result"] == RESULT_UNKNOWN
    assert security_api_check("not a url")["result"] == RESULT_UNKNOWN


def test_new_domain_is_elevated_not_malicious(monkeypatch) -> None:
    """A <7-day-old domain is a review signal; a real new program can use one."""
    monkeypatch.setattr(security_api.settings, "SCAMSNIFFER_API_KEY", "k", raising=False)

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"scam": False, "domain_age_days": 3}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            return FakeResponse()

    monkeypatch.setattr(security_api.httpx, "Client", FakeClient)

    result = security_api.check_scamsniffer("brand-new.example")

    assert result["result"] == RESULT_UNKNOWN
    assert result["risk_level"] == "elevated"
    assert result["passed"] is True  # unknown must not read as malicious
