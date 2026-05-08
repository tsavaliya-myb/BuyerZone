import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    qdrant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), unique=True, nullable=True
    )
    wholesaler_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wholesalers.id"), nullable=True
    )
    chat_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("monitored_chats.chat_id"), nullable=True
    )
    telegram_msg_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raw_caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_platform: Mapped[str] = mapped_column(String(20), default="telegram")
    status: Mapped[str] = mapped_column(String(20), default="active")  # active|stale|removed
    received_at: Mapped[datetime] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    wholesaler: Mapped["Wholesaler"] = relationship(back_populates="products")  # noqa: F821
    chat: Mapped["MonitoredChat"] = relationship(back_populates="products")  # noqa: F821

    __table_args__ = (
        Index("idx_products_wholesaler", "wholesaler_id"),
        Index("idx_products_status", "status"),
        Index("idx_products_received_at", "received_at"),
    )
