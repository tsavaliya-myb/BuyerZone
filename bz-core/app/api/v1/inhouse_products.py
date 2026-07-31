import asyncio
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from qdrant_client.models import PointIdsList, PointStruct
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.core.clip import embed_image
from app.core.database import get_db
from app.core.qdrant import get_qdrant_client
from app.core.security import require_admin
from app.models.inhouse_product import InHouseProduct
from app.models.inhouse_product_photo import InHouseProductPhoto
from app.schemas.inhouse_product import (
    InHouseProductListResponse,
    InHouseProductResponse,
    InHouseProductUpdate,
)
from app.services.storage import delete_inhouse_photo, upload_inhouse_photo

router = APIRouter(prefix="/admin/inhouse-products", tags=["inhouse-products"])
settings = get_settings()

MAX_PHOTOS_PER_PRODUCT = 10

# (photo_id, url, key, embedding_vector) — carried between upload, embed, and index steps
_UploadedPhoto = tuple[uuid.UUID, str, str, list[float]]


def _validate_image(data: bytes) -> bool:
    """Check magic bytes for JPEG/PNG/WEBP."""
    return (
        data[:3] == b"\xff\xd8\xff"
        or data[:8] == b"\x89PNG\r\n\x1a\n"
        or data[:4] == b"RIFF"
    )


def _parse_keywords(keywords: str) -> list[str]:
    return [k.strip() for k in keywords.split(",") if k.strip()]


async def _embed_photo(image_bytes: bytes) -> list[float]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, embed_image, image_bytes)


async def _process_photo_uploads(
    photos: list[UploadFile], product_id: uuid.UUID
) -> list[_UploadedPhoto]:
    """Validate, upload to R2, and embed each photo. Cleans up any R2 uploads made
    so far if a later photo in the batch fails validation or embedding."""
    uploaded: list[_UploadedPhoto] = []
    try:
        for photo in photos:
            image_bytes = await photo.read()
            if not _validate_image(image_bytes):
                raise HTTPException(status_code=400, detail=f"Invalid image file: {photo.filename}")
            url, key = upload_inhouse_photo(image_bytes, product_id, photo.content_type or "image/jpeg")
            try:
                vector = await _embed_photo(image_bytes)
            except Exception as exc:
                delete_inhouse_photo(key)
                raise HTTPException(status_code=500, detail="Failed to generate image embedding") from exc
            uploaded.append((uuid.uuid4(), url, key, vector))
    except HTTPException:
        for _, _, key, _ in uploaded:
            delete_inhouse_photo(key)
        raise
    return uploaded


async def _index_photos(product_id: uuid.UUID, status: str, uploaded: list[_UploadedPhoto]) -> None:
    """Upsert embeddings for a batch of already-uploaded photos. Rolls back their
    R2 objects if Qdrant indexing fails, so we never persist a photo row with no vector."""
    if not uploaded:
        return
    qdrant_client = get_qdrant_client()
    try:
        await qdrant_client.upsert(
            collection_name=settings.qdrant_inhouse_collection,
            points=[
                PointStruct(
                    id=str(photo_id),
                    vector=vector,
                    payload={"product_id": str(product_id), "status": status},
                )
                for photo_id, _, _, vector in uploaded
            ],
        )
    except Exception as exc:
        for _, _, key, _ in uploaded:
            delete_inhouse_photo(key)
        raise HTTPException(status_code=500, detail="Failed to index image embeddings") from exc


async def _get_or_404(db: AsyncSession, product_id: uuid.UUID) -> InHouseProduct:
    result = await db.execute(
        select(InHouseProduct)
        .options(selectinload(InHouseProduct.photos))
        .where(InHouseProduct.id == product_id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.post("", response_model=InHouseProductResponse, status_code=201)
async def create_inhouse_product(
    name: str = Form(...),
    price: float = Form(..., gt=0),
    keywords: str = Form(""),
    photos: list[UploadFile] = File(default=[]),
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    if len(photos) > MAX_PHOTOS_PER_PRODUCT:
        raise HTTPException(
            status_code=400, detail=f"Max {MAX_PHOTOS_PER_PRODUCT} photos per product"
        )

    product = InHouseProduct(
        name=name,
        price=price,
        keywords=_parse_keywords(keywords),
        created_by=uuid.UUID(admin["sub"]),
    )
    db.add(product)
    await db.flush()

    uploaded = await _process_photo_uploads(photos, product.id)
    await _index_photos(product.id, "active", uploaded)

    for position, (photo_id, url, key, _) in enumerate(uploaded):
        db.add(InHouseProductPhoto(id=photo_id, product_id=product.id, url=url, key=key, position=position))

    await db.commit()
    return await _get_or_404(db, product.id)


@router.get("", response_model=InHouseProductListResponse)
async def list_inhouse_products(
    keyword: str | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    q = select(InHouseProduct).options(selectinload(InHouseProduct.photos))
    if status:
        q = q.where(InHouseProduct.status == status)
    if keyword:
        q = q.where(
            or_(
                InHouseProduct.name.ilike(f"%{keyword}%"),
                InHouseProduct.keywords.any(keyword),
            )
        )
    q = q.order_by(InHouseProduct.created_at.desc())

    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar_one()

    q = q.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(q)
    items = result.scalars().unique().all()

    return InHouseProductListResponse(
        items=[InHouseProductResponse.model_validate(p) for p in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=-(-total // page_size),
    )


@router.get("/{product_id}", response_model=InHouseProductResponse)
async def get_inhouse_product(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    return await _get_or_404(db, product_id)


@router.patch("/{product_id}", response_model=InHouseProductResponse)
async def update_inhouse_product(
    product_id: uuid.UUID,
    body: InHouseProductUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    product = await _get_or_404(db, product_id)
    changes = body.model_dump(exclude_unset=True)
    status_changed = "status" in changes and changes["status"] != product.status
    for field, value in changes.items():
        setattr(product, field, value)

    # Mirror status to Qdrant payloads, same pattern as update_product_status in products.py
    if status_changed and product.photos:
        qdrant_client = get_qdrant_client()
        await qdrant_client.set_payload(
            collection_name=settings.qdrant_inhouse_collection,
            payload={"status": product.status},
            points=[str(p.id) for p in product.photos],
        )

    await db.commit()
    return await _get_or_404(db, product_id)


@router.delete("/{product_id}", status_code=204)
async def delete_inhouse_product(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    product = await _get_or_404(db, product_id)
    if product.photos:
        qdrant_client = get_qdrant_client()
        await qdrant_client.delete(
            collection_name=settings.qdrant_inhouse_collection,
            points_selector=PointIdsList(points=[str(p.id) for p in product.photos]),
        )
        for photo in product.photos:
            delete_inhouse_photo(photo.key)
    await db.delete(product)
    await db.commit()


@router.post("/{product_id}/photos", response_model=InHouseProductResponse, status_code=201)
async def add_inhouse_product_photos(
    product_id: uuid.UUID,
    photos: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    product = await _get_or_404(db, product_id)
    if len(product.photos) + len(photos) > MAX_PHOTOS_PER_PRODUCT:
        raise HTTPException(
            status_code=400, detail=f"Max {MAX_PHOTOS_PER_PRODUCT} photos per product"
        )

    uploaded = await _process_photo_uploads(photos, product.id)
    await _index_photos(product.id, product.status, uploaded)

    next_position = len(product.photos)
    for offset, (photo_id, url, key, _) in enumerate(uploaded):
        db.add(
            InHouseProductPhoto(
                id=photo_id, product_id=product.id, url=url, key=key, position=next_position + offset
            )
        )

    await db.commit()
    return await _get_or_404(db, product_id)


@router.delete("/{product_id}/photos/{photo_id}", response_model=InHouseProductResponse)
async def delete_inhouse_product_photo(
    product_id: uuid.UUID,
    photo_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    result = await db.execute(
        select(InHouseProductPhoto).where(
            InHouseProductPhoto.id == photo_id, InHouseProductPhoto.product_id == product_id
        )
    )
    photo = result.scalar_one_or_none()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    qdrant_client = get_qdrant_client()
    await qdrant_client.delete(
        collection_name=settings.qdrant_inhouse_collection,
        points_selector=PointIdsList(points=[str(photo.id)]),
    )
    delete_inhouse_photo(photo.key)
    await db.delete(photo)
    await db.commit()
    return await _get_or_404(db, product_id)
