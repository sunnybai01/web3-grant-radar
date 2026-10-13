"""Layer 2 cross-reference must actually run.

The pipeline passes event_type in lowercase ("grant") while the check compared
against "GRANT"/"HACKATHON", so all 70 events recorded
no_cross_ref_checks_applicable and the layer never ran.
"""
import sys
from pathlib import Path

import httpx

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.verifier import cross_reference
from src.verifier.cross_reference import cross_reference_check


def _client(handler):
    real = httpx.Client
    return lambda **kwargs: real(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_lowercase_event_types_are_checked(monkeypatch) -> None:
    monkeypatch.setattr(cross_reference.httpx, "Client", _client(lambda request: httpx.Response(200)))

    result = cross_reference_check("grant", "https://base.org/apply", "https://x.com/base/status/1")

    assert result["passed"] is True
    assert result["reason"] == "application_url_reachable"


def test_a_site_that_rejects_head_is_retried_with_get(monkeypatch) -> None:
    """Many sites answer HEAD with 405 or 403 although the page is up."""
    def handler(request):
        return httpx.Response(405 if request.method == "HEAD" else 200)
    monkeypatch.setattr(cross_reference.httpx, "Client", _client(handler))

    result = cross_reference_check("hackathon", "https://hackathon.example/apply", "")

    assert result["passed"] is True
    assert result["reason"] == "application_url_reachable"


def test_a_missing_page_still_fails(monkeypatch) -> None:
    monkeypatch.setattr(cross_reference.httpx, "Client", _client(lambda request: httpx.Response(404)))

    result = cross_reference_check("grant", "https://base.org/gone", "")

    assert result["passed"] is False
    assert result["reason"] == "url_returned_404"
