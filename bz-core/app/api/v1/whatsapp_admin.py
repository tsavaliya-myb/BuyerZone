"""Admin endpoints for WhatsApp pairing, chat management, and status."""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import whatsapp as wa
from app.core.database import get_db
from app.core.security import require_admin
from app.models.monitored_chat import MonitoredChat
from app.models.platform_session import PlatformSession
from app.models.product import Product
from app.schemas.whatsapp_admin import (
    WAChatAddRequest,
    WAChatResolveRequest,
    WAChatResponse,
    WAPairRequest,
    WAPairResponse,
    WASessionUpdateRequest,
    WAStatus,
)
from app.services.wa_chat_resolver import resolve_query

router = APIRouter(prefix="/admin/whatsapp", tags=["whatsapp-admin"])
log = structlog.get_logger(__name__)


def _normalize_phone(raw: str) -> str:
    phone = raw.strip().lstrip("+").replace(" ", "").replace("-", "")
    if not phone.isdigit() or not (7 <= len(phone) <= 15):
        raise HTTPException(
            status_code=400,
            detail="Invalid phone — digits only, 7-15 chars, country code included",
        )
    return phone


# ── Status ─────────────────────────────────────────────────────────────────────


@router.get("/status", response_model=WAStatus)
async def get_status(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    listener_status = await wa.get_status()
    q = await db.execute(
        select(PlatformSession).where(
            PlatformSession.platform == "whatsapp",
            PlatformSession.status == "active",
        )
    )
    sess = q.scalar_one_or_none()
    return WAStatus(
        state=listener_status.get("state", "unreachable"),
        phone=sess.phone_number if sess else None,
        display_name=sess.display_name if sess else None,
        session_id=str(sess.id) if sess else None,
    )


# ── Pairing ────────────────────────────────────────────────────────────────────


@router.post("/pair", response_model=WAPairResponse)
async def request_pair_code(body: WAPairRequest, _=Depends(require_admin)):
    phone = _normalize_phone(body.phone)
    try:
        result = await wa.request_pair_code(phone)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=str(exc)) from exc
    except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.TimeoutException) as exc:
        log.warning("wa_listener_pair_failed", error=str(exc))
        raise HTTPException(
            status_code=502,
            detail={"error": "wa_listener_unavailable", "message": str(exc)},
        ) from exc
    return WAPairResponse(code=result["code"], expires_in=result.get("expires_in", 60))


@router.delete("", status_code=204)
async def revoke_session(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    """Revoke active WhatsApp session and reset the listener to awaiting_pair_code."""
    await db.execute(
        update(PlatformSession)
        .where(
            PlatformSession.platform == "whatsapp",
            PlatformSession.status == "active",
        )
        .values(status="revoked", updated_at=datetime.utcnow())
    )
    await db.commit()
    try:
        await wa.reset_session()
    except Exception as exc:
        log.warning("wa_reset_failed", error=str(exc))


# ── Chat management ────────────────────────────────────────────────────────────


@router.post("/chats/resolve")
async def resolve_chats(body: WAChatResolveRequest, _=Depends(require_admin)):
    """Resolve a name fragment or invite URL to a list of WA chats."""
    try:
        result = await resolve_query(body.query)
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json()
        except Exception:
            detail = str(exc)
        raise HTTPException(status_code=exc.response.status_code, detail=detail) from exc
    except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.TimeoutException) as exc:
        # wa_listener crashed, timed out, or dropped the connection mid-response
        log.warning("wa_listener_unreachable", error=str(exc))
        raise HTTPException(
            status_code=502,
            detail={"error": "wa_listener_unavailable", "message": str(exc)},
        ) from exc
    return result


@router.post("/chats/add", response_model=WAChatResponse, status_code=201)
async def add_chat(
    body: WAChatAddRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_admin),
):
    jid = body.jid.strip()

    # Defensive: verify the bot is still a member of this JID
    # try:
    #     joined = await wa.get_joined_chats()
    #     print(joined)
    #     joined_jids = {c["jid"] for c in joined} if isinstance(joined, list) else set()
    #     if jid not in joined_jids:
    #         raise HTTPException(
    #             status_code=409,
    #             detail={
    #                 "error": "not_joined",
    #                 "message": f"Bot is not a member of {jid}. Join on the linked phone first.",
    #             },
    #         )
    # except HTTPException:
    #     raise
    # except Exception as exc:
    #     log.warning("wa_joined_check_failed", jid=jid, error=str(exc))

    # Determine chat_type from JID suffix
    if jid.endswith("@newsletter") or jid.endswith("@broadcast"):
        chat_type = "wa_channel"
    elif jid.endswith("@s.whatsapp.net"):
        chat_type = "wa_contact"
    else:
        chat_type = "wa_group"

    chat_name = (body.chat_name or "").strip() or jid

    # Upsert into monitored_chats
    existing = await db.execute(
        select(MonitoredChat).where(
            MonitoredChat.chat_id == jid,
            MonitoredChat.platform == "whatsapp",
        )
    )
    chat = existing.scalar_one_or_none()
    if chat:
        chat.is_active = True
        chat.chat_name = chat_name
    else:
        chat = MonitoredChat(
            chat_id=jid,
            platform="whatsapp",
            chat_name=chat_name,
            chat_type=chat_type,
            added_by=uuid.UUID(admin["sub"]),
        )
        db.add(chat)

    await db.flush()
    await db.commit()
    await db.refresh(chat)

    # Notify listener to reload whitelist
    await wa.reload_whitelist()

    # For channels: subscribe to live updates
    if chat_type == "wa_channel":
        await wa.subscribe_newsletter(jid)

    count_result = await db.execute(select(func.count(Product.id)).where(Product.chat_id == jid))
    count = count_result.scalar_one()

    return WAChatResponse(
        id=str(chat.id),
        jid=chat.chat_id,
        platform=chat.platform,
        chat_name=chat.chat_name,
        chat_type=chat.chat_type,
        is_active=chat.is_active,
        product_count=count,
    )


@router.delete("/chats/{chat_db_id}", status_code=204)
async def remove_chat(
    chat_db_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    result = await db.execute(
        select(MonitoredChat).where(
            MonitoredChat.id == chat_db_id,
            MonitoredChat.platform == "whatsapp",
        )
    )
    chat = result.scalar_one_or_none()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    chat.is_active = False
    await db.commit()
    await wa.reload_whitelist()


@router.get("/chats", response_model=list[WAChatResponse])
async def list_chats(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await db.execute(
        select(MonitoredChat)
        .where(MonitoredChat.platform == "whatsapp")
        .order_by(MonitoredChat.added_at.desc())
    )
    chats = result.scalars().all()

    counts_result = await db.execute(
        select(Product.chat_id, func.count(Product.id))
        .where(Product.source_platform == "whatsapp")
        .group_by(Product.chat_id)
    )
    counts = {row[0]: row[1] for row in counts_result.fetchall()}

    return [
        WAChatResponse(
            id=str(c.id),
            jid=c.chat_id,
            platform=c.platform,
            chat_name=c.chat_name,
            chat_type=c.chat_type,
            is_active=c.is_active,
            product_count=counts.get(c.chat_id, 0),
        )
        for c in chats
    ]


# ── Internal: Node.js listener → FastAPI session-update ───────────────────────


@router.post("/internal/session-update", include_in_schema=False)
async def session_update(
    body: WASessionUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Called by the WA Listener on every creds.update to persist auth state."""
    secret = request.headers.get("X-Internal-Secret", "")
    from app.config import get_settings

    if secret != get_settings().wa_internal_secret:
        raise HTTPException(status_code=403, detail="Forbidden")

    phone = body.phone.strip().lstrip("+").replace(" ", "")
    auth_state_str = json.dumps(body.auth_state)

    await db.execute(
        update(PlatformSession)
        .where(
            PlatformSession.platform == "whatsapp",
            PlatformSession.status == "active",
        )
        .values(status="revoked", updated_at=datetime.utcnow())
    )

    existing_q = await db.execute(
        select(PlatformSession).where(
            PlatformSession.platform == "whatsapp",
            PlatformSession.phone_number == phone,
        )
    )
    existing = existing_q.scalar_one_or_none()
    if existing:
        existing.session_data = auth_state_str
        existing.status = "active"
        existing.display_name = body.display_name
        existing.updated_at = datetime.utcnow()
    else:
        db.add(
            PlatformSession(
                platform="whatsapp",
                phone_number=phone,
                session_data=auth_state_str,
                status="active",
                display_name=body.display_name,
            )
        )

    await db.commit()
    log.debug("wa_session_saved", phone=phone)
    return {"status": "ok"}
