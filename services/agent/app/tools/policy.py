import re
import time

from app.schemas import PolicyClause, PolicyResult, ToolResult, ToolStatus


def _terms(value: str) -> set[str]:
    return {term for term in re.findall(r"[a-z0-9]+", value.lower()) if len(term) > 2}


def retrieve_policies(query: str, clauses: list[PolicyClause], idempotency_key: str, minimum_score: float = 0.20) -> ToolResult[PolicyResult]:
    """Deterministic lexical fallback. Production Qdrant replaces candidate generation, not safety thresholds."""
    started = time.perf_counter()
    query_terms = _terms(query)
    ranked: list[PolicyClause] = []
    for clause in clauses:
        terms = _terms(f"{clause.title} {clause.content}")
        score = len(query_terms & terms) / max(1, len(query_terms | terms))
        if score >= minimum_score:
            ranked.append(clause.model_copy(update={"score": round(score, 4)}))
    ranked.sort(key=lambda item: item.score, reverse=True)
    result = PolicyResult(disposition="SUPPORTED" if ranked else "INSUFFICIENT_EVIDENCE", clauses=ranked[:8])
    return ToolResult(
        status=ToolStatus.SUCCESS if ranked else ToolStatus.BLOCKED,
        data=result,
        error_code=None if ranked else "INSUFFICIENT_EVIDENCE",
        retryable=False,
        provider_version="policy-retrieval-lexical-v1",
        idempotency_key=idempotency_key,
        latency_ms=round((time.perf_counter() - started) * 1000),
    )
