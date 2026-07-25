"""Add invoice history table.

Revision ID: fc2233445566
Revises: fb1122334455
"""

from collections.abc import Sequence

from alembic import op
from app import models  # noqa: F401 - registers mappings
from app.database import Base

revision: str = "fc2233445566"
down_revision: str | None = "fb1122334455"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)
    if bind.dialect.name == "postgresql":
        op.execute('ALTER TABLE "invoice_history" ENABLE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE "invoice_history" FORCE ROW LEVEL SECURITY')
        op.execute(
            '''CREATE POLICY tenant_isolation_invoice_history ON "invoice_history"
                USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
                WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)'''
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute('DROP POLICY IF EXISTS tenant_isolation_invoice_history ON "invoice_history"')
    op.execute('DROP TABLE IF EXISTS "invoice_history" CASCADE')
