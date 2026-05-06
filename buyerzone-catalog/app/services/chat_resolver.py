"""Pyrogram dialog search and in-memory whitelist management."""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from pyrogram import Client

log = structlog.get_logger(__name__)

# In-memory whitelist: chat_id -> chat_name (auto-refreshed from DB every TTL seconds)
_whitelist: dict[int, str] = {}
_lock = asyncio.Lock()
_last_refreshed: float = 0.0
WHITELIST_TTL = 60.0  # seconds


def is_whitelisted(chat_id: int) -> bool:
    global _last_refreshed
    if time.monotonic() - _last_refreshed > WHITELIST_TTL:
        _last_refreshed = time.monotonic()  # prevent task storm before reload finishes
        with contextlib.suppress(RuntimeError):
            asyncio.get_event_loop().create_task(_refresh_whitelist())
    return chat_id in _whitelist


async def _refresh_whitelist() -> None:
    await load_whitelist_from_db()


def get_whitelist() -> dict[int, str]:
    return dict(_whitelist)


async def load_whitelist_from_db() -> None:
    """Called on startup — hydrates in-memory whitelist from PostgreSQL."""
    from sqlalchemy import select

    from app.core.database import AsyncSessionLocal
    from app.models.monitored_chat import MonitoredChat

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(MonitoredChat).where(MonitoredChat.is_active.is_(True))
        )
        chats = result.scalars().all()

    async with _lock:
        _whitelist.clear()
        for chat in chats:
            _whitelist[chat.chat_id] = chat.chat_name

    log.info("whitelist_loaded", count=len(_whitelist))


async def search_dialogs(client: Client, name: str) -> list[dict]:
    """Search joined Telegram dialogs by name (case-insensitive substring)."""
    matches = []
    name_lower = name.lower()

    async for dialog in client.get_dialogs():
        if dialog.chat and dialog.chat.title and name_lower in dialog.chat.title.lower():
            matches.append(
                {
                    "chat_id": dialog.chat.id,
                    "chat_name": dialog.chat.title,
                    "chat_type": dialog.chat.type.value if dialog.chat.type else "unknown",
                    "member_count": getattr(dialog.chat, "members_count", None),
                }
            )

    return matches


async def resolve_dialog_by_exact_name(client: Client, name: str) -> dict | None:
    """Find a dialog whose title exactly matches name (case-sensitive)."""
    async for dialog in client.get_dialogs():
        if dialog.chat and dialog.chat.title == name:
            return {
                "chat_id": dialog.chat.id,
                "chat_name": dialog.chat.title,
                "chat_type": dialog.chat.type.value if dialog.chat.type else "unknown",
                "member_count": getattr(dialog.chat, "members_count", None),
            }
    return None
