"""Record where each piece of evidence came from.

Without this column an uploaded purchase order and one read from the ERP are
indistinguishable downstream, so the case UI presents a document supplied by a
party to the transaction as if it were the system of record.

Existing rows are backfilled from their source_type, which already carries
enough information to classify them.

See plans/03-phase-2-correctness.md item 2.5.

Revision ID: c2334455bbcc
Revises: c1223344aabb
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c2334455bbcc"
down_revision: str | None = "c1223344aabb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Mirrors app/domain/provenance.SOURCE_TYPE_PROVENANCE. Duplicated on purpose:
# a migration must describe the schema as it was at this revision, not follow
# a module that will keep changing.
_BACKFILL: dict[str, str] = {
    "POLICY": "TENANT_POLICY",
    "POLICY_CLAUSE": "TENANT_POLICY",
    "VENDOR_MASTER": "ERP_SYSTEM_OF_RECORD",
    "INVOICE_HISTORY": "ERP_SYSTEM_OF_RECORD",
    "PURCHASE_ORDER": "ERP_SYSTEM_OF_RECORD",
    "GOODS_RECEIPT": "ERP_SYSTEM_OF_RECORD",
    "SANCTIONS_LIST": "EXTERNAL_OFFICIAL_LIST",
    "RISK_SERVICE": "EXTERNAL_OFFICIAL_LIST",
    "DOCUMENT": "USER_UPLOADED",
    "DOCUMENT_PAGE": "USER_UPLOADED",
    "EXTRACTED_FIELD": "USER_UPLOADED",
    "UPLOADED_PURCHASE_ORDER": "USER_UPLOADED",
    "UPLOADED_GOODS_RECEIPT": "USER_UPLOADED",
}


def upgrade() -> None:
    op.add_column(
        "evidence_items",
        sa.Column(
            "provenance",
            sa.String(length=40),
            nullable=False,
            # Unknown sources default to derived rather than authoritative:
            # nothing should become system-of-record by omission.
            server_default="DERIVED_BY_SYSTEM",
        ),
    )
    for source_type, provenance in _BACKFILL.items():
        op.execute(
            sa.text(
                "UPDATE evidence_items SET provenance = :provenance "
                "WHERE upper(source_type) = :source_type"
            ).bindparams(provenance=provenance, source_type=source_type)
        )


def downgrade() -> None:
    op.drop_column("evidence_items", "provenance")
