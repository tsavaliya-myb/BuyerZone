"""Pyrogram dialog search and in-memory whitelist management."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from pyrogram import Client

log = structlog.get_logger(__name__)

# In-memory whitelist: chat_id -> chat_name. Hydrated at startup and refreshed
# every WHITELIST_REFRESH_INTERVAL seconds by a background task so admin
# add/remove operations propagate without restarting the ingestion service.
_whitelist: dict[int, str] = {}
WHITELIST_REFRESH_INTERVAL = 600.0  # seconds (10 min) — safety net for the
# push-based reload via the ingestion internal API. The push path handles the
# common case; this poll catches transient HTTP failures.


def is_whitelisted(chat_id: int) -> bool:
    return chat_id in _whitelist


def get_whitelist() -> dict[int, str]:
    return dict(_whitelist)


async def whitelist_refresher() -> None:
    """Background loop — re-hydrates the whitelist from the DB on a fixed cadence.
    Started once from the ingestion service entrypoint."""
    while True:
        await asyncio.sleep(WHITELIST_REFRESH_INTERVAL)
        try:
            await load_whitelist_from_db()
        except Exception as exc:
            log.error("whitelist_refresh_failed", error=str(exc))


async def load_whitelist_from_db() -> None:
    """Hydrates in-memory whitelist from PostgreSQL. Safe to call concurrently
    with is_whitelisted() — the new dict is built outside the lock and swapped
    in atomically so readers never see a partially-populated state."""
    from sqlalchemy import select

    from app.core.database import AsyncSessionLocal
    from app.models.monitored_chat import MonitoredChat

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(MonitoredChat).where(
                MonitoredChat.is_active.is_(True),
                MonitoredChat.platform == "telegram",
            )
        )
        chats = result.scalars().all()

    new_whitelist = {int(chat.chat_id): chat.chat_name for chat in chats}

    # Atomic reference swap — readers see either the old dict or the new dict,
    # never a half-populated state. CPython guarantees module-attribute
    # assignment is a single bytecode op.
    global _whitelist
    _whitelist = new_whitelist

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
