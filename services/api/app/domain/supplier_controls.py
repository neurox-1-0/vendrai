"""Deterministic supplier controls: cross-border, spend, residency, expiry.

These are the checks a supplier onboarding policy actually asks for, and that
the workflow previously could not perform. Each one is a pure function over
already-extracted evidence and the tenant's configured thresholds, so the
answer to "why was this escalated?" is a configuration value and a document
field rather than a code path.

Every control shares one rule: **absent evidence is UNVERIFIED, never CLEAR.**
A check that cannot run has not passed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal

from app.domain.tenant_config import TenantConfiguration

Disposition = Literal["CLEAR", "ATTENTION", "UNVERIFIED"]


@dataclass(frozen=True)
class ControlFinding:
    """One control's answer, with everything a reviewer needs to judge it."""

    control: str
    disposition: Disposition
    reason_code: str | None = None
    summary: str = ""
    evidence: dict[str, object] = field(default_factory=dict)

    @property
    def needs_attention(self) -> bool:
        return self.disposition == "ATTENTION"


@dataclass(frozen=True)
class SupplierControlResult:
    findings: tuple[ControlFinding, ...]

    @property
    def reason_codes(self) -> list[str]:
        return [
            finding.reason_code
            for finding in self.findings
            if finding.reason_code and finding.needs_attention
        ]

    @property
    def unverified(self) -> list[str]:
        return [
            finding.control
            for finding in self.findings
            if finding.disposition == "UNVERIFIED"
        ]

    @property
    def disposition(self) -> Disposition:
        if any(finding.needs_attention for finding in self.findings):
            return "ATTENTION"
        if self.unverified:
            return "UNVERIFIED"
        return "CLEAR"

    def as_dict(self) -> dict[str, object]:
        return {
            "disposition": self.disposition,
            "reason_codes": self.reason_codes,
            "unverified_controls": self.unverified,
            "findings": [
                {
                    "control": finding.control,
                    "disposition": finding.disposition,
                    "reason_code": finding.reason_code,
                    "summary": finding.summary,
                    "evidence": finding.evidence,
                }
                for finding in self.findings
            ],
        }


def check_banking_country(
    configuration: TenantConfiguration,
    *,
    registered_country: str | None,
    bank_country: str | None,
) -> ControlFinding:
    """Is the supplier banking where it is registered, or somewhere approved?"""
    if not registered_country or not bank_country:
        return ControlFinding(
            control="banking_country",
            disposition="UNVERIFIED",
            summary="Registered country or bank country was not stated.",
            evidence={
                "registered_country": registered_country,
                "bank_country": bank_country,
            },
        )
    registered = registered_country.upper()
    bank = bank_country.upper()
    if registered == bank:
        return ControlFinding(
            control="banking_country",
            disposition="CLEAR",
            summary=f"Bank and registered entity are both in {registered}.",
            evidence={"country": registered},
        )
    approved = configuration.jurisdiction.bank_country_approved(bank)
    return ControlFinding(
        control="banking_country",
        disposition="CLEAR" if approved else "ATTENTION",
        reason_code=None if approved else "BANKING_COUNTRY_MISMATCH",
        summary=(
            f"Supplier is registered in {registered} but banks in {bank}."
            + ("" if approved else " That pairing is not on the approved list.")
        ),
        evidence={
            "registered_country": registered,
            "bank_country": bank,
            "approved": approved,
        },
    )


def check_spend_band(
    configuration: TenantConfiguration,
    *,
    annual_spend: Decimal | None,
    currency: str | None,
) -> ControlFinding:
    """Which approval band does the declared annual spend fall into?"""
    if annual_spend is None:
        return ControlFinding(
            control="spend_band",
            disposition="UNVERIFIED",
            summary="Declared annual spend was not stated.",
        )
    configured_currency = configuration.spend.currency
    if currency and currency.upper() != configured_currency.upper():
        # Converting currencies here would invent an exchange rate and hide the
        # assumption inside a control. Say so instead.
        return ControlFinding(
            control="spend_band",
            disposition="UNVERIFIED",
            reason_code="SPEND_CURRENCY_MISMATCH",
            summary=(
                f"Spend is declared in {currency.upper()} but the approval "
                f"bands are configured in {configured_currency}. No conversion "
                "rate is configured, so the band cannot be determined."
            ),
            evidence={"declared_currency": currency.upper()},
        )
    band = configuration.spend.band_for(annual_spend)
    elevated = configuration.spend.is_elevated(annual_spend)
    return ControlFinding(
        control="spend_band",
        disposition="ATTENTION" if elevated else "CLEAR",
        reason_code="SPEND_ABOVE_ELEVATED_THRESHOLD" if elevated else None,
        summary=(
            f"Declared annual spend of {configured_currency} {annual_spend:,} "
            f"falls in the band {band.label}, requiring "
            f"{', '.join(band.required_approvers)}."
        ),
        evidence={
            "annual_spend": str(annual_spend),
            "currency": configured_currency,
            "band": band.label,
            "required_approvers": band.required_approvers,
            "elevated_threshold": str(
                configuration.spend.elevated_review_threshold
            ),
        },
    )


def check_data_residency(
    configuration: TenantConfiguration,
    *,
    data_access_declared: bool | None,
    data_stored_outside_country: bool | None,
    declared_locations: list[str] | None = None,
) -> ControlFinding:
    """Will company data leave the approved jurisdictions?"""
    if data_access_declared is None:
        return ControlFinding(
            control="data_residency",
            disposition="UNVERIFIED",
            summary="The supplier did not state whether it will access company data.",
        )
    if not data_access_declared:
        return ControlFinding(
            control="data_residency",
            disposition="CLEAR",
            summary="The supplier declared no access to company data.",
        )
    if data_stored_outside_country is None:
        return ControlFinding(
            control="data_residency",
            disposition="UNVERIFIED",
            reason_code="DATA_RESIDENCY_UNSTATED",
            summary=(
                "The supplier will access company data but did not state where "
                "that data will be stored."
            ),
        )
    if not data_stored_outside_country:
        return ControlFinding(
            control="data_residency",
            disposition="CLEAR",
            summary=(
                "The supplier will access company data, and states it is stored "
                f"within {configuration.jurisdiction.home_country}."
            ),
        )
    return ControlFinding(
        control="data_residency",
        disposition="ATTENTION",
        reason_code="DATA_STORED_OUTSIDE_APPROVED_LOCATION",
        summary=(
            "The supplier will store company data outside "
            f"{configuration.jurisdiction.home_country}, which requires "
            "Information Security and Legal review."
        ),
        evidence={
            "approved_locations": configuration.jurisdiction.approved_data_locations,
            "declared_locations": declared_locations or [],
        },
    )


def check_data_processing_agreement(
    *,
    data_access_declared: bool | None,
    agreement_available: bool | None,
    agreement_document_present: bool,
) -> ControlFinding:
    """Is there a data processing agreement where one is required?"""
    if not data_access_declared:
        return ControlFinding(
            control="data_processing_agreement",
            disposition="CLEAR",
            summary="No company data access declared, so no agreement is required.",
        )
    if agreement_document_present:
        return ControlFinding(
            control="data_processing_agreement",
            disposition="CLEAR",
            summary="A data processing agreement was submitted.",
        )
    if agreement_available is False:
        return ControlFinding(
            control="data_processing_agreement",
            disposition="ATTENTION",
            reason_code="DPA_UNAVAILABLE",
            summary=(
                "The supplier will access company data and has stated that no "
                "current data processing agreement is available."
            ),
        )
    return ControlFinding(
        control="data_processing_agreement",
        disposition="UNVERIFIED",
        reason_code="DPA_UNVERIFIED",
        summary=(
            "The supplier will access company data, and no data processing "
            "agreement was submitted or declared."
        ),
    )


def check_certificate_validity(
    *,
    control: str,
    valid_from: date | None,
    valid_to: date | None,
    as_of: date,
    label: str,
) -> ControlFinding:
    """Is a dated certificate in force on the assessment date?"""
    if valid_to is None:
        return ControlFinding(
            control=control,
            disposition="UNVERIFIED",
            reason_code="CERTIFICATE_VALIDITY_UNSTATED",
            summary=f"The {label} does not state an expiry date.",
        )
    if valid_to < as_of:
        return ControlFinding(
            control=control,
            disposition="ATTENTION",
            reason_code="CERTIFICATE_EXPIRED",
            summary=(
                f"The {label} expired on {valid_to.isoformat()}, before the "
                f"assessment date {as_of.isoformat()}."
            ),
            evidence={
                "valid_from": valid_from.isoformat() if valid_from else None,
                "valid_to": valid_to.isoformat(),
                "as_of": as_of.isoformat(),
            },
        )
    if valid_from and valid_from > as_of:
        return ControlFinding(
            control=control,
            disposition="ATTENTION",
            reason_code="CERTIFICATE_NOT_YET_EFFECTIVE",
            summary=(
                f"The {label} does not take effect until "
                f"{valid_from.isoformat()}."
            ),
            evidence={"valid_from": valid_from.isoformat(), "as_of": as_of.isoformat()},
        )
    return ControlFinding(
        control=control,
        disposition="CLEAR",
        summary=f"The {label} is in force until {valid_to.isoformat()}.",
        evidence={"valid_to": valid_to.isoformat()},
    )


def evaluate_supplier_controls(
    configuration: TenantConfiguration,
    *,
    registered_country: str | None,
    bank_country: str | None,
    annual_spend: Decimal | None,
    spend_currency: str | None,
    data_access_declared: bool | None,
    data_stored_outside_country: bool | None,
    dpa_available: bool | None,
    dpa_document_present: bool,
    insurance_valid_from: date | None,
    insurance_valid_to: date | None,
    tax_certificate_valid_to: date | None,
    as_of: date,
) -> SupplierControlResult:
    """Run every supplier control and collect the findings."""
    findings = [
        check_banking_country(
            configuration,
            registered_country=registered_country,
            bank_country=bank_country,
        ),
        check_spend_band(
            configuration,
            annual_spend=annual_spend,
            currency=spend_currency,
        ),
        check_data_residency(
            configuration,
            data_access_declared=data_access_declared,
            data_stored_outside_country=data_stored_outside_country,
        ),
        check_data_processing_agreement(
            data_access_declared=data_access_declared,
            agreement_available=dpa_available,
            agreement_document_present=dpa_document_present,
        ),
        check_certificate_validity(
            control="insurance_validity",
            valid_from=insurance_valid_from,
            valid_to=insurance_valid_to,
            as_of=as_of,
            label="insurance certificate",
        ),
        check_certificate_validity(
            control="tax_registration_validity",
            valid_from=None,
            valid_to=tax_certificate_valid_to,
            as_of=as_of,
            label="tax registration certificate",
        ),
    ]
    return SupplierControlResult(findings=tuple(findings))
