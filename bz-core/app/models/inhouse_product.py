import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Numeric, String, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class InHouseProduct(Base):
    __tablename__ = "inhouse_products"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    keywords: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active|inactive
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin_users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    photos: Mapped[list["InHouseProductPhoto"]] = relationship(
        back_populates="product",
        order_by="InHouseProductPhoto.position",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_inhouse_products_status", "status"),
        Index("idx_inhouse_products_keywords", "keywords", postgresql_using="gin"),
    )
