"""Add invoice exception tables.

Revision ID: fb1122334455
Revises: fa2f4a40b692

This migration is deliberately static. Historical migrations must never call
``Base.metadata.create_all`` because mutable ORM metadata also contains tables
owned by later revisions.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "fb1122334455"
down_revision: str | None = "fa2f4a40b692"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TENANT_TABLES = (
    "goods_receipt_lines",
    "goods_receipts",
    "invoice_exceptions",
    "invoice_lines",
    "invoices",
    "purchase_order_lines",
    "purchase_orders",
)


def upgrade() -> None:
    op.create_table(
        "purchase_orders",
        sa.Column("purchase_order_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("vendor_id", sa.Uuid(), nullable=False),
        sa.Column("po_number", sa.String(length=80), nullable=False),
        sa.Column("total_amount", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("issued_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivery_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.tenant_id"],
        ),
        sa.ForeignKeyConstraint(
            ["vendor_id"],
            ["vendors.vendor_id"],
        ),
        sa.PrimaryKeyConstraint("purchase_order_id"),
        sa.UniqueConstraint("tenant_id", "po_number"),
    )
    op.create_index(op.f("ix_purchase_orders_tenant_id"), "purchase_orders", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_purchase_orders_vendor_id"), "purchase_orders", ["vendor_id"], unique=False)
    op.create_table(
        "goods_receipts",
        sa.Column("goods_receipt_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("purchase_order_id", sa.Uuid(), nullable=False),
        sa.Column("grn_number", sa.String(length=80), nullable=False),
        sa.Column("received_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_by", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["purchase_order_id"],
            ["purchase_orders.purchase_order_id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.tenant_id"],
        ),
        sa.PrimaryKeyConstraint("goods_receipt_id"),
        sa.UniqueConstraint("tenant_id", "grn_number"),
    )
    op.create_index(op.f("ix_goods_receipts_purchase_order_id"), "goods_receipts", ["purchase_order_id"], unique=False)
    op.create_index(op.f("ix_goods_receipts_tenant_id"), "goods_receipts", ["tenant_id"], unique=False)
    op.create_table(
        "invoices",
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=True),
        sa.Column("vendor_id", sa.Uuid(), nullable=True),
        sa.Column("invoice_number", sa.String(length=120), nullable=False),
        sa.Column("po_number", sa.String(length=80), nullable=True),
        sa.Column("total_amount", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("tax_amount", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("invoice_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payment_terms", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
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
            ["vendor_id"],
            ["vendors.vendor_id"],
        ),
        sa.PrimaryKeyConstraint("invoice_id"),
        sa.UniqueConstraint("tenant_id", "invoice_number", "vendor_id"),
    )
    op.create_index(op.f("ix_invoices_case_id"), "invoices", ["case_id"], unique=False)
    op.create_index(op.f("ix_invoices_tenant_id"), "invoices", ["tenant_id"], unique=False)
    op.create_index("ix_invoices_tenant_vendor", "invoices", ["tenant_id", "vendor_id"], unique=False)
    op.create_index(op.f("ix_invoices_vendor_id"), "invoices", ["vendor_id"], unique=False)
    op.create_table(
        "purchase_order_lines",
        sa.Column("po_line_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("purchase_order_id", sa.Uuid(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("item_description", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("amount", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("tax_rate", sa.Numeric(precision=9, scale=4), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["purchase_order_id"], ["purchase_orders.purchase_order_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.tenant_id"],
        ),
        sa.PrimaryKeyConstraint("po_line_id"),
        sa.UniqueConstraint("purchase_order_id", "line_number"),
    )
    op.create_index(
        op.f("ix_purchase_order_lines_purchase_order_id"), "purchase_order_lines", ["purchase_order_id"], unique=False
    )
    op.create_index(op.f("ix_purchase_order_lines_tenant_id"), "purchase_order_lines", ["tenant_id"], unique=False)
    op.create_table(
        "goods_receipt_lines",
        sa.Column("grn_line_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("goods_receipt_id", sa.Uuid(), nullable=False),
        sa.Column("po_line_id", sa.Uuid(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("quantity_received", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("quality_status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["goods_receipt_id"], ["goods_receipts.goods_receipt_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["po_line_id"],
            ["purchase_order_lines.po_line_id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.tenant_id"],
        ),
        sa.PrimaryKeyConstraint("grn_line_id"),
        sa.UniqueConstraint("goods_receipt_id", "line_number"),
    )
    op.create_index(
        op.f("ix_goods_receipt_lines_goods_receipt_id"), "goods_receipt_lines", ["goods_receipt_id"], unique=False
    )
    op.create_index(op.f("ix_goods_receipt_lines_po_line_id"), "goods_receipt_lines", ["po_line_id"], unique=False)
    op.create_index(op.f("ix_goods_receipt_lines_tenant_id"), "goods_receipt_lines", ["tenant_id"], unique=False)
    op.create_table(
        "invoice_exceptions",
        sa.Column("invoice_exception_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), nullable=True),
        sa.Column("exception_type", sa.String(length=40), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column(
            "mismatch_details",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("variance_amount", sa.Numeric(precision=19, scale=4), nullable=True),
        sa.Column("variance_pct", sa.Numeric(precision=9, scale=4), nullable=True),
        sa.Column("tolerance_threshold_amount", sa.Numeric(precision=19, scale=4), nullable=True),
        sa.Column("tolerance_threshold_pct", sa.Numeric(precision=9, scale=4), nullable=True),
        sa.Column("within_tolerance", sa.Boolean(), nullable=True),
        sa.Column("resolution_status", sa.String(length=30), nullable=False),
        sa.Column(
            "resolution_details",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("policy_reference", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.case_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["invoice_id"],
            ["invoices.invoice_id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.tenant_id"],
        ),
        sa.PrimaryKeyConstraint("invoice_exception_id"),
    )
    op.create_index(op.f("ix_invoice_exceptions_case_id"), "invoice_exceptions", ["case_id"], unique=False)
    op.create_index(op.f("ix_invoice_exceptions_invoice_id"), "invoice_exceptions", ["invoice_id"], unique=False)
    op.create_index(op.f("ix_invoice_exceptions_tenant_id"), "invoice_exceptions", ["tenant_id"], unique=False)
    op.create_table(
        "invoice_lines",
        sa.Column("invoice_line_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("amount", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("tax_rate", sa.Numeric(precision=9, scale=4), nullable=False),
        sa.Column("po_line_ref", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.invoice_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.tenant_id"],
        ),
        sa.PrimaryKeyConstraint("invoice_line_id"),
        sa.UniqueConstraint("invoice_id", "line_number"),
    )
    op.create_index(op.f("ix_invoice_lines_invoice_id"), "invoice_lines", ["invoice_id"], unique=False)
    op.create_index(op.f("ix_invoice_lines_tenant_id"), "invoice_lines", ["tenant_id"], unique=False)
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
    op.drop_index(op.f("ix_invoice_lines_tenant_id"), table_name="invoice_lines")
    op.drop_index(op.f("ix_invoice_lines_invoice_id"), table_name="invoice_lines")
    op.drop_table("invoice_lines")
    op.drop_index(op.f("ix_invoice_exceptions_tenant_id"), table_name="invoice_exceptions")
    op.drop_index(op.f("ix_invoice_exceptions_invoice_id"), table_name="invoice_exceptions")
    op.drop_index(op.f("ix_invoice_exceptions_case_id"), table_name="invoice_exceptions")
    op.drop_table("invoice_exceptions")
    op.drop_index(op.f("ix_goods_receipt_lines_tenant_id"), table_name="goods_receipt_lines")
    op.drop_index(op.f("ix_goods_receipt_lines_po_line_id"), table_name="goods_receipt_lines")
    op.drop_index(op.f("ix_goods_receipt_lines_goods_receipt_id"), table_name="goods_receipt_lines")
    op.drop_table("goods_receipt_lines")
    op.drop_index(op.f("ix_purchase_order_lines_tenant_id"), table_name="purchase_order_lines")
    op.drop_index(op.f("ix_purchase_order_lines_purchase_order_id"), table_name="purchase_order_lines")
    op.drop_table("purchase_order_lines")
    op.drop_index(op.f("ix_invoices_vendor_id"), table_name="invoices")
    op.drop_index("ix_invoices_tenant_vendor", table_name="invoices")
    op.drop_index(op.f("ix_invoices_tenant_id"), table_name="invoices")
    op.drop_index(op.f("ix_invoices_case_id"), table_name="invoices")
    op.drop_table("invoices")
    op.drop_index(op.f("ix_goods_receipts_tenant_id"), table_name="goods_receipts")
    op.drop_index(op.f("ix_goods_receipts_purchase_order_id"), table_name="goods_receipts")
    op.drop_table("goods_receipts")
    op.drop_index(op.f("ix_purchase_orders_vendor_id"), table_name="purchase_orders")
    op.drop_index(op.f("ix_purchase_orders_tenant_id"), table_name="purchase_orders")
    op.drop_table("purchase_orders")
