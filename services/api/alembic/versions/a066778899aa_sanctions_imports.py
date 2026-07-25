"""Add durable tenant-scoped sanctions import jobs.

Revision ID: a066778899aa
Revises: ff5566778899
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a066778899aa"
down_revision: str | None = "ff5566778899"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("sanctions_imports"):
        op.create_table(
            "sanctions_imports",
            sa.Column("sanctions_import_id", sa.Uuid(), primary_key=True),
            sa.Column(
                "tenant_id",
                sa.Uuid(),
                sa.ForeignKey("tenants.tenant_id"),
                nullable=False,
            ),
            sa.Column("source", sa.String(20), nullable=False),
            sa.Column("source_url", sa.Text(), nullable=False),
            sa.Column(
                "status",
                sa.String(30),
                nullable=False,
                server_default="QUEUED",
            ),
            sa.Column(
                "requested_by",
                sa.Uuid(),
                sa.ForeignKey("users.user_id"),
                nullable=False,
            ),
            sa.Column(
                "dataset_id",
                sa.Uuid(),
                sa.ForeignKey("sanctions_datasets.dataset_id"),
            ),
            sa.Column("etag", sa.Text()),
            sa.Column("sha256", sa.String(64)),
            sa.Column("entity_count", sa.Integer()),
            sa.Column("error_code", sa.String(80)),
            sa.Column("started_at", sa.DateTime(timezone=True)),
            sa.Column("completed_at", sa.DateTime(timezone=True)),
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
        )
        op.create_index(
            "ix_sanctions_imports_tenant_id",
            "sanctions_imports",
            ["tenant_id"],
        )
    if bind.dialect.name == "postgresql":
        op.execute('ALTER TABLE "sanctions_imports" ENABLE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE "sanctions_imports" FORCE ROW LEVEL SECURITY')
        op.execute(
            "DROP POLICY IF EXISTS "
            "tenant_isolation_sanctions_imports ON sanctions_imports"
        )
        op.execute(
            """CREATE POLICY tenant_isolation_sanctions_imports
               ON sanctions_imports
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
    op.drop_index(
        "ix_sanctions_imports_tenant_id",
        table_name="sanctions_imports",
    )
    op.drop_table("sanctions_imports")
