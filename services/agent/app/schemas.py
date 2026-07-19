from enum import StrEnum
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field


T = TypeVar("T")


class ToolStatus(StrEnum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    PENDING = "PENDING"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class EvidenceRef(BaseModel):
    source_type: str
    source_id: str
    locator: dict[str, Any] = Field(default_factory=dict)
    reason_code: str
    confidence: float | None = Field(default=None, ge=0, le=1)


class ToolResult(BaseModel, Generic[T]):
    status: ToolStatus
    data: T | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False
    latency_ms: int = Field(default=0, ge=0)
    provider_version: str
    idempotency_key: str


class ExtractedVendor(BaseModel):
    legal_name: str | None = None
    normalized_legal_name: str | None = None
    tax_id_token: str | None = None
    bank_account_token: str | None = None
    registered_country: str | None = None
    address_masked: str | None = None
    email_domain: str | None = None
    phone_token: str | None = None
    fields_requiring_confirmation: list[str] = Field(default_factory=list)


class VendorRecord(BaseModel):
    vendor_id: str
    legal_name: str
    normalized_legal_name: str
    tax_id_hash: str | None = None
    bank_account_hash: str | None = None
    registered_country: str | None = None
    address_normalized: str | None = None
    email_domain: str | None = None
    phone_hash: str | None = None


class DuplicateCandidate(BaseModel):
    vendor_id: str
    display_name: str
    score: float = Field(ge=0, le=1)
    signals: dict[str, float | bool | str | None]
    review_required: bool


class SanctionsEntity(BaseModel):
    source: Literal["OFAC", "UN", "EU"]
    dataset_version: str
    entity_id: str
    primary_name: str
    aliases: list[str] = Field(default_factory=list)
    countries: list[str] = Field(default_factory=list)


class SanctionsCandidate(BaseModel):
    source: str
    dataset_version: str
    entity_id: str
    matched_name: str
    score: float = Field(ge=0, le=1)
    exact: bool
    review_required: bool = True


class RiskAssessment(BaseModel):
    disposition: Literal["CLEAR", "POSSIBLE_MATCH", "UNAVAILABLE"]
    candidates: list[SanctionsCandidate] = Field(default_factory=list)


class PolicyClause(BaseModel):
    policy_id: str
    version: str
    clause_id: str
    title: str
    content: str
    score: float = Field(ge=0, le=1)
    effective_date: str


class PolicyResult(BaseModel):
    disposition: Literal["SUPPORTED", "INSUFFICIENT_EVIDENCE"]
    clauses: list[PolicyClause] = Field(default_factory=list)


class EvidencePacket(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    run_id: str
    recommendation: Literal["CREATE_VENDOR", "REJECT", "REQUEST_INFORMATION", "REVIEW_REQUIRED"]
    reason_codes: list[str]
    extracted_vendor: ExtractedVendor
    duplicate_candidates: list[DuplicateCandidate]
    risk: RiskAssessment
    policy_clauses: list[PolicyClause]
    evidence: list[EvidenceRef]
    unresolved_items: list[str]


class VerificationResult(BaseModel):
    passed: bool
    blocking_reasons: list[str] = Field(default_factory=list)
    approval_role: str = "approver"
