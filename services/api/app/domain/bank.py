"""Deterministic bank-evidence consistency checks.

The supplier question is *"is this bank account consistent with the registered
entity and its country?"* - which is not the same as the invoice question
(*"does it match the resolved vendor master record?"*). A new supplier has no
vendor-master row to compare against, so the only available comparison is
between the pieces of evidence the supplier themselves submitted.

Two independent signals:

1. **Beneficiary vs legal entity.** A bank confirmation naming a person, or a
   different company, than the entity being onboarded is the classic payment
   redirection pattern.
2. **Bank country vs registered country.** An entity registered in one
   jurisdiction banking in another is not wrong, but it is a control question,
   and the policy requires it to be answered rather than assumed.

Everything here is a pure function so the control stays testable without a
database, an ORM session, or a model call.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from app.domain.intelligence import string_similarity
from app.domain.security import normalize_vendor_name

Disposition = Literal["CLEAR", "MISMATCH", "UNVERIFIED"]

# Above this the beneficiary and the legal entity are the same party under a
# formatting variation ("ABC (Pvt) Ltd" vs "ABC Private Limited"). Below it,
# a human decides. Deliberately generous, because normalize_vendor_name has
# already stripped legal suffixes and punctuation - what remains is the name.
BENEFICIARY_NAME_MATCH_THRESHOLD = 0.85

# SWIFT/BIC positions 5-6 are the ISO 3166-1 alpha-2 country code.
_SWIFT_PATTERN = re.compile(r"^[A-Z]{4}([A-Z]{2})[A-Z0-9]{2}([A-Z0-9]{3})?$")

# Honorifics and given-name markers that indicate a natural person rather than
# a company. A beneficiary that is an individual is the VO-005 pattern.
_INDIVIDUAL_MARKERS = frozenset(
    {"mr", "mrs", "ms", "miss", "dr", "prof", "messrs", "sri", "shri"}
)
_COMPANY_MARKERS = frozenset(
    {
        "ltd",
        "limited",
        "pvt",
        "private",
        "plc",
        "llc",
        "inc",
        "incorporated",
        "corp",
        "corporation",
        "company",
        "holdings",
        "enterprises",
        "trading",
        "traders",
        "industries",
        "services",
        "solutions",
        "group",
        "gmbh",
        "sarl",
        "bv",
        "nv",
        "ag",
        "pte",
        "sdn",
        "bhd",
    }
)


@dataclass(frozen=True)
class BankConsistencyResult:
    disposition: Disposition
    signals: dict[str, object]
    reason_codes: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)

    @property
    def requires_review(self) -> bool:
        return self.disposition == "MISMATCH"


def swift_country(swift_code: str | None) -> str | None:
    """Extract the ISO country code from a SWIFT/BIC, or None if unparseable."""
    if not swift_code:
        return None
    match = _SWIFT_PATTERN.match("".join(swift_code.split()).upper())
    return match.group(1) if match else None


def looks_like_individual(name: str | None) -> bool:
    """Heuristic: does this beneficiary name denote a natural person?

    Deliberately conservative. It only fires on an explicit honorific or on a
    short all-alphabetic name carrying no company marker, because the cost of a
    false positive is a spurious review and the cost of a false negative is
    covered by the name-similarity signal anyway.
    """
    if not name:
        return False
    tokens = [token for token in re.split(r"[^A-Za-z]+", name.lower()) if token]
    if not tokens:
        return False
    if tokens[0] in _INDIVIDUAL_MARKERS:
        return True
    if any(token in _COMPANY_MARKERS for token in tokens):
        return False
    return 2 <= len(tokens) <= 4


def evaluate_bank_consistency(
    *,
    legal_name: str | None,
    beneficiary_name: str | None,
    registered_country: str | None,
    bank_country: str | None = None,
    swift_code: str | None = None,
) -> BankConsistencyResult:
    """Compare bank evidence against the entity being onboarded.

    ``bank_country`` wins over a country derived from ``swift_code`` when both
    are present: an explicitly stated country is stronger evidence than one
    inferred from an identifier.
    """
    derived_country = swift_country(swift_code)
    effective_bank_country = (bank_country or derived_country or "").upper() or None
    effective_registered_country = (registered_country or "").upper() or None

    missing: list[str] = []
    if not legal_name:
        missing.append("legal_name")
    if not beneficiary_name:
        missing.append("bank_beneficiary_name")
    if not effective_bank_country:
        missing.append("bank_country")
    if not effective_registered_country:
        missing.append("registered_country")

    name_similarity: float | None = None
    beneficiary_mismatch = False
    beneficiary_is_individual = False
    if legal_name and beneficiary_name:
        name_similarity = round(string_similarity(legal_name, beneficiary_name), 4)
        beneficiary_mismatch = name_similarity < BENEFICIARY_NAME_MATCH_THRESHOLD
        if beneficiary_mismatch:
            beneficiary_is_individual = looks_like_individual(beneficiary_name)

    country_mismatch = bool(
        effective_bank_country
        and effective_registered_country
        and effective_bank_country != effective_registered_country
    )

    signals: dict[str, object] = {
        "beneficiary_name_similarity": name_similarity,
        "beneficiary_name_mismatch": beneficiary_mismatch,
        "beneficiary_appears_to_be_individual": beneficiary_is_individual,
        "normalized_legal_name": normalize_vendor_name(legal_name or "") or None,
        "normalized_beneficiary_name": (
            normalize_vendor_name(beneficiary_name or "") or None
        ),
        "bank_country": effective_bank_country,
        "bank_country_source": (
            "declared" if bank_country else "swift" if derived_country else None
        ),
        "registered_country": effective_registered_country,
        "banking_country_mismatch": country_mismatch,
    }

    reason_codes: list[str] = []
    if beneficiary_mismatch:
        reason_codes.append("BANK_BENEFICIARY_MISMATCH")
    if beneficiary_is_individual:
        reason_codes.append("BANK_BENEFICIARY_IS_INDIVIDUAL")
    if country_mismatch:
        reason_codes.append("BANKING_COUNTRY_MISMATCH")

    if reason_codes:
        disposition: Disposition = "MISMATCH"
    elif missing:
        # Evidence absent is not evidence of consistency. Reporting CLEAR here
        # would be the exact silent-success failure this whole control exists
        # to prevent.
        disposition = "UNVERIFIED"
        reason_codes.append("BANK_EVIDENCE_INCOMPLETE")
    else:
        disposition = "CLEAR"

    return BankConsistencyResult(
        disposition=disposition,
        signals=signals,
        reason_codes=reason_codes,
        missing_evidence=missing,
    )
