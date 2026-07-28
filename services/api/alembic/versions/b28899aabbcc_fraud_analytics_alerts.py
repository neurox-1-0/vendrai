"""Add fraud findings, analytics alert rules, and alert instances.

Revision ID: b28899aabbcc
Revises: a1778899aabb
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b28899aabbcc"
down_revision: str | None = "a1778899aabb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tenant_policy(table: str) -> None:
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


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    ]


def upgrade() -> None:
    op.add_column(
        "extracted_fields",
        sa.Column(
            "confidence_grade",
            sa.String(20),
            nullable=False,
            server_default="UNKNOWN",
        ),
    )
    op.add_column(
        "extracted_fields",
        sa.Column(
            "validation_results",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.create_table(
        "risk_findings",
        sa.Column("risk_finding_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey("tenants.tenant_id"),
            nullable=False,
        ),
        sa.Column(
            "case_id",
            sa.Uuid(),
            sa.ForeignKey("cases.case_id", ondelete="CASCADE"),
        ),
        sa.Column("subject_type", sa.String(30), nullable=False),
        sa.Column("subject_id", sa.Text()),
        sa.Column("finding_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False, server_default="MEDIUM"),
        sa.Column("mode", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column(
            "data_origin",
            sa.String(20),
            nullable=False,
            server_default="PRODUCTION",
        ),
        sa.Column("detector_key", sa.String(100), nullable=False),
        sa.Column("detector_version", sa.String(80), nullable=False),
        sa.Column(
            "model_version_id",
            sa.Uuid(),
            sa.ForeignKey("model_versions.model_version_id"),
        ),
        sa.Column("score", sa.Float()),
        sa.Column("threshold", sa.Float()),
        sa.Column(
            "reason_codes",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "feature_snapshot",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "explanation",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "evidence_refs",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("status", sa.String(30), nullable=False, server_default="OPEN"),
        sa.Column("disposition", sa.String(30)),
        sa.Column("disposition_reason", sa.Text()),
        sa.Column("reviewed_by", sa.Uuid(), sa.ForeignKey("users.user_id")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        *_timestamps(),
    )
    op.create_index("ix_risk_findings_tenant_id", "risk_findings", ["tenant_id"])
    op.create_index("ix_risk_findings_case_id", "risk_findings", ["case_id"])
    op.create_index(
        "ix_risk_findings_tenant_status_created",
        "risk_findings",
        ["tenant_id", "status", "created_at"],
    )
    op.create_index(
        "ix_risk_findings_tenant_type_severity",
        "risk_findings",
        ["tenant_id", "finding_type", "severity"],
    )

    op.create_table(
        "alert_rules",
        sa.Column("alert_rule_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey("tenants.tenant_id"),
            nullable=False,
        ),
        sa.Column("rule_key", sa.String(100), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("rule_type", sa.String(50), nullable=False),
        sa.Column(
            "configuration",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("severity", sa.String(20), nullable=False, server_default="MEDIUM"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        *_timestamps(),
        sa.UniqueConstraint("tenant_id", "rule_key"),
    )
    op.create_index("ix_alert_rules_tenant_id", "alert_rules", ["tenant_id"])
    op.create_index(
        "ix_alert_rules_tenant_enabled", "alert_rules", ["tenant_id", "enabled"]
    )

    op.create_table(
        "alert_instances",
        sa.Column("alert_instance_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey("tenants.tenant_id"),
            nullable=False,
        ),
        sa.Column(
            "alert_rule_id",
            sa.Uuid(),
            sa.ForeignKey("alert_rules.alert_rule_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "case_id",
            sa.Uuid(),
            sa.ForeignKey("cases.case_id", ondelete="CASCADE"),
        ),
        sa.Column(
            "risk_finding_id",
            sa.Uuid(),
            sa.ForeignKey("risk_findings.risk_finding_id", ondelete="SET NULL"),
        ),
        sa.Column("deduplication_key", sa.String(180), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False, server_default="MEDIUM"),
        sa.Column("status", sa.String(30), nullable=False, server_default="OPEN"),
        sa.Column("grouping_key", sa.String(120)),
        sa.Column(
            "metric_snapshot",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "first_triggered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "last_triggered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("acknowledged_by", sa.Uuid(), sa.ForeignKey("users.user_id")),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.UniqueConstraint("tenant_id", "deduplication_key"),
    )
    op.create_index(
        "ix_alert_instances_tenant_id", "alert_instances", ["tenant_id"]
    )
    op.create_index(
        "ix_alert_instances_alert_rule_id",
        "alert_instances",
        ["alert_rule_id"],
    )
    op.create_index(
        "ix_alert_instances_case_id", "alert_instances", ["case_id"]
    )
    op.create_index(
        "ix_alert_instances_risk_finding_id",
        "alert_instances",
        ["risk_finding_id"],
    )
    op.create_index(
        "ix_alert_instances_tenant_status_created",
        "alert_instances",
        ["tenant_id", "status", "created_at"],
    )

    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        op.execute(
            "CREATE INDEX ix_vendors_normalized_name_trgm "
            "ON vendors USING gin (normalized_legal_name gin_trgm_ops)"
        )
        for table in ("risk_findings", "alert_rules", "alert_instances"):
            _tenant_policy(table)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_vendors_normalized_name_trgm")
    op.drop_index(
        "ix_alert_instances_tenant_status_created",
        table_name="alert_instances",
    )
    op.drop_index(
        "ix_alert_instances_risk_finding_id", table_name="alert_instances"
    )
    op.drop_index("ix_alert_instances_case_id", table_name="alert_instances")
    op.drop_index(
        "ix_alert_instances_alert_rule_id", table_name="alert_instances"
    )
    op.drop_index("ix_alert_instances_tenant_id", table_name="alert_instances")
    op.drop_table("alert_instances")
    op.drop_index("ix_alert_rules_tenant_enabled", table_name="alert_rules")
    op.drop_index("ix_alert_rules_tenant_id", table_name="alert_rules")
    op.drop_table("alert_rules")
    op.drop_index(
        "ix_risk_findings_tenant_type_severity", table_name="risk_findings"
    )
    op.drop_index(
        "ix_risk_findings_tenant_status_created", table_name="risk_findings"
    )
    op.drop_index("ix_risk_findings_case_id", table_name="risk_findings")
    op.drop_index("ix_risk_findings_tenant_id", table_name="risk_findings")
    op.drop_table("risk_findings")
    op.drop_column("extracted_fields", "validation_results")
    op.drop_column("extracted_fields", "confidence_grade")
