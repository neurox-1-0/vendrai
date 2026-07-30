"""The supplier controls VO-003 and VO-005 turn on.

Each test names the scenario it protects, because these thresholds are policy
and the next person to change one needs to know what it was for.
"""

from datetime import date
from decimal import Decimal

import pytest
from app.domain.supplier_controls import (
    check_banking_country,
    check_certificate_validity,
    check_data_processing_agreement,
    check_data_residency,
    check_spend_band,
    evaluate_supplier_controls,
)
from app.domain.tenant_config import TenantConfiguration

CONFIG = TenantConfiguration()
TODAY = date(2026, 7, 20)


def test_same_country_banking_is_clear():
    finding = check_banking_country(
        CONFIG, registered_country="LK", bank_country="LK"
    )
    assert finding.disposition == "CLEAR"


def test_cross_border_banking_is_flagged():
    """VO-003: registered in Singapore, banking in Hong Kong."""
    finding = check_banking_country(
        CONFIG, registered_country="SG", bank_country="HK"
    )
    assert finding.reason_code == "BANKING_COUNTRY_MISMATCH"
    assert finding.needs_attention


def test_an_approved_pairing_is_not_flagged():
    configuration = TenantConfiguration()
    configuration.jurisdiction.approved_bank_countries = ["SG"]
    finding = check_banking_country(
        configuration, registered_country="LK", bank_country="SG"
    )
    assert finding.disposition == "CLEAR"


def test_missing_country_evidence_is_unverified_not_clear():
    finding = check_banking_country(
        CONFIG, registered_country="LK", bank_country=None
    )
    assert finding.disposition == "UNVERIFIED"
    assert not finding.needs_attention


@pytest.mark.parametrize(
    ("spend", "expected_approvers"),
    [
        (Decimal("900000"), ["procurement_approver"]),
        (Decimal("3600000"), ["procurement_approver", "budget_owner"]),
        (
            Decimal("8400000"),
            ["procurement_director", "finance_controller"],
        ),
    ],
)
def test_spend_lands_in_the_configured_band(spend, expected_approvers):
    finding = check_spend_band(CONFIG, annual_spend=spend, currency="LKR")
    assert finding.evidence["required_approvers"] == expected_approvers


def test_spend_above_the_elevated_threshold_is_flagged():
    """VO-003 and VO-005 both expect "annual spend above LKR 5 million"."""
    finding = check_spend_band(
        CONFIG, annual_spend=Decimal("8400000"), currency="LKR"
    )
    assert finding.reason_code == "SPEND_ABOVE_ELEVATED_THRESHOLD"


def test_spend_just_at_the_threshold_is_not_elevated():
    finding = check_spend_band(
        CONFIG, annual_spend=Decimal("5000000"), currency="LKR"
    )
    assert finding.disposition == "CLEAR"


def test_a_foreign_currency_spend_is_unverified_rather_than_converted():
    """Converting here would hide an invented exchange rate inside a control."""
    finding = check_spend_band(
        CONFIG, annual_spend=Decimal("50000"), currency="USD"
    )
    assert finding.disposition == "UNVERIFIED"
    assert finding.reason_code == "SPEND_CURRENCY_MISMATCH"


def test_data_stored_outside_the_home_country_is_flagged():
    """VO-003: "data stored outside Sri Lanka"."""
    finding = check_data_residency(
        CONFIG,
        data_access_declared=True,
        data_stored_outside_country=True,
    )
    assert finding.reason_code == "DATA_STORED_OUTSIDE_APPROVED_LOCATION"


def test_no_data_access_makes_residency_irrelevant():
    finding = check_data_residency(
        CONFIG, data_access_declared=False, data_stored_outside_country=None
    )
    assert finding.disposition == "CLEAR"


def test_data_access_with_no_residency_answer_is_unverified():
    finding = check_data_residency(
        CONFIG, data_access_declared=True, data_stored_outside_country=None
    )
    assert finding.disposition == "UNVERIFIED"
    assert finding.reason_code == "DATA_RESIDENCY_UNSTATED"


def test_declared_unavailable_dpa_is_flagged():
    """VO-003: "data processing agreement unavailable"."""
    finding = check_data_processing_agreement(
        data_access_declared=True,
        agreement_available=False,
        agreement_document_present=False,
    )
    assert finding.reason_code == "DPA_UNAVAILABLE"


def test_a_submitted_dpa_satisfies_the_control():
    finding = check_data_processing_agreement(
        data_access_declared=True,
        agreement_available=None,
        agreement_document_present=True,
    )
    assert finding.disposition == "CLEAR"


def test_data_access_with_no_dpa_answer_at_all_is_unverified():
    finding = check_data_processing_agreement(
        data_access_declared=True,
        agreement_available=None,
        agreement_document_present=False,
    )
    assert finding.disposition == "UNVERIFIED"
    assert finding.reason_code == "DPA_UNVERIFIED"


def test_expired_certificate_is_flagged():
    """VO-003: the insurance certificate expired on 31 August 2025."""
    finding = check_certificate_validity(
        control="insurance_validity",
        valid_from=date(2024, 9, 1),
        valid_to=date(2025, 8, 31),
        as_of=TODAY,
        label="insurance certificate",
    )
    assert finding.reason_code == "CERTIFICATE_EXPIRED"
    assert "2025-08-31" in finding.summary


def test_current_certificate_is_clear():
    finding = check_certificate_validity(
        control="insurance_validity",
        valid_from=date(2026, 1, 1),
        valid_to=date(2026, 12, 31),
        as_of=TODAY,
        label="insurance certificate",
    )
    assert finding.disposition == "CLEAR"


def test_certificate_with_no_stated_expiry_is_unverified():
    finding = check_certificate_validity(
        control="insurance_validity",
        valid_from=None,
        valid_to=None,
        as_of=TODAY,
        label="insurance certificate",
    )
    assert finding.disposition == "UNVERIFIED"


def test_vo_003_produces_every_expected_control_finding():
    result = evaluate_supplier_controls(
        CONFIG,
        registered_country="SG",
        bank_country="HK",
        annual_spend=Decimal("8400000"),
        spend_currency="LKR",
        data_access_declared=True,
        data_stored_outside_country=True,
        dpa_available=False,
        dpa_document_present=False,
        insurance_valid_from=date(2024, 9, 1),
        insurance_valid_to=date(2025, 8, 31),
        tax_certificate_valid_to=None,
        as_of=TODAY,
    )
    assert set(result.reason_codes) >= {
        "BANKING_COUNTRY_MISMATCH",
        "SPEND_ABOVE_ELEVATED_THRESHOLD",
        "DATA_STORED_OUTSIDE_APPROVED_LOCATION",
        "DPA_UNAVAILABLE",
        "CERTIFICATE_EXPIRED",
    }
    assert result.disposition == "ATTENTION"


def test_vo_001_produces_no_control_findings():
    result = evaluate_supplier_controls(
        CONFIG,
        registered_country="LK",
        bank_country="LK",
        annual_spend=Decimal("3600000"),
        spend_currency="LKR",
        data_access_declared=False,
        data_stored_outside_country=False,
        dpa_available=None,
        dpa_document_present=False,
        insurance_valid_from=date(2026, 1, 1),
        insurance_valid_to=date(2026, 12, 31),
        tax_certificate_valid_to=date(2027, 1, 14),
        as_of=TODAY,
    )
    assert result.reason_codes == []
    assert result.disposition == "CLEAR"
