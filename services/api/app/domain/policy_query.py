"""Compose the policy retrieval query from the facts of the case.

One fixed query string was used for every supplier case:

    "new vendor onboarding required documents bank details sanctions
     screening human approval"

VO-003 needs clauses on cross-border banking, data residency, and insurance.
None of those words appear above, and retrieval cannot cite what it never
searched for - so the scenario failed on missing policy evidence while the
policy sat correctly indexed the whole time.

The query is built deterministically from case facts and active findings, and
returned alongside the terms that produced it so the retrieval step is
auditable: a reviewer can see what was searched for, not just what came back.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Reason code -> the policy vocabulary that finds the clause governing it.
#: These are retrieval terms, not display text; they exist to overlap with how
#: the policy is actually worded.
_REASON_TERMS: dict[str, tuple[str, ...]] = {
    "BANKING_COUNTRY_MISMATCH": (
        "cross-border banking",
        "foreign bank account",
        "bank country mismatch",
        "Treasury approval",
    ),
    "BANK_BENEFICIARY_MISMATCH": (
        "beneficiary name",
        "third-party account",
        "independent verification",
    ),
    "BANK_BENEFICIARY_IS_INDIVIDUAL": (
        "beneficiary name",
        "third-party account",
        "banking controls",
    ),
    "DATA_STORED_OUTSIDE_APPROVED_LOCATION": (
        "data residency",
        "data processed outside approved locations",
        "Information Security approval",
    ),
    "DPA_UNAVAILABLE": (
        "data processing agreement",
        "contractual data-processing terms",
        "data access",
    ),
    "DPA_UNVERIFIED": ("data processing agreement", "data access"),
    "CERTIFICATE_EXPIRED": ("insurance", "current evidence", "required documents"),
    "SPEND_ABOVE_ELEVATED_THRESHOLD": (
        "spend-based approvals",
        "Procurement Director",
        "Finance Controller",
    ),
    "MISSING_REQUIRED_DOCUMENT": (
        "required documents",
        "tax registration evidence",
        "bank account confirmation",
    ),
    "POSSIBLE_DUPLICATE": (
        "duplicate screening",
        "tax identification number match",
        "Vendor Master Control",
    ),
    "SANCTIONS_REVIEW_REQUIRED": (
        "sanctions screening",
        "beneficial owners",
        "escalation",
    ),
    "SANCTIONS_DATA_UNAVAILABLE": (
        "failed or unavailable check",
        "must not be treated as a pass",
    ),
    "RISK_SERVICE_UNAVAILABLE": (
        "failed or unavailable check",
        "risk and sanctions checks",
    ),
    "ADVERSE_MEDIA_POSSIBLE_MATCH": ("adverse media", "risk severity", "escalation"),
    "UNTRUSTED_DOCUMENT_INSTRUCTION": (
        "human approval",
        "controlled decisions",
        "authorised human reviewer",
    ),
}

#: Always searched for, because every supplier case is judged against them.
_BASE_TERMS: tuple[str, ...] = (
    "supplier onboarding",
    "required documents",
    "duplicate screening",
    "banking controls",
    "human approval",
)

#: Retrieval quality degrades once a query sprawls; keep it focused on what
#: this case actually raised.
MAX_TERMS = 18


@dataclass(frozen=True)
class PolicyQuery:
    text: str
    terms: tuple[str, ...]
    #: The reason codes that contributed, for the audit trail.
    driven_by: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, object]:
        return {
            "query": self.text,
            "terms": list(self.terms),
            "driven_by": list(self.driven_by),
        }


def build_supplier_policy_query(
    *,
    reason_codes: list[str] | None = None,
    registered_country: str | None = None,
    bank_country: str | None = None,
    data_access_declared: bool = False,
    spend_elevated: bool = False,
) -> PolicyQuery:
    """Build a case-specific query, and record what drove it."""
    terms: list[str] = list(_BASE_TERMS)
    driven_by: list[str] = []

    for reason_code in reason_codes or []:
        extra = _REASON_TERMS.get(reason_code)
        if not extra:
            continue
        driven_by.append(reason_code)
        terms.extend(extra)

    # Case facts contribute even when they raised no finding: a cross-border
    # supplier is judged against the cross-border clause whether or not the
    # pairing happened to be approved.
    if registered_country and bank_country and registered_country != bank_country:
        terms.extend(("cross-border supplier", "foreign bank account"))
    if data_access_declared:
        terms.extend(("data access", "enhanced review"))
    if spend_elevated:
        terms.extend(("spend-based approvals", "budget owner"))

    ordered: list[str] = []
    for term in terms:
        if term not in ordered:
            ordered.append(term)
    ordered = ordered[:MAX_TERMS]

    return PolicyQuery(
        text=" ".join(ordered),
        terms=tuple(ordered),
        driven_by=tuple(dict.fromkeys(driven_by)),
    )
