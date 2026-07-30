"""Interpreting the external risk provider's verdicts.

The seeded fixture deliberately includes an UNAVAILABLE vendor so the
fail-closed path is exercised on a real case (VO-004). These tests pin the rule
that makes that meaningful: unavailable never reads as clear.
"""

from app.services.risk_screening import interpret, unavailable


def test_a_clean_vendor_is_clear():
    result = interpret(
        {
            "sanctions": "CLEAR",
            "adverse_media": "NO MATERIAL MATCH",
            "country_risk": "LOW",
        }
    )
    assert result.disposition == "CLEAR"
    assert result.reason_codes == []


def test_an_adverse_media_hit_requires_review():
    """VO-005: "possible adverse-media name match"."""
    result = interpret(
        {
            "sanctions": "CLEAR",
            "adverse_media": "POSSIBLE NAME MATCH - REVIEW",
            "country_risk": "LOW",
        }
    )
    assert result.disposition == "REVIEW_REQUIRED"
    assert "ADVERSE_MEDIA_POSSIBLE_MATCH" in result.reason_codes


def test_an_unavailable_check_is_never_a_pass():
    """VO-004: Crescent Stationery Traders returns sanctions UNAVAILABLE."""
    result = interpret(
        {
            "sanctions": "UNAVAILABLE",
            "adverse_media": "NOT RUN",
            "country_risk": "LOW",
        }
    )
    assert result.disposition == "UNAVAILABLE"
    assert "RISK_SERVICE_UNAVAILABLE" in result.reason_codes


def test_an_unknown_vendor_is_unavailable_not_clear():
    result = interpret(
        {
            "sanctions": "UNAVAILABLE",
            "adverse_media": "NOT RUN",
            "country_risk": "UNKNOWN",
            "unknown_vendor": True,
        }
    )
    assert result.disposition == "UNAVAILABLE"


def test_unavailable_outranks_an_otherwise_clean_response():
    """A provider that could not run sanctions has not cleared the supplier."""
    result = interpret(
        {
            "sanctions": "UNAVAILABLE",
            "adverse_media": "NO MATERIAL MATCH",
            "country_risk": "LOW",
        }
    )
    assert result.disposition == "UNAVAILABLE"


def test_high_country_risk_is_reported():
    result = interpret(
        {
            "sanctions": "CLEAR",
            "adverse_media": "NO MATERIAL MATCH",
            "country_risk": "HIGH",
        }
    )
    assert "HIGH_COUNTRY_RISK" in result.reason_codes
    assert result.disposition == "REVIEW_REQUIRED"


def test_medium_country_risk_alone_does_not_escalate():
    """VO-003's supplier is MEDIUM; its escalation comes from other controls."""
    result = interpret(
        {
            "sanctions": "CLEAR",
            "adverse_media": "NO MATERIAL MATCH",
            "country_risk": "MEDIUM",
        }
    )
    assert result.disposition == "CLEAR"


def test_a_transport_failure_produces_an_unavailable_result():
    result = unavailable("RISK_SERVICE_TIMEOUT")
    assert result.disposition == "UNAVAILABLE"
    assert result.error_code == "RISK_SERVICE_TIMEOUT"
    assert "RISK_SERVICE_UNAVAILABLE" in result.reason_codes
