"""In-house products — new tables, separate from ingested products

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-31
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inhouse_products",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column(
            "keywords",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("admin_users.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.func.now()),
    )
    op.create_index("idx_inhouse_products_status", "inhouse_products", ["status"])
    op.create_index(
        "idx_inhouse_products_keywords",
        "inhouse_products",
        ["keywords"],
        postgresql_using="gin",
    )

    op.create_table(
        "inhouse_product_photos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("inhouse_products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now()),
    )
    op.create_index("idx_inhouse_photos_product", "inhouse_product_photos", ["product_id"])


def downgrade() -> None:
    op.drop_index("idx_inhouse_photos_product", table_name="inhouse_product_photos")
    op.drop_table("inhouse_product_photos")

    op.drop_index("idx_inhouse_products_keywords", table_name="inhouse_products")
    op.drop_index("idx_inhouse_products_status", table_name="inhouse_products")
    op.drop_table("inhouse_products")
