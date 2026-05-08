"""Internal endpoints consumed by other BuyerZone modules."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.qdrant import get_qdrant_client
from app.core.redis import get_redis
from app.core.security import get_current_user
from app.models.product import Product
from app.models.wholesaler import Wholesaler
from app.schemas.admin import WholesalerResponse
from app.schemas.product import ProductResponse

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/products/recent", response_model=list[ProductResponse])
async def recent_products(
    n: int = Query(default=50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    result = await db.execute(
        select(Product)
        .where(Product.status == "active")
        .order_by(Product.received_at.desc())
        .limit(n)
    )
    return [ProductResponse.model_validate(p) for p in result.scalars().all()]


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
