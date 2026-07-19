from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

class ApiMeta(BaseModel):
    request_id: str
    timestamp: datetime


class CaseCreate(BaseModel):
    title: str = Field(min_length=3, max_length=240)
    priority: Literal["LOW", "NORMAL", "HIGH", "URGENT"] = "NORMAL"

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        return " ".join(value.split())


class CaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    case_id: UUID
    tenant_id: UUID
    case_number: str
    case_type: str
    status: str
    title: str
    priority: str
    requester_user_id: UUID
    current_version: int
    created_at: datetime
    updated_at: datetime


class CaseListResponse(BaseModel):
    items: list[CaseResponse]
    total: int


class ActionAccepted(BaseModel):
    case_id: UUID
    run_id: UUID | None = None
    status: str
    event_url: str | None = None


class UploadInitiateRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=3, max_length=120)
    size_bytes: int = Field(gt=0)
    document_type: str = Field(default="UNKNOWN", max_length=50)


class UploadInitiateResponse(BaseModel):
    document_id: UUID
    upload_url: str
    method: Literal["PUT"] = "PUT"
    expires_at: datetime
    required_headers: dict[str, str]


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    document_id: UUID
    case_id: UUID
    original_filename: str
    mime_type: str
    size_bytes: int
    sha256: str | None
    malware_status: str
    processing_status: str
    created_at: datetime


class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    event_id: UUID
    case_id: UUID
    sequence: int
    event_type: str
    actor_type: str
    payload: dict[str, Any]
    created_at: datetime


class RunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    run_id: UUID
    case_id: UUID
    thread_id: str
    graph_name: str
    graph_version: str
    status: str
    current_node: str | None
    state_version: int
    created_at: datetime
    updated_at: datetime


class ApprovalTaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    approval_task_id: UUID
    case_id: UUID
    run_id: UUID
    task_type: str
    status: str
    assigned_role: str
    proposed_action: dict[str, Any]
    evidence_packet: dict[str, Any]
    evidence_hash: str
    case_version: int
    created_at: datetime


class ApprovalDecisionRequest(BaseModel):
    decision: Literal["APPROVED", "REJECTED", "MORE_INFO", "ESCALATED"]
    expected_version: int = Field(gt=0)
    evidence_hash: str = Field(min_length=64, max_length=64)
    comment: str | None = Field(default=None, max_length=2000)
    edited_payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("comment")
    @classmethod
    def require_comment_for_nonapproval(cls, value: str | None, info):
        decision = info.data.get("decision")
        if decision in {"REJECTED", "MORE_INFO", "ESCALATED"} and not value:
            raise ValueError("A comment is required for this decision")
        return value


class EvidenceResponse(BaseModel):
    items: list[dict[str, Any]]
    evidence_hash: str | None


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    notification_id: UUID
    case_id: UUID | None
    notification_type: str
    title: str
    body: str
    status: str
    read_at: datetime | None
    created_at: datetime


class HealthResponse(BaseModel):
    status: Literal["healthy", "degraded"]
    checks: dict[str, str]


class PolicyUploadRequest(BaseModel):
    policy_code: str = Field(min_length=2, max_length=80, pattern=r"^[A-Z0-9_-]+$")
    title: str = Field(min_length=3, max_length=240)
    owner_department: str = Field(min_length=2, max_length=100)
    version: str = Field(min_length=1, max_length=40)
    effective_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    content: str = Field(min_length=20, max_length=200_000)


class PolicyResponse(BaseModel):
    policy_document_id: UUID
    policy_version_id: UUID
    policy_code: str
    title: str
    version: str
    status: str
    chunk_count: int


class ClarificationResponseRequest(BaseModel):
    answers: dict[str, str]
    expected_version: int = Field(gt=0)
