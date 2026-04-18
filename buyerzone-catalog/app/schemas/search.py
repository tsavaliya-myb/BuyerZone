import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ImageSearchRequest(BaseModel):
    image_base64: str | None = None  # base64-encoded image (alternative to multipart)
    top_k: int = Field(default=10, ge=1, le=100)


class TextSearchRequest(BaseModel):
    q: str
    top_k: int = Field(default=10, ge=1, le=100)


class CombinedSearchRequest(BaseModel):
    image_base64: str | None = None
    text: str | None = None
    image_weight: float = Field(default=0.7, ge=0.0, le=1.0)
    top_k: int = Field(default=10, ge=1, le=100)


class SearchResultItem(BaseModel):
    product_id: uuid.UUID
    similarity_score: float
    name: str | None
    price: float | None
    currency: str
    image_url: str
    wholesaler_name: str | None
    wholesaler_phone: str | None
    chat_name: str | None
    received_at: datetime
    status: str


class SearchResponse(BaseModel):
    results: list[SearchResultItem]
    total: int
    query_time_ms: float
