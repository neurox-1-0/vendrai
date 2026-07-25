from typing import Any, Literal

from pydantic import BaseModel, Field

ToolStatus = Literal["SUCCESS", "PARTIAL", "BLOCKED", "FAILED"]


class ToolResult(BaseModel):
    status: ToolStatus
    data: dict[str, Any] = Field(default_factory=dict)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    error_code: str | None = None
    retryable: bool = False
    latency_ms: int
    provider_version: str
    idempotency_key: str


class Contradiction(BaseModel):
    claim_a: str = Field(max_length=300)
    claim_b: str = Field(max_length=300)
    evidence_ids: list[str] = Field(default_factory=list, max_length=8)
    severity: Literal["LOW", "MEDIUM", "HIGH"]


class ContradictionAnalysis(BaseModel):
    contradictions: list[Contradiction] = Field(default_factory=list)
    clarification_questions: list[str] = Field(
        default_factory=list,
        max_length=8,
    )
    explanation: str = Field(max_length=1000)


class EvidenceCritique(BaseModel):
    completeness_score: float = Field(ge=0, le=1)
    unsupported_claims: list[str] = Field(default_factory=list, max_length=12)
    cited_evidence_ids: list[str] = Field(default_factory=list, max_length=24)
    explanation: str = Field(max_length=1000)


class HumanResume(BaseModel):
    decision: Literal[
        "APPROVED",
        "REJECTED",
        "MORE_INFO",
        "ESCALATED",
        "CLARIFIED",
    ]
    task_id: str
    evidence_hash: str
    expected_version: int = Field(ge=1)
    actor_id: str


class ErpResume(BaseModel):
    status: Literal["SUCCEEDED", "FAILED"]
    operation_id: str
    provider_reference: str | None = None
    error_code: str | None = None
