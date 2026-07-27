"""Frozen pre-release NeuroX onboarding baseline.

Revision ID: fa2f4a40b692
Revises:

This migration is deliberately static. Historical migrations must never call
``Base.metadata.create_all`` because current ORM models include tables owned by
later revisions.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "fa2f4a40b692"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TENANT_TABLES = (
    "users",
    "vendors",
    "cases",
    "documents",
    "document_pages",
    "extracted_fields",
    "case_events",
    "outbox_events",
    "agent_runs",
    "agent_steps",
    "evidence_items",
    "episodic_memories",
    "prompt_versions",
    "model_versions",
    "evaluation_datasets",
    "evaluation_results",
    "approval_tasks",
    "approval_decisions",
    "notifications",
    "notification_deliveries",
    "audit_logs",
    "policy_documents",
    "policy_versions",
    "policy_chunks",
    "duplicate_candidates",
    "risk_checks",
    "clarification_tasks",
    "erp_operations",
    "inbox_receipts",
)


def _enable_tenant_isolation(table: str) -> None:
    op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f"""CREATE POLICY tenant_isolation_{table}
            ON "{table}"
            USING (
              tenant_id = NULLIF(
                current_setting('app.current_tenant_id', true), ''
              )::uuid
            )
            WITH CHECK (
              tenant_id = NULLIF(
                current_setting('app.current_tenant_id', true), ''
              )::uuid
            )"""
    )


def upgrade() -> None:
    op.create_table(
        "inbox_receipts",
        sa.Column("consumer_name", sa.String(length=100), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("consumer_name", "event_id"),
    )
    op.create_index(op.f("ix_inbox_receipts_tenant_id"), "inbox_receipts", ["tenant_id"], unique=False)
    op.create_table(
        "sanctions_datasets",
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("version", sa.String(length=80), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("dataset_id"),
        sa.UniqueConstraint("source", "version"),
    )
    op.create_table(
        "tenants",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "evaluation_datasets",
        sa.Column("evaluation_dataset_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("case_count", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.tenant_id"],
        ),
        sa.PrimaryKeyConstraint("evaluation_dataset_id"),
        sa.UniqueConstraint("tenant_id", "name", "version"),
    )
    op.create_index(op.f("ix_evaluation_datasets_tenant_id"), "evaluation_datasets", ["tenant_id"], unique=False)
    op.create_table(
        "model_versions",
        sa.Column("model_version_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("version", sa.String(length=80), nullable=False),
        sa.Column("configuration_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.tenant_id"],
        ),
        sa.PrimaryKeyConstraint("model_version_id"),
        sa.UniqueConstraint("tenant_id", "provider", "model_name", "version"),
    )
    op.create_index(op.f("ix_model_versions_tenant_id"), "model_versions", ["tenant_id"], unique=False)
    op.create_table(
        "outbox_events",
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("aggregate_type", sa.String(length=50), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("aggregate_version", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=180), nullable=False),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column("causation_id", sa.Uuid(), nullable=True),
        sa.Column("traceparent", sa.Text(), nullable=True),
        sa.Column(
            "payload", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=False
        ),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.tenant_id"],
        ),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint("tenant_id", "idempotency_key"),
    )
    op.create_index(op.f("ix_outbox_events_tenant_id"), "outbox_events", ["tenant_id"], unique=False)
    op.create_index("ix_outbox_unpublished", "outbox_events", ["published_at", "created_at"], unique=False)
    op.create_table(
        "policy_documents",
        sa.Column("policy_document_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("policy_code", sa.String(length=80), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("owner_department", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.tenant_id"],
        ),
        sa.PrimaryKeyConstraint("policy_document_id"),
        sa.UniqueConstraint("tenant_id", "policy_code"),
    )
    op.create_index(op.f("ix_policy_documents_tenant_id"), "policy_documents", ["tenant_id"], unique=False)
    op.create_table(
        "prompt_versions",
        sa.Column("prompt_version_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("prompt_name", sa.String(length=120), nullable=False),
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("template_hash", sa.String(length=64), nullable=False),
        sa.Column("output_schema_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.tenant_id"],
        ),
        sa.PrimaryKeyConstraint("prompt_version_id"),
        sa.UniqueConstraint("tenant_id", "prompt_name", "version"),
    )
    op.create_index(op.f("ix_prompt_versions_tenant_id"), "prompt_versions", ["tenant_id"], unique=False)
    op.create_table(
        "sanctions_entities",
        sa.Column("sanctions_entity_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(length=120), nullable=False),
        sa.Column("primary_name", sa.Text(), nullable=False),
        sa.Column("normalized_name", sa.Text(), nullable=False),
        sa.Column(
            "aliases", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=False
        ),
        sa.Column(
            "countries", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=False
        ),
        sa.ForeignKeyConstraint(["dataset_id"], ["sanctions_datasets.dataset_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("sanctions_entity_id"),
    )
    op.create_index(op.f("ix_sanctions_entities_dataset_id"), "sanctions_entities", ["dataset_id"], unique=False)
    op.create_index(
        op.f("ix_sanctions_entities_normalized_name"), "sanctions_entities", ["normalized_name"], unique=False
    )
    op.create_table(
        "users",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("external_subject", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column(
            "roles", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=False
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.tenant_id"],
        ),
        sa.PrimaryKeyConstraint("user_id"),
        sa.UniqueConstraint("tenant_id", "email"),
        sa.UniqueConstraint("tenant_id", "external_subject"),
    )
    op.create_index(op.f("ix_users_tenant_id"), "users", ["tenant_id"], unique=False)
    op.create_table(
        "vendors",
        sa.Column("vendor_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("legal_name", sa.Text(), nullable=False),
        sa.Column("normalized_legal_name", sa.Text(), nullable=False),
        sa.Column("tax_id_hash", sa.LargeBinary(), nullable=True),
        sa.Column("bank_account_hash", sa.LargeBinary(), nullable=True),
        sa.Column("registered_country", sa.String(length=2), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("erp_vendor_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.tenant_id"],
        ),
        sa.PrimaryKeyConstraint("vendor_id"),
        sa.UniqueConstraint("tenant_id", "erp_vendor_id"),
    )
    op.create_index(op.f("ix_vendors_normalized_legal_name"), "vendors", ["normalized_legal_name"], unique=False)
    op.create_index(op.f("ix_vendors_tenant_id"), "vendors", ["tenant_id"], unique=False)
    op.create_table(
        "cases",
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_number", sa.String(length=40), nullable=False),
        sa.Column("case_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("requester_user_id", sa.Uuid(), nullable=False),
        sa.Column("assigned_user_id", sa.Uuid(), nullable=True),
        sa.Column("vendor_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["assigned_user_id"],
            ["users.user_id"],
        ),
        sa.ForeignKeyConstraint(
            ["requester_user_id"],
            ["users.user_id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.tenant_id"],
        ),
        sa.ForeignKeyConstraint(
            ["vendor_id"],
            ["vendors.vendor_id"],
        ),
        sa.PrimaryKeyConstraint("case_id"),
        sa.UniqueConstraint("tenant_id", "case_number"),
    )
    op.create_index(op.f("ix_cases_tenant_id"), "cases", ["tenant_id"], unique=False)
    op.create_index("ix_cases_tenant_status", "cases", ["tenant_id", "status"], unique=False)
    op.create_table(
        "evaluation_results",
        sa.Column("evaluation_result_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("evaluation_dataset_id", sa.Uuid(), nullable=False),
        sa.Column("model_version_id", sa.Uuid(), nullable=True),
        sa.Column("prompt_version_id", sa.Uuid(), nullable=True),
        sa.Column(
            "metrics", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=False
        ),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("evaluator_type", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["evaluation_dataset_id"],
            ["evaluation_datasets.evaluation_dataset_id"],
        ),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["model_versions.model_version_id"],
        ),
        sa.ForeignKeyConstraint(
            ["prompt_version_id"],
            ["prompt_versions.prompt_version_id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.tenant_id"],
        ),
        sa.PrimaryKeyConstraint("evaluation_result_id"),
    )
    op.create_index(
        op.f("ix_evaluation_results_evaluation_dataset_id"),
        "evaluation_results",
        ["evaluation_dataset_id"],
        unique=False,
    )
    op.create_index(op.f("ix_evaluation_results_tenant_id"), "evaluation_results", ["tenant_id"], unique=False)
    op.create_table(
        "policy_versions",
        sa.Column("policy_version_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("policy_document_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("effective_date", sa.String(length=10), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["policy_document_id"], ["policy_documents.policy_document_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.tenant_id"],
        ),
        sa.PrimaryKeyConstraint("policy_version_id"),
        sa.UniqueConstraint("policy_document_id", "version"),
    )
    op.create_index(op.f("ix_policy_versions_tenant_id"), "policy_versions", ["tenant_id"], unique=False)
    op.create_table(
        "agent_runs",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("thread_id", sa.String(length=180), nullable=False),
        sa.Column("graph_name", sa.String(length=80), nullable=False),
        sa.Column("graph_version", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("current_node", sa.String(length=80), nullable=True),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column(
            "state_json", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=False
        ),
        sa.Column("model_name", sa.String(length=100), nullable=True),
        sa.Column("prompt_version", sa.String(length=80), nullable=True),
        sa.Column("input_hash", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.case_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.tenant_id"],
        ),
        sa.PrimaryKeyConstraint("run_id"),
        sa.UniqueConstraint("thread_id"),
    )
    op.create_index(op.f("ix_agent_runs_case_id"), "agent_runs", ["case_id"], unique=False)
    op.create_index(op.f("ix_agent_runs_tenant_id"), "agent_runs", ["tenant_id"], unique=False)
    op.create_table(
        "audit_logs",
        sa.Column("audit_log_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=True),
        sa.Column("actor_type", sa.String(length=30), nullable=False),
        sa.Column("actor_id", sa.Text(), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=80), nullable=False),
        sa.Column("resource_id", sa.Text(), nullable=True),
        sa.Column(
            "metadata", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=False
        ),
        sa.Column("previous_hash", sa.String(length=64), nullable=True),
        sa.Column("record_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.case_id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.tenant_id"],
        ),
        sa.PrimaryKeyConstraint("audit_log_id"),
    )
    op.create_index(op.f("ix_audit_logs_case_id"), "audit_logs", ["case_id"], unique=False)
    op.create_index(op.f("ix_audit_logs_tenant_id"), "audit_logs", ["tenant_id"], unique=False)
    op.create_table(
        "case_events",
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("actor_type", sa.String(length=30), nullable=False),
        sa.Column("actor_id", sa.Text(), nullable=True),
        sa.Column(
            "payload", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.case_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.tenant_id"],
        ),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint("tenant_id", "case_id", "sequence"),
    )
    op.create_index(op.f("ix_case_events_case_id"), "case_events", ["case_id"], unique=False)
    op.create_index(op.f("ix_case_events_tenant_id"), "case_events", ["tenant_id"], unique=False)
    op.create_table(
        "documents",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("document_type", sa.String(length=50), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("sanitized_filename", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("upload_token_hash", sa.String(length=64), nullable=False),
        sa.Column("malware_status", sa.String(length=32), nullable=False),
        sa.Column("processing_status", sa.String(length=40), nullable=False),
        sa.Column("parser_version", sa.String(length=80), nullable=True),
        sa.Column("ocr_version", sa.String(length=80), nullable=True),
        sa.Column("uploaded_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.case_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.tenant_id"],
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["users.user_id"],
        ),
        sa.PrimaryKeyConstraint("document_id"),
    )
    op.create_index(op.f("ix_documents_case_id"), "documents", ["case_id"], unique=False)
    op.create_index(op.f("ix_documents_tenant_id"), "documents", ["tenant_id"], unique=False)
    op.create_table(
        "duplicate_candidates",
        sa.Column("duplicate_candidate_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("vendor_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column(
            "signals", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=False
        ),
        sa.Column("review_required", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.case_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.tenant_id"],
        ),
        sa.ForeignKeyConstraint(
            ["vendor_id"],
            ["vendors.vendor_id"],
        ),
        sa.PrimaryKeyConstraint("duplicate_candidate_id"),
    )
    op.create_index(op.f("ix_duplicate_candidates_case_id"), "duplicate_candidates", ["case_id"], unique=False)
    op.create_index(op.f("ix_duplicate_candidates_tenant_id"), "duplicate_candidates", ["tenant_id"], unique=False)
    op.create_table(
        "episodic_memories",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("episodic_memory_id", sa.Uuid(), nullable=False),
        sa.Column("source_case_id", sa.Uuid(), nullable=False),
        sa.Column("source_evidence_hash", sa.String(length=64), nullable=False),
        sa.Column("deidentified_summary", sa.Text(), nullable=False),
        sa.Column("outcome", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["approved_by"],
            ["users.user_id"],
        ),
        sa.ForeignKeyConstraint(
            ["source_case_id"],
            ["cases.case_id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.tenant_id"],
        ),
        sa.PrimaryKeyConstraint("episodic_memory_id"),
    )
    op.create_index(op.f("ix_episodic_memories_source_case_id"), "episodic_memories", ["source_case_id"], unique=False)
    op.create_index(op.f("ix_episodic_memories_tenant_id"), "episodic_memories", ["tenant_id"], unique=False)
    op.create_table(
        "notifications",
        sa.Column("notification_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("case_id", sa.Uuid(), nullable=True),
        sa.Column("notification_type", sa.String(length=80), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.case_id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.tenant_id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
        ),
        sa.PrimaryKeyConstraint("notification_id"),
    )
    op.create_index(op.f("ix_notifications_tenant_id"), "notifications", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_notifications_user_id"), "notifications", ["user_id"], unique=False)
    op.create_table(
        "policy_chunks",
        sa.Column("policy_chunk_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("policy_version_id", sa.Uuid(), nullable=False),
        sa.Column("clause_id", sa.String(length=100), nullable=False),
        sa.Column(
            "heading_path",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("parent_content", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("qdrant_point_id", sa.String(length=100), nullable=True),
        sa.Column("acl", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["policy_version_id"], ["policy_versions.policy_version_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.tenant_id"],
        ),
        sa.PrimaryKeyConstraint("policy_chunk_id"),
    )
    op.create_index(op.f("ix_policy_chunks_policy_version_id"), "policy_chunks", ["policy_version_id"], unique=False)
    op.create_index(op.f("ix_policy_chunks_tenant_id"), "policy_chunks", ["tenant_id"], unique=False)
    op.create_table(
        "risk_checks",
        sa.Column("risk_check_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column(
            "dataset_versions",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("disposition", sa.String(length=40), nullable=False),
        sa.Column(
            "result", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.case_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.tenant_id"],
        ),
        sa.PrimaryKeyConstraint("risk_check_id"),
    )
    op.create_index(op.f("ix_risk_checks_case_id"), "risk_checks", ["case_id"], unique=False)
    op.create_index(op.f("ix_risk_checks_tenant_id"), "risk_checks", ["tenant_id"], unique=False)
    op.create_table(
        "agent_steps",
        sa.Column("step_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("node_name", sa.String(length=80), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column(
            "input_summary",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "output_summary",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "error", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=False
        ),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.run_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.tenant_id"],
        ),
        sa.PrimaryKeyConstraint("step_id"),
        sa.UniqueConstraint("run_id", "node_name", "attempt"),
    )
    op.create_index(op.f("ix_agent_steps_run_id"), "agent_steps", ["run_id"], unique=False)
    op.create_index(op.f("ix_agent_steps_tenant_id"), "agent_steps", ["tenant_id"], unique=False)
    op.create_table(
        "approval_tasks",
        sa.Column("approval_task_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("task_type", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("assigned_role", sa.String(length=60), nullable=False),
        sa.Column("assigned_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "proposed_action",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "evidence_packet",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("evidence_hash", sa.String(length=64), nullable=False),
        sa.Column("case_version", sa.Integer(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["assigned_user_id"],
            ["users.user_id"],
        ),
        sa.ForeignKeyConstraint(["case_id"], ["cases.case_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["agent_runs.run_id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.tenant_id"],
        ),
        sa.PrimaryKeyConstraint("approval_task_id"),
    )
    op.create_index(op.f("ix_approval_tasks_case_id"), "approval_tasks", ["case_id"], unique=False)
    op.create_index(op.f("ix_approval_tasks_tenant_id"), "approval_tasks", ["tenant_id"], unique=False)
    op.create_table(
        "clarification_tasks",
        sa.Column("clarification_task_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column(
            "questions", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=False
        ),
        sa.Column(
            "response", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=False
        ),
        sa.Column("responded_by", sa.Uuid(), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.case_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["responded_by"],
            ["users.user_id"],
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["agent_runs.run_id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.tenant_id"],
        ),
        sa.PrimaryKeyConstraint("clarification_task_id"),
    )
    op.create_index(op.f("ix_clarification_tasks_case_id"), "clarification_tasks", ["case_id"], unique=False)
    op.create_index(op.f("ix_clarification_tasks_tenant_id"), "clarification_tasks", ["tenant_id"], unique=False)
    op.create_table(
        "document_pages",
        sa.Column("page_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("text_content", sa.Text(), nullable=True),
        sa.Column(
            "layout_json", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=False
        ),
        sa.Column("ocr_confidence", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["documents.document_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.tenant_id"],
        ),
        sa.PrimaryKeyConstraint("page_id"),
        sa.UniqueConstraint("document_id", "page_number"),
    )
    op.create_index(op.f("ix_document_pages_tenant_id"), "document_pages", ["tenant_id"], unique=False)
    op.create_table(
        "evidence_items",
        sa.Column("evidence_item_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=True),
        sa.Column(
            "source_locator",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("claim", sa.Text(), nullable=False),
        sa.Column("reason_code", sa.String(length=100), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.case_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["agent_runs.run_id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.tenant_id"],
        ),
        sa.PrimaryKeyConstraint("evidence_item_id"),
    )
    op.create_index(op.f("ix_evidence_items_case_id"), "evidence_items", ["case_id"], unique=False)
    op.create_index(op.f("ix_evidence_items_tenant_id"), "evidence_items", ["tenant_id"], unique=False)
    op.create_table(
        "extracted_fields",
        sa.Column("extracted_field_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("field_name", sa.String(length=80), nullable=False),
        sa.Column("field_value_masked", sa.Text(), nullable=True),
        sa.Column("field_value_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("normalized_value", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("source_page", sa.Integer(), nullable=True),
        sa.Column(
            "source_bbox", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=False
        ),
        sa.Column("extractor_type", sa.String(length=80), nullable=False),
        sa.Column("extractor_version", sa.String(length=80), nullable=True),
        sa.Column("human_verified", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.document_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.tenant_id"],
        ),
        sa.PrimaryKeyConstraint("extracted_field_id"),
    )
    op.create_index(op.f("ix_extracted_fields_tenant_id"), "extracted_fields", ["tenant_id"], unique=False)
    op.create_table(
        "notification_deliveries",
        sa.Column("delivery_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("notification_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.String(length=30), nullable=False),
        sa.Column("destination_masked", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["notification_id"], ["notifications.notification_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("delivery_id"),
    )
    op.create_index(
        op.f("ix_notification_deliveries_tenant_id"), "notification_deliveries", ["tenant_id"], unique=False
    )
    op.create_table(
        "approval_decisions",
        sa.Column("approval_decision_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("approval_task_id", sa.Uuid(), nullable=False),
        sa.Column("decided_by", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(length=30), nullable=False),
        sa.Column(
            "edited_payload",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("evidence_hash", sa.String(length=64), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["approval_task_id"], ["approval_tasks.approval_task_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["decided_by"],
            ["users.user_id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.tenant_id"],
        ),
        sa.PrimaryKeyConstraint("approval_decision_id"),
        sa.UniqueConstraint("approval_task_id"),
    )
    op.create_index(op.f("ix_approval_decisions_tenant_id"), "approval_decisions", ["tenant_id"], unique=False)
    op.create_table(
        "erp_operations",
        sa.Column("erp_operation_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("approval_task_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=180), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column(
            "request_payload",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "response_payload",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("provider_reference", sa.String(length=120), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["approval_task_id"],
            ["approval_tasks.approval_task_id"],
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.case_id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.tenant_id"],
        ),
        sa.PrimaryKeyConstraint("erp_operation_id"),
        sa.UniqueConstraint("tenant_id", "idempotency_key"),
    )
    op.create_index(op.f("ix_erp_operations_case_id"), "erp_operations", ["case_id"], unique=False)
    op.create_index(op.f("ix_erp_operations_tenant_id"), "erp_operations", ["tenant_id"], unique=False)
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in TENANT_TABLES:
        _enable_tenant_isolation(table)
    op.execute("REVOKE UPDATE, DELETE ON audit_logs FROM PUBLIC")
    op.execute("GRANT SELECT, UPDATE ON outbox_events TO neurox_relay")
    op.execute(
        """CREATE OR REPLACE FUNCTION reject_audit_mutation()
        RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'audit_logs is append-only';
        END;
        $$ LANGUAGE plpgsql"""
    )
    op.execute(
        """CREATE TRIGGER audit_logs_append_only
          BEFORE UPDATE OR DELETE ON audit_logs
          FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()"""
    )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS audit_logs_append_only ON audit_logs")
        op.execute("DROP FUNCTION IF EXISTS reject_audit_mutation")
    op.drop_index(op.f("ix_erp_operations_tenant_id"), table_name="erp_operations")
    op.drop_index(op.f("ix_erp_operations_case_id"), table_name="erp_operations")
    op.drop_table("erp_operations")
    op.drop_index(op.f("ix_approval_decisions_tenant_id"), table_name="approval_decisions")
    op.drop_table("approval_decisions")
    op.drop_index(op.f("ix_notification_deliveries_tenant_id"), table_name="notification_deliveries")
    op.drop_table("notification_deliveries")
    op.drop_index(op.f("ix_extracted_fields_tenant_id"), table_name="extracted_fields")
    op.drop_table("extracted_fields")
    op.drop_index(op.f("ix_evidence_items_tenant_id"), table_name="evidence_items")
    op.drop_index(op.f("ix_evidence_items_case_id"), table_name="evidence_items")
    op.drop_table("evidence_items")
    op.drop_index(op.f("ix_document_pages_tenant_id"), table_name="document_pages")
    op.drop_table("document_pages")
    op.drop_index(op.f("ix_clarification_tasks_tenant_id"), table_name="clarification_tasks")
    op.drop_index(op.f("ix_clarification_tasks_case_id"), table_name="clarification_tasks")
    op.drop_table("clarification_tasks")
    op.drop_index(op.f("ix_approval_tasks_tenant_id"), table_name="approval_tasks")
    op.drop_index(op.f("ix_approval_tasks_case_id"), table_name="approval_tasks")
    op.drop_table("approval_tasks")
    op.drop_index(op.f("ix_agent_steps_tenant_id"), table_name="agent_steps")
    op.drop_index(op.f("ix_agent_steps_run_id"), table_name="agent_steps")
    op.drop_table("agent_steps")
    op.drop_index(op.f("ix_risk_checks_tenant_id"), table_name="risk_checks")
    op.drop_index(op.f("ix_risk_checks_case_id"), table_name="risk_checks")
    op.drop_table("risk_checks")
    op.drop_index(op.f("ix_policy_chunks_tenant_id"), table_name="policy_chunks")
    op.drop_index(op.f("ix_policy_chunks_policy_version_id"), table_name="policy_chunks")
    op.drop_table("policy_chunks")
    op.drop_index(op.f("ix_notifications_user_id"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_tenant_id"), table_name="notifications")
    op.drop_table("notifications")
    op.drop_index(op.f("ix_episodic_memories_tenant_id"), table_name="episodic_memories")
    op.drop_index(op.f("ix_episodic_memories_source_case_id"), table_name="episodic_memories")
    op.drop_table("episodic_memories")
    op.drop_index(op.f("ix_duplicate_candidates_tenant_id"), table_name="duplicate_candidates")
    op.drop_index(op.f("ix_duplicate_candidates_case_id"), table_name="duplicate_candidates")
    op.drop_table("duplicate_candidates")
    op.drop_index(op.f("ix_documents_tenant_id"), table_name="documents")
    op.drop_index(op.f("ix_documents_case_id"), table_name="documents")
    op.drop_table("documents")
    op.drop_index(op.f("ix_case_events_tenant_id"), table_name="case_events")
    op.drop_index(op.f("ix_case_events_case_id"), table_name="case_events")
    op.drop_table("case_events")
    op.drop_index(op.f("ix_audit_logs_tenant_id"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_case_id"), table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index(op.f("ix_agent_runs_tenant_id"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_case_id"), table_name="agent_runs")
    op.drop_table("agent_runs")
    op.drop_index(op.f("ix_policy_versions_tenant_id"), table_name="policy_versions")
    op.drop_table("policy_versions")
    op.drop_index(op.f("ix_evaluation_results_tenant_id"), table_name="evaluation_results")
    op.drop_index(op.f("ix_evaluation_results_evaluation_dataset_id"), table_name="evaluation_results")
    op.drop_table("evaluation_results")
    op.drop_index("ix_cases_tenant_status", table_name="cases")
    op.drop_index(op.f("ix_cases_tenant_id"), table_name="cases")
    op.drop_table("cases")
    op.drop_index(op.f("ix_vendors_tenant_id"), table_name="vendors")
    op.drop_index(op.f("ix_vendors_normalized_legal_name"), table_name="vendors")
    op.drop_table("vendors")
    op.drop_index(op.f("ix_users_tenant_id"), table_name="users")
    op.drop_table("users")
    op.drop_index(op.f("ix_sanctions_entities_normalized_name"), table_name="sanctions_entities")
    op.drop_index(op.f("ix_sanctions_entities_dataset_id"), table_name="sanctions_entities")
    op.drop_table("sanctions_entities")
    op.drop_index(op.f("ix_prompt_versions_tenant_id"), table_name="prompt_versions")
    op.drop_table("prompt_versions")
    op.drop_index(op.f("ix_policy_documents_tenant_id"), table_name="policy_documents")
    op.drop_table("policy_documents")
    op.drop_index("ix_outbox_unpublished", table_name="outbox_events")
    op.drop_index(op.f("ix_outbox_events_tenant_id"), table_name="outbox_events")
    op.drop_table("outbox_events")
    op.drop_index(op.f("ix_model_versions_tenant_id"), table_name="model_versions")
    op.drop_table("model_versions")
    op.drop_index(op.f("ix_evaluation_datasets_tenant_id"), table_name="evaluation_datasets")
    op.drop_table("evaluation_datasets")
    op.drop_table("tenants")
    op.drop_table("sanctions_datasets")
    op.drop_index(op.f("ix_inbox_receipts_tenant_id"), table_name="inbox_receipts")
    op.drop_table("inbox_receipts")
