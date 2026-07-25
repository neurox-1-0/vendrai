"""Add tenant-scoped application copilot sessions and messages.

Revision ID: a1778899aabb
Revises: a066778899aa
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1778899aabb"
down_revision: str | None = "a066778899aa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tenant_policy(table: str) -> None:
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


def upgrade() -> None:
    op.create_table(
        "copilot_sessions",
        sa.Column("copilot_session_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey("tenants.tenant_id"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.user_id"),
            nullable=False,
        ),
        sa.Column(
            "context_case_id",
            sa.Uuid(),
            sa.ForeignKey("cases.case_id", ondelete="SET NULL"),
        ),
        sa.Column(
            "title",
            sa.String(160),
            nullable=False,
            server_default="Application help",
        ),
        sa.Column("help_pack_version", sa.String(40), nullable=False),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default="ACTIVE",
        ),
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
        "ix_copilot_sessions_tenant_id",
        "copilot_sessions",
        ["tenant_id"],
    )
    op.create_index(
        "ix_copilot_sessions_user_id",
        "copilot_sessions",
        ["user_id"],
    )
    op.create_index(
        "ix_copilot_sessions_context_case_id",
        "copilot_sessions",
        ["context_case_id"],
    )
    op.create_index(
        "ix_copilot_sessions_tenant_user_updated",
        "copilot_sessions",
        ["tenant_id", "user_id", "updated_at"],
    )

    op.create_table(
        "copilot_messages",
        sa.Column("copilot_message_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey("tenants.tenant_id"),
            nullable=False,
        ),
        sa.Column(
            "copilot_session_id",
            sa.Uuid(),
            sa.ForeignKey(
                "copilot_sessions.copilot_session_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content_masked", sa.Text(), nullable=False),
        sa.Column(
            "citations",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "ui_actions",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "provider",
            sa.String(40),
            nullable=False,
            server_default="LOCAL_CAG",
        ),
        sa.Column("model_version", sa.String(120)),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("error_code", sa.String(80)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(
        "ix_copilot_messages_tenant_id",
        "copilot_messages",
        ["tenant_id"],
    )
    op.create_index(
        "ix_copilot_messages_copilot_session_id",
        "copilot_messages",
        ["copilot_session_id"],
    )
    op.create_index(
        "ix_copilot_messages_tenant_session_created",
        "copilot_messages",
        ["tenant_id", "copilot_session_id", "created_at"],
    )
    op.create_table(
        "copilot_feedback",
        sa.Column("copilot_feedback_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey("tenants.tenant_id"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.user_id"),
            nullable=False,
        ),
        sa.Column(
            "copilot_message_id",
            sa.Uuid(),
            sa.ForeignKey(
                "copilot_messages.copilot_message_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("rating", sa.String(20), nullable=False),
        sa.Column("reason_masked", sa.Text()),
        sa.Column("help_pack_version", sa.String(40), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("user_id", "copilot_message_id"),
    )
    op.create_index(
        "ix_copilot_feedback_tenant_id",
        "copilot_feedback",
        ["tenant_id"],
    )
    op.create_index(
        "ix_copilot_feedback_user_id",
        "copilot_feedback",
        ["user_id"],
    )
    op.create_index(
        "ix_copilot_feedback_copilot_message_id",
        "copilot_feedback",
        ["copilot_message_id"],
    )
    op.create_index(
        "ix_copilot_feedback_tenant_created",
        "copilot_feedback",
        ["tenant_id", "created_at"],
    )

    if op.get_bind().dialect.name == "postgresql":
        _tenant_policy("copilot_sessions")
        _tenant_policy("copilot_messages")
        _tenant_policy("copilot_feedback")


def downgrade() -> None:
    op.drop_index(
        "ix_copilot_feedback_tenant_created",
        table_name="copilot_feedback",
    )
    op.drop_index(
        "ix_copilot_feedback_copilot_message_id",
        table_name="copilot_feedback",
    )
    op.drop_index(
        "ix_copilot_feedback_user_id",
        table_name="copilot_feedback",
    )
    op.drop_index(
        "ix_copilot_feedback_tenant_id",
        table_name="copilot_feedback",
    )
    op.drop_table("copilot_feedback")
    op.drop_index(
        "ix_copilot_messages_tenant_session_created",
        table_name="copilot_messages",
    )
    op.drop_index(
        "ix_copilot_messages_copilot_session_id",
        table_name="copilot_messages",
    )
    op.drop_index(
        "ix_copilot_messages_tenant_id",
        table_name="copilot_messages",
    )
    op.drop_table("copilot_messages")
    op.drop_index(
        "ix_copilot_sessions_tenant_user_updated",
        table_name="copilot_sessions",
    )
    op.drop_index(
        "ix_copilot_sessions_context_case_id",
        table_name="copilot_sessions",
    )
    op.drop_index(
        "ix_copilot_sessions_user_id",
        table_name="copilot_sessions",
    )
    op.drop_index(
        "ix_copilot_sessions_tenant_id",
        table_name="copilot_sessions",
    )
    op.drop_table("copilot_sessions")
