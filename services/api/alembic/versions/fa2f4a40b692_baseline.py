"""Pre-release NeuroX onboarding baseline.

Revision ID: fa2f4a40b692
Revises:
"""

from collections.abc import Sequence

from alembic import op

from app.database import Base
from app import models  # noqa: F401 - registers mappings

revision: str = "fa2f4a40b692"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TENANT_TABLES = (
    "users", "vendors", "cases", "documents", "document_pages", "extracted_fields",
    "case_events", "outbox_events", "agent_runs", "agent_steps", "evidence_items",
    "graph_checkpoints", "episodic_memories", "prompt_versions", "model_versions",
    "evaluation_datasets", "evaluation_results",
    "approval_tasks", "approval_decisions", "notifications", "notification_deliveries", "audit_logs",
    "policy_documents", "policy_versions", "policy_chunks", "duplicate_candidates", "risk_checks",
    "clarification_tasks", "erp_operations", "inbox_receipts",
)


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=False)
    if bind.dialect.name != "postgresql":
        return
    for table in TENANT_TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'''CREATE POLICY tenant_isolation_{table} ON "{table}"
                USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
                WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)'''
        )
    op.execute("REVOKE UPDATE, DELETE ON audit_logs FROM PUBLIC")
    op.execute("GRANT SELECT, UPDATE ON outbox_events TO neurox_relay")
    op.execute(
        """CREATE OR REPLACE FUNCTION reject_audit_mutation() RETURNS trigger AS $$
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
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS audit_logs_append_only ON audit_logs")
        op.execute("DROP FUNCTION IF EXISTS reject_audit_mutation")
    Base.metadata.drop_all(bind=bind, checkfirst=True)
