"""Pyrogram listener — runs as a standalone long-lived process.

Start with:  python -m app.services.ingestion

Also exposes an internal HTTP server on port 8001 for dialog
lookups used by the admin API (no second Pyrogram session needed),
plus the Telegram authentication state machine driven by the admin UI.
check CICD 
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import io
import logging
import os
import re
import secrets
import signal
from datetime import UTC
import tempfile

SESSION_DIR = "/data/pyrogram_sessions"

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pyrogram import Client
from pyrogram.errors import (
    FloodWait,
    PasswordHashInvalid,
    PhoneCodeExpired,
    PhoneCodeInvalid,
    PhoneNumberInvalid,
    SessionPasswordNeeded,
)
from pyrogram.handlers import RawUpdateHandler
from pyrogram.utils import get_peer_id

from app.config import get_settings
from app.core.redis import close_arq_pool, enqueue_message
from app.services.chat_resolver import (
    get_whitelist,
    is_whitelisted,
    load_whitelist_from_db,
    resolve_dialog_by_exact_name,
    save_session_and_reload,
    search_dialogs,
)

logging.basicConfig(level=logging.WARNING)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.engine.Engine").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)

log = structlog.get_logger(__name__)
settings = get_settings()

OUT_OF_STOCK_PATTERNS = re.compile(
    r"\b(out\s+of\s+stock|stock\s+out|sold\s+out|not\s+available|unavailable|oos|stockout)\b",
    re.IGNORECASE,
)

MAX_CONCURRENT_DOWNLOADS = 20
_download_sem = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)

CATCH_UP_FIRST_RUN_HOURS = 24

# Set in main() once we know whether a session is available.
pyrogram_client: Client | None = None

# In-flight Telegram auth attempts. Keyed by an opaque login_id; the value
# holds the live Pyrogram client whose socket carries phone_code_hash. The
# auth flow is single-process by design so this dict is enough.
_login_states: dict[str, dict] = {}
LOGIN_TTL_SECONDS = 600


# ── Internal HTTP server ───────────────────────────────────────────────────────

internal_app = FastAPI(title="BuyerZone Ingestion Internal API", docs_url=None, redoc_url=None)


@internal_app.get("/dialogs/search")
async def dialog_search(name: str):
    if pyrogram_client is None:
        return JSONResponse({"error": "no_active_session"}, status_code=503)
    try:
        return await search_dialogs(pyrogram_client, name)
    except Exception as exc:
        log.error("dialog_search_error", error=str(exc))
        return JSONResponse({"error": str(exc)}, status_code=500)


@internal_app.get("/dialogs/resolve")
async def dialog_resolve(name: str):
    if pyrogram_client is None:
        return JSONResponse({"error": "no_active_session"}, status_code=503)
    try:
        result = await resolve_dialog_by_exact_name(pyrogram_client, name)
        return result or {}
    except Exception as exc:
        log.error("dialog_resolve_error", error=str(exc))
        return JSONResponse({"error": str(exc)}, status_code=500)


@internal_app.get("/health")
async def health():
    return {
        "status": "ok",
        "connected": bool(pyrogram_client and pyrogram_client.is_connected),
    }


@internal_app.post("/whitelist/reload")
async def whitelist_reload():
    previous = set(get_whitelist().keys())
    await load_whitelist_from_db()
    current = set(get_whitelist().keys())
    new_chat_ids = current - previous

    # Subscribe to channel update streams via getChannelDifference.
    # resolve_peer/get_chat/get_chat_history do NOT register the client for
    # future UpdateNewChannelMessage pushes — only getChannelDifference does.
    if current and pyrogram_client is not None:
        for chat_id in current:
            try:
                await _subscribe_channel(pyrogram_client, chat_id)
                log.info("channel_subscribed", chat_id=chat_id)
            except Exception as exc:
                log.error("channel_subscribe_failed", chat_id=chat_id, error=str(exc))

    return {"status": "ok", "count": len(current), "newly_subscribed": len(new_chat_ids)}


# ── Auth state machine ────────────────────────────────────────────────────────


@internal_app.post("/auth/send-code")
async def auth_send_code(payload: dict):
    phone = (payload or {}).get("phone", "").strip()
    if not phone.isdigit() or not (7 <= len(phone) <= 15):
        return JSONResponse({"error": "invalid_phone"}, status_code=400)

    login_id = secrets.token_hex(16)
    client = Client(
        name=f"login_{login_id}",
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
        in_memory=True,
    )
    try:
        await client.connect()
        sent = await client.send_code(phone)
    except PhoneNumberInvalid:
        await _safe_disconnect(client)
        return JSONResponse({"error": "invalid_phone"}, status_code=400)
    except FloodWait as exc:
        await _safe_disconnect(client)
        return JSONResponse(
            {"error": "flood_wait", "retry_after": exc.value},
            status_code=429,
        )
    except Exception as exc:
        await _safe_disconnect(client)
        log.error("auth_send_code_failed", error=str(exc))
        return JSONResponse({"error": "send_code_failed"}, status_code=500)

    expire_task = asyncio.create_task(_expire_login(login_id, LOGIN_TTL_SECONDS))
    _login_states[login_id] = {
        "client": client,
        "phone": phone,
        "phone_code_hash": sent.phone_code_hash,
        "expire_task": expire_task,
    }
    log.info("auth_send_code_ok", login_id=login_id, phone=phone)
    return {"login_id": login_id, "expires_in": LOGIN_TTL_SECONDS}


@internal_app.post("/auth/verify-code")
async def auth_verify_code(payload: dict):
    login_id = (payload or {}).get("login_id")
    code = (payload or {}).get("code", "")
    state = _login_states.get(login_id)
    if not state:
        return JSONResponse({"error": "login_not_found"}, status_code=404)

    client: Client = state["client"]
    try:
        await client.sign_in(state["phone"], state["phone_code_hash"], code)
    except SessionPasswordNeeded:
        return {"status": "requires_2fa"}
    except PhoneCodeInvalid:
        return JSONResponse({"error": "invalid_code"}, status_code=400)
    except PhoneCodeExpired:
        await _drop_login(login_id)
        return JSONResponse({"error": "code_expired"}, status_code=400)
    except Exception as exc:
        log.error("auth_verify_code_failed", error=str(exc))
        await _drop_login(login_id)
        return JSONResponse({"error": "verify_code_failed"}, status_code=500)

    return await _finalize_login(login_id)


@internal_app.post("/auth/verify-password")
async def auth_verify_password(payload: dict):
    login_id = (payload or {}).get("login_id")
    password = (payload or {}).get("password", "")
    state = _login_states.get(login_id)
    if not state:
        return JSONResponse({"error": "login_not_found"}, status_code=404)

    client: Client = state["client"]
    try:
        await client.check_password(password)
    except PasswordHashInvalid:
        return JSONResponse({"error": "invalid_password"}, status_code=400)
    except Exception as exc:
        log.error("auth_verify_password_failed", error=str(exc))
        await _drop_login(login_id)
        return JSONResponse({"error": "verify_password_failed"}, status_code=500)

    return await _finalize_login(login_id)


@internal_app.post("/session/reload")
async def session_reload():
    """Exit gracefully so the supervisor (Docker `restart: always`) brings the
    process back up with the newly-saved DB session string."""
    log.warning("session_reload_requested — exiting for supervisor restart")
    asyncio.create_task(_kill_self())
    return {"status": "restarting"}

SESSION_NAME = "buyerzone"


async def _ensure_session_file(session_string: str) -> None:
    """Bootstrap SQLite session file from the DB session_string if missing.

    Why: passing session_string to Client uses MemoryStorage, which never
    persists pts/qts to disk. Copying the auth fields into a FileStorage
    once lets Pyrogram maintain update state across restarts.
    """
    from pathlib import Path

    from pyrogram.storage import FileStorage

    os.makedirs(SESSION_DIR, exist_ok=True)
    session_file = os.path.join(SESSION_DIR, f"{SESSION_NAME}.session")
    if os.path.exists(session_file):
        return

    tmp = Client(
        name=SESSION_NAME,
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
        session_string=session_string,
        in_memory=True,
    )
    await tmp.connect()
    mem = tmp.storage
    fs = FileStorage(SESSION_NAME, Path(SESSION_DIR))
    await fs.open()
    await fs.dc_id(await mem.dc_id())
    await fs.api_id(await mem.api_id())
    await fs.test_mode(await mem.test_mode())
    await fs.auth_key(await mem.auth_key())
    await fs.user_id(await mem.user_id())
    await fs.is_bot(await mem.is_bot())
    await fs.date(0)
    await fs.save()
    await fs.close()
    await tmp.disconnect()
    log.info("session_file_bootstrapped", path=session_file)


async def _kill_self() -> None:
    await asyncio.sleep(0.5)
    os.kill(os.getpid(), signal.SIGTERM)


async def _expire_login(login_id: str, delay: int) -> None:
    try:
        await asyncio.sleep(delay)
    except asyncio.CancelledError:
        return
    state = _login_states.pop(login_id, None)
    if state:
        await _safe_disconnect(state["client"])
        log.info("login_expired", login_id=login_id)


async def _drop_login(login_id: str) -> None:
    state = _login_states.pop(login_id, None)
    if not state:
        return
    state["expire_task"].cancel()
    await _safe_disconnect(state["client"])


async def _safe_disconnect(client: Client) -> None:
    with contextlib.suppress(Exception):
        await client.disconnect()


async def _finalize_login(login_id: str) -> dict:
    state = _login_states.pop(login_id)
    state["expire_task"].cancel()
    client: Client = state["client"]
    try:
        me = await client.get_me()
        display_name = (
            f"{(me.first_name or '').strip()} {(me.last_name or '').strip()}".strip()
            or (me.username or state["phone"])
        )
        session_string = await client.export_session_string()
    finally:
        await _safe_disconnect(client)

    # Remove stale session file so next restart rebuilds from new session_string
    stale = os.path.join(SESSION_DIR, "buyerzone.session")
    with contextlib.suppress(Exception):
        os.remove(stale)
        
    log.info("login_finalized", phone=state["phone"], display_name=display_name)
    return {
        "status": "success",
        "session_string": session_string,
        "phone": state["phone"],
        "display_name": display_name,
    }

async def _save_session_to_db(session_string: str) -> None:
    await save_session_and_reload(session_string)
    log.info("session_saved_to_db")
    
# ── Channel subscription (the actual fix for on_raw missing channels) ─────────


async def _subscribe_channel(client: Client, chat_id: int) -> None:
    """Force Telegram to register this client for a channel's update stream.

    The key insight: resolve_peer / get_chat / get_chat_history do NOT cause
    Telegram to push UpdateNewChannelMessage for a channel. Only
    updates.getChannelDifference (or the initial get_dialogs iteration) does.

    This function:
    1. Resolves the peer (access hash)
    2. Reads the channel's current pts from Pyrogram's session
    3. Calls getChannelDifference to subscribe to future updates
    """
    from pyrogram.raw.functions.updates import GetChannelDifference
    from pyrogram.raw.types import ChannelMessagesFilterEmpty, InputChannel

    # Step 1: resolve peer to get access_hash
    peer = await client.resolve_peer(chat_id)

    # peer might be InputPeerChannel — extract channel_id and access_hash
    channel_id = getattr(peer, "channel_id", None)
    access_hash = getattr(peer, "access_hash", None)
    if channel_id is None or access_hash is None:
        log.warning("subscribe_skip_not_channel", chat_id=chat_id, peer_type=type(peer).__name__)
        return

    # Step 2: get current pts from Pyrogram's session storage
    # If no pts exists, use pts=1 to force Telegram to return the current state
    try:
        session_pts = await client.storage.get_peer_by_id(chat_id)
        # session_pts is a tuple; pts is not directly available from get_peer_by_id
        # Fall back to fetching one message to establish a baseline
    except Exception:
        pass

    # Step 3: call getChannelDifference — this is what actually subscribes
    # us to UpdateNewChannelMessage for this channel
    try:
        await client.invoke(
            GetChannelDifference(
                force=True,
                channel=InputChannel(
                    channel_id=channel_id,
                    access_hash=access_hash,
                ),
                filter=ChannelMessagesFilterEmpty(),
                pts=1,  # pts=1 with force=True makes Telegram return current
                         # state and registers us for future updates
                limit=1,
            )
        )
    except Exception as exc:
        # Some errors (CHANNEL_PRIVATE, etc.) are expected for certain chats
        log.warning("get_channel_difference_failed", chat_id=chat_id, error=str(exc))


# ── Pyrogram raw update handler ───────────────────────────────────────────────


async def on_raw(client: Client, update, users, chats):
    from pyrogram.raw.types import Message as RawMessage
    from pyrogram.raw.types import UpdateNewChannelMessage, UpdateNewMessage

    log.info("on_raw_fired", update_type=type(update).__name__)

    print("Update received:", update)
    print("users received:", users)
    print("chats received:", chats)
    
    if not isinstance(update, UpdateNewChannelMessage | UpdateNewMessage):
        return

    raw_msg = update.message
    if not isinstance(raw_msg, RawMessage):
        log.info("on_raw_skip_not_raw_message", msg_type=type(raw_msg).__name__)
        return

    peer = getattr(raw_msg, "peer_id", None)
    if peer is None:
        return

    try:
        chat_id = get_peer_id(peer)
    except (ValueError, AttributeError):
        return

    log.info(
        "on_raw_chat_id",
        chat_id=chat_id,
        peer_type=type(peer).__name__,
        in_whitelist=is_whitelisted(chat_id),
        whitelist_keys=list(get_whitelist().keys()),
    )

    if not is_whitelisted(chat_id):
        return

    msg_id = raw_msg.id
    caption = (raw_msg.message or "").strip()
    media = getattr(raw_msg, "media", None)
    is_photo = media is not None and type(media).__name__ == "MessageMediaPhoto"
    grouped_id = getattr(raw_msg, "grouped_id", None)

    if is_photo and grouped_id is not None and not caption:
        return
    if not is_photo and not caption:
        return
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

    sender_username: str | None = None
    sender_name: str | None = None
    if sender_id and sender_id in users:
        u = users[sender_id]
        sender_username = getattr(u, "username", None)
        first = getattr(u, "first_name", "") or ""
        last = getattr(u, "last_name", "") or ""
        sender_name = (f"{first} {last}".strip()) or None

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


# ── Startup catch-up ──────────────────────────────────────────────────────────


async def _get_last_logged_msg_id(chat_id: int) -> int | None:
    from sqlalchemy import func, select

    from app.core.database import AsyncSessionLocal
    from app.models.ingestion_log import IngestionLog

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(func.max(IngestionLog.message_id)).where(IngestionLog.chat_id == str(chat_id))
        )
        val = result.scalar_one_or_none()
        return int(val) if val is not None else None


async def _enqueue_from_history(client: Client, message, chat_title: str) -> bool:
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

    missed = []
    async for message in client.get_chat_history(chat_id):
        if last_msg_id is not None and message.id <= last_msg_id:
            break
        if cutoff_dt is not None and message.date:
            msg_dt = message.date
            if msg_dt.tzinfo is None:
                msg_dt = msg_dt.replace(tzinfo=UTC)
            if msg_dt < cutoff_dt:
                break
        missed.append(message)

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


# ── Session loading ───────────────────────────────────────────────────────────


async def _load_active_session_string() -> str | None:
    from sqlalchemy import select

    from app.core.database import AsyncSessionLocal
    from app.models.platform_session import PlatformSession

    async with AsyncSessionLocal() as session:
        q = await session.execute(
            select(PlatformSession.session_data)
            .where(
                PlatformSession.platform == "telegram",
                PlatformSession.status == "active",
            )
            .order_by(PlatformSession.updated_at.desc())
            .limit(1)
        )
        return q.scalar_one_or_none()


def _build_client() -> Client:
    return Client(
        name=SESSION_NAME,
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
        workdir=SESSION_DIR,
    )


# ── Entrypoint ────────────────────────────────────────────────────────────────


async def main() -> None:
    global pyrogram_client

    await load_whitelist_from_db()
    log.info("whitelist_contents", chats=get_whitelist())

    config = uvicorn.Config(
        internal_app,
        host="0.0.0.0",
        port=settings.ingestion_internal_port,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    asyncio.create_task(server.serve())

    session_string = await _load_active_session_string()
    if not session_string:
        log.warning(
            "no_telegram_session_available — internal API up; "
            "authenticate via /api/v1/admin/telegram/auth/send-code"
        )
        try:
            await asyncio.Event().wait()
        finally:
            await close_arq_pool()
        return

    await _ensure_session_file(session_string)
    client = _build_client()
    
    # Pyrogram requires at least one high-level handler (like MessageHandler) to fully
    # initialize the event processing stream and maintain channel pts states. Without it,
    # it may drop or ignore UpdateNewChannelMessage events for channels.
    from pyrogram.handlers import MessageHandler
    async def dummy_handler(c, m):
        pass

    client.add_handler(RawUpdateHandler(on_raw))
    client.add_handler(MessageHandler(dummy_handler))
    pyrogram_client = client

    async with client:
        me = await client.get_me()
        log.info("pyrogram_me", id=me.id, username=me.username, phone=me.phone_number)

        dialog_count = 0
        async for _ in client.get_dialogs():
            dialog_count += 1
        log.info("dialogs_loaded", count=dialog_count)

        # Hydrate all whitelisted chats so Pyrogram's in-memory session maintains their
        # peer/pts state. Without this, Telegram won't push UpdateNewChannelMessage 
        # events for pre-existing channels after a service restart.
        await whitelist_reload()
        
        # Small settle delay — gives Telegram time to register subscriptions
        await asyncio.sleep(2)

        if settings.catch_up_enabled:
            asyncio.create_task(_catch_up_missed(client))
        else:
            log.info("catch_up_disabled")

        # ── Periodic catch-up safety net ──────────────────────────────────────
        # on_raw is the primary ingestion path. This loop is a safety net that
        # catches anything on_raw missed (e.g. transient MTProto disconnects,
        # channels that lost their subscription). Runs every 10 minutes.
        # SAFETY_NET_INTERVAL = 10 * 60  # seconds

        # async def _safety_net_loop():
        #     while True:
        #         await asyncio.sleep(SAFETY_NET_INTERVAL)
        #         try:
        #             log.info("safety_net_catch_up_start")
        #             await _catch_up_missed(client)
        #         except Exception as exc:
        #             log.error("safety_net_catch_up_failed", error=str(exc))

        # asyncio.create_task(_safety_net_loop())
            
        # whitelist reload every 10 minutes    
        async def _periodic_whitelist_reload():
            from app.services.chat_resolver import WHITELIST_REFRESH_INTERVAL
            while True:
                await asyncio.sleep(WHITELIST_REFRESH_INTERVAL)
                try:
                    await whitelist_reload()
                except Exception as exc:
                    log.error("periodic_whitelist_reload_failed", error=str(exc))
                    
        asyncio.create_task(_periodic_whitelist_reload())

        # ── Periodically flush updated session string back to DB ──────────────
        async def _periodic_session_save():
            while True:
                await asyncio.sleep(3600)          # every hour
                try:
                    ss = await client.export_session_string()
                    await _save_session_to_db(ss)
                except Exception as exc:
                    log.error("periodic_session_save_failed", error=str(exc))

        asyncio.create_task(_periodic_session_save())

        log.info("ingestion_service_ready")
        try:
            from pyrogram import idle

            await idle()
        finally:
            # ── Save final session state before exit ──────────────────────────
            try:
                ss = await client.export_session_string()
                await _save_session_to_db(ss)
                log.info("session_saved_on_shutdown")
            except Exception as exc:
                log.error("session_shutdown_save_failed", error=str(exc))
            await close_arq_pool()


if __name__ == "__main__":
    asyncio.run(main())
