"""Add invoice exception tables.

Revision ID: fb1122334455
Revises: fa2f4a40b692
"""

from collections.abc import Sequence

from alembic import op

from app.database import Base
from app import models  # noqa: F401 - registers mappings

revision: str = "fb1122334455"
down_revision: str | None = "fa2f4a40b692"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_TENANT_TABLES = (
    "purchase_orders",
    "purchase_order_lines",
    "goods_receipts",
    "goods_receipt_lines",
    "invoices",
    "invoice_lines",
    "invoice_exceptions",
    "invoice_history",
)

def upgrade() -> None:
    bind = op.get_bind()
    # Create the new tables defined in models.py that don't exist yet
    Base.metadata.create_all(bind=bind, checkfirst=True)
    
    if bind.dialect.name != "postgresql":
        return
        
    for table in NEW_TENANT_TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'''CREATE POLICY tenant_isolation_{table} ON "{table}"
                USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
                WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)'''
        )

def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in NEW_TENANT_TABLES:
            op.execute(f'DROP POLICY IF EXISTS tenant_isolation_{table} ON "{table}"')
    
    # We explicitly drop the new tables since Base.metadata.drop_all drops everything
    for table in reversed(NEW_TENANT_TABLES):
        op.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
