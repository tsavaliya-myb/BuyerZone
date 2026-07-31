import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class InHouseProductPhotoResponse(BaseModel):
    id: uuid.UUID
    url: str
    position: int

    model_config = {"from_attributes": True}


class InHouseProductResponse(BaseModel):
    id: uuid.UUID
    name: str
    price: float
    keywords: list[str]
    status: str
    photos: list[InHouseProductPhotoResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class InHouseProductListResponse(BaseModel):
    items: list[InHouseProductResponse]
    total: int
    page: int
    page_size: int
    pages: int


class InHouseProductUpdate(BaseModel):
    name: str | None = None
    price: float | None = Field(default=None, gt=0)
    keywords: list[str] | None = None
    status: str | None = None
