"""Initial schema — all tables

Revision ID: 0001
Revises:
Create Date: 2026-04-16
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── admin_users ────────────────────────────────────────────────────────────
    op.create_table(
        "admin_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("username", sa.String(100), nullable=False, unique=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )

    # ── wholesalers ────────────────────────────────────────────────────────────
    op.create_table(
        "wholesalers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=True, unique=True),
        sa.Column("telegram_username", sa.String(100), nullable=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )

    # ── monitored_chats ────────────────────────────────────────────────────────
    op.create_table(
        "monitored_chats",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("chat_name", sa.String(255), nullable=False),
        sa.Column("chat_type", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "added_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("admin_users.id"),
            nullable=True,
        ),
        sa.Column("added_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )

    # ── products ───────────────────────────────────────────────────────────────
    op.create_table(
        "products",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("qdrant_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column(
            "wholesaler_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("wholesalers.id"),
            nullable=True,
        ),
        sa.Column(
            "chat_id",
            sa.BigInteger(),
            sa.ForeignKey("monitored_chats.chat_id"),
            nullable=True,
        ),
        sa.Column("telegram_msg_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(500), nullable=True),
        sa.Column("raw_caption", sa.Text(), nullable=True),
        sa.Column("price", sa.Numeric(10, 2), nullable=True),
        sa.Column("currency", sa.String(10), nullable=False, server_default="INR"),
        sa.Column("image_url", sa.Text(), nullable=False),
        sa.Column("image_key", sa.Text(), nullable=False),
        sa.Column("source_platform", sa.String(20), nullable=False, server_default="telegram"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("received_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_products_wholesaler", "products", ["wholesaler_id"])
    op.create_index("idx_products_status", "products", ["status"])
    op.create_index(
        "idx_products_received_at", "products", [sa.text("received_at DESC")]
    )

    # ── ingestion_logs ─────────────────────────────────────────────────────────
    op.create_table(
        "ingestion_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_msg_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("products.id"),
            nullable=True,
        ),
        sa.Column("processed_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("ingestion_logs")
    op.drop_index("idx_products_received_at", table_name="products")
    op.drop_index("idx_products_status", table_name="products")
    op.drop_index("idx_products_wholesaler", table_name="products")
    op.drop_table("products")
    op.drop_table("monitored_chats")
    op.drop_table("wholesalers")
    op.drop_table("admin_users")
