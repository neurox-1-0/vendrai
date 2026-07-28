from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.cases import CaseStatus
from app.domain.pii import mask_sensitive_text


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
    status: CaseStatus
    title: str
    priority: str
    requester_user_id: UUID
    assigned_user_id: UUID | None
    current_version: int
    created_at: datetime
    updated_at: datetime


class CaseListResponse(BaseModel):
    items: list[CaseResponse]
    total: int


class WorkQueueItem(CaseResponse):
    age_seconds: int
    ownership: Literal["UNCLAIMED", "MINE", "OTHER"]


class WorkQueueResponse(BaseModel):
    items: list[WorkQueueItem]
    total: int


class AuditExportResponse(BaseModel):
    audit_export_id: UUID
    case_id: UUID
    status: str
    sha256: str
    expires_at: datetime
    download_url: str


class ActionAccepted(BaseModel):
    case_id: UUID
    run_id: UUID | None = None
    status: CaseStatus
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


class DocumentPageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    page_id: UUID
    document_id: UUID
    page_number: int
    text_content: str | None
    layout_json: dict[str, Any]
    ocr_confidence: float | None


class ExtractedFieldResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    extracted_field_id: UUID
    document_id: UUID
    field_name: str
    field_value_masked: str | None
    confidence: float | None
    confidence_grade: str
    validation_results: list[dict[str, Any]]
    source_page: int | None
    source_bbox: dict[str, Any]
    extractor_type: str
    extractor_version: str | None
    human_verified: bool
    updated_at: datetime


class FieldCorrectionRequest(BaseModel):
    value: str = Field(min_length=1, max_length=2000)
    expected_version: int = Field(gt=0)
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("value")
    @classmethod
    def normalize_correction_value(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("reason")
    @classmethod
    def normalize_and_mask_correction_reason(cls, value: str) -> str:
        return mask_sensitive_text(" ".join(value.split()))


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


class AgentStepResponse(BaseModel):
    step_id: UUID
    run_id: UUID
    node_name: str
    display_name: str
    agent_kind: Literal["PLANNER", "SPECIALIST", "REASONING", "VERIFIER", "HUMAN", "EXECUTION"]
    attempt: int
    status: str
    route_reason: str
    dependencies: list[str]
    input_summary: dict[str, Any]
    output_summary: dict[str, Any]
    error: dict[str, Any]
    latency_ms: int | None
    started_at: datetime
    completed_at: datetime | None


class RunGraphEdge(BaseModel):
    source: str
    target: str
    relation: Literal["DEPENDS_ON", "ROUTES_TO"] = "DEPENDS_ON"


class RunTimingSummary(BaseModel):
    total_elapsed_ms: int | None
    active_compute_ms: int
    critical_path_ms: int
    parallel_time_saved_ms: int
    human_waiting_ms: int | None = None


class RunGraphResponse(BaseModel):
    run: RunResponse
    objective: str
    selected_path: list[str]
    plan: dict[str, Any]
    nodes: list[AgentStepResponse]
    edges: list[RunGraphEdge]
    timing: RunTimingSummary


class RunDiagnosticsResponse(BaseModel):
    graph: RunGraphResponse
    versions: dict[str, str | None]
    integrity: dict[str, str | int | bool | None]
    decision_summary: dict[str, Any]


class CopilotSessionCreate(BaseModel):
    current_path: str = Field(default="/", min_length=1, max_length=300)
    case_id: UUID | None = None

    @field_validator("current_path")
    @classmethod
    def validate_internal_path(cls, value: str) -> str:
        if not value.startswith("/") or value.startswith("//"):
            raise ValueError("Only internal application paths are allowed")
        return value


class CopilotSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    copilot_session_id: UUID
    context_case_id: UUID | None
    title: str
    help_pack_version: str
    status: str
    created_at: datetime
    updated_at: datetime


class CopilotAssistanceTarget(BaseModel):
    target_id: str = Field(
        min_length=3,
        max_length=120,
        pattern=r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$",
    )
    title: str = Field(min_length=2, max_length=120)
    description: str = Field(min_length=4, max_length=300)

    @field_validator("title", "description")
    @classmethod
    def normalize_and_mask_context(cls, value: str) -> str:
        return mask_sensitive_text(" ".join(value.split()))


class CopilotMessageRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1200)
    current_path: str = Field(default="/", min_length=1, max_length=300)
    case_id: UUID | None = None
    assistance_targets: list[CopilotAssistanceTarget] = Field(
        default_factory=list,
        max_length=40,
    )

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("current_path")
    @classmethod
    def validate_internal_path(cls, value: str) -> str:
        if not value.startswith("/") or value.startswith("//"):
            raise ValueError("Only internal application paths are allowed")
        return value


class CopilotCitation(BaseModel):
    source_id: str
    title: str
    help_pack_version: str


class CopilotUIAction(BaseModel):
    action_type: Literal[
        "NAVIGATE",
        "SPOTLIGHT",
        "OPEN_PANEL",
        "SET_FILTER",
        "START_TOUR",
    ]
    target: str
    label: str


class CopilotMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    copilot_message_id: UUID
    copilot_session_id: UUID
    role: Literal["USER", "ASSISTANT"]
    content: str
    citations: list[CopilotCitation]
    ui_actions: list[CopilotUIAction]
    provider: str
    model_version: str | None
    latency_ms: int | None
    error_code: str | None
    created_at: datetime


class CopilotFeedbackRequest(BaseModel):
    rating: Literal["HELPFUL", "NOT_HELPFUL"]
    reason: str | None = Field(default=None, max_length=800)

    @field_validator("reason")
    @classmethod
    def normalize_and_mask_reason(cls, value: str | None) -> str | None:
        if not value:
            return None
        return mask_sensitive_text(" ".join(value.split()))


class CopilotFeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    copilot_feedback_id: UUID
    copilot_message_id: UUID
    rating: Literal["HELPFUL", "NOT_HELPFUL"]
    reason_masked: str | None
    help_pack_version: str
    created_at: datetime


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
    edited_payload: dict[str, Any] = Field(
        default_factory=dict,
        json_schema_extra={"maxProperties": 0},
    )

    @field_validator("comment")
    @classmethod
    def require_comment_for_nonapproval(cls, value: str | None, info):
        decision = info.data.get("decision")
        if decision in {"REJECTED", "MORE_INFO", "ESCALATED"} and not value:
            raise ValueError("A comment is required for this decision")
        return mask_sensitive_text(" ".join(value.split())) if value else None

    @field_validator("edited_payload")
    @classmethod
    def reject_unverified_payload_edits(cls, value: dict[str, Any]):
        if value:
            raise ValueError(
                "Payload edits require field correction, reanalysis and a new evidence hash"
            )
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


class IntegrationCheck(BaseModel):
    status: Literal["HEALTHY", "DEGRADED", "UNAVAILABLE", "DISABLED"]
    error_code: str | None = None
    action: str | None = None
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class IntegrationHealthResponse(BaseModel):
    status: Literal["HEALTHY", "DEGRADED"]
    checks: dict[str, IntegrationCheck]


class SanctionsImportRequest(BaseModel):
    source: Literal["OFAC", "UN", "EU"]


class SanctionsImportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    sanctions_import_id: UUID
    source: str
    source_url: str
    status: str
    dataset_id: UUID | None
    etag: str | None
    sha256: str | None
    entity_count: int | None
    error_code: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class SanctionsDatasetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    dataset_id: UUID
    source: str
    version: str
    source_url: str
    sha256: str
    status: str
    published_at: datetime | None
    created_at: datetime


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


class ClarificationTaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    clarification_task_id: UUID
    case_id: UUID
    run_id: UUID
    status: str
    questions: list[dict[str, Any]]
    response: dict[str, Any]
    responded_by: UUID | None
    responded_at: datetime | None
    created_at: datetime


class InvoiceSubmissionRequest(BaseModel):
    invoice_number: str = Field(min_length=1, max_length=50)
    document_id: UUID | None = None
    document_ids: list[UUID] = Field(default_factory=list)
    priority: Literal["LOW", "NORMAL", "HIGH", "URGENT"] = "NORMAL"
    po_number: str | None = Field(default=None, max_length=50)
    vendor_id: UUID | None = None

    @model_validator(mode="after")
    def require_documents(self) -> "InvoiceSubmissionRequest":
        if not self.document_id and not self.document_ids:
            raise ValueError("At least one document is required")
        if len(set(self.document_ids)) > 10:
            raise ValueError("At most 10 documents may be submitted")
        return self


class InvoiceDraftRequest(BaseModel):
    invoice_number: str = Field(min_length=1, max_length=120)
    priority: Literal["LOW", "NORMAL", "HIGH", "URGENT"] = "NORMAL"
    po_number: str | None = Field(default=None, max_length=80)
    vendor_id: UUID | None = None
    currency: str = Field(default="LKR", min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")

    @field_validator("invoice_number")
    @classmethod
    def clean_invoice_number(cls, value: str) -> str:
        return " ".join(value.split())


MetricKey = Literal[
    "invoice_stp_rate",
    "invoice_cycle_hours",
    "vendor_onboarding_cycle_hours",
    "vendor_activation_rate",
    "invoice_exception_rate",
    "pending_approval_count",
]


class MetricValue(BaseModel):
    key: MetricKey
    label: str
    value: float | None
    unit: Literal["percent", "hours", "count"]
    numerator: int | None = None
    denominator: int | None = None
    previous_value: float | None = None
    definition: str
    statistics: dict[str, float | None] = Field(default_factory=dict)


class AnalyticsSummaryResponse(BaseModel):
    period_start: datetime
    period_end: datetime
    timezone: str
    metrics: list[MetricValue]
    approval_aging: dict[str, int]
    generated_at: datetime


class MetricPoint(BaseModel):
    period_start: datetime
    value: float | None
    numerator: int | None = None
    denominator: int | None = None


class MetricSeries(BaseModel):
    key: MetricKey
    grain: Literal["day", "week"]
    points: list[MetricPoint]


class MetricQuery(BaseModel):
    metric: MetricKey
    start: datetime | None = None
    end: datetime | None = None
    case_type: Literal["INVOICE_EXCEPTION", "VENDOR_ONBOARDING"] | None = None
    grain: Literal["day", "week"] = "week"


class AnalyticsQuestionRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)

    @field_validator("question")
    @classmethod
    def mask_question(cls, value: str) -> str:
        return mask_sensitive_text(" ".join(value.split()))


class AnalyticsQuestionResponse(BaseModel):
    answer: str
    query: MetricQuery
    metric: MetricValue
    citations: list[dict[str, str]]
    provider: Literal["GOVERNED_LOCAL", "GEMINI_STRUCTURED"]


class ExceptionBreakdown(BaseModel):
    exception_type: str
    severity: str
    count: int
    open_count: int


class ExceptionAnalyticsResponse(BaseModel):
    items: list[ExceptionBreakdown]
    total: int


RiskFindingType = Literal[
    "DUPLICATE_VENDOR",
    "DUPLICATE_INVOICE",
    "PRICE_ANOMALY",
    "QUANTITY_ANOMALY",
    "BANK_ACCOUNT_CHANGE",
    "VENDOR_MISMATCH",
    "LOW_CONFIDENCE_EXTRACTION",
    "MULTIPLE_EXCEPTIONS",
]
RiskFindingMode = Literal["ACTIVE", "SHADOW"]
RiskFindingDisposition = Literal[
    "CONFIRMED",
    "FALSE_POSITIVE",
    "ACCEPTED_RISK",
    "ESCALATED",
]


class RiskFindingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    risk_finding_id: UUID
    case_id: UUID | None
    subject_type: str
    subject_id: str | None
    finding_type: str
    severity: str
    mode: str
    data_origin: str
    detector_key: str
    detector_version: str
    score: float | None
    threshold: float | None
    reason_codes: list[str]
    feature_snapshot: dict[str, Any]
    explanation: dict[str, Any]
    evidence_refs: list[dict[str, Any]]
    status: str
    disposition: str | None
    disposition_reason: str | None
    reviewed_by: UUID | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RiskFindingDispositionRequest(BaseModel):
    disposition: RiskFindingDisposition
    reason: str = Field(min_length=3, max_length=1000)

    @field_validator("reason")
    @classmethod
    def mask_reason(cls, value: str) -> str:
        return mask_sensitive_text(" ".join(value.split()))


class AlertRuleCreate(BaseModel):
    rule_key: str = Field(
        min_length=3, max_length=100, pattern=r"^[A-Z0-9_]+$"
    )
    name: str = Field(min_length=3, max_length=160)
    description: str = Field(min_length=3, max_length=1000)
    rule_type: Literal[
        "EXCEPTION_AGING",
        "APPROVAL_AGING",
        "RISK_FINDING",
        "EXTRACTION_FAILURE",
    ]
    configuration: dict[str, Any] = Field(default_factory=dict)
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "MEDIUM"
    enabled: bool = True


class AlertRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=160)
    description: str | None = Field(
        default=None, min_length=3, max_length=1000
    )
    configuration: dict[str, Any] | None = None
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] | None = None
    enabled: bool | None = None


class AlertRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    alert_rule_id: UUID
    rule_key: str
    name: str
    description: str
    rule_type: str
    configuration: dict[str, Any]
    severity: str
    enabled: bool
    version: int
    created_at: datetime
    updated_at: datetime


class AlertInstanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    alert_instance_id: UUID
    alert_rule_id: UUID
    case_id: UUID | None
    risk_finding_id: UUID | None
    title: str
    body: str
    severity: str
    status: str
    grouping_key: str | None
    metric_snapshot: dict[str, Any]
    first_triggered_at: datetime
    last_triggered_at: datetime
    acknowledged_by: UUID | None
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ExtractionCandidate(BaseModel):
    field_name: str
    value_masked: str | None
    normalized_value: str | None
    source_page: int | None
    source_bbox: dict[str, Any] = Field(default_factory=dict)
    extractor_type: str
    extractor_version: str
    confidence: float | None = Field(default=None, ge=0, le=1)
    confidence_grade: Literal["POOR", "FAIR", "GOOD", "EXCELLENT", "UNKNOWN"]
    validations: list[dict[str, Any]] = Field(default_factory=list)
    human_verified: bool = False
