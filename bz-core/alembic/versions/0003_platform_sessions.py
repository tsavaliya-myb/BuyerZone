"""platform_sessions table for Telegram + WhatsApp auth state

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-08
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("phone_number", sa.String(20), nullable=False),
        sa.Column("session_data", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("session_metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("admin_users.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("platform", "phone_number", name="uq_platform_sessions_platform_phone"),
    )
    op.create_index(
        "uq_platform_sessions_one_active_per_platform",
        "platform_sessions",
        ["platform"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_platform_sessions_one_active_per_platform",
        table_name="platform_sessions",
    )
    op.drop_table("platform_sessions")
