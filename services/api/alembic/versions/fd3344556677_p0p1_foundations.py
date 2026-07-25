"""Add P0/P1 platform foundation records.

Revision ID: fd3344556677
Revises: fc2233445566
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "fd3344556677"
down_revision: str | None = "fc2233445566"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("idempotency_records"):
        op.create_table(
            "idempotency_records",
            sa.Column("idempotency_record_id", sa.Uuid(), nullable=False),
            sa.Column("tenant_id", sa.Uuid(), nullable=False),
            sa.Column("actor_id", sa.Uuid(), nullable=False),
            sa.Column("scope", sa.String(length=100), nullable=False),
            sa.Column("key_hash", sa.String(length=64), nullable=False),
            sa.Column("request_hash", sa.String(length=64), nullable=False),
            sa.Column("resource_id", sa.Uuid(), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["actor_id"], ["users.user_id"]),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"]),
            sa.PrimaryKeyConstraint("idempotency_record_id"),
            sa.UniqueConstraint(
                "tenant_id",
                "scope",
                "key_hash",
                name="uq_idempotency_tenant_scope_key",
            ),
        )
        op.create_index(
            "ix_idempotency_records_tenant_id",
            "idempotency_records",
            ["tenant_id"],
        )
        op.create_index(
            "ix_idempotency_expiry",
            "idempotency_records",
            ["expires_at"],
        )
    if bind.dialect.name == "postgresql":
        op.execute('ALTER TABLE "idempotency_records" ENABLE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE "idempotency_records" FORCE ROW LEVEL SECURITY')
        op.execute(
            """CREATE POLICY tenant_isolation_idempotency_records
               ON "idempotency_records"
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
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "DROP POLICY IF EXISTS "
            "tenant_isolation_idempotency_records ON idempotency_records"
        )
    op.drop_index("ix_idempotency_expiry", table_name="idempotency_records")
    op.drop_index(
        "ix_idempotency_records_tenant_id",
        table_name="idempotency_records",
    )
    op.drop_table("idempotency_records")
