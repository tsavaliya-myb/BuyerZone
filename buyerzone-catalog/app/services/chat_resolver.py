"""Pyrogram dialog search and in-memory whitelist management."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from pyrogram import Client

log = structlog.get_logger(__name__)

# In-memory whitelist: chat_id -> chat_name (refreshed from DB on startup + after admin changes)
_whitelist: dict[int, str] = {}
_lock = asyncio.Lock()


def is_whitelisted(chat_id: int) -> bool:
    return chat_id in _whitelist


def get_whitelist() -> dict[int, str]:
    return dict(_whitelist)


async def add_to_whitelist(chat_id: int, chat_name: str) -> None:
    async with _lock:
        _whitelist[chat_id] = chat_name


async def remove_from_whitelist(chat_id: int) -> None:
    async with _lock:
        _whitelist.pop(chat_id, None)


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


async def search_dialogs(client: "Client", name: str) -> list[dict]:
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


async def resolve_dialog_by_exact_name(client: "Client", name: str) -> dict | None:
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
