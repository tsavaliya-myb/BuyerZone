"""Core processing pipeline — called by ARQ worker for each ingested message."""

from __future__ import annotations

import base64
import re
import uuid
from datetime import UTC, datetime

import structlog

from app.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.exceptions import ProcessingError
from app.core.qdrant import get_qdrant_client
from app.services.storage import upload_image

log = structlog.get_logger(__name__)
settings = get_settings()

# Price extraction — INR only (₹, Rs, optional "price"/"rate" prefix, or bare number followed by /-)
_PRICE_PREFIX = r"(?:(?:price|rate)\s*[:\-]?\s*)?"
_PRICE_RE = re.compile(
    rf"{_PRICE_PREFIX}(?:₹|Rs\.?\s*)(\d[\d,]*(?:\.\d{{1,2}})?)"
    rf"|{_PRICE_PREFIX}(\d[\d,]*)\s*/-"
    rf"|(?:price|rate)\s*[:\-]?\s*(\d[\d,]*(?:\.\d{{1,2}})?)",
    re.IGNORECASE,
)
# Name = caption with price tokens stripped
_CLEAN_RE = re.compile(
    rf"{_PRICE_PREFIX}(?:₹|Rs\.?\s*)\d[\d,]*(?:\.\d{{1,2}})?"
    rf"|{_PRICE_PREFIX}\d[\d,]*\s*/-"
    rf"|(?:price|rate)\s*[:\-]?\s*\d[\d,]*(?:\.\d{{1,2}})?",
    re.IGNORECASE,
)


def _validate_image(data: bytes) -> bool:
    """Check magic bytes for JPEG/PNG/WEBP."""
    return (
        data[:3] == b"\xff\xd8\xff"  # JPEG
        or data[:8] == b"\x89PNG\r\n\x1a\n"  # PNG
        or data[:4] == b"RIFF"  # WEBP
    )


def _extract_price(caption: str) -> float | None:
    m = _PRICE_RE.search(caption)
    if not m:
        return None
    raw = (m.group(1) or m.group(2) or m.group(3)).replace(",", "")
    try:
        return float(raw)
    except ValueError:
        return None


def _extract_name(caption: str) -> str | None:
    name = _CLEAN_RE.sub("", caption).strip()
    if not name:
        return None
    # First non-empty line, capped at 500 chars to fit products.name VARCHAR(500)
    first_line = next((ln.strip() for ln in name.splitlines() if ln.strip()), name)
    return first_line[:500]


async def _get_wholesaler_id(
    session,
    sender_id: int | None,
    sender_username: str | None = None,
    sender_name: str | None = None,
    chat_title: str | None = None,
):
    """Resolve a wholesaler row for the Telegram sender.

    If the sender isn't registered yet, insert a stub row so their products
    are immediately attributable and can participate in per-wholesaler dedup.
    Admins can later rename / deactivate via the admin API.

    Uses ON CONFLICT (telegram_id) to stay safe under concurrent ingests.
    """
    if sender_id is None:
        return None

    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models.wholesaler import Wholesaler

    result = await session.execute(
        select(Wholesaler.id).where(Wholesaler.telegram_id == sender_id)
    )
    wid = result.scalar_one_or_none()
    if wid is not None:
        return wid

    # Prefer the source group/channel title (it identifies the wholesaler
    # as a business) → sender display name → @username → numeric id fallback.
    name = (
        (chat_title or "").strip()
        or sender_name
        or (f"@{sender_username}" if sender_username else f"tg:{sender_id}")
    )
    stmt = (
        pg_insert(Wholesaler)
        .values(
            telegram_id=sender_id,
            telegram_username=sender_username,
            name=name,
            is_active=True,
        )
        .on_conflict_do_nothing(index_elements=["telegram_id"])
        .returning(Wholesaler.id)
    )
    inserted = (await session.execute(stmt)).scalar_one_or_none()
    await session.commit()

    if inserted is not None:
        log.info(
            "wholesaler_auto_created",
            telegram_id=sender_id,
            username=sender_username,
            wholesaler_id=str(inserted),
        )
        return inserted

    # Lost the race — another worker just inserted. Re-select.
    result = await session.execute(
        select(Wholesaler.id).where(Wholesaler.telegram_id == sender_id)
    )
    return result.scalar_one_or_none()


async def _check_duplicate(
    vector: list[float], wholesaler_id: uuid.UUID | None
) -> bool:
    # Dedup is per-wholesaler by design: the same product from different
    # wholesalers (with different rates) must be kept. Skip the check
    # entirely when the sender isn't linked to a known wholesaler.
    if wholesaler_id is None:
        return False

    from datetime import timedelta

    from qdrant_client.models import FieldCondition, Filter, MatchValue, Range

    client = get_qdrant_client()
    cutoff = (datetime.now(UTC) - timedelta(days=30)).timestamp()

    must = [
        FieldCondition(key="status", match=MatchValue(value="active")),
        FieldCondition(key="wholesaler_id", match=MatchValue(value=str(wholesaler_id))),
        FieldCondition(key="received_at", range=Range(gte=cutoff)),
    ]

    response = await client.query_points(
        collection_name=settings.qdrant_collection,
        query=vector,
        query_filter=Filter(must=must),
        limit=1,
        score_threshold=settings.dedup_similarity_threshold,
    )
    return len(response.points) > 0


async def process_message(payload: dict) -> None:
    """Full pipeline. Image path: validate → upload → embed → dedup → persist.
    Text-only path: parse caption → persist (no R2, no CLIP, no dedup)."""
    from app.core.clip import embed_image
    from app.models.ingestion_log import IngestionLog
    from app.models.product import Product

    chat_id: int = payload["chat_id"]
    msg_id: int = payload["message_id"]
    caption: str = payload.get("caption", "")
    sender_id: int | None = payload.get("sender_id")
    has_image: bool = payload.get("has_image", payload.get("image_b64") is not None)
    received_at = (
        datetime.fromisoformat(payload["date"]).astimezone(UTC).replace(tzinfo=None)
        if payload.get("date")
        else datetime.utcnow()
    )

    log.info("processing_start", chat_id=chat_id, msg_id=msg_id, has_image=has_image)

    price = _extract_price(caption) if caption else None
    name = _extract_name(caption) if caption else None

    image_url: str | None = None
    image_key: str | None = None
    vector: list[float] | None = None

    if has_image:
        try:
            image_bytes = base64.b64decode(payload["image_b64"])
        except Exception as exc:
            log.error("image_decode_failed", chat_id=chat_id, msg_id=msg_id, error=str(exc))
            await _write_log(chat_id, msg_id, "failed", f"image decode error: {exc}")
            return

        if not _validate_image(image_bytes):
            log.warning("invalid_image", chat_id=chat_id, msg_id=msg_id)
            await _write_log(chat_id, msg_id, "skipped", "invalid image format")
            return

        try:
            image_url, image_key = upload_image(image_bytes, chat_id, msg_id)
        except Exception as exc:
            log.error("upload_failed", error=str(exc))
            await _write_log(chat_id, msg_id, "failed", str(exc))
            return

        try:
            vector = embed_image(image_bytes)
        except Exception as exc:
            log.error("embed_failed", error=str(exc))
            await _write_log(chat_id, msg_id, "failed", f"embedding error: {exc}")
            return

    async with AsyncSessionLocal() as session:
        wholesaler_id = await _get_wholesaler_id(
            session,
            sender_id,
            sender_username=payload.get("sender_username"),
            sender_name=payload.get("sender_name"),
            chat_title=payload.get("chat_title"),
        )

    if vector is not None and wholesaler_id is not None:
        is_dup = await _check_duplicate(vector, wholesaler_id)
        if is_dup:
            log.info("duplicate_detected", chat_id=chat_id, msg_id=msg_id)
            await _write_log(chat_id, msg_id, "duplicate", "similarity threshold exceeded")
            return

    qdrant_id = uuid.uuid4() if vector is not None else None
    product_id = uuid.uuid4()

    async with AsyncSessionLocal() as session:
        try:
            product = Product(
                id=product_id,
                qdrant_id=qdrant_id,
                wholesaler_id=wholesaler_id,
                chat_id=chat_id,
                telegram_msg_id=msg_id,
                name=name,
                raw_caption=caption or None,
                price=price,
                image_url=image_url,
                image_key=image_key,
                received_at=received_at,
            )
            session.add(product)
            await session.flush()

            if vector is not None:
                from qdrant_client.models import PointStruct
                qdrant_client = get_qdrant_client()
                await qdrant_client.upsert(
                    collection_name=settings.qdrant_collection,
                    points=[
                        PointStruct(
                            id=str(qdrant_id),
                            vector=vector,
                            payload={
                                "product_id": str(product_id),
                                "wholesaler_id": str(wholesaler_id) if wholesaler_id else None,
                                "price": price,
                                "chat_name": payload.get("chat_title", ""),
                                "received_at": received_at.timestamp(),
                                "status": "active",
                            },
                        )
                    ],
                )

            log_entry = IngestionLog(
                chat_id=chat_id,
                telegram_msg_id=msg_id,
                status="processed",
                product_id=product_id,
            )
            session.add(log_entry)
            await session.commit()
            log.info("product_persisted", product_id=str(product_id), has_image=has_image)

        except Exception as exc:
            await session.rollback()
            if qdrant_id is not None:
                try:
                    from qdrant_client.models import PointIdsList
                    qdrant_client = get_qdrant_client()
                    await qdrant_client.delete(
                        collection_name=settings.qdrant_collection,
                        points_selector=PointIdsList(points=[str(qdrant_id)]),
                    )
                except Exception:
                    pass
            log.error("persist_failed", error=str(exc))
            await _write_log(chat_id, msg_id, "failed", str(exc))
            raise ProcessingError(str(exc)) from exc


async def _write_log(
    chat_id: int, msg_id: int, status: str, reason: str | None = None
) -> None:
    from app.models.ingestion_log import IngestionLog

    async with AsyncSessionLocal() as session:
        session.add(
            IngestionLog(
                chat_id=chat_id,
                telegram_msg_id=msg_id,
                status=status,
                reason=reason,
            )
        )
        await session.commit()
