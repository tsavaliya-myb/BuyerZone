import uuid
from datetime import datetime

from pydantic import BaseModel


class ProductResponse(BaseModel):
    id: uuid.UUID
    wholesaler_id: uuid.UUID | None
    wholesaler_name: str | None = None
    wholesaler_phone: str | None = None
    chat_id: str | None
    chat_name: str | None = None
    message_id: str
    name: str | None
    raw_caption: str | None
    price: float | None
    currency: str
    image_url: str | None
    source_platform: str
    platform: str | None = None
    status: str
    received_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class ProductListResponse(BaseModel):
    items: list[ProductResponse]
    total: int
    page: int
    page_size: int
    pages: int


class ProductStatusUpdate(BaseModel):
    status: str  # active | stale | removed


class ProductFilters(BaseModel):
    wholesaler_id: uuid.UUID | None = None
    chat_id: int | None = None
    status: str | None = "active"
    date_from: datetime | None = None
    date_to: datetime | None = None
    page: int = 1
    page_size: int = 20
