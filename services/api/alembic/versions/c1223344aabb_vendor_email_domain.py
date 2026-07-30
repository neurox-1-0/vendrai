"""Add vendors.email_domain so the duplicate email signal can fire.

``score_duplicate`` computes an ``email_domain_exact`` signal, but no vendor
row could ever supply the candidate side of that comparison because the column
did not exist. The signal was therefore permanently False - a real duplicate
signal, silently inert. The shipped vendor master already carries the data.

See plans/90-defect-register.md D-021.

Revision ID: c1223344aabb
Revises: b28899aabbcc
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c1223344aabb"
down_revision: str | None = "b28899aabbcc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("vendors", sa.Column("email_domain", sa.Text(), nullable=True))
    # Duplicate detection scans every vendor in the tenant, so the domain is
    # read on each candidate comparison.
    op.create_index(
        "ix_vendors_tenant_email_domain",
        "vendors",
        ["tenant_id", "email_domain"],
    )


def downgrade() -> None:
    op.drop_index("ix_vendors_tenant_email_domain", table_name="vendors")
    op.drop_column("vendors", "email_domain")
