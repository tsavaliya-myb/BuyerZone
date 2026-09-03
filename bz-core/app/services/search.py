"""Qdrant search + PostgreSQL enrichment."""

from __future__ import annotations

import time
import uuid

import structlog
from qdrant_client.models import FieldCondition, Filter, MatchValue, QueryRequest
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.core.qdrant import get_qdrant_client
from app.models.inhouse_product import InHouseProduct
from app.models.monitored_chat import MonitoredChat
from app.models.product import Product
from app.schemas.search import SearchResponse, SearchResultItem

log = structlog.get_logger(__name__)
settings = get_settings()

STRONG_MATCH_THRESHOLD = 0.90
BORDERLINE_MATCH_THRESHOLD = 0.85


async def search_by_image(vector: list[float], page: int, size: int, db: AsyncSession, sort_by: str | None = None, sort_order: str = "desc") -> SearchResponse:
    t0 = time.perf_counter()
    client = get_qdrant_client()

    offset = (page - 1) * size if not sort_by else 0
    limit = size if not sort_by else 1000

    response = await client.query_points(
        collection_name=settings.qdrant_collection,
        query=vector,
        query_filter=Filter(must=[FieldCondition(key="status", match=MatchValue(value="active"))]),
        limit=limit,
        offset=offset,
        score_threshold=settings.search_similarity_threshold,
        with_payload=True,
    )

    items = await _enrich(response.points, db, sort_by=sort_by, sort_order=sort_order, page=page, size=size)
    total = len(response.points) if sort_by else len(items)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    return SearchResponse(
        results=items, 
        total=total, 
        query_time_ms=round(elapsed_ms, 2),
        page=page,
        size=size
    )


async def search_by_text(query: str, page: int, size: int, db: AsyncSession, sort_by: str | None = None, sort_order: str = "desc") -> SearchResponse:
    t0 = time.perf_counter()
    pattern = f"%{query}%"

    from sqlalchemy import func

    total_result = await db.execute(
        select(func.count(Product.id)).where(
            Product.status == "active",
            or_(Product.name.ilike(pattern), Product.raw_caption.ilike(pattern)),
        )
    )
    total = total_result.scalar_one()

    offset = (page - 1) * size

    query_obj = (
        select(Product)
        .options(selectinload(Product.wholesaler))
        .where(
            Product.status == "active",
            or_(Product.name.ilike(pattern), Product.raw_caption.ilike(pattern)),
        )
    )
    if sort_by == "price":
        query_obj = query_obj.order_by(Product.price.asc() if sort_order == "asc" else Product.price.desc())
    elif sort_by == "receivedAt":
        query_obj = query_obj.order_by(Product.received_at.asc() if sort_order == "asc" else Product.received_at.desc())
        
    result = await db.execute(query_obj.offset(offset).limit(size))
    products = list(result.scalars().all())
    chats = await _load_chats(products, db)
    items = [_product_to_result(p, 1.0, chats) for p in products]
    elapsed_ms = (time.perf_counter() - t0) * 1000
    return SearchResponse(
        results=items, 
        total=total, 
        query_time_ms=round(elapsed_ms, 2),
        page=page,
        size=size
    )


async def search_combined(
    image_vector: list[float] | None,
    text_vector: list[float] | None,
    image_weight: float,
    page: int,
    size: int,
    db: AsyncSession,
    sort_by: str | None = None,
    sort_order: str = "desc",
    text_query: str | None = None,
) -> SearchResponse:
    t0 = time.perf_counter()
    client = get_qdrant_client()
    text_weight = 1.0 - image_weight

    fetch_k = 1000 if sort_by else 100 
    active_filter = Filter(must=[FieldCondition(key="status", match=MatchValue(value="active"))])

    scores: dict[str, float] = {}
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

    sorted_qdrant_ids = sorted(scores, key=lambda k: scores[k], reverse=True)[:fetch_k]

    product_ids_from_qdrant: list[str] = []
    if sorted_qdrant_ids:
        product_ids_from_qdrant = [
            str(r.payload["product_id"])
            for r in await client.retrieve(
                collection_name=settings.qdrant_collection,
                ids=sorted_qdrant_ids,
                with_payload=True,
            )
            if r.payload and r.payload.get("product_id")
        ]

    merged: dict[str, float] = {}
    for qdrant_id, pid in zip(sorted_qdrant_ids, product_ids_from_qdrant, strict=False):
        if pid:
            merged[pid] = scores[qdrant_id]
    for pid, kw_score in keyword_scores.items():
        if pid not in merged:
            merged[pid] = kw_score

    if not merged:
        return SearchResponse(results=[], total=0, query_time_ms=0, page=page, size=size)

    offset = (page - 1) * size
    if sort_by:
        sorted_pids = list(merged.keys())
    else:
        sorted_pids = sorted(merged, key=lambda k: merged[k], reverse=True)[offset:offset + size]
        
    total_matches = len(merged)

    query_obj = select(Product).options(selectinload(Product.wholesaler)).where(Product.id.in_([uuid.UUID(pid) for pid in sorted_pids]))
    if sort_by == "price":
        query_obj = query_obj.order_by(Product.price.asc() if sort_order == "asc" else Product.price.desc())
    elif sort_by == "receivedAt":
        query_obj = query_obj.order_by(Product.received_at.asc() if sort_order == "asc" else Product.received_at.desc())

    if sort_by:
        query_obj = query_obj.offset(offset).limit(size)

    result = await db.execute(query_obj)
    products_list = list(result.scalars().all())
    products_map = {str(p.id): p for p in products_list}

    chats = await _load_chats(products_list, db)
    
    if sort_by:
        items = [
            _product_to_result(p, merged.get(str(p.id), 0.0), chats)
            for p in products_list
        ]
    else:
        items = [
            _product_to_result(products_map[pid], merged[pid], chats)
            for pid in sorted_pids
            if pid in products_map
        ]

    elapsed_ms = (time.perf_counter() - t0) * 1000
    return SearchResponse(
        results=items, 
        total=total_matches, 
        query_time_ms=round(elapsed_ms, 2),
        page=page,
        size=size
    )


async def _enrich(qdrant_results, db: AsyncSession, sort_by: str | None = None, sort_order: str = "desc", page: int | None = None, size: int | None = None) -> list[SearchResultItem]:
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

    query = select(Product).options(selectinload(Product.wholesaler)).where(Product.id.in_(product_ids))
    if sort_by == "price":
        query = query.order_by(Product.price.asc() if sort_order == "asc" else Product.price.desc())
    elif sort_by == "receivedAt":
        query = query.order_by(Product.received_at.asc() if sort_order == "asc" else Product.received_at.desc())
        
    if sort_by and page is not None and size is not None:
        query = query.offset((page - 1) * size).limit(size)

    result = await db.execute(query)
    products_list = list(result.scalars().all())
    chats = await _load_chats(products_list, db)

    if sort_by:
        items = []
        for p in products_list:
            items.append(_product_to_result(p, scores_by_product.get(str(p.id), 0.0), chats))
        return items
    else:
        products = {str(p.id): p for p in products_list}
        items = []
        for r in qdrant_results:
            pid = r.payload.get("product_id") if r.payload else None
            if pid and pid in products:
                items.append(_product_to_result(products[pid], scores_by_product.get(pid, 0.0), chats))
        return items


async def _load_chats(products: list[Product], db: AsyncSession) -> dict[str, MonitoredChat]:
    chat_ids = {p.chat_id for p in products if p.chat_id}
    if not chat_ids:
        return {}
    rows = await db.execute(select(MonitoredChat).where(MonitoredChat.chat_id.in_(chat_ids)))
    return {c.chat_id: c for c in rows.scalars().all()}


async def search_from_inhouse_product(
    inhouse_product: InHouseProduct, page: int, size: int, db: AsyncSession, sort_by: str | None = None, sort_order: str = "desc"
) -> SearchResponse:
    t0 = time.perf_counter()
    client = get_qdrant_client()
    fetch_k = 1000 if sort_by else 100
    active_filter = Filter(must=[FieldCondition(key="status", match=MatchValue(value="active"))])

    scores: dict[str, float] = {}
    if inhouse_product.photos:
        photo_ids = [str(p.id) for p in inhouse_product.photos]
        records = await client.retrieve(
            collection_name=settings.qdrant_inhouse_collection,
            ids=photo_ids,
            with_vectors=True,
        )
        vectors = [r.vector for r in records if r.vector]

        if vectors:
            batch_responses = await client.query_batch_points(
                collection_name=settings.qdrant_collection,
                requests=[
                    QueryRequest(
                        query=vector,
                        filter=active_filter,
                        limit=fetch_k,
                        score_threshold=BORDERLINE_MATCH_THRESHOLD,
                        with_payload=True,
                    )
                    for vector in vectors
                ],
            )
            for response in batch_responses:
                for r in response.points:
                    pid = r.payload.get("product_id") if r.payload else None
                    if not pid:
                        continue
                    scores[pid] = max(scores.get(pid, 0.0), r.score)

    strong = {pid: s for pid, s in scores.items() if s > STRONG_MATCH_THRESHOLD}
    borderline = {pid: s for pid, s in scores.items() if BORDERLINE_MATCH_THRESHOLD <= s <= STRONG_MATCH_THRESHOLD}

    merged = dict(strong)
    if borderline and inhouse_product.keywords:
        conditions = []
        for kw in inhouse_product.keywords:
            pattern = f"%{kw}%"
            conditions.append(Product.name.ilike(pattern))
            conditions.append(Product.raw_caption.ilike(pattern))
        kw_result = await db.execute(
            select(Product.id).where(
                Product.id.in_([uuid.UUID(pid) for pid in borderline]),
                Product.status == "active",
                or_(*conditions),
            )
        )
        for (pid,) in kw_result.all():
            merged[str(pid)] = borderline[str(pid)]

    if not merged:
        return SearchResponse(
            results=[],
            total=0,
            query_time_ms=round((time.perf_counter() - t0) * 1000, 2),
            page=page,
            size=size,
        )

    offset = (page - 1) * size
    if sort_by:
        sorted_pids = list(merged.keys())
    else:
        sorted_pids = sorted(merged, key=lambda k: merged[k], reverse=True)[offset : offset + size]
        
    total_matches = len(merged)

    query_obj = select(Product).options(selectinload(Product.wholesaler)).where(Product.id.in_([uuid.UUID(pid) for pid in sorted_pids]))
    if sort_by == "price":
        query_obj = query_obj.order_by(Product.price.asc() if sort_order == "asc" else Product.price.desc())
    elif sort_by == "receivedAt":
        query_obj = query_obj.order_by(Product.received_at.asc() if sort_order == "asc" else Product.received_at.desc())

    if sort_by:
        query_obj = query_obj.offset(offset).limit(size)

    result = await db.execute(query_obj)
    products_list = list(result.scalars().all())
    products_map = {str(p.id): p for p in products_list}
    chats = await _load_chats(products_list, db)
    
    if sort_by:
        items = [
            _product_to_result(p, merged.get(str(p.id), 0.0), chats)
            for p in products_list
        ]
    else:
        items = [
            _product_to_result(products_map[pid], merged[pid], chats)
            for pid in sorted_pids
            if pid in products_map
        ]

    elapsed_ms = (time.perf_counter() - t0) * 1000
    return SearchResponse(
        results=items, total=total_matches, query_time_ms=round(elapsed_ms, 2), page=page, size=size
    )


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
