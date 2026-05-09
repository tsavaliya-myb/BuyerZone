"""Qdrant search + PostgreSQL enrichment."""

from __future__ import annotations

import time
import uuid

import structlog
from qdrant_client.models import FieldCondition, Filter, MatchValue
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.core.qdrant import get_qdrant_client
from app.models.monitored_chat import MonitoredChat
from app.models.product import Product
from app.schemas.search import SearchResponse, SearchResultItem

log = structlog.get_logger(__name__)
settings = get_settings()


async def search_by_image(vector: list[float], top_k: int, db: AsyncSession) -> SearchResponse:
    t0 = time.perf_counter()
    client = get_qdrant_client()

    response = await client.query_points(
        collection_name=settings.qdrant_collection,
        query=vector,
        query_filter=Filter(must=[FieldCondition(key="status", match=MatchValue(value="active"))]),
        limit=top_k,
        score_threshold=settings.search_similarity_threshold,
        with_payload=True,
    )

    items = await _enrich(response.points, db)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    return SearchResponse(results=items, total=len(items), query_time_ms=round(elapsed_ms, 2))


async def search_by_text(query: str, top_k: int, db: AsyncSession) -> SearchResponse:
    t0 = time.perf_counter()
    pattern = f"%{query}%"
    result = await db.execute(
        select(Product)
        .options(selectinload(Product.wholesaler))
        .where(
            Product.status == "active",
            or_(Product.name.ilike(pattern), Product.raw_caption.ilike(pattern)),
        )
        .limit(top_k)
    )
    products = result.scalars().all()
    chats = await _load_chats(products, db)
    items = [_product_to_result(p, 1.0, chats) for p in products]
    elapsed_ms = (time.perf_counter() - t0) * 1000
    return SearchResponse(results=items, total=len(items), query_time_ms=round(elapsed_ms, 2))


async def search_combined(
    image_vector: list[float] | None,
    text_vector: list[float] | None,
    image_weight: float,
    top_k: int,
    db: AsyncSession,
    text_query: str | None = None,
) -> SearchResponse:
    """Weighted fusion of image and text CLIP vectors, supplemented by keyword matching."""
    t0 = time.perf_counter()
    client = get_qdrant_client()
    text_weight = 1.0 - image_weight

    fetch_k = min(top_k * 3, 100)
    active_filter = Filter(must=[FieldCondition(key="status", match=MatchValue(value="active"))])

    # qdrant_id → fused score
    scores: dict[str, float] = {}
    # product_id (str UUID) → fused score for keyword-only hits
    keyword_scores: dict[str, float] = {}

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

    # Keyword supplement: products matching name/raw_caption that may not rank in Qdrant
    if text_query:
        pattern = f"%{text_query}%"
        kw_result = await db.execute(
            select(Product.id)
            .where(
                Product.status == "active",
                or_(Product.name.ilike(pattern), Product.raw_caption.ilike(pattern)),
            )
            .limit(fetch_k)
        )
        for (pid,) in kw_result.all():
            keyword_scores[str(pid)] = text_weight

    # Resolve qdrant scores → product_ids
    sorted_qdrant_ids = sorted(scores, key=lambda k: scores[k], reverse=True)[:top_k]

    product_ids_from_qdrant: list[str] = []
    if sorted_qdrant_ids:
        product_ids_from_qdrant = [
            r.payload.get("product_id")
            for r in await client.retrieve(
                collection_name=settings.qdrant_collection,
                ids=sorted_qdrant_ids,
                with_payload=True,
            )
            if r.payload
        ]

    # Merge: give qdrant hits their vector score; add keyword-only hits with text_weight
    merged: dict[str, float] = {}
    for qdrant_id, pid in zip(sorted_qdrant_ids, product_ids_from_qdrant):
        if pid:
            merged[pid] = scores[qdrant_id]
    for pid, kw_score in keyword_scores.items():
        if pid not in merged:
            merged[pid] = kw_score

    if not merged:
        return SearchResponse(results=[], total=0, query_time_ms=0)

    sorted_pids = sorted(merged, key=lambda k: merged[k], reverse=True)[:top_k]

    result = await db.execute(
        select(Product)
        .options(selectinload(Product.wholesaler))
        .where(Product.id.in_([uuid.UUID(pid) for pid in sorted_pids]))
    )
    products_map = {str(p.id): p for p in result.scalars().all()}

    chats = await _load_chats(list(products_map.values()), db)
    items = [
        _product_to_result(products_map[pid], merged[pid], chats)
        for pid in sorted_pids
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
        .options(selectinload(Product.wholesaler))
        .where(Product.id.in_(product_ids))
    )
    products = {str(p.id): p for p in result.scalars().all()}
    chats = await _load_chats(list(products.values()), db)

    items = []
    for r in qdrant_results:
        pid = r.payload.get("product_id") if r.payload else None
        if pid and pid in products:
            items.append(_product_to_result(products[pid], scores_by_product.get(pid, 0.0), chats))

    return items


async def _load_chats(
    products: list[Product], db: AsyncSession
) -> dict[str, MonitoredChat]:
    chat_ids = {p.chat_id for p in products if p.chat_id}
    if not chat_ids:
        return {}
    rows = await db.execute(
        select(MonitoredChat).where(MonitoredChat.chat_id.in_(chat_ids))
    )
    return {c.chat_id: c for c in rows.scalars().all()}


def _product_to_result(
    product: Product, score: float, chats: dict[str, MonitoredChat]
) -> SearchResultItem:
    wholesaler = getattr(product, "wholesaler", None)
    chat = chats.get(product.chat_id) if product.chat_id else None
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
        platform=product.source_platform,
        raw_caption=product.raw_caption,
        received_at=product.received_at,
        status=product.status,
    )
