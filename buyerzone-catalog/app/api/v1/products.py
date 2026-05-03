import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.database import get_db
from app.core.security import require_admin
from app.models.product import Product
from app.schemas.product import ProductListResponse, ProductResponse, ProductStatusUpdate

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=ProductListResponse)
async def list_products(
    wholesaler_id: uuid.UUID | None = Query(None),
    chat_id: int | None = Query(None),
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
        .options(joinedload(Product.wholesaler), joinedload(Product.chat))
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

    items = []
    for p in products:
        item = ProductResponse.model_validate(p)
        if p.wholesaler:
            item.wholesaler_name = p.wholesaler.name
            item.wholesaler_phone = p.wholesaler.phone
        if p.chat:
            item.chat_name = p.chat.chat_name
        items.append(item)

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
        select(Product)
        .options(joinedload(Product.wholesaler), joinedload(Product.chat))
        .where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    item = ProductResponse.model_validate(product)
    if product.wholesaler:
        item.wholesaler_name = product.wholesaler.name
        item.wholesaler_phone = product.wholesaler.phone
    if product.chat:
        item.chat_name = product.chat.chat_name
    return item


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
    return ProductResponse.model_validate(product)
