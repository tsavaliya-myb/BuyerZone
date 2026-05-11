import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import require_admin
from app.models.monitored_chat import MonitoredChat
from app.models.product import Product
from app.schemas.product import ProductListResponse, ProductResponse, ProductStatusUpdate


async def _load_chats(products, db: AsyncSession) -> dict[str, MonitoredChat]:
    chat_ids = {p.chat_id for p in products if p.chat_id}
    if not chat_ids:
        return {}
    rows = await db.execute(select(MonitoredChat).where(MonitoredChat.chat_id.in_(chat_ids)))
    return {c.chat_id: c for c in rows.scalars().all()}


def _to_response(product: Product, chats: dict[str, MonitoredChat]) -> ProductResponse:
    wholesaler = getattr(product, "wholesaler", None)
    chat = chats.get(product.chat_id) if product.chat_id else None
    item = ProductResponse.model_validate(product)
    item.wholesaler_name = wholesaler.name if wholesaler else None
    item.wholesaler_phone = wholesaler.phone if wholesaler else None
    item.chat_name = chat.chat_name if chat else None
    item.platform = chat.platform if chat else product.source_platform
    return item


router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=ProductListResponse)
async def list_products(
    wholesaler_id: uuid.UUID | None = Query(None),
    chat_id: str | None = Query(None),
    status: str | None = Query("active"),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    q = (
        select(Product)
        .options(selectinload(Product.wholesaler))
        .order_by(Product.received_at.desc())
    )
    if wholesaler_id:
        q = q.where(Product.wholesaler_id == wholesaler_id)
    if chat_id:
        q = q.where(Product.chat_id == chat_id)
    if status:
        q = q.where(Product.status == status)
    if date_from:
        q = q.where(Product.received_at >= date_from)
    if date_to:
        q = q.where(Product.received_at <= date_to)

    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar_one()

    q = q.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(q)
    products = result.scalars().all()

    chats = await _load_chats(products, db)
    items = [_to_response(p, chats) for p in products]

    return ProductListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=-(-total // page_size),
    )


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    result = await db.execute(
        select(Product).options(selectinload(Product.wholesaler)).where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    chats = await _load_chats([product], db)
    return _to_response(product, chats)


@router.patch("/{product_id}/status", response_model=ProductResponse)
async def update_product_status(
    product_id: uuid.UUID,
    body: ProductStatusUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    if body.status not in ("active", "stale", "removed"):
        raise HTTPException(status_code=400, detail="Invalid status value")

    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    product.status = body.status

    # Mirror to Qdrant
    from app.config import get_settings
    from app.core.qdrant import get_qdrant_client

    settings = get_settings()
    qdrant_client = get_qdrant_client()
    await qdrant_client.set_payload(
        collection_name=settings.qdrant_collection,
        payload={"status": body.status},
        points=[str(product.qdrant_id)],
    )

    await db.commit()
    await db.refresh(product)
    chats = await _load_chats([product], db)
    return _to_response(product, chats)
