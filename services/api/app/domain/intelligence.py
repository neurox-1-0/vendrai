from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from typing import Protocol

from app.domain.security import normalize_vendor_name


@dataclass(frozen=True)
class DuplicateScore:
    score: float
    signals: dict[str, float | bool]
    review_required: bool


class SanctionsDatasetLike(Protocol):
    status: str
    source: str
    published_at: datetime | None


def string_similarity(left: str | None, right: str | None) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, normalize_vendor_name(left), normalize_vendor_name(right)).ratio()


def score_duplicate(
    *,
    legal_name: str,
    tax_id_blind_index: bytes | None,
    bank_account_blind_index: bytes | None,
    country: str | None,
    email_domain: str | None,
    candidate_name: str,
    candidate_tax_id_blind_index: bytes | None,
    candidate_bank_account_blind_index: bytes | None,
    candidate_country: str | None,
    candidate_email_domain: str | None = None,
) -> DuplicateScore:
    name_score = string_similarity(legal_name, candidate_name)
    tax_exact = bool(
        tax_id_blind_index
        and candidate_tax_id_blind_index
        and tax_id_blind_index == candidate_tax_id_blind_index
    )
    bank_exact = bool(
        bank_account_blind_index
        and candidate_bank_account_blind_index
        and bank_account_blind_index == candidate_bank_account_blind_index
    )
    country_exact = bool(
        country
        and candidate_country
        and country.upper() == candidate_country.upper()
    )
    email_exact = bool(
        email_domain
        and candidate_email_domain
        and email_domain.lower() == candidate_email_domain.lower()
    )
    score = min(
        1.0,
        (0.40 if tax_exact else 0.0)
        + (0.20 if bank_exact else 0.0)
        + 0.30 * name_score
        + (0.05 if country_exact else 0.0)
        + (0.05 if email_exact else 0.0),
    )
    signals: dict[str, float | bool] = {
        "tax_exact": tax_exact,
        "bank_exact": bank_exact,
        "name_similarity": round(name_score, 4),
        "country_exact": country_exact,
        "email_domain_exact": email_exact,
    }
    return DuplicateScore(
        score=round(score, 4),
        signals=signals,
        review_required=score >= 0.70 or tax_exact or bank_exact,
    )


def sanctions_name_score(query: str, candidate: str) -> float:
    normalized_query = normalize_vendor_name(query)
    normalized_candidate = normalize_vendor_name(candidate)
    if not normalized_query or not normalized_candidate:
        return 0.0
    if normalized_query == normalized_candidate:
        return 1.0
    return SequenceMatcher(None, normalized_query, normalized_candidate).ratio()


def current_sanctions_datasets(
    datasets: list[SanctionsDatasetLike],
    *,
    max_age_hours: int,
    now: datetime | None = None,
) -> tuple[list[SanctionsDatasetLike], list[str], list[str]]:
    """Return one current published dataset per mandatory source.

    The function deliberately uses structural attributes so the deterministic
    control stays unit-testable without a database or ORM session.
    """
    reference = now or datetime.now(UTC)
    latest: dict[str, SanctionsDatasetLike] = {}
    for dataset in datasets:
        if dataset.status != "PUBLISHED":
            continue
        source = str(dataset.source).upper()
        published_at = dataset.published_at
        existing = latest.get(source)
        if not existing or (
            published_at
            and (
                not existing.published_at
                or published_at > existing.published_at
            )
        ):
            latest[source] = dataset
    mandatory = {"OFAC", "UN", "EU"}
    missing = sorted(mandatory - latest.keys())
    cutoff = reference - timedelta(hours=max_age_hours)
    stale = sorted(
        source
        for source, dataset in latest.items()
        if source in mandatory
        and (
            not dataset.published_at
            or dataset.published_at < cutoff
        )
    )
    active = [
        latest[source]
        for source in sorted(mandatory)
        if source in latest and source not in stale
    ]
    return active, missing, stale
