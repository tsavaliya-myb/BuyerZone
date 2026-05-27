"""Pydantic schemas for WhatsApp admin API endpoints."""

from __future__ import annotations

from pydantic import BaseModel

# ── Auth / Pairing ─────────────────────────────────────────────────────────────


class WAPairRequest(BaseModel):
    phone: str  # digits only, e.g. "919876543210"


class WAPairResponse(BaseModel):
    code: str  # e.g. "ABCD-EFGH"
    expires_in: int  # seconds


class WAStatus(BaseModel):
    state: str  # awaiting_pair_code | pair_pending | connected | disconnected | requires_repair
    phone: str | None = None
    display_name: str | None = None
    session_id: str | None = None


# ── Chat resolve / add ─────────────────────────────────────────────────────────


class WAChatResolveRequest(BaseModel):
    query: str  # name fragment OR full invite URL


class WAChatResult(BaseModel):
    jid: str
    name: str
    type: str  # wa_group | wa_channel
    is_community_parent: bool = False
    is_community_subgroup: bool = False
    participant_count: int | None = None
    already_monitored: bool = False


class WAChatAddRequest(BaseModel):
    jid: str
    chat_name: str | None = None


class WAChatAddBatchRequest(BaseModel):
    chats: list[WAChatAddRequest]


class WAChatResponse(BaseModel):
    id: str
    jid: str
    platform: str = "whatsapp"
    chat_name: str
    chat_type: str
    is_active: bool
    product_count: int = 0


# ── Internal session update (Node → FastAPI) ───────────────────────────────────


class WASessionUpdateRequest(BaseModel):
    auth_state: dict  # full Baileys auth state JSONB
    phone: str
    display_name: str | None = None
