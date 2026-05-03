"""Qdrant search + PostgreSQL enrichment."""

from __future__ import annotations

import time
import uuid

import structlog
from qdrant_client.models import FieldCondition, Filter, MatchValue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.config import get_settings
from app.core.qdrant import get_qdrant_client
from app.models.product import Product
from app.schemas.search import SearchResponse, SearchResultItem

log = structlog.get_logger(__name__)
settings = get_settings()


async def search_by_image(
    vector: list[float], top_k: int, db: AsyncSession
) -> SearchResponse:
    t0 = time.perf_counter()
    client = get_qdrant_client()

    response = await client.query_points(
        collection_name=settings.qdrant_collection,
        query=vector,
        query_filter=Filter(
            must=[FieldCondition(key="status", match=MatchValue(value="active"))]
        ),
        limit=top_k,
        score_threshold=settings.search_similarity_threshold,
        with_payload=True,
    )

    items = await _enrich(response.points, db)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    return SearchResponse(results=items, total=len(items), query_time_ms=round(elapsed_ms, 2))


async def search_by_text(query: str, top_k: int, db: AsyncSession) -> SearchResponse:
    t0 = time.perf_counter()
    result = await db.execute(
        select(Product)
        .options(joinedload(Product.wholesaler), joinedload(Product.chat))
        .where(
            Product.status == "active",
            Product.name.ilike(f"%{query}%"),
        )
        .limit(top_k)
    )
    products = result.scalars().all()
    items = [_product_to_result(p, 1.0) for p in products]
    elapsed_ms = (time.perf_counter() - t0) * 1000
    return SearchResponse(results=items, total=len(items), query_time_ms=round(elapsed_ms, 2))


async def search_combined(
    image_vector: list[float] | None,
    text_vector: list[float] | None,
    image_weight: float,
    top_k: int,
    db: AsyncSession,
) -> SearchResponse:
    """Weighted fusion of image and text CLIP vectors."""
    t0 = time.perf_counter()
    client = get_qdrant_client()
    text_weight = 1.0 - image_weight

    # Fetch more candidates then re-rank
    fetch_k = min(top_k * 3, 100)
    active_filter = Filter(
        must=[FieldCondition(key="status", match=MatchValue(value="active"))]
    )

    scores: dict[str, float] = {}

    if image_vector:
        image_response = await client.query_points(
            collection_name=settings.qdrant_collection,
            query=image_vector,
            query_filter=active_filter,
            limit=fetch_k,
            score_threshold=settings.search_similarity_threshold,
            with_payload=True,
        )
        for r in image_response.points:
            scores[str(r.id)] = scores.get(str(r.id), 0) + r.score * image_weight

    if text_vector:
        text_response = await client.query_points(
            collection_name=settings.qdrant_collection,
            query=text_vector,
            query_filter=active_filter,
            limit=fetch_k,
            score_threshold=settings.search_similarity_threshold,
            with_payload=True,
        )
        for r in text_response.points:
            scores[str(r.id)] = scores.get(str(r.id), 0) + r.score * text_weight

    # Sort by fused score and take top_k
    sorted_ids = sorted(scores, key=lambda k: scores[k], reverse=True)[:top_k]
    if not sorted_ids:
        return SearchResponse(results=[], total=0, query_time_ms=0)

    product_ids_str = [
        r.payload.get("product_id")
        for r in (
            await client.retrieve(
                collection_name=settings.qdrant_collection,
                ids=sorted_ids,
                with_payload=True,
            )
        )
        if r.payload
    ]

    result = await db.execute(
        select(Product)
        .options(joinedload(Product.wholesaler), joinedload(Product.chat))
        .where(Product.id.in_([uuid.UUID(pid) for pid in product_ids_str if pid]))
    )
    products_map = {str(p.id): p for p in result.scalars().all()}

    items = []
    for _pid in sorted_ids:
        # Retrieve payload to get product_id
        pass  # already resolved above

    # Simpler: just map by product_id from scores
    items = [
        _product_to_result(products_map[pid], scores.get(pid, 0.0))
        for pid in sorted_ids
        if pid in products_map
    ]

    elapsed_ms = (time.perf_counter() - t0) * 1000
    return SearchResponse(results=items, total=len(items), query_time_ms=round(elapsed_ms, 2))


async def _enrich(qdrant_results, db: AsyncSession) -> list[SearchResultItem]:
    if not qdrant_results:
        return []

    product_ids = [
        uuid.UUID(r.payload["product_id"])
        for r in qdrant_results
        if r.payload and r.payload.get("product_id")
    ]
    scores_by_product = {
        r.payload["product_id"]: r.score
        for r in qdrant_results
        if r.payload and r.payload.get("product_id")
    }

    result = await db.execute(
        select(Product)
        .options(joinedload(Product.wholesaler), joinedload(Product.chat))
        .where(Product.id.in_(product_ids))
    )
    products = {str(p.id): p for p in result.scalars().all()}

    items = []
    for r in qdrant_results:
        pid = r.payload.get("product_id") if r.payload else None
        if pid and pid in products:
            items.append(_product_to_result(products[pid], scores_by_product.get(pid, 0.0)))

    return items


def _product_to_result(product: Product, score: float) -> SearchResultItem:
    wholesaler = getattr(product, "wholesaler", None)
    chat = getattr(product, "chat", None)
    return SearchResultItem(
        product_id=product.id,
        similarity_score=round(score, 4),
        name=product.name,
        price=float(product.price) if product.price else None,
        currency=product.currency,
        image_url=product.image_url,
        wholesaler_name=wholesaler.name if wholesaler else None,
        wholesaler_phone=wholesaler.phone if wholesaler else None,
        chat_name=chat.chat_name if chat else None,
        received_at=product.received_at,
        status=product.status,
    )
