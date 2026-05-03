import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from passlib.context import CryptContext
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import create_access_token, require_admin
from app.models.admin_user import AdminUser
from app.models.ingestion_log import IngestionLog
from app.models.monitored_chat import MonitoredChat
from app.models.product import Product
from app.models.wholesaler import Wholesaler
from app.schemas.admin import (
    ChatAddRequest,
    ChatSearchRequest,
    DashboardStats,
    IngestionLogResponse,
    LoginRequest,
    MonitoredChatResponse,
    TokenResponse,
    WholesalerCreate,
    WholesalerResponse,
    WholesalerUpdate,
)
from app.services.chat_resolver import (
    add_to_whitelist,
    remove_from_whitelist,
)

router = APIRouter(prefix="/admin", tags=["admin"])
pwd_context = CryptContext(schemes=["sha256_crypt"])


# ── Auth ───────────────────────────────────────────────────────────────────────


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AdminUser).where(AdminUser.username == body.username, AdminUser.is_active.is_(True))
    )
    user = result.scalar_one_or_none()
    if not user or not pwd_context.verify(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token({"sub": str(user.id), "role": "admin"})
    return TokenResponse(access_token=token)


# ── Chat whitelist management ──────────────────────────────────────────────────


@router.post("/chats/search")
async def search_chats(body: ChatSearchRequest, _=Depends(require_admin)):
    from app.core.telegram import search_dialogs_via_ingestion

    results = await search_dialogs_via_ingestion(body.name)
    if not results:
        raise HTTPException(status_code=404, detail="No matching chats found")
    return results


@router.post("/chats/add", response_model=MonitoredChatResponse, status_code=201)
async def add_chat(
    body: ChatAddRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_admin),
):
    from app.core.telegram import resolve_dialog_via_ingestion

    match = await resolve_dialog_via_ingestion(body.chat_name)
    if not match:
        raise HTTPException(
            status_code=404,
            detail=f"Chat '{body.chat_name}' not found in joined dialogs",
        )

    # Check if already monitored
    existing = await db.execute(
        select(MonitoredChat).where(MonitoredChat.chat_id == match["chat_id"])
    )
    chat = existing.scalar_one_or_none()
    if chat:
        chat.is_active = True
    else:
        chat = MonitoredChat(
            chat_id=match["chat_id"],
            chat_name=match["chat_name"],
            chat_type=match["chat_type"],
            added_by=uuid.UUID(admin["sub"]),
        )
        db.add(chat)

    await db.flush()
    await add_to_whitelist(match["chat_id"], match["chat_name"])
    await db.commit()
    await db.refresh(chat)
    return MonitoredChatResponse.model_validate(chat)


@router.delete("/chats/{chat_db_id}", status_code=204)
async def remove_chat(
    chat_db_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    result = await db.execute(select(MonitoredChat).where(MonitoredChat.id == chat_db_id))
    chat = result.scalar_one_or_none()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    chat.is_active = False
    await remove_from_whitelist(chat.chat_id)
    await db.commit()


@router.get("/chats", response_model=list[MonitoredChatResponse])
async def list_chats(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await db.execute(select(MonitoredChat).order_by(MonitoredChat.added_at.desc()))
    chats = result.scalars().all()
    # Attach product counts
    counts_result = await db.execute(
        select(Product.chat_id, func.count(Product.id)).group_by(Product.chat_id)
    )
    counts = {row[0]: row[1] for row in counts_result.fetchall()}
    items = []
    for chat in chats:
        item = MonitoredChatResponse.model_validate(chat)
        item.product_count = counts.get(chat.chat_id, 0)
        items.append(item)
    return items


# ── Wholesalers ────────────────────────────────────────────────────────────────


@router.post("/wholesalers", response_model=WholesalerResponse, status_code=201)
async def create_wholesaler(
    body: WholesalerCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    wholesaler = Wholesaler(**body.model_dump())
    db.add(wholesaler)
    await db.commit()
    await db.refresh(wholesaler)
    return WholesalerResponse.model_validate(wholesaler)


@router.get("/wholesalers", response_model=list[WholesalerResponse])
async def list_wholesalers(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await db.execute(select(Wholesaler).order_by(Wholesaler.name))
    return [WholesalerResponse.model_validate(w) for w in result.scalars().all()]


@router.patch("/wholesalers/{wholesaler_id}", response_model=WholesalerResponse)
async def update_wholesaler(
    wholesaler_id: uuid.UUID,
    body: WholesalerUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    result = await db.execute(select(Wholesaler).where(Wholesaler.id == wholesaler_id))
    wholesaler = result.scalar_one_or_none()
    if not wholesaler:
        raise HTTPException(status_code=404, detail="Wholesaler not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(wholesaler, field, value)
    await db.commit()
    await db.refresh(wholesaler)
    return WholesalerResponse.model_validate(wholesaler)


# ── Logs & Stats ───────────────────────────────────────────────────────────────


@router.get("/logs", response_model=list[IngestionLogResponse])
async def get_logs(
    chat_id: int | None = Query(None),
    log_status: str | None = Query(None, alias="status"),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    q = select(IngestionLog).order_by(IngestionLog.processed_at.desc())
    if chat_id:
        q = q.where(IngestionLog.chat_id == chat_id)
    if log_status:
        q = q.where(IngestionLog.status == log_status)
    if date_from:
        q = q.where(IngestionLog.processed_at >= date_from)
    if date_to:
        q = q.where(IngestionLog.processed_at <= date_to)
    q = q.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(q)
    return [IngestionLogResponse.model_validate(r) for r in result.scalars().all()]


@router.get("/stats", response_model=DashboardStats)
async def get_stats(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    # Product.created_at is a naive TIMESTAMP column (no tzinfo) — asyncpg
    # can't bind tz-aware datetimes against it, so compute bounds naive-UTC.
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=7)

    total = (await db.execute(select(func.count(Product.id)))).scalar_one()
    active = (
        await db.execute(select(func.count(Product.id)).where(Product.status == "active"))
    ).scalar_one()
    stale = (
        await db.execute(select(func.count(Product.id)).where(Product.status == "stale"))
    ).scalar_one()
    total_wholesalers = (await db.execute(select(func.count(Wholesaler.id)))).scalar_one()
    active_chats = (
        await db.execute(
            select(func.count(MonitoredChat.id)).where(MonitoredChat.is_active.is_(True))
        )
    ).scalar_one()
    today_count = (
        await db.execute(select(func.count(Product.id)).where(Product.created_at >= today_start))
    ).scalar_one()
    week_count = (
        await db.execute(select(func.count(Product.id)).where(Product.created_at >= week_start))
    ).scalar_one()

    by_chat_result = await db.execute(
        select(Product.chat_id, func.count(Product.id))
        .group_by(Product.chat_id)
        .order_by(func.count(Product.id).desc())
        .limit(10)
    )
    by_chat = [{"chat_id": r[0], "count": r[1]} for r in by_chat_result.fetchall()]

    by_wholesaler_result = await db.execute(
        select(Product.wholesaler_id, func.count(Product.id))
        .group_by(Product.wholesaler_id)
        .order_by(func.count(Product.id).desc())
        .limit(10)
    )
    by_wholesaler = [
        {"wholesaler_id": str(r[0]), "count": r[1]} for r in by_wholesaler_result.fetchall()
    ]

    return DashboardStats(
        total_products=total,
        active_products=active,
        stale_products=stale,
        total_wholesalers=total_wholesalers,
        active_chats=active_chats,
        ingested_today=today_count,
        ingested_this_week=week_count,
        by_chat=by_chat,
        by_wholesaler=by_wholesaler,
    )
