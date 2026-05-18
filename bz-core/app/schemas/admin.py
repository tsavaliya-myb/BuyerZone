import uuid
from datetime import datetime

from pydantic import BaseModel

# ── Auth ───────────────────────────────────────────────────────────────────────


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ── Wholesaler ─────────────────────────────────────────────────────────────────


class WholesalerCreate(BaseModel):
    name: str
    telegram_id: int | None = None
    telegram_username: str | None = None
    wa_jid: str | None = None
    phone: str | None = None


class WholesalerUpdate(BaseModel):
    name: str | None = None
    telegram_id: int | None = None
    telegram_username: str | None = None
    wa_jid: str | None = None
    phone: str | None = None
    is_active: bool | None = None


class WholesalerResponse(BaseModel):
    id: uuid.UUID
    name: str
    telegram_id: int | None
    telegram_username: str | None
    wa_jid: str | None = None
    phone: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Monitored Chats ────────────────────────────────────────────────────────────


class ChatSearchRequest(BaseModel):
    name: str


class ChatSearchResult(BaseModel):
    chat_id: str
    chat_name: str
    chat_type: str
    member_count: int | None = None


class ChatAddRequest(BaseModel):
    chat_name: str  # Exact name as seen in Telegram


class ChatUpdateRequest(BaseModel):
    phone: str | None = None


class MonitoredChatResponse(BaseModel):
    id: uuid.UUID
    chat_id: str
    platform: str = "telegram"
    chat_name: str
    chat_type: str
    phone: str | None = None
    is_active: bool
    added_at: datetime
    product_count: int = 0

    model_config = {"from_attributes": True}


# ── Ingestion Logs ─────────────────────────────────────────────────────────────


class IngestionLogResponse(BaseModel):
    id: uuid.UUID
    chat_id: str
    message_id: str
    status: str
    reason: str | None
    product_id: uuid.UUID | None
    processed_at: datetime

    model_config = {"from_attributes": True}


# ── Stats ──────────────────────────────────────────────────────────────────────


class DashboardStats(BaseModel):
    total_products: int
    active_products: int
    stale_products: int
    total_wholesalers: int
    active_chats: int
    ingested_today: int
    ingested_this_week: int
    by_chat: list[dict]
    by_wholesaler: list[dict]
