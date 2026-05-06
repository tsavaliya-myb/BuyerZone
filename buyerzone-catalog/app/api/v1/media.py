"""Public media proxy — streams private R2 objects with no auth required."""

import asyncio
from concurrent.futures import ThreadPoolExecutor

from botocore.exceptions import ClientError
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.config import get_settings
from app.services.storage import _get_client

router = APIRouter(tags=["media"])
settings = get_settings()

ALLOWED_PREFIXES = {"products"}
_executor = ThreadPoolExecutor(max_workers=4)


def _fetch_object(key: str):
    client = _get_client()
    return client.get_object(Bucket=settings.s3_bucket_name, Key=key)


@router.get("/media/{prefix}/{rest:path}", include_in_schema=False)
async def serve_media(prefix: str, rest: str):
    if prefix not in ALLOWED_PREFIXES:
        raise HTTPException(status_code=404)

    key = f"{prefix}/{rest}"
    loop = asyncio.get_event_loop()
    try:
        obj = await loop.run_in_executor(_executor, _fetch_object, key)
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        raise HTTPException(status_code=404 if code in ("NoSuchKey", "404") else 502) from None

    content_type = obj.get("ContentType", "image/jpeg")

    def iter_body():
        yield from obj["Body"].iter_chunks(chunk_size=65536)

    return StreamingResponse(
        iter_body(),
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=86400, immutable"},
    )
