import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, LargeBinary, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, Uuid

from app.database import Base


JSONType = JSON().with_variant(JSONB(), "postgresql")


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text)
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")


class User(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "external_subject"), UniqueConstraint("tenant_id", "email"))
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.tenant_id"), index=True)
    external_subject: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(Text)
    full_name: Mapped[str] = mapped_column(Text)
    roles: Mapped[list[str]] = mapped_column(JSONType, default=list)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")


class Vendor(Base, TimestampMixin):
    __tablename__ = "vendors"
    __table_args__ = (UniqueConstraint("tenant_id", "erp_vendor_id"),)
    vendor_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.tenant_id"), index=True)
    legal_name: Mapped[str] = mapped_column(Text)
    normalized_legal_name: Mapped[str] = mapped_column(Text, index=True)
    tax_id_hash: Mapped[bytes | None] = mapped_column(LargeBinary)
    bank_account_hash: Mapped[bytes | None] = mapped_column(LargeBinary)
    registered_country: Mapped[str | None] = mapped_column(String(2))
    status: Mapped[str] = mapped_column(String(32), default="PROPOSED")
    erp_vendor_id: Mapped[str | None] = mapped_column(Text)


class Case(Base, TimestampMixin):
    __tablename__ = "cases"
    __table_args__ = (UniqueConstraint("tenant_id", "case_number"), Index("ix_cases_tenant_status", "tenant_id", "status"))
    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.tenant_id"), index=True)
    case_number: Mapped[str] = mapped_column(String(40))
    case_type: Mapped[str] = mapped_column(String(40), default="VENDOR_ONBOARDING")
    status: Mapped[str] = mapped_column(String(40), default="DRAFT")
    requester_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.user_id"))
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.user_id"))
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vendors.vendor_id"))
    title: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(20), default="NORMAL")
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Document(Base, TimestampMixin):
    __tablename__ = "documents"
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.tenant_id"), index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.case_id", ondelete="CASCADE"), index=True)
    document_type: Mapped[str] = mapped_column(String(50), default="UNKNOWN")
    original_filename: Mapped[str] = mapped_column(Text)
    sanitized_filename: Mapped[str] = mapped_column(Text)
    mime_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    sha256: Mapped[str | None] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(Text)
    upload_token_hash: Mapped[str] = mapped_column(String(64))
    malware_status: Mapped[str] = mapped_column(String(32), default="PENDING")
    processing_status: Mapped[str] = mapped_column(String(40), default="INITIATED")
    parser_version: Mapped[str | None] = mapped_column(String(80))
    ocr_version: Mapped[str | None] = mapped_column(String(80))
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.user_id"))


class DocumentPage(Base):
    __tablename__ = "document_pages"
    __table_args__ = (UniqueConstraint("document_id", "page_number"),)
    page_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.tenant_id"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.document_id", ondelete="CASCADE"))
    page_number: Mapped[int] = mapped_column(Integer)
    text_content: Mapped[str | None] = mapped_column(Text)
    layout_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    ocr_confidence: Mapped[float | None]


class ExtractedField(Base, TimestampMixin):
    __tablename__ = "extracted_fields"
    extracted_field_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.tenant_id"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.document_id", ondelete="CASCADE"))
    field_name: Mapped[str] = mapped_column(String(80))
    field_value_masked: Mapped[str | None] = mapped_column(Text)
    field_value_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    normalized_value: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None]
    source_page: Mapped[int | None]
    source_bbox: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    extractor_type: Mapped[str] = mapped_column(String(80))
    extractor_version: Mapped[str | None] = mapped_column(String(80))
    human_verified: Mapped[bool] = mapped_column(Boolean, default=False)


class CaseEvent(Base):
    __tablename__ = "case_events"
    __table_args__ = (UniqueConstraint("tenant_id", "case_id", "sequence"),)
    event_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.tenant_id"), index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.case_id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(BigInteger)
    event_type: Mapped[str] = mapped_column(String(100))
    actor_type: Mapped[str] = mapped_column(String(30))
    actor_id: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key"), Index("ix_outbox_unpublished", "published_at", "created_at"))
    event_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.tenant_id"), index=True)
    aggregate_type: Mapped[str] = mapped_column(String(50))
    aggregate_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    aggregate_version: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(100))
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    idempotency_key: Mapped[str] = mapped_column(String(180))
    correlation_id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4)
    causation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    traceparent: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InboxReceipt(Base):
    __tablename__ = "inbox_receipts"
    consumer_name: Mapped[str] = mapped_column(String(100), primary_key=True)
    event_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AgentRun(Base, TimestampMixin):
    __tablename__ = "agent_runs"
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.tenant_id"), index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.case_id", ondelete="CASCADE"), index=True)
    thread_id: Mapped[str] = mapped_column(String(180), unique=True)
    graph_name: Mapped[str] = mapped_column(String(80), default="vendor_onboarding")
    graph_version: Mapped[str] = mapped_column(String(40), default="1.0.0")
    status: Mapped[str] = mapped_column(String(40), default="QUEUED")
    current_node: Mapped[str | None] = mapped_column(String(80))
    state_version: Mapped[int] = mapped_column(Integer, default=1)
    state_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    model_name: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(80))
    input_hash: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentStep(Base):
    __tablename__ = "agent_steps"
    __table_args__ = (UniqueConstraint("run_id", "node_name", "attempt"),)
    step_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.tenant_id"), index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_runs.run_id", ondelete="CASCADE"), index=True)
    node_name: Mapped[str] = mapped_column(String(80))
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(40))
    input_summary: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    output_summary: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    error: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    latency_ms: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GraphCheckpoint(Base):
    __tablename__ = "graph_checkpoints"
    __table_args__ = (UniqueConstraint("tenant_id", "thread_id", "checkpoint_namespace", "checkpoint_id"),)
    graph_checkpoint_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.tenant_id"), index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_runs.run_id", ondelete="CASCADE"), index=True)
    thread_id: Mapped[str] = mapped_column(String(180), index=True)
    checkpoint_namespace: Mapped[str] = mapped_column(String(120), default="")
    checkpoint_id: Mapped[str] = mapped_column(String(180))
    parent_checkpoint_id: Mapped[str | None] = mapped_column(String(180))
    state_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EpisodicMemory(Base, TimestampMixin):
    __tablename__ = "episodic_memories"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.tenant_id"), index=True)
    episodic_memory_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source_case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.case_id"), index=True)
    source_evidence_hash: Mapped[str] = mapped_column(String(64))
    deidentified_summary: Mapped[str] = mapped_column(Text)
    outcome: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(30), default="PENDING_REVIEW")
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.user_id"))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PromptVersion(Base, TimestampMixin):
    __tablename__ = "prompt_versions"
    __table_args__ = (UniqueConstraint("tenant_id", "prompt_name", "version"),)
    prompt_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.tenant_id"), index=True)
    prompt_name: Mapped[str] = mapped_column(String(120))
    version: Mapped[str] = mapped_column(String(40))
    template_hash: Mapped[str] = mapped_column(String(64))
    output_schema_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), default="DRAFT")


class ModelVersion(Base, TimestampMixin):
    __tablename__ = "model_versions"
    __table_args__ = (UniqueConstraint("tenant_id", "provider", "model_name", "version"),)
    model_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.tenant_id"), index=True)
    provider: Mapped[str] = mapped_column(String(80))
    model_name: Mapped[str] = mapped_column(String(120))
    version: Mapped[str] = mapped_column(String(80))
    configuration_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), default="EVALUATION_REQUIRED")


class EvaluationDataset(Base, TimestampMixin):
    __tablename__ = "evaluation_datasets"
    __table_args__ = (UniqueConstraint("tenant_id", "name", "version"),)
    evaluation_dataset_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.tenant_id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    version: Mapped[str] = mapped_column(String(40))
    case_count: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), default="DRAFT")


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"
    evaluation_result_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.tenant_id"), index=True)
    evaluation_dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evaluation_datasets.evaluation_dataset_id"), index=True)
    model_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("model_versions.model_version_id"))
    prompt_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("prompt_versions.prompt_version_id"))
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    passed: Mapped[bool] = mapped_column(Boolean)
    evaluator_type: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvidenceItem(Base):
    __tablename__ = "evidence_items"
    evidence_item_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.tenant_id"), index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.case_id", ondelete="CASCADE"), index=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agent_runs.run_id"))
    source_type: Mapped[str] = mapped_column(String(50))
    source_id: Mapped[str | None] = mapped_column(Text)
    source_locator: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    claim: Mapped[str] = mapped_column(Text)
    reason_code: Mapped[str] = mapped_column(String(100))
    confidence: Mapped[float | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ApprovalTask(Base, TimestampMixin):
    __tablename__ = "approval_tasks"
    approval_task_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.tenant_id"), index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.case_id", ondelete="CASCADE"), index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_runs.run_id"))
    task_type: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(40), default="PENDING")
    assigned_role: Mapped[str] = mapped_column(String(60), default="approver")
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.user_id"))
    proposed_action: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    evidence_packet: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    evidence_hash: Mapped[str] = mapped_column(String(64))
    case_version: Mapped[int] = mapped_column(Integer)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApprovalDecision(Base):
    __tablename__ = "approval_decisions"
    __table_args__ = (UniqueConstraint("approval_task_id"),)
    approval_decision_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.tenant_id"), index=True)
    approval_task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("approval_tasks.approval_task_id", ondelete="CASCADE"))
    decided_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.user_id"))
    decision: Mapped[str] = mapped_column(String(30))
    edited_payload: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    comment: Mapped[str | None] = mapped_column(Text)
    evidence_hash: Mapped[str] = mapped_column(String(64))
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"
    notification_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.tenant_id"), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.user_id"), index=True)
    case_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cases.case_id"))
    notification_type: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="UNREAD")
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"
    delivery_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    notification_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("notifications.notification_id", ondelete="CASCADE"))
    channel: Mapped[str] = mapped_column(String(30))
    destination_masked: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="PENDING")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"
    audit_log_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.tenant_id"), index=True)
    case_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cases.case_id"), index=True)
    actor_type: Mapped[str] = mapped_column(String(30))
    actor_id: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str] = mapped_column(String(100))
    resource_type: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    previous_hash: Mapped[str | None] = mapped_column(String(64))
    record_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PolicyDocument(Base, TimestampMixin):
    __tablename__ = "policy_documents"
    __table_args__ = (UniqueConstraint("tenant_id", "policy_code"),)
    policy_document_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.tenant_id"), index=True)
    policy_code: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(Text)
    owner_department: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), default="DRAFT")


class PolicyVersion(Base, TimestampMixin):
    __tablename__ = "policy_versions"
    __table_args__ = (UniqueConstraint("policy_document_id", "version"),)
    policy_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.tenant_id"), index=True)
    policy_document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("policy_documents.policy_document_id", ondelete="CASCADE"))
    version: Mapped[str] = mapped_column(String(40))
    effective_date: Mapped[str] = mapped_column(String(10))
    content_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), default="DRAFT")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PolicyChunk(Base, TimestampMixin):
    __tablename__ = "policy_chunks"
    policy_chunk_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.tenant_id"), index=True)
    policy_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("policy_versions.policy_version_id", ondelete="CASCADE"), index=True)
    clause_id: Mapped[str] = mapped_column(String(100))
    heading_path: Mapped[list[str]] = mapped_column(JSONType, default=list)
    parent_content: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer)
    qdrant_point_id: Mapped[str | None] = mapped_column(String(100))
    acl: Mapped[list[str]] = mapped_column(JSONType, default=list)


class SanctionsDataset(Base, TimestampMixin):
    __tablename__ = "sanctions_datasets"
    __table_args__ = (UniqueConstraint("source", "version"),)
    dataset_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(20))
    version: Mapped[str] = mapped_column(String(80))
    source_url: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), default="STAGED")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SanctionsEntityRecord(Base):
    __tablename__ = "sanctions_entities"
    sanctions_entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sanctions_datasets.dataset_id", ondelete="CASCADE"), index=True)
    external_id: Mapped[str] = mapped_column(String(120))
    primary_name: Mapped[str] = mapped_column(Text)
    normalized_name: Mapped[str] = mapped_column(Text, index=True)
    aliases: Mapped[list[str]] = mapped_column(JSONType, default=list)
    countries: Mapped[list[str]] = mapped_column(JSONType, default=list)


class DuplicateCandidateRecord(Base, TimestampMixin):
    __tablename__ = "duplicate_candidates"
    duplicate_candidate_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.tenant_id"), index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.case_id", ondelete="CASCADE"), index=True)
    vendor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vendors.vendor_id"))
    score: Mapped[float]
    signals: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    review_required: Mapped[bool] = mapped_column(Boolean)


class RiskCheck(Base, TimestampMixin):
    __tablename__ = "risk_checks"
    risk_check_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.tenant_id"), index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.case_id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(80))
    dataset_versions: Mapped[dict[str, str]] = mapped_column(JSONType, default=dict)
    status: Mapped[str] = mapped_column(String(30))
    disposition: Mapped[str] = mapped_column(String(40))
    result: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)


class ClarificationTask(Base, TimestampMixin):
    __tablename__ = "clarification_tasks"
    clarification_task_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.tenant_id"), index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.case_id", ondelete="CASCADE"), index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_runs.run_id"))
    status: Mapped[str] = mapped_column(String(30), default="OPEN")
    questions: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    response: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    responded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.user_id"))
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ErpOperation(Base, TimestampMixin):
    __tablename__ = "erp_operations"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key"),)
    erp_operation_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.tenant_id"), index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.case_id"), index=True)
    approval_task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("approval_tasks.approval_task_id"))
    idempotency_key: Mapped[str] = mapped_column(String(180))
    status: Mapped[str] = mapped_column(String(30), default="PENDING")
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    response_payload: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    provider_reference: Mapped[str | None] = mapped_column(String(120))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)


# ---------------------------------------------------------------------------
# AP Extension — Invoice Exception Handling (Blueprint §7.5)
# ---------------------------------------------------------------------------


class PurchaseOrder(Base, TimestampMixin):
    __tablename__ = "purchase_orders"
    __table_args__ = (UniqueConstraint("tenant_id", "po_number"),)
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.tenant_id"), index=True)
    vendor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vendors.vendor_id"), index=True)
    po_number: Mapped[str] = mapped_column(String(80))
    total_amount: Mapped[float]
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    status: Mapped[str] = mapped_column(String(30), default="OPEN")
    issued_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivery_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PurchaseOrderLine(Base):
    __tablename__ = "purchase_order_lines"
    __table_args__ = (UniqueConstraint("purchase_order_id", "line_number"),)
    po_line_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.tenant_id"), index=True)
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("purchase_orders.purchase_order_id", ondelete="CASCADE"), index=True)
    line_number: Mapped[int] = mapped_column(Integer)
    item_description: Mapped[str] = mapped_column(Text)
    quantity: Mapped[float]
    unit_price: Mapped[float]
    amount: Mapped[float]
    tax_rate: Mapped[float] = mapped_column(default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GoodsReceipt(Base, TimestampMixin):
    __tablename__ = "goods_receipts"
    __table_args__ = (UniqueConstraint("tenant_id", "grn_number"),)
    goods_receipt_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.tenant_id"), index=True)
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("purchase_orders.purchase_order_id"), index=True)
    grn_number: Mapped[str] = mapped_column(String(80))
    received_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_by: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="RECEIVED")


class GoodsReceiptLine(Base):
    __tablename__ = "goods_receipt_lines"
    __table_args__ = (UniqueConstraint("goods_receipt_id", "line_number"),)
    grn_line_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.tenant_id"), index=True)
    goods_receipt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("goods_receipts.goods_receipt_id", ondelete="CASCADE"), index=True)
    po_line_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("purchase_order_lines.po_line_id"), index=True)
    line_number: Mapped[int] = mapped_column(Integer)
    quantity_received: Mapped[float]
    quality_status: Mapped[str] = mapped_column(String(30), default="ACCEPTED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InvoiceRecord(Base, TimestampMixin):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("tenant_id", "invoice_number", "vendor_id"),
        Index("ix_invoices_tenant_vendor", "tenant_id", "vendor_id"),
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.tenant_id"), index=True)
    case_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cases.case_id"), index=True)
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vendors.vendor_id"), index=True)
    invoice_number: Mapped[str] = mapped_column(String(120))
    po_number: Mapped[str | None] = mapped_column(String(80))
    total_amount: Mapped[float]
    tax_amount: Mapped[float] = mapped_column(default=0.0)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    invoice_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payment_terms: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30), default="RECEIVED")


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"
    __table_args__ = (UniqueConstraint("invoice_id", "line_number"),)
    invoice_line_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.tenant_id"), index=True)
    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.invoice_id", ondelete="CASCADE"), index=True)
    line_number: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text)
    quantity: Mapped[float]
    unit_price: Mapped[float]
    amount: Mapped[float]
    tax_rate: Mapped[float] = mapped_column(default=0.0)
    po_line_ref: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InvoiceException(Base, TimestampMixin):
    __tablename__ = "invoice_exceptions"
    invoice_exception_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.tenant_id"), index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.case_id", ondelete="CASCADE"), index=True)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("invoices.invoice_id"), index=True)
    exception_type: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(20), default="MEDIUM")
    mismatch_details: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    variance_amount: Mapped[float | None]
    variance_pct: Mapped[float | None]
    tolerance_threshold_amount: Mapped[float | None]
    tolerance_threshold_pct: Mapped[float | None]
    within_tolerance: Mapped[bool | None] = mapped_column(Boolean)
    resolution_status: Mapped[str] = mapped_column(String(30), default="OPEN")
    resolution_details: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    policy_reference: Mapped[str | None] = mapped_column(Text)
