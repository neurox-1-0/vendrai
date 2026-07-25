"""Install the official LangGraph PostgreSQL checkpoint schema.

Revision ID: fe4455667788
Revises: fd3344556677
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "fe4455667788"
down_revision: str | None = "fd3344556677"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


CHECKPOINT_TABLES = ("checkpoints", "checkpoint_blobs", "checkpoint_writes")


def _tenant_policy(table: str) -> None:
    op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f"""CREATE POLICY tenant_isolation_{table} ON "{table}"
            USING (
              split_part(thread_id, ':', 1) =
              NULLIF(current_setting('app.current_tenant_id', true), '')
            )
            WITH CHECK (
              split_part(thread_id, ':', 1) =
              NULLIF(current_setting('app.current_tenant_id', true), '')
            )"""
    )
    op.execute(f'REVOKE ALL ON TABLE "{table}" FROM PUBLIC')
    op.execute(f'REVOKE ALL ON TABLE "{table}" FROM neurox_app')
    op.execute(f'REVOKE ALL ON TABLE "{table}" FROM neurox_relay')
    op.execute(f'REVOKE ALL ON TABLE "{table}" FROM neurox_audit')
    op.execute(
        f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE "{table}" '
        "TO neurox_worker"
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("graph_checkpoints"):
        op.drop_table("graph_checkpoints")

    op.create_table(
        "checkpoint_migrations",
        sa.Column("v", sa.Integer(), primary_key=True),
    )
    op.create_table(
        "checkpoints",
        sa.Column("thread_id", sa.Text(), nullable=False),
        sa.Column("checkpoint_ns", sa.Text(), nullable=False, server_default=""),
        sa.Column("checkpoint_id", sa.Text(), nullable=False),
        sa.Column("parent_checkpoint_id", sa.Text()),
        sa.Column("type", sa.Text()),
        sa.Column("checkpoint", postgresql.JSONB(), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.PrimaryKeyConstraint("thread_id", "checkpoint_ns", "checkpoint_id"),
    )
    op.create_table(
        "checkpoint_blobs",
        sa.Column("thread_id", sa.Text(), nullable=False),
        sa.Column("checkpoint_ns", sa.Text(), nullable=False, server_default=""),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("blob", sa.LargeBinary()),
        sa.PrimaryKeyConstraint(
            "thread_id", "checkpoint_ns", "channel", "version"
        ),
    )
    op.create_table(
        "checkpoint_writes",
        sa.Column("thread_id", sa.Text(), nullable=False),
        sa.Column("checkpoint_ns", sa.Text(), nullable=False, server_default=""),
        sa.Column("checkpoint_id", sa.Text(), nullable=False),
        sa.Column("task_id", sa.Text(), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("type", sa.Text()),
        sa.Column("blob", sa.LargeBinary(), nullable=False),
        sa.Column("task_path", sa.Text(), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint(
            "thread_id",
            "checkpoint_ns",
            "checkpoint_id",
            "task_id",
            "idx",
        ),
    )
    for table in CHECKPOINT_TABLES:
        op.create_index(f"{table}_thread_id_idx", table, ["thread_id"])

    # Mark the schema as compatible with checkpoint-postgres migration 9.
    op.bulk_insert(
        sa.table("checkpoint_migrations", sa.column("v", sa.Integer())),
        [{"v": version} for version in range(10)],
    )
    if bind.dialect.name == "postgresql":
        for table in CHECKPOINT_TABLES:
            _tenant_policy(table)
        op.execute("REVOKE ALL ON TABLE checkpoint_migrations FROM PUBLIC")
        op.execute(
            "GRANT SELECT ON TABLE checkpoint_migrations TO neurox_worker"
        )


def downgrade() -> None:
    for table in reversed(CHECKPOINT_TABLES):
        op.drop_index(f"{table}_thread_id_idx", table_name=table)
        op.drop_table(table)
    op.drop_table("checkpoint_migrations")
