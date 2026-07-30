"""Store business thresholds as tenant configuration.

Spend approval bands, price tolerance, the expected tax rate, and the approved
country lists are policy, not implementation. Held as constants they cannot be
changed without a deployment, and cannot differ between tenants at all.

An absent row means "use the defaults", so this migration creates no rows.

Revision ID: c3445566ccdd
Revises: c2334455bbcc
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c3445566ccdd"
down_revision: str | None = "c2334455bbcc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenant_configurations",
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey("tenants.tenant_id"),
            primary_key=True,
        ),
        sa.Column(
            "configuration",
            postgresql.JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "updated_by",
            sa.Uuid(),
            sa.ForeignKey("users.user_id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.execute('ALTER TABLE "tenant_configurations" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "tenant_configurations" FORCE ROW LEVEL SECURITY')
    op.execute(
        """CREATE POLICY tenant_isolation_tenant_configurations
            ON "tenant_configurations"
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
    op.drop_table("tenant_configurations")
