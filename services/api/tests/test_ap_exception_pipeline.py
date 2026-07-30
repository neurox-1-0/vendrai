from decimal import Decimal

from app.domain.invoice_checks import (
    check_arithmetic,
    check_currency_consistency,
    evaluate_price_tolerance,
    evaluate_tax_rate,
    find_quantity_overruns,
)
from app.domain.tenant_config import TenantConfiguration
from app.workers.invoice_agent import check_missing_po

CONFIG = TenantConfiguration()


def test_missing_po_detection():
    extracted_no_po = {"invoice_number": "INV-100", "po_reference": None}
    all_docs_no_po = []
    po_data_empty = {"lines": {}}
    assert check_missing_po(extracted_no_po, all_docs_no_po, po_data_empty) is True

    po_data_present = {"lines": {1: {"description": "Item 1"}}}
    assert check_missing_po(extracted_no_po, all_docs_no_po, po_data_present) is False


def test_variance_within_both_limits_is_accepted():
    result = evaluate_price_tolerance(
        CONFIG,
        variance_amount=Decimal("1000"),
        variance_percent=Decimal("1.5"),
    )
    assert result.disposition == "WITHIN_TOLERANCE"
    assert result.reason_codes == []


def test_ap_002_price_variance_exceeds_the_configured_tolerance():
    """AP-002: 7.02% against a configured 2% tolerance."""
    result = evaluate_price_tolerance(
        CONFIG,
        variance_amount=Decimal("80000"),
        variance_percent=Decimal("7.02"),
    )
    assert result.disposition == "EXCEEDS_TOLERANCE"
    assert result.reason_codes == ["EXCEEDS_TOLERANCE"]
    assert "7.02% exceeds the 2% tolerance" in result.summary


def test_a_small_percentage_can_still_breach_the_absolute_cap():
    """AP-001 §3 requires both conditions, not either."""
    result = evaluate_price_tolerance(
        CONFIG,
        variance_amount=Decimal("40000"),
        variance_percent=Decimal("1.0"),
    )
    assert result.disposition == "EXCEEDS_TOLERANCE"
    assert "cap" in result.summary


def test_tolerances_come_from_configuration_not_constants():
    relaxed = TenantConfiguration()
    relaxed.invoice_tolerances.price_variance_percent = Decimal("10")
    relaxed.invoice_tolerances.price_variance_amount = Decimal("1000000")
    result = evaluate_price_tolerance(
        relaxed,
        variance_amount=Decimal("80000"),
        variance_percent=Decimal("7.02"),
    )
    assert result.disposition == "WITHIN_TOLERANCE"


def test_ap_003_quantity_overrun_is_reported_with_both_figures():
    """AP-003: 50 invoiced against 40 received."""
    overruns = find_quantity_overruns(
        [
            {
                "invoice_line": {"line_number": 1, "quantity": 50},
                "grn_line": {"received": 40},
            }
        ]
    )
    assert len(overruns) == 1
    assert overruns[0].invoiced == Decimal("50")
    assert overruns[0].received == Decimal("40")
    assert "50 exceeds accepted receipt quantity 40" in overruns[0].summary


def test_invoicing_at_or_below_the_receipt_is_not_an_overrun():
    assert (
        find_quantity_overruns(
            [
                {
                    "invoice_line": {"line_number": 1, "quantity": 40},
                    "grn_line": {"received": 40},
                }
            ]
        )
        == []
    )


def test_ap_005_tax_rate_is_compared_against_the_configured_reference():
    """AP-005: "invoice tax rate is 15 percent while configured reference is 18"."""
    result = evaluate_tax_rate(
        CONFIG,
        invoice_rate=Decimal("15"),
        jurisdiction="LK",
        invoice_date_iso="2026-07-15",
    )
    assert result.disposition == "MISMATCH"
    assert result.reason_codes == ["TAX_MISMATCH"]
    assert "15 percent" in result.summary
    assert "18 percent" in result.summary


def test_a_matching_tax_rate_passes():
    result = evaluate_tax_rate(
        CONFIG,
        invoice_rate=Decimal("18"),
        jurisdiction="LK",
        invoice_date_iso="2026-07-15",
    )
    assert result.disposition == "MATCH"


def test_an_unconfigured_jurisdiction_is_unverified_not_a_pass():
    result = evaluate_tax_rate(
        CONFIG,
        invoice_rate=Decimal("18"),
        jurisdiction="SG",
        invoice_date_iso="2026-07-15",
    )
    assert result.disposition == "UNVERIFIED"
    assert result.reason_codes == ["TAX_POLICY_UNVERIFIED"]


def test_an_invoice_with_no_stated_rate_is_unverified_not_zero():
    result = evaluate_tax_rate(
        CONFIG,
        invoice_rate=None,
        jurisdiction="LK",
        invoice_date_iso="2026-07-15",
    )
    assert result.disposition == "UNVERIFIED"


def test_a_rate_effective_later_does_not_apply_to_an_earlier_invoice():
    result = evaluate_tax_rate(
        CONFIG,
        invoice_rate=Decimal("18"),
        jurisdiction="LK",
        invoice_date_iso="2025-06-01",
    )
    assert result.disposition == "UNVERIFIED"


def test_a_reconciling_invoice_passes_arithmetic():
    result = check_arithmetic(
        line_items=[{"amount": 1250000.00}],
        tax_amount=Decimal("225000.00"),
        stated_total=Decimal("1475000.00"),
    )
    assert result.reconciles is True
    assert result.reason_codes == []


def test_arithmetic_inconsistency_is_surfaced():
    """Catches a mis-extraction before it becomes a wrong three-way match."""
    result = check_arithmetic(
        line_items=[{"amount": 1250000.00}],
        tax_amount=Decimal("225000.00"),
        stated_total=Decimal("1000000.00"),
    )
    assert result.reconciles is False
    assert result.reason_codes == ["INVOICE_ARITHMETIC_INCONSISTENT"]
    assert "cannot be trusted" in result.summary


def test_rounding_across_lines_does_not_trip_the_arithmetic_check():
    result = check_arithmetic(
        line_items=[{"amount": 100.005}, {"amount": 200.004}],
        tax_amount=Decimal("54.00"),
        stated_total=Decimal("354.00"),
    )
    assert result.reconciles is True


def test_currency_disagreement_is_flagged():
    assert check_currency_consistency(
        invoice_currency="USD", po_currency="LKR"
    ) == ["CURRENCY_MISMATCH"]
    assert check_currency_consistency(invoice_currency="LKR", po_currency="LKR") == []
    assert check_currency_consistency(invoice_currency="LKR", po_currency=None) == []
