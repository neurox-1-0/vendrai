import re
import time
import unicodedata
from difflib import SequenceMatcher

from app.schemas import DuplicateCandidate, ExtractedVendor, EvidenceRef, ToolResult, ToolStatus, VendorRecord


LEGAL_SUFFIXES = re.compile(r"\b(llc|inc|incorporated|ltd|limited|plc|pvt|private|corp|corporation|company|co)\b", re.I)


def normalize_name(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", LEGAL_SUFFIXES.sub(" ", ascii_value.lower())).split())


def similarity(left: str | None, right: str | None) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def score_candidate(incoming: ExtractedVendor, existing: VendorRecord) -> DuplicateCandidate:
    name_score = similarity(incoming.normalized_legal_name, existing.normalized_legal_name)
    tax_exact = bool(incoming.tax_id_token and existing.tax_id_hash and incoming.tax_id_token == existing.tax_id_hash)
    bank_exact = bool(incoming.bank_account_token and existing.bank_account_hash and incoming.bank_account_token == existing.bank_account_hash)
    country_exact = bool(incoming.registered_country and existing.registered_country and incoming.registered_country == existing.registered_country)
    email_exact = bool(incoming.email_domain and existing.email_domain and incoming.email_domain == existing.email_domain)
    score = min(1.0, (0.40 if tax_exact else 0) + (0.20 if bank_exact else 0) + 0.30 * name_score + (0.05 if country_exact else 0) + (0.05 if email_exact else 0))
    return DuplicateCandidate(
        vendor_id=existing.vendor_id,
        display_name=existing.legal_name,
        score=round(score, 4),
        signals={"tax_id_exact": tax_exact, "bank_exact": bank_exact, "name_similarity": round(name_score, 4), "country_exact": country_exact, "email_domain_exact": email_exact},
        review_required=score >= 0.70 or tax_exact or bank_exact,
    )


def find_duplicates(incoming: ExtractedVendor, vendors: list[VendorRecord], idempotency_key: str) -> ToolResult[list[DuplicateCandidate]]:
    started = time.perf_counter()
    if not incoming.normalized_legal_name:
        return ToolResult(
            status=ToolStatus.BLOCKED, error_code="VENDOR_NAME_REQUIRED", retryable=False,
            provider_version="duplicate-score-v1", idempotency_key=idempotency_key,
            latency_ms=round((time.perf_counter() - started) * 1000),
        )
    candidates = [score_candidate(incoming, vendor) for vendor in vendors]
    candidates = sorted((candidate for candidate in candidates if candidate.score >= 0.45), key=lambda item: item.score, reverse=True)[:10]
    evidence = [EvidenceRef(
        source_type="VENDOR_MASTER", source_id=item.vendor_id,
        locator={"signals": item.signals}, reason_code="DUPLICATE_SCORE", confidence=item.score,
    ) for item in candidates]
    return ToolResult(
        status=ToolStatus.SUCCESS, data=candidates, evidence=evidence,
        provider_version="duplicate-score-v1", idempotency_key=idempotency_key,
        latency_ms=round((time.perf_counter() - started) * 1000),
    )
