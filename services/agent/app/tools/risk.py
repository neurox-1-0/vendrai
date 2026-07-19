import time
from difflib import SequenceMatcher

from app.schemas import ExtractedVendor, RiskAssessment, SanctionsCandidate, SanctionsEntity, ToolResult, ToolStatus
from app.tools.duplicate import normalize_name


def screen_sanctions(
    vendor: ExtractedVendor,
    entities: list[SanctionsEntity],
    idempotency_key: str,
    minimum_candidate_score: float = 0.84,
) -> ToolResult[RiskAssessment]:
    started = time.perf_counter()
    if not entities:
        return ToolResult(
            status=ToolStatus.BLOCKED,
            data=RiskAssessment(disposition="UNAVAILABLE"),
            error_code="SANCTIONS_DATA_UNAVAILABLE",
            error_message="No verified OFAC, UN, or EU dataset is active.",
            retryable=True,
            provider_version="sanctions-local-v1",
            idempotency_key=idempotency_key,
            latency_ms=round((time.perf_counter() - started) * 1000),
        )
    query = normalize_name(vendor.legal_name or "")
    candidates: list[SanctionsCandidate] = []
    for entity in entities:
        for candidate_name in [entity.primary_name, *entity.aliases]:
            normalized = normalize_name(candidate_name)
            exact = query == normalized and bool(query)
            score = 1.0 if exact else SequenceMatcher(None, query, normalized).ratio()
            country_match = not vendor.registered_country or not entity.countries or vendor.registered_country in entity.countries
            if score >= minimum_candidate_score and country_match:
                candidates.append(SanctionsCandidate(
                    source=entity.source, dataset_version=entity.dataset_version, entity_id=entity.entity_id,
                    matched_name=candidate_name, score=round(score, 4), exact=exact,
                ))
                break
    candidates.sort(key=lambda item: item.score, reverse=True)
    assessment = RiskAssessment(disposition="POSSIBLE_MATCH" if candidates else "CLEAR", candidates=candidates[:20])
    return ToolResult(
        status=ToolStatus.SUCCESS, data=assessment,
        provider_version="sanctions-local-v1", idempotency_key=idempotency_key,
        latency_ms=round((time.perf_counter() - started) * 1000),
    )
