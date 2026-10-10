import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.verifier.verifier import verify_opportunity


def test_verify_opportunity_l1_failure_degrades_and_is_not_stored_as_verified(monkeypatch) -> None:
    """Official metadata does not override L1 — L1 only lowers confidence.
    Only L3 (security APIs) can reject as fraud.

    `is_verified` is now strictly "fully corroborated": an item whose origin could
    not be anchored must not be persisted (and displayed) as verified.
    """
    monkeypatch.setattr(
        "src.verifier.verifier.origin_check",
        lambda source_url, source_name: {"passed": False, "reason": "domain not in global whitelist"},
    )
    monkeypatch.setattr(
        "src.verifier.verifier.cross_reference_check",
        lambda event_type, application_url, source_url, metadata: {"passed": True, "reason": "matched"},
    )
    monkeypatch.setattr(
        "src.verifier.verifier.security_api_check",
        lambda check_url: {"passed": True, "result": "clean", "reason": "clean"},
    )

    result = verify_opportunity(
        event_type="grant",
        source_url="https://grants.base.org/programs",
        application_url="https://apply.base.org/grant",
        source_name="base_grants",
        metadata={
            "chain": "base",
            "source_tier": "official",
            "official": True,
            "signal_type": "grant",
        },
    )

    assert result["verdict"] == "degraded"  # L1 failed → degraded, not verified
    assert result["is_verified"] is False  # not fraud, but not "verified" either
    assert result["verification_log"]["source_context"] == {
        "chain": "base",
        "source_tier": "official",
        "official": True,
        "signal_type": "grant",
    }
    assert result["verification_log"]["layers"]["origin_anchor"]["passed"] is False


def test_all_layers_passing_is_the_only_verified_verdict(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.verifier.verifier.origin_check",
        lambda source_url, source_name: {"passed": True, "reason": "domain_match:base.org"},
    )
    monkeypatch.setattr(
        "src.verifier.verifier.cross_reference_check",
        lambda event_type, application_url, source_url, metadata: {"passed": True, "reason": "matched"},
    )
    monkeypatch.setattr(
        "src.verifier.verifier.security_api_check",
        lambda check_url: {"passed": True, "result": "clean", "reason": "clean_by:goplus"},
    )

    result = verify_opportunity(
        event_type="grant",
        source_url="https://grants.base.org/programs",
        application_url="https://apply.base.org/grant",
    )

    assert result["verdict"] == "verified"
    assert result["is_verified"] is True


def test_unanswered_security_layer_is_unchecked_not_verified(monkeypatch) -> None:
    """No provider key configured used to report "all security checks passed"."""
    monkeypatch.setattr(
        "src.verifier.verifier.origin_check",
        lambda source_url, source_name: {"passed": True, "reason": "domain_match:base.org"},
    )
    monkeypatch.setattr(
        "src.verifier.verifier.cross_reference_check",
        lambda event_type, application_url, source_url, metadata: {"passed": True, "reason": "matched"},
    )
    monkeypatch.setattr(
        "src.verifier.verifier.security_api_check",
        lambda check_url: {
            "passed": True, "result": "unknown", "configured": False,
            "reason": "no_security_provider_answered",
        },
    )

    result = verify_opportunity(
        event_type="grant",
        source_url="https://grants.base.org/programs",
        application_url="https://apply.base.org/grant",
    )

    assert result["verdict"] == "unchecked"
    assert result["is_verified"] is False


def test_verify_opportunity_l3_failure_still_rejects_as_fraud(monkeypatch) -> None:
    """L3 (security API) is the only hard gate — phishing/malware = fraud."""
    monkeypatch.setattr(
        "src.verifier.verifier.origin_check",
        lambda source_url, source_name: {"passed": True, "reason": "domain_match:base.org"},
    )
    monkeypatch.setattr(
        "src.verifier.verifier.cross_reference_check",
        lambda event_type, application_url, source_url, metadata: {"passed": True, "reason": "matched"},
    )
    monkeypatch.setattr(
        "src.verifier.verifier.security_api_check",
        lambda check_url: {"passed": False, "reason": "phishing_detected"},
    )

    result = verify_opportunity(
        event_type="grant",
        source_url="https://fake-grants.scam/phish",
        application_url="https://fake-grants.scam/apply",
        source_name="unknown",
    )

    assert result["is_verified"] is False
    assert result["verdict"] == "fraud"
