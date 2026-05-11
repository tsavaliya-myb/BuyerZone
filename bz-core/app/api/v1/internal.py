"""Internal endpoints consumed by other BuyerZone modules."""

import json

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.qdrant import get_qdrant_client
from app.core.redis import get_redis
from app.core.security import get_current_user
from app.models.monitored_chat import MonitoredChat
from app.models.platform_session import PlatformSession
from app.models.product import Product
from app.models.wholesaler import Wholesaler
from app.schemas.admin import WholesalerResponse
from app.schemas.product import ProductListResponse

router = APIRouter(prefix="/internal", tags=["internal"])


def _check_internal_key(x_internal_key: str = Header(...)):
    from app.config import get_settings

    if x_internal_key != get_settings().wa_internal_secret:
        raise HTTPException(status_code=403, detail="Forbidden")


# ── WhatsApp listener bootstrap endpoints ─────────────────────────────────────


@router.get("/whatsapp/session", include_in_schema=False)
async def wa_get_session(
    db: AsyncSession = Depends(get_db),
    _=Depends(_check_internal_key),
):
    """Return the active WhatsApp auth state for Baileys to initialise with."""
    q = await db.execute(
        select(PlatformSession).where(
            PlatformSession.platform == "whatsapp",
            PlatformSession.status == "active",
        )
    )
    sess = q.scalar_one_or_none()
    if not sess:
        return {"auth_state": None}
    try:
        auth_state = json.loads(sess.session_data)
    except Exception:
        auth_state = None
    return {"auth_state": auth_state, "phone": sess.phone_number}


@router.get("/whatsapp/monitored-chats", include_in_schema=False)
async def wa_monitored_chats(
    db: AsyncSession = Depends(get_db),
    _=Depends(_check_internal_key),
):
    """Return all active WhatsApp monitored chats for the listener whitelist."""
    result = await db.execute(
        select(MonitoredChat).where(
            MonitoredChat.platform == "whatsapp",
            MonitoredChat.is_active.is_(True),
        )
    )
    chats = result.scalars().all()
    return [{"chat_id": c.chat_id, "chat_name": c.chat_name} for c in chats]


@router.post("/whatsapp/enqueue", status_code=202, include_in_schema=False)
async def wa_enqueue(
    payload: dict,
    _=Depends(_check_internal_key),
):
    """Accept a MessagePayload from wa-listener and push it into the ARQ job queue."""
    from app.core.redis import enqueue_message

    await enqueue_message(payload, bypass_limits=False)
    return {"status": "queued"}


@router.get("/products/recent", response_model=ProductListResponse)
async def recent_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    from sqlalchemy import func
    from sqlalchemy.orm import selectinload

    from app.api.v1.products import _load_chats, _to_response

    q = (
        select(Product)
        .options(selectinload(Product.wholesaler))
        .where(Product.status == "active")
        .order_by(Product.received_at.desc())
    )

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()

    result = await db.execute(q.offset((page - 1) * page_size).limit(page_size))
    products = result.scalars().all()
    chats = await _load_chats(products, db)

    return ProductListResponse(
        items=[_to_response(p, chats) for p in products],
        total=total,
        page=page,
        page_size=page_size,
        pages=-(-total // page_size),
    )


@router.get("/wholesalers/active", response_model=list[WholesalerResponse])
async def active_wholesalers(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    result = await db.execute(
        select(Wholesaler).where(Wholesaler.is_active.is_(True)).order_by(Wholesaler.name)
    )
    return [WholesalerResponse.model_validate(w) for w in result.scalars().all()]


@router.post("/products/bulk-status", status_code=204)
async def bulk_update_status(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """payload: { product_ids: [...], status: "stale" }"""
    import uuid

    from sqlalchemy import update

    ids = [uuid.UUID(pid) for pid in payload.get("product_ids", [])]
    new_status = payload.get("status", "stale")
    if not ids:
        return

    await db.execute(update(Product).where(Product.id.in_(ids)).values(status=new_status))
    await db.commit()


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    health_status = {
        "api": "ok",
        "database": "unknown",
        "qdrant": "unknown",
        "redis": "unknown",
    }

    try:
        await db.execute(select(1))
        health_status["database"] = "ok"
    except Exception as exc:
        health_status["database"] = f"error: {exc}"

    try:
        client = get_qdrant_client()
        await client.get_collections()
        health_status["qdrant"] = "ok"
    except Exception as exc:
        health_status["qdrant"] = f"error: {exc}"

    try:
        redis = get_redis()
        await redis.ping()
        health_status["redis"] = "ok"
    except Exception as exc:
        health_status["redis"] = f"error: {exc}"

    return health_status
