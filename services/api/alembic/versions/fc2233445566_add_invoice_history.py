"""Add invoice history table.

Revision ID: fc2233445566
Revises: fb1122334455

This migration is deliberately static. Historical migrations must never call
``Base.metadata.create_all`` because mutable ORM metadata also contains tables
owned by later revisions.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "fc2233445566"
down_revision: str | None = "fb1122334455"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TENANT_TABLES = ("invoice_history",)


def upgrade() -> None:
    op.create_table(
        "invoice_history",
        sa.Column("record_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("vendor_id", sa.String(length=50), nullable=False),
        sa.Column("invoice_number", sa.String(length=120), nullable=False),
        sa.Column("invoice_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("gross_amount", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("po_number", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.tenant_id"],
        ),
        sa.PrimaryKeyConstraint("record_id"),
        sa.UniqueConstraint("tenant_id", "vendor_id", "invoice_number"),
    )
    op.create_index(op.f("ix_invoice_history_invoice_number"), "invoice_history", ["invoice_number"], unique=False)
    op.create_index(op.f("ix_invoice_history_tenant_id"), "invoice_history", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_invoice_history_vendor_id"), "invoice_history", ["vendor_id"], unique=False)
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in TENANT_TABLES:
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


def downgrade() -> None:
    op.drop_index(op.f("ix_invoice_history_vendor_id"), table_name="invoice_history")
    op.drop_index(op.f("ix_invoice_history_tenant_id"), table_name="invoice_history")
    op.drop_index(op.f("ix_invoice_history_invoice_number"), table_name="invoice_history")
    op.drop_table("invoice_history")
