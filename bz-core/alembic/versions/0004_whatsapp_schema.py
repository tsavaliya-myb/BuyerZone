"""WhatsApp schema changes — platform column, message_id rename, wa_jid

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-08
"""

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NOTE: products_chat_id_fkey was dropped manually before this migration.
    # The commented-out line below is kept for documentation.
    op.drop_constraint("products_chat_id_fkey", "products", type_="foreignkey")

    # ── monitored_chats ────────────────────────────────────────────────────────
    op.drop_constraint("monitored_chats_chat_id_key", "monitored_chats", type_="unique")
    op.alter_column(
        "monitored_chats",
        "chat_id",
        type_=sa.Text(),
        existing_type=sa.BigInteger(),
        postgresql_using="chat_id::text",
    )
    op.add_column(
        "monitored_chats",
        sa.Column("platform", sa.String(20), nullable=False, server_default="telegram"),
    )
    op.create_unique_constraint(
        "monitored_chats_chat_id_platform_unique", "monitored_chats", ["chat_id", "platform"]
    )

    # ── products: change chat_id type, then rename telegram_msg_id ─────────────
    op.alter_column(
        "products",
        "chat_id",
        type_=sa.Text(),
        existing_type=sa.BigInteger(),
        existing_nullable=True,
        postgresql_using="chat_id::text",
    )
    # Split into two steps: type change first, then rename
    op.alter_column(
        "products",
        "telegram_msg_id",
        type_=sa.Text(),
        existing_type=sa.BigInteger(),
        postgresql_using="telegram_msg_id::text",
    )
    op.alter_column(
        "products",
        "telegram_msg_id",
        new_column_name="message_id",
    )

    # ── ingestion_logs: change chat_id type, then rename telegram_msg_id ───────
    op.alter_column(
        "ingestion_logs",
        "chat_id",
        type_=sa.Text(),
        existing_type=sa.BigInteger(),
        postgresql_using="chat_id::text",
    )
    op.alter_column(
        "ingestion_logs",
        "telegram_msg_id",
        type_=sa.Text(),
        existing_type=sa.BigInteger(),
        postgresql_using="telegram_msg_id::text",
    )
    op.alter_column(
        "ingestion_logs",
        "telegram_msg_id",
        new_column_name="message_id",
    )

    # ── wholesalers ────────────────────────────────────────────────────────────
    op.add_column(
        "wholesalers",
        sa.Column("wa_jid", sa.String(100), nullable=True, unique=True),
    )


def downgrade() -> None:
    op.drop_column("wholesalers", "wa_jid")

    op.alter_column("ingestion_logs", "message_id", new_column_name="telegram_msg_id")
    op.alter_column(
        "ingestion_logs",
        "telegram_msg_id",
        type_=sa.BigInteger(),
        existing_type=sa.Text(),
        postgresql_using="telegram_msg_id::bigint",
    )
    op.alter_column(
        "ingestion_logs",
        "chat_id",
        type_=sa.BigInteger(),
        existing_type=sa.Text(),
        postgresql_using="chat_id::bigint",
    )

    op.alter_column("products", "message_id", new_column_name="telegram_msg_id")
    op.alter_column(
        "products",
        "telegram_msg_id",
        type_=sa.BigInteger(),
        existing_type=sa.Text(),
        postgresql_using="telegram_msg_id::bigint",
    )
    op.alter_column(
        "products",
        "chat_id",
        type_=sa.BigInteger(),
        existing_type=sa.Text(),
        existing_nullable=True,
        postgresql_using="chat_id::bigint",
    )

    op.drop_constraint("monitored_chats_chat_id_platform_unique", "monitored_chats", type_="unique")
    op.drop_column("monitored_chats", "platform")
    op.alter_column(
        "monitored_chats",
        "chat_id",
        type_=sa.BigInteger(),
        existing_type=sa.Text(),
        postgresql_using="chat_id::bigint",
    )
    op.create_unique_constraint("monitored_chats_chat_id_key", "monitored_chats", ["chat_id"])
