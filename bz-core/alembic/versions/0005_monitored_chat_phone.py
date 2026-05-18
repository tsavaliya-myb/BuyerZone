"""add phone to monitored_chats

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-18
"""

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "monitored_chats",
        sa.Column("phone", sa.String(30), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("monitored_chats", "phone")
