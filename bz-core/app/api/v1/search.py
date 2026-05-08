import base64

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_admin
from app.schemas.search import SearchResponse
from app.services import search as search_svc

router = APIRouter(prefix="/search", tags=["search"])


def _decode_image(b64: str) -> bytes:
    try:
        return base64.b64decode(b64)
    except Exception as err:
        raise HTTPException(status_code=400, detail="Invalid base64 image data") from err


@router.post("/image", response_model=SearchResponse)
async def search_by_image(
    file: UploadFile | None = File(None),
    image_base64: str | None = Form(None),
    top_k: int = Query(default=10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    if file:
        image_bytes = await file.read()
    elif image_base64:
        image_bytes = _decode_image(image_base64)
    else:
        raise HTTPException(status_code=400, detail="Provide file or image_base64")

    from app.core.clip import embed_image

    vector = embed_image(image_bytes)
    return await search_svc.search_by_image(vector, top_k, db)


@router.get("/text", response_model=SearchResponse)
async def search_by_text(
    q: str = Query(..., min_length=1),
    top_k: int = Query(default=10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    return await search_svc.search_by_text(q, top_k, db)


@router.post("/combined", response_model=SearchResponse)
async def search_combined(
    file: UploadFile | None = File(None),
    image_base64: str | None = Form(None),
    text: str | None = Form(None),
    image_weight: float = Form(default=0.7),
    top_k: int = Query(default=10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    from app.core.clip import embed_image, embed_text

    image_vector = None
    text_vector = None

    if file:
        image_bytes = await file.read()
        image_vector = embed_image(image_bytes)
    elif image_base64:
        image_vector = embed_image(_decode_image(image_base64))

    if text:
        text_vector = embed_text(text)

    if not image_vector and not text_vector:
        raise HTTPException(status_code=400, detail="Provide at least image or text")

    return await search_svc.search_combined(image_vector, text_vector, image_weight, top_k, db)
