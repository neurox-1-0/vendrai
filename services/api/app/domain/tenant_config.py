"""Business thresholds, as tenant configuration rather than code constants.

Every number here is policy. Spend approval bands, price tolerance, the
expected tax rate, the set of approved countries - each one will be questioned
by someone, and each one differs between tenants. Hardcoding them makes the
answer to "why did this route to the Finance Controller?" a code reading rather
than a configuration lookup, and makes changing it a deployment.

The defaults below are transcribed from the two shipped policies (PROC-001
§7 and AP-001 §3-§6). They are defaults, not truths: a tenant that configures
different ones is not misconfigured.

See plans/04-phase-3-supplier.md item 3.2 and plans/05-phase-4-invoice.md 4.4.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field


class SpendBand(BaseModel):
    """One rung of the spend approval ladder.

    ``upper_bound`` is inclusive; the final band leaves it unset to mean "and
    above".
    """

    upper_bound: Decimal | None = None
    required_approvers: list[str] = Field(default_factory=list)
    label: str


class SpendPolicy(BaseModel):
    currency: str = "LKR"
    bands: list[SpendBand] = Field(
        default_factory=lambda: [
            SpendBand(
                upper_bound=Decimal("1000000"),
                required_approvers=["procurement_approver"],
                label="up to LKR 1,000,000",
            ),
            SpendBand(
                upper_bound=Decimal("5000000"),
                required_approvers=["procurement_approver", "budget_owner"],
                label="LKR 1,000,001 to LKR 5,000,000",
            ),
            SpendBand(
                upper_bound=None,
                required_approvers=[
                    "procurement_director",
                    "finance_controller",
                ],
                label="above LKR 5,000,000",
            ),
        ]
    )
    #: Spend above this is called out as a finding in its own right, because
    #: several scenarios turn on it ("annual spend above LKR 5 million").
    elevated_review_threshold: Decimal = Decimal("5000000")

    def band_for(self, amount: Decimal) -> SpendBand:
        for band in self.bands:
            if band.upper_bound is None or amount <= band.upper_bound:
                return band
        return self.bands[-1]

    def is_elevated(self, amount: Decimal) -> bool:
        return amount > self.elevated_review_threshold


class JurisdictionPolicy(BaseModel):
    #: Where the tenant operates. Data held outside this country triggers an
    #: information-security review; a bank account outside it is cross-border.
    home_country: str = "LK"
    #: Countries a supplier may bank in without an explicit justification.
    #: Empty means "the home country only".
    approved_bank_countries: list[str] = Field(default_factory=list)
    #: Countries where the tenant permits its data to be stored.
    approved_data_locations: list[str] = Field(default_factory=lambda: ["LK"])

    def bank_country_approved(self, country: str | None) -> bool:
        if not country:
            return False
        allowed = set(self.approved_bank_countries) | {self.home_country}
        return country.upper() in allowed

    def data_location_approved(self, country: str | None) -> bool:
        if not country:
            return False
        return country.upper() in {
            item.upper() for item in self.approved_data_locations
        }


class InvoiceTolerancePolicy(BaseModel):
    #: AP-001 §3: up to 2 percent, when the financial impact is below the
    #: absolute cap. Both conditions must hold - a 1 percent variance on a
    #: large order can still exceed the cap.
    price_variance_percent: Decimal = Decimal("2")
    price_variance_amount: Decimal = Decimal("25000")
    #: AP-001 §4: no automatic tolerance for invoicing above accepted receipt.
    quantity_variance_percent: Decimal = Decimal("0")
    #: AP-001 §6: an exact supplier and invoice-number match within this window
    #: must be blocked until reviewed.
    duplicate_window_months: int = 24


class TaxRule(BaseModel):
    jurisdiction: str
    rate_percent: Decimal
    effective_from: str
    effective_to: str | None = None

    def applies_on(self, iso_date: str) -> bool:
        if iso_date < self.effective_from:
            return False
        return self.effective_to is None or iso_date <= self.effective_to


class TaxPolicy(BaseModel):
    rules: list[TaxRule] = Field(
        default_factory=lambda: [
            TaxRule(
                jurisdiction="LK",
                rate_percent=Decimal("18"),
                effective_from="2026-01-01",
            )
        ]
    )

    def expected_rate(self, jurisdiction: str, iso_date: str) -> Decimal | None:
        """The configured reference rate, or None when nothing is configured.

        None is meaningful: it means the tax check is unverified rather than
        passing. A missing rule must never read as agreement.
        """
        for rule in self.rules:
            if rule.jurisdiction.upper() == jurisdiction.upper() and rule.applies_on(
                iso_date
            ):
                return rule.rate_percent
        return None


class TenantConfiguration(BaseModel):
    """The full configurable policy surface for one tenant."""

    spend: SpendPolicy = Field(default_factory=SpendPolicy)
    jurisdiction: JurisdictionPolicy = Field(default_factory=JurisdictionPolicy)
    invoice_tolerances: InvoiceTolerancePolicy = Field(
        default_factory=InvoiceTolerancePolicy
    )
    tax: TaxPolicy = Field(default_factory=TaxPolicy)


DEFAULT_CONFIGURATION = TenantConfiguration()
