"""products: make qdrant_id, image_url, image_key nullable (text-only messages)

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-16
"""

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "products",
        "qdrant_id",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    op.alter_column("products", "image_url", existing_type=sa.Text(), nullable=True)
    op.alter_column("products", "image_key", existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    op.alter_column("products", "image_key", existing_type=sa.Text(), nullable=False)
    op.alter_column("products", "image_url", existing_type=sa.Text(), nullable=False)
    op.alter_column(
        "products",
        "qdrant_id",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=False,
    )
