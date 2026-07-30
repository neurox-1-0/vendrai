"""Deterministic invoice checks driven by tenant configuration.

Three things live here that previously did not exist, or existed as constants:

* **Tolerance evaluation** against the tenant's configured percentage *and*
  absolute cap. AP-001 §3 requires both to hold; a 1% variance on a large
  order can still exceed the cap.
* **A configured tax reference rate.** The tax check used to compare the
  invoice against the purchase order, which only detects a disagreement
  between two supplier-influenced documents. AP-005 expects the comparison to
  be against "the configured reference", and phrasing it that way is doing
  real work: the reference is the tenant's, not the supplier's.
* **Arithmetic reconciliation.** Cheap, and high value: it catches a large
  class of extraction errors before they reach matching, converting a silent
  wrong answer into a visible extraction failure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from app.domain.tenant_config import TenantConfiguration

Disposition = Literal["WITHIN_TOLERANCE", "EXCEEDS_TOLERANCE", "UNVERIFIED"]


def _decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, ArithmeticError):
        return Decimal("0")


@dataclass(frozen=True)
class ToleranceResult:
    disposition: Disposition
    variance_amount: Decimal
    variance_percent: Decimal
    threshold_percent: Decimal
    threshold_amount: Decimal
    reason_codes: list[str] = field(default_factory=list)
    summary: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "disposition": self.disposition,
            "variance_amount": str(self.variance_amount),
            "variance_percent": str(self.variance_percent),
            "threshold_percent": str(self.threshold_percent),
            "threshold_amount": str(self.threshold_amount),
            "reason_codes": self.reason_codes,
            "summary": self.summary,
        }


def evaluate_price_tolerance(
    configuration: TenantConfiguration,
    *,
    variance_amount: Decimal,
    variance_percent: Decimal,
) -> ToleranceResult:
    """Both the percentage and the absolute cap must hold (AP-001 §3)."""
    tolerances = configuration.invoice_tolerances
    within_percent = abs(variance_percent) <= tolerances.price_variance_percent
    within_amount = abs(variance_amount) <= tolerances.price_variance_amount
    within = within_percent and within_amount

    reason_codes: list[str] = []
    if not within:
        reason_codes.append("EXCEEDS_TOLERANCE")

    breached = []
    if not within_percent:
        breached.append(
            f"{variance_percent}% exceeds the {tolerances.price_variance_percent}% tolerance"
        )
    if not within_amount:
        breached.append(
            f"{variance_amount} exceeds the {tolerances.price_variance_amount} cap"
        )

    return ToleranceResult(
        disposition="WITHIN_TOLERANCE" if within else "EXCEEDS_TOLERANCE",
        variance_amount=variance_amount,
        variance_percent=variance_percent,
        threshold_percent=tolerances.price_variance_percent,
        threshold_amount=tolerances.price_variance_amount,
        reason_codes=reason_codes,
        summary=(
            "Variance is within the configured tolerance."
            if within
            else "Variance exceeds the configured tolerance: " + "; ".join(breached)
        ),
    )


@dataclass(frozen=True)
class QuantityFinding:
    line_number: int
    invoiced: Decimal
    received: Decimal

    @property
    def excess(self) -> Decimal:
        return self.invoiced - self.received

    @property
    def summary(self) -> str:
        return (
            f"Line {self.line_number}: invoice quantity {self.invoiced:g} exceeds "
            f"accepted receipt quantity {self.received:g}."
        )


def find_quantity_overruns(line_matches: list[dict[str, object]]) -> list[QuantityFinding]:
    """Lines invoiced above the accepted receipt quantity.

    AP-001 §4 allows no automatic tolerance here, so any excess is a finding.
    """
    overruns: list[QuantityFinding] = []
    for match in line_matches:
        invoice_line = match.get("invoice_line") or {}
        grn_line = match.get("grn_line")
        if not isinstance(invoice_line, dict) or not isinstance(grn_line, dict):
            continue
        invoiced = _decimal(invoice_line.get("quantity"))
        received = _decimal(grn_line.get("received"))
        if invoiced > received:
            overruns.append(
                QuantityFinding(
                    line_number=int(invoice_line.get("line_number") or 0),
                    invoiced=invoiced,
                    received=received,
                )
            )
    return overruns


@dataclass(frozen=True)
class TaxResult:
    disposition: Literal["MATCH", "MISMATCH", "UNVERIFIED"]
    invoice_rate: Decimal | None
    expected_rate: Decimal | None
    reason_codes: list[str] = field(default_factory=list)
    summary: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "disposition": self.disposition,
            "invoice_tax_rate": (
                str(self.invoice_rate) if self.invoice_rate is not None else None
            ),
            "configured_reference_rate": (
                str(self.expected_rate) if self.expected_rate is not None else None
            ),
            "reason_codes": self.reason_codes,
            "summary": self.summary,
        }


#: Rates are printed to whole or half percentages; anything closer than this is
#: a rounding artefact rather than a different rate.
TAX_RATE_EPSILON = Decimal("0.1")


def evaluate_tax_rate(
    configuration: TenantConfiguration,
    *,
    invoice_rate: Decimal | None,
    jurisdiction: str,
    invoice_date_iso: str,
) -> TaxResult:
    """Compare the invoice's tax rate against the tenant's configured reference."""
    expected = configuration.tax.expected_rate(jurisdiction, invoice_date_iso)
    if expected is None:
        return TaxResult(
            disposition="UNVERIFIED",
            invoice_rate=invoice_rate,
            expected_rate=None,
            reason_codes=["TAX_POLICY_UNVERIFIED"],
            summary=(
                f"No tax rule is configured for {jurisdiction} on "
                f"{invoice_date_iso}, so the invoice tax rate cannot be checked."
            ),
        )
    if invoice_rate is None:
        return TaxResult(
            disposition="UNVERIFIED",
            invoice_rate=None,
            expected_rate=expected,
            reason_codes=["TAX_POLICY_UNVERIFIED"],
            summary="The invoice does not state a tax rate.",
        )
    if abs(invoice_rate - expected) <= TAX_RATE_EPSILON:
        return TaxResult(
            disposition="MATCH",
            invoice_rate=invoice_rate,
            expected_rate=expected,
            summary=f"Invoice tax rate {invoice_rate}% matches the configured reference.",
        )
    return TaxResult(
        disposition="MISMATCH",
        invoice_rate=invoice_rate,
        expected_rate=expected,
        reason_codes=["TAX_MISMATCH"],
        summary=(
            f"Invoice tax rate is {invoice_rate} percent while the configured "
            f"reference is {expected} percent."
        ),
    )


@dataclass(frozen=True)
class ArithmeticResult:
    reconciles: bool
    line_total: Decimal
    tax_amount: Decimal
    stated_total: Decimal
    difference: Decimal
    reason_codes: list[str] = field(default_factory=list)
    summary: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "reconciles": self.reconciles,
            "line_total": str(self.line_total),
            "tax_amount": str(self.tax_amount),
            "stated_total": str(self.stated_total),
            "difference": str(self.difference),
            "reason_codes": self.reason_codes,
            "summary": self.summary,
        }


#: Rounding across several lines can legitimately differ by small change.
ARITHMETIC_EPSILON = Decimal("1.00")


def check_arithmetic(
    *,
    line_items: list[dict[str, object]],
    tax_amount: Decimal,
    stated_total: Decimal,
) -> ArithmeticResult:
    """Does the invoice add up?

    An invoice whose lines do not reconcile to its stated total has almost
    certainly been mis-extracted. Catching that here turns a wrong three-way
    match into a visible extraction failure.
    """
    line_total = sum(
        (_decimal(item.get("amount")) for item in line_items), Decimal("0")
    )
    computed = line_total + tax_amount
    difference = computed - stated_total
    reconciles = abs(difference) <= ARITHMETIC_EPSILON
    return ArithmeticResult(
        reconciles=reconciles,
        line_total=line_total,
        tax_amount=tax_amount,
        stated_total=stated_total,
        difference=difference,
        reason_codes=[] if reconciles else ["INVOICE_ARITHMETIC_INCONSISTENT"],
        summary=(
            "Line totals plus tax reconcile to the stated total."
            if reconciles
            else (
                f"Line totals ({line_total}) plus tax ({tax_amount}) come to "
                f"{computed}, but the invoice states {stated_total}. The "
                "extraction is unreliable, so matching results cannot be trusted."
            )
        ),
    )


def check_currency_consistency(
    *,
    invoice_currency: str | None,
    po_currency: str | None,
) -> list[str]:
    """A currency disagreement makes every amount comparison meaningless."""
    if not invoice_currency or not po_currency:
        return []
    if invoice_currency.upper() != po_currency.upper():
        return ["CURRENCY_MISMATCH"]
    return []
