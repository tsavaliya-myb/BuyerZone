"""Pyrogram listener — runs as a standalone long-lived process.

Start with:  python -m app.services.ingestion

Also exposes an internal HTTP server on port 8001 for dialog
lookups used by the admin API (no second Pyrogram session needed).
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import re
import threading
from datetime import UTC

import structlog
import uvicorn
from fastapi import FastAPI
from pyrogram import Client

from app.config import get_settings
from app.core.redis import close_arq_pool, enqueue_message
from app.services.chat_resolver import (
    get_whitelist,
    is_whitelisted,
    load_whitelist_from_db,
    resolve_dialog_by_exact_name,
    search_dialogs,
    whitelist_refresher,
)

logging.basicConfig(level=logging.WARNING)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.engine.Engine").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)

log = structlog.get_logger(__name__)
settings = get_settings()

# Keywords that signal an out-of-stock message — skip these
OUT_OF_STOCK_PATTERNS = re.compile(
    r"\b(out\s+of\s+stock|stock\s+out|sold\s+out|not\s+available|unavailable|oos|stockout)\b",
    re.IGNORECASE,
)

# Cap in-flight downloads so a burst of album photos can't exhaust memory
# or Telegram's per-session concurrency budget.
MAX_CONCURRENT_DOWNLOADS = 20
_download_sem = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)

# Startup catch-up: replay messages the listener missed while it was down.
CATCH_UP_FIRST_RUN_HOURS = 24  # on first-ever run with no prior logs

pyrogram_client = Client(
    name=settings.telegram_session_name,
    api_id=settings.telegram_api_id,
    api_hash=settings.telegram_api_hash,
    workdir="sessions",
)

# ── Internal HTTP server ───────────────────────────────────────────────────────

internal_app = FastAPI(title="BuyerZone Ingestion Internal API", docs_url=None, redoc_url=None)


@internal_app.get("/dialogs/search")
async def dialog_search(name: str):
    results = await search_dialogs(pyrogram_client, name)
    return results


@internal_app.get("/dialogs/resolve")
async def dialog_resolve(name: str):
    result = await resolve_dialog_by_exact_name(pyrogram_client, name)
    return result or {}


@internal_app.get("/health")
async def health():
    return {"status": "ok", "connected": pyrogram_client.is_connected}


@internal_app.post("/whitelist/reload")
async def whitelist_reload():
    await load_whitelist_from_db()
    return {"status": "ok", "count": len(get_whitelist())}


# ── Pyrogram listener ──────────────────────────────────────────────────────────


@pyrogram_client.on_raw_update()
async def on_raw(client: Client, update, users, chats):
    from pyrogram.raw.types import Message as RawMessage
    from pyrogram.raw.types import UpdateNewChannelMessage, UpdateNewMessage

    # Edits (UpdateEditChannelMessage) and deletes (UpdateDeleteChannelMessages)
    # are intentionally not handled — the "new message" updates are the only
    # source of catalog rows.
    if not isinstance(update, UpdateNewChannelMessage | UpdateNewMessage):
        return

    raw_msg = update.message
    # MessageService (joins, pins, etc.) and MessageEmpty (deleted/unavailable)
    # share the Update envelope with real messages — filter them out explicitly.
    if not isinstance(raw_msg, RawMessage):
        return

    # Replies are conversational noise in wholesaler groups — skip them.
    # Forwards (raw_msg.fwd_from set) are ingested as normal messages.
    if getattr(raw_msg, "reply_to", None) is not None:
        return

    peer = getattr(raw_msg, "peer_id", None)
    if peer is None:
        return

    # Channel posts: peer is PeerChannel with channel_id (positive).
    # Our DB chat_ids are stored as -100<channel_id> (Bot API format).
    if hasattr(peer, "channel_id"):
        chat_id = int(f"-100{peer.channel_id}")
    elif hasattr(peer, "chat_id"):
        chat_id = -peer.chat_id
    elif hasattr(peer, "user_id"):
        chat_id = peer.user_id
    else:
        return

    if not is_whitelisted(chat_id):
        return

    msg_id = raw_msg.id
    caption = (raw_msg.message or "").strip()
    media = getattr(raw_msg, "media", None)
    is_photo = media is not None and type(media).__name__ == "MessageMediaPhoto"
    grouped_id = getattr(raw_msg, "grouped_id", None)

    # Album sibling without caption — the captioned sibling carries the product info.
    # Albums where no sibling carries a caption are dropped entirely, by design.
    if is_photo and grouped_id is not None and not caption:
        return

    # Text-only messages require a caption; photos are allowed either way.
    if not is_photo and not caption:
        return

    # Non-photo media (stickers, videos, documents, etc.) — skip.
    if not is_photo and media is not None:
        return

    if caption and OUT_OF_STOCK_PATTERNS.search(caption):
        return

    chat_title = (
        chats.get(peer.channel_id).title
        if hasattr(peer, "channel_id") and peer.channel_id in chats
        else ""
    )
    sender = getattr(raw_msg, "from_id", None)
    sender_id = getattr(sender, "user_id", None) if sender else None
    date = raw_msg.date

    # Sender display name / username from the raw update's users dict.
    sender_username: str | None = None
    sender_name: str | None = None
    if sender_id and sender_id in users:
        u = users[sender_id]
        sender_username = getattr(u, "username", None)
        first = getattr(u, "first_name", "") or ""
        last = getattr(u, "last_name", "") or ""
        sender_name = (f"{first} {last}".strip()) or None

    # Debug log — full key/value breakdown of what we parsed from this update.
    log.info(
        "telegram_message_received",
        chat_id=chat_id,
        chat_title=chat_title,
        peer_type=type(peer).__name__,
        msg_id=msg_id,
        grouped_id=grouped_id,
        is_photo=is_photo,
        media_type=type(media).__name__ if media else None,
        caption_len=len(caption),
        caption_preview=caption[:120] if caption else None,
        sender_id=sender_id,
        sender_username=sender_username,
        sender_name=sender_name,
        date=date,
        is_forward=getattr(raw_msg, "fwd_from", None) is not None,
    )

    # Hand off download + enqueue so the dispatcher stays free to pull the
    # next update. Multiple downloads run concurrently on the same event loop.
    asyncio.create_task(
        _download_and_enqueue(
            client=client,
            chat_id=chat_id,
            msg_id=msg_id,
            caption=caption,
            is_photo=is_photo,
            sender_id=sender_id,
            sender_username=sender_username,
            sender_name=sender_name,
            chat_title=chat_title,
            date=date,
        )
    )


async def _download_and_enqueue(
    *,
    client: Client,
    chat_id: int,
    msg_id: int,
    caption: str,
    is_photo: bool,
    sender_id: int | None,
    sender_username: str | None = None,
    sender_name: str | None = None,
    chat_title: str,
    date,
    bypass_limits: bool = False,
) -> None:
    from datetime import datetime

    image_b64: str | None = None
    if is_photo:
        async with _download_sem:
            try:
                msg = await client.get_messages(chat_id, msg_id)
                buf = io.BytesIO()
                async for chunk in client.stream_media(msg.photo.file_id):
                    buf.write(chunk)
                image_b64 = base64.b64encode(buf.getvalue()).decode()
            except Exception as exc:
                log.error("image_download_failed", chat_id=chat_id, msg_id=msg_id, error=str(exc))
                return

    payload = {
        "image_b64": image_b64,
        "has_image": is_photo,
        "caption": caption,
        "sender_id": sender_id,
        "sender_username": sender_username,
        "sender_name": sender_name,
        "chat_id": chat_id,
        "chat_title": chat_title,
        "message_id": msg_id,
        "date": datetime.fromtimestamp(date, tz=UTC).isoformat() if date else None,
    }

    try:
        await enqueue_message(payload, bypass_limits=bypass_limits)
        log.info("message_enqueued", chat_id=chat_id, msg_id=msg_id, has_image=is_photo)
    except Exception as exc:
        log.error("enqueue_failed", chat_id=chat_id, msg_id=msg_id, error=str(exc))


# ── Startup catch-up ───────────────────────────────────────────────────────────


async def _get_last_logged_msg_id(chat_id: int) -> int | None:
    from sqlalchemy import func, select

    from app.core.database import AsyncSessionLocal
    from app.models.ingestion_log import IngestionLog

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(func.max(IngestionLog.telegram_msg_id)).where(IngestionLog.chat_id == chat_id)
        )
        return result.scalar_one_or_none()


async def _enqueue_from_history(client: Client, message, chat_title: str) -> bool:
    """Apply the same filters as the live handler and dispatch to the shared
    download+enqueue path. Returns True if enqueued, False if skipped."""
    # Service messages (joins, pins, etc.) and replies: skip.
    # Forwards pass through unchanged — they're valid product posts.
    if getattr(message, "service", None):
        return False
    if getattr(message, "reply_to_message_id", None):
        return False

    caption = (message.caption or message.text or "").strip()
    is_photo = message.photo is not None
    grouped_id = message.media_group_id

    if is_photo and grouped_id is not None and not caption:
        return False
    if not is_photo and not caption:
        return False
    if not is_photo and (
        message.video
        or message.document
        or message.sticker
        or message.voice
        or message.audio
        or message.animation
    ):
        return False
    if caption and OUT_OF_STOCK_PATTERNS.search(caption):
        return False

    sender_id = message.from_user.id if message.from_user else None
    date = int(message.date.timestamp()) if message.date else None

    await _download_and_enqueue(
        client=client,
        chat_id=message.chat.id,
        msg_id=message.id,
        caption=caption,
        is_photo=is_photo,
        sender_id=sender_id,
        chat_title=chat_title,
        date=date,
        bypass_limits=True,
    )
    return True


async def _catch_up_chat(client: Client, chat_id: int, chat_title: str) -> int:
    from datetime import datetime, timedelta

    last_msg_id = await _get_last_logged_msg_id(chat_id)
    cutoff_dt = (
        datetime.now(UTC) - timedelta(hours=CATCH_UP_FIRST_RUN_HOURS)
        if last_msg_id is None
        else None
    )

    # get_chat_history returns newest-first; stop once we cross the threshold.
    missed = []
    async for message in client.get_chat_history(chat_id):
        if last_msg_id is not None and message.id <= last_msg_id:
            break
        if cutoff_dt is not None and message.date:
            # Pyrogram may return a naive datetime (UTC) — normalise before compare.
            msg_dt = message.date
            if msg_dt.tzinfo is None:
                msg_dt = msg_dt.replace(tzinfo=UTC)
            if msg_dt < cutoff_dt:
                break
        missed.append(message)

    # Replay in chronological order so downstream logs look sane.
    missed.reverse()
    enqueued = 0
    for message in missed:
        try:
            if await _enqueue_from_history(client, message, chat_title):
                enqueued += 1
        except Exception as exc:
            log.error(
                "catch_up_message_failed",
                chat_id=chat_id,
                msg_id=message.id,
                error=str(exc),
            )
    return enqueued


async def _catch_up_missed(client: Client) -> None:
    whitelist = get_whitelist()
    log.info("catch_up_begin", chats=len(whitelist))
    total = 0
    for chat_id, chat_title in whitelist.items():
        try:
            count = await _catch_up_chat(client, chat_id, chat_title)
            total += count
            if count:
                log.info("catch_up_chat_done", chat_id=chat_id, enqueued=count)
        except Exception as exc:
            log.error("catch_up_chat_failed", chat_id=chat_id, error=str(exc))
    log.info("catch_up_complete", total_enqueued=total)


# ── Entrypoint ─────────────────────────────────────────────────────────────────


async def main() -> None:
    await load_whitelist_from_db()
    log.info("whitelist_contents", chats=get_whitelist())

    # Run uvicorn in a thread so it doesn't starve Pyrogram's update dispatcher
    config = uvicorn.Config(
        internal_app,
        host="0.0.0.0",
        port=settings.ingestion_internal_port,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()

    async with pyrogram_client:
        me = await pyrogram_client.get_me()
        log.info("pyrogram_me", id=me.id, username=me.username, phone=me.phone_number)

        # Populate peer cache — required for channel posts to dispatch correctly
        dialog_count = 0
        async for _ in pyrogram_client.get_dialogs():
            dialog_count += 1
        log.info("dialogs_loaded", count=dialog_count)

        # Replay messages missed while the listener was down. Runs in the
        # background so live updates start flowing immediately.
        asyncio.create_task(_catch_up_missed(pyrogram_client))

        # Periodically re-hydrate the whitelist so admin add/remove operations
        # propagate without a service restart.
        asyncio.create_task(whitelist_refresher())

        log.info("ingestion_service_ready")
        try:
            from pyrogram import idle

            await idle()
        finally:
            await close_arq_pool()


if __name__ == "__main__":
    pyrogram_client.run(main())
