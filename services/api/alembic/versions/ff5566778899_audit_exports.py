"""Add authorized, expiring audit export records.

Revision ID: ff5566778899
Revises: fe4455667788
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ff5566778899"
down_revision: str | None = "fe4455667788"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("audit_exports"):
        op.create_table(
            "audit_exports",
            sa.Column("audit_export_id", sa.Uuid(), primary_key=True),
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
                nullable=False,
            ),
            sa.Column(
                "requested_by",
                sa.Uuid(),
                sa.ForeignKey("users.user_id"),
                nullable=False,
            ),
            sa.Column("storage_key", sa.Text(), nullable=False),
            sa.Column("sha256", sa.String(64), nullable=False),
            sa.Column(
                "status",
                sa.String(30),
                nullable=False,
                server_default="READY",
            ),
            sa.Column(
                "expires_at",
                sa.DateTime(timezone=True),
                nullable=False,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
        )
        op.create_index(
            "ix_audit_exports_tenant_id",
            "audit_exports",
            ["tenant_id"],
        )
        op.create_index(
            "ix_audit_exports_case_id",
            "audit_exports",
            ["case_id"],
        )
    if bind.dialect.name == "postgresql":
        op.execute('ALTER TABLE "audit_exports" ENABLE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE "audit_exports" FORCE ROW LEVEL SECURITY')
        op.execute(
            """CREATE POLICY tenant_isolation_audit_exports
               ON audit_exports
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


def downgrade() -> None:
    op.drop_index("ix_audit_exports_case_id", table_name="audit_exports")
    op.drop_index("ix_audit_exports_tenant_id", table_name="audit_exports")
    op.drop_table("audit_exports")
