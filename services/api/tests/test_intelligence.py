from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.domain.intelligence import (
    current_sanctions_datasets,
    sanctions_name_score,
    score_duplicate,
)


@dataclass
class Dataset:
    source: str
    status: str
    published_at: datetime | None


def test_exact_tax_match_always_requires_duplicate_review():
    result = score_duplicate(
        legal_name="Acme Technologies Ltd",
        tax_id_blind_index=b"same-tax",
        bank_account_blind_index=None,
        country="US",
        email_domain="acme.example",
        candidate_name="Acme Technology LLC",
        candidate_tax_id_blind_index=b"same-tax",
        candidate_bank_account_blind_index=None,
        candidate_country="US",
        candidate_email_domain="acme.example",
    )
    assert result.signals["tax_exact"] is True
    assert result.review_required is True


def test_legal_suffix_names_are_normalized():
    assert sanctions_name_score("ACME Trading Limited", "Acme Trading LLC") == 1.0


def test_empty_sanctions_name_never_matches():
    assert sanctions_name_score("", "Example") == 0.0


def test_sanctions_require_all_three_current_sources():
    now = datetime(2026, 7, 25, tzinfo=UTC)
    datasets = [
        Dataset("OFAC", "PUBLISHED", now - timedelta(hours=2)),
        Dataset("UN", "PUBLISHED", now - timedelta(hours=50)),
    ]
    active, missing, stale = current_sanctions_datasets(
        datasets,
        max_age_hours=36,
        now=now,
    )
    assert [item.source for item in active] == ["OFAC"]
    assert missing == ["EU"]
    assert stale == ["UN"]
