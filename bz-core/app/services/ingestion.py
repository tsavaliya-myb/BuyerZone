"""Pyrogram polling ingestion — runs as a standalone long-lived process.
Start with:  python -m app.services.ingestion
Polls whitelisted Telegram chats every POLL_INTERVAL seconds to ingest
new messages. Chats are staggered across the interval to minimise
Telegram API load and avoid FloodWait.
Also exposes an internal HTTP server on port 8001 for dialog
lookups used by the admin API (no second Pyrogram session needed),
plus the Telegram authentication state machine driven by the admin UI."""

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
import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pyrogram import Client
from pyrogram.errors import (
    AuthKeyUnregistered,
    FloodWait,
    PasswordHashInvalid,
    PhoneCodeExpired,
    PhoneCodeInvalid,
    PhoneNumberInvalid,
    SessionPasswordNeeded,
)
from app.config import get_settings
from app.core.redis import close_arq_pool, enqueue_message
from app.services.chat_resolver import (
    get_whitelist,
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

# ── Structlog global configuration ───────────────────────────────────────────
from app.core.logging_config import configure_logging
configure_logging()

log = structlog.get_logger(__name__)

settings = get_settings()
OUT_OF_STOCK_PATTERNS = re.compile(
    r"\b(out\s+of\s+stock|stock\s+out|sold\s+out|not\s+available|unavailable|oos|stockout)\b",
    re.IGNORECASE,
)

MAX_CONCURRENT_DOWNLOADS = 20
_download_sem = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)

FIRST_RUN_MSG_LIMIT = 1  # messages to fetch on first-ever poll (no prior state)
POLL_INTERVAL = 15 * 60  # seconds between full poll cycles

# Set in main() once we know whether a session is available.
pyrogram_client: Client | None = None

# In-flight Telegram auth attempts. Keyed by an opaque login_id; the value
# holds the live Pyrogram client whose socket carries phone_code_hash. The
# auth flow is single-process by design so this dict is enough.
_login_states: dict[str, dict] = {}
LOGIN_TTL_SECONDS = 600

# ── Internal HTTP server ───────────────────────────────────────────────────────
internal_app = FastAPI(
    title="BuyerZone Ingestion Internal API", docs_url=None, redoc_url=None
)

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
    
    return {
        "status": "ok",
        "count": len(current),
        "newly_subscribed": len(new_chat_ids),
    }

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
    
    log.info("login_finalized", phone=state["phone"], display_name=display_name)
    
    return {
        "status": "success",
        "session_string": session_string,
        "phone": state["phone"],
        "display_name": display_name,
    }

# ── Telegram history helpers ─────────────────────────────────────────────────
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
                log.error(
                    "image_download_failed",
                    chat_id=chat_id,
                    msg_id=msg_id,
                    error=str(exc),
                )
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
    from sqlalchemy import func, select, cast, Integer
    from app.core.database import AsyncSessionLocal
    from app.models.ingestion_log import IngestionLog
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(func.max(cast(IngestionLog.message_id, Integer))).where(
                IngestionLog.chat_id == str(chat_id)
            )
        )
        val = result.scalar_one_or_none()
        return val

async def _advance_cursor(chat_id: int, max_msg_id: int) -> None:
    """Write a 'seen' ingestion_log so the cursor advances past all fetched messages.
    Only writes if max_msg_id is higher than the current cursor.
    This prevents re-fetching filtered/skipped messages on the next cycle.
    """
    from app.core.database import AsyncSessionLocal
    from app.models.ingestion_log import IngestionLog
    
    current = await _get_last_logged_msg_id(chat_id)
    if current is not None and max_msg_id <= current:
        return  # cursor already past this point
    
    async with AsyncSessionLocal() as session:
        session.add(
            IngestionLog(
                chat_id=str(chat_id),
                message_id=str(max_msg_id),
                status="seen",
                reason="poll_cursor_advance",
            )
        )
        await session.commit()

async def _enqueue_from_history(client: Client, message, chat_title: str) -> bool:
    if getattr(message, "service", None):
        return False
    if getattr(message, "reply_to_message_id", None):
        return False
    
    caption = (message.caption or message.text or "").strip()
    is_photo = message.photo is not None
    grouped_id = message.media_group_id
    
    if not is_photo:
        return False

    if grouped_id is not None and not caption:
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

async def _load_existing_products(chat_id: int) -> set[tuple[str, float | None]]:
    """Load (raw_caption, price) pairs for active products in one query.
    Returns a set of tuples for fast O(1) dedup lookup.
    """
    from sqlalchemy import select
    from app.core.database import AsyncSessionLocal
    from app.models.product import Product
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Product.raw_caption, Product.price).where(
                Product.chat_id == str(chat_id),
                Product.status == "active",
                Product.raw_caption.isnot(None),
            )
        )
        return {
            (row[0], float(row[1]) if row[1] is not None else None)
            for row in result.all()
        }

async def _resolve_peer(client: Client, chat_id: int) -> bool:
    """Ensure Pyrogram's internal peer cache has the access_hash for this chat.
    Without this, get_chat_history() raises 'Peer id invalid' for channels
    the session hasn't interacted with via get_dialogs() yet.
    Returns True if the peer was resolved successfully, False otherwise.
    """
    try:
        await client.get_chat(chat_id)
        return True
    except Exception as exc:
        log.warning("peer_resolve_failed", chat_id=chat_id, error=str(exc))
        return False


async def _catch_up_chat(client: Client, chat_id: int, chat_title: str) -> int:
    """Fetch new messages from a single chat since the last ingested message.
    First run (no prior state): fetches only the last FIRST_RUN_MSG_LIMIT messages
    to avoid flooding the queue on initial deploy.
    Subsequent runs: walks backwards from newest until it hits last_msg_id.
    """
    # Hydrate the peer cache so get_chat_history doesn't fail with "Peer id invalid"
    if not await _resolve_peer(client, chat_id):
        log.error("skip_chat_unresolvable", chat_id=chat_id, chat_title=chat_title)
        return 0

    last_msg_id = await _get_last_logged_msg_id(chat_id)
    is_first_run = last_msg_id is None
    missed = []
    limit = FIRST_RUN_MSG_LIMIT if is_first_run else 0  # 0 = no hard limit
    count = 0
    
    async for message in client.get_chat_history(chat_id):
        if last_msg_id is not None and message.id <= last_msg_id:
            break
        missed.append(message)
        count += 1
        if is_first_run and count >= limit:
            break
    missed.reverse()
    
    # Batch dedup: 1 DB query to load existing (caption, price) pairs
    existing_products = await _load_existing_products(chat_id)
    from app.services.processing import _extract_price
    enqueued = 0
    
    for message in missed:
        try:
            caption = (message.caption or message.text or "").strip()
            price = None
            if caption:
                price = _extract_price(caption)
                if (caption, price) in existing_products:
                    log.debug(
                        "poll_skip_existing_product",
                        chat_id=chat_id,
                        msg_id=message.id,
                    )
                    continue
            if await _enqueue_from_history(client, message, chat_title):
                enqueued += 1
                if caption:
                    existing_products.add((caption, price))
        except Exception as exc:
            log.error(
                "catch_up_message_failed",
                chat_id=chat_id,
                msg_id=message.id,
                error=str(exc),
            )
    
    # Advance the cursor to the highest message_id we saw in this batch.
    # This ensures filtered/skipped messages are never re-fetched.
    if missed:
        max_seen_id = missed[-1].id  # list is sorted ascending after reverse
        await _advance_cursor(chat_id, max_seen_id)
    return enqueued

async def _catch_up(client: Client) -> None:
    """Poll all whitelisted chats, staggered to avoid Telegram rate limits.
    Chats are processed sequentially with a gap between each one.
    If a FloodWait is received, we honour the wait and continue.
    """
    whitelist = get_whitelist()
    n = len(whitelist)
    if not n:
        return
    
    # Spread chats across 80% of the interval to leave headroom
    gap = (POLL_INTERVAL * 0.8) / n
    # Floor at 2s to avoid hammering, cap at 60s so small lists don't wait forever
    gap = max(2.0, min(gap, 60.0))
    log.info("poll_cycle_begin", chats=n, gap_seconds=round(gap, 1))
    total = 0
    
    for i, (chat_id, chat_title) in enumerate(whitelist.items()):
        try:
            count = await _catch_up_chat(client, chat_id, chat_title)
            total += count
            if count:
                log.info("poll_chat_done", chat_id=chat_id, enqueued=count)
        except FloodWait as fw:
            wait = getattr(fw, "value", 30)
            log.warning("poll_flood_wait", chat_id=chat_id, wait_seconds=wait)
            await asyncio.sleep(wait)
        except Exception as exc:
            log.error("poll_chat_failed", chat_id=chat_id, error=str(exc))
        
        # Stagger: sleep between chats (skip after last one)
        if i < n - 1:
            await asyncio.sleep(gap)
    log.info("poll_cycle_complete", total_enqueued=total)

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

async def _revoke_active_session() -> None:
    """Mark the active Telegram session as 'revoked' in the DB.
    Called when Pyrogram raises AuthKeyUnregistered, meaning the
    user terminated the session from the Telegram app."""
    from datetime import datetime
    from sqlalchemy import update
    from app.core.database import AsyncSessionLocal
    from app.models.platform_session import PlatformSession
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(PlatformSession)
            .where(
                PlatformSession.platform == "telegram",
                PlatformSession.status == "active",
            )
            .values(status="revoked", updated_at=datetime.utcnow())
        )
        await session.commit()
    log.warning("telegram_session_revoked_in_db")

def _build_client(session_string: str) -> Client:
    return Client(
        name="buyerzone",
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
        session_string=session_string,
        in_memory=True,
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
    
    client = _build_client(session_string)
    
    try:
        async with client:
            # Only expose the client to health checks once the connection succeeds
            pyrogram_client = client
            me = await client.get_me()
            log.info("pyrogram_me", id=me.id, username=me.username, phone=me.phone_number)
            
            # Bulk-hydrate Pyrogram's peer cache by walking all dialogs once.
            # This populates access_hash entries for every joined channel/group
            # so that get_chat_history() calls never hit "Peer id invalid".
            dialog_count = 0
            async for _ in client.get_dialogs():
                dialog_count += 1
            log.info("peer_cache_hydrated", dialogs=dialog_count)
            
            # Load whitelist into memory
            await whitelist_reload()
            
            # ── Polling loop — primary ingestion mechanism ────────────────────────
            # Runs _catch_up (staggered) on a fixed interval.
            async def _polling_loop():
                # Immediate first run to catch up from last known state
                try:
                    await _catch_up(client)
                except AuthKeyUnregistered:
                    raise  # bubble up to the outer handler
                except Exception as exc:
                    log.error("poll_first_run_failed", error=str(exc))
                while True:
                    await asyncio.sleep(POLL_INTERVAL)
                    try:
                        # Refresh whitelist before each cycle
                        await load_whitelist_from_db()
                        await _catch_up(client)
                    except AuthKeyUnregistered:
                        raise  # bubble up to the outer handler
                    except Exception as exc:
                        log.error("poll_loop_error", error=str(exc))
            asyncio.create_task(_polling_loop())

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

            log.info("ingestion_service_ready")
            try:
                from pyrogram import idle
                await idle()
            finally:
                await close_arq_pool()
    except AuthKeyUnregistered:
        # User terminated the session from the Telegram app.
        # Mark it as revoked in the DB and fall into idle mode so
        # Docker doesn't restart-loop with a dead session string.
        log.warning(
            "telegram_session_terminated_by_user — "
            "marking session as revoked in platform_sessions"
        )
        pyrogram_client = None
        await _revoke_active_session()
        log.warning(
            "no_telegram_session_available — session was revoked; "
            "re-authenticate via /api/v1/admin/telegram/auth/send-code"
        )
        try:
            await asyncio.Event().wait()
        finally:
            await close_arq_pool()
    except Exception as exc:
        # Catch-all for connection failures (network errors, corrupt session, etc.)
        # Fall into idle mode so the internal API stays up and the operator can
        # re-authenticate — instead of Docker restart-looping with a bad session.
        log.error(
            "pyrogram_connection_failed — falling back to idle mode",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        pyrogram_client = None
        try:
            await asyncio.Event().wait()
        finally:
            await close_arq_pool()

if __name__ == "__main__":
    asyncio.run(main())
