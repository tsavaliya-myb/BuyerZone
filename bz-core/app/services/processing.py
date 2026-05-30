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
# NOTE: Use [^\S\n] (whitespace-except-newline) so patterns don't match across lines
# (prevents phone numbers on the *next* line from being grabbed as prices).
_SP = r"[^\S\n]"                       # horizontal whitespace only
_PRICE_PREFIX = rf"(?:(?:price|rate){_SP}*[:\-]?{_SP}*)?"
_PRICE_RE = re.compile(
    rf"{_PRICE_PREFIX}(?:₹|Rs\.?{_SP}*)(\d[\d,]*(?:\.\d{{1,2}})?)"
    rf"|{_PRICE_PREFIX}(\d[\d,]*){_SP}*/-"
    rf"|(?:price|rate){_SP}*[:\-]?{_SP}*(\d[\d,]*(?:\.\d{{1,2}})?)" ,
    re.IGNORECASE,
)
_CLEAN_RE = re.compile(
    rf"{_PRICE_PREFIX}(?:₹|Rs\.?{_SP}*)\d[\d,]*(?:\.\d{{1,2}})?"
    rf"|{_PRICE_PREFIX}\d[\d,]*{_SP}*/-"
    rf"|(?:price|rate){_SP}*[:\-]?{_SP}*\d[\d,]*(?:\.\d{{1,2}})?",
    re.IGNORECASE,
)

# Maximum plausible product price in INR (₹99,99,999.99 → ~$12k).
# Anything above this is almost certainly a phone number or junk.
_MAX_PRICE = 9_999_999.99


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
        value = float(raw)
    except ValueError:
        return None
    # Reject values that overflow NUMERIC(10,2) or look like phone numbers
    if value > _MAX_PRICE or value <= 0:
        log.debug("price_rejected", raw=raw, value=value, reason="out_of_range")
        return None
    return value


def _extract_name(caption: str) -> str | None:
    name = _CLEAN_RE.sub("", caption).strip()
    if not name:
        return None
    first_line = next((ln.strip() for ln in name.splitlines() if ln.strip()), name)
    return first_line[:500]


async def _get_wholesaler_id(
    session,
    source_platform: str,
    sender_id: str | int | None,
    sender_username: str | None = None,
    sender_name: str | None = None,
    chat_title: str | None = None,
):
    """Resolve or auto-create a wholesaler row for the sender.

    Telegram: looks up by telegram_id (int).
    WhatsApp: looks up by wa_jid (string JID like "919876...@s.whatsapp.net").
    """
    if sender_id is None:
        return None

    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models.wholesaler import Wholesaler

    if source_platform == "whatsapp":
        wa_jid = str(sender_id)
        result = await session.execute(select(Wholesaler.id).where(Wholesaler.wa_jid == wa_jid))
        wid = result.scalar_one_or_none()
        if wid is not None:
            return wid

        name = (chat_title or "").strip() or sender_name or wa_jid
        stmt = (
            pg_insert(Wholesaler)
            .values(wa_jid=wa_jid, name=name, is_active=True)
            .on_conflict_do_nothing(index_elements=["wa_jid"])
            .returning(Wholesaler.id)
        )
        inserted = (await session.execute(stmt)).scalar_one_or_none()
        await session.commit()

        if inserted is not None:
            log.info("wholesaler_auto_created", wa_jid=wa_jid, wholesaler_id=str(inserted))
            return inserted

        result = await session.execute(select(Wholesaler.id).where(Wholesaler.wa_jid == wa_jid))
        return result.scalar_one_or_none()

    # Telegram path
    tg_id = int(sender_id)
    result = await session.execute(select(Wholesaler.id).where(Wholesaler.telegram_id == tg_id))
    wid = result.scalar_one_or_none()
    if wid is not None:
        return wid

    name = (
        (chat_title or "").strip()
        or sender_name
        or (f"@{sender_username}" if sender_username else f"tg:{tg_id}")
    )
    stmt = (
        pg_insert(Wholesaler)
        .values(
            telegram_id=tg_id,
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
            telegram_id=tg_id,
            username=sender_username,
            wholesaler_id=str(inserted),
        )
        return inserted

    result = await session.execute(select(Wholesaler.id).where(Wholesaler.telegram_id == tg_id))
    return result.scalar_one_or_none()


async def _check_duplicate(
    vector: list[float], wholesaler_id: uuid.UUID | None, source_platform: str
) -> bool:
    # Per-platform dedup: same wholesaler + same platform + cosine > threshold + last 30 days.
    if wholesaler_id is None:
        return False

    from datetime import timedelta

    from qdrant_client.models import FieldCondition, Filter, MatchValue, Range

    client = get_qdrant_client()
    cutoff = (datetime.now(UTC) - timedelta(days=30)).timestamp()

    must = [
        FieldCondition(key="status", match=MatchValue(value="active")),
        FieldCondition(key="wholesaler_id", match=MatchValue(value=str(wholesaler_id))),
        FieldCondition(key="source_platform", match=MatchValue(value=source_platform)),
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
    """Full pipeline. Handles both Telegram and WhatsApp payloads.

    Image path: validate → upload → embed → dedup → persist.
    Text-only path: parse caption → persist (no R2, no CLIP, no dedup).
    """
    from app.core.clip import embed_image
    from app.models.ingestion_log import IngestionLog
    from app.models.product import Product

    source_platform: str = payload.get("source_platform", "telegram")
    chat_id: str = str(payload["chat_id"])
    msg_id: str = str(payload["message_id"])

    from app.core.redis import get_redis
    redis = get_redis()
    idem_key = f"bz:processed:{source_platform}:{chat_id}:{msg_id}"
    
    if await redis.get(idem_key):
        log.info("skip_already_processed_msg_redis", chat_id=chat_id, msg_id=msg_id)
        return

    caption: str = payload.get("caption", "")
    sender_id = payload.get("sender_id")

    # Normalise image field: WhatsApp uses "image_data_b64", Telegram uses "image_b64"
    image_b64: str | None = payload.get("image_data_b64") or payload.get("image_b64")
    has_image: bool = payload.get("has_image", image_b64 is not None)

    # Normalise timestamp: WhatsApp uses "received_at", Telegram uses "date"
    raw_ts = payload.get("received_at") or payload.get("date")
    if raw_ts:
        received_at = (
            datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
            .astimezone(UTC)
            .replace(tzinfo=None)
        )
    else:
        received_at = datetime.utcnow()

    log.info(
        "processing_start",
        platform=source_platform,
        chat_id=chat_id,
        msg_id=msg_id,
        has_image=has_image,
    )

    price = _extract_price(caption) if caption else None
    name = _extract_name(caption) if caption else None

    image_url: str | None = None
    image_key: str | None = None
    vector: list[float] | None = None

    if has_image:
        if not image_b64:
            log.warning("image_missing_b64", chat_id=chat_id, msg_id=msg_id)
            await _write_log(chat_id, msg_id, "failed", "image_b64 missing in payload")
            return

        try:
            image_bytes = base64.b64decode(image_b64)
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
            import asyncio
            vector = await asyncio.get_running_loop().run_in_executor(None, embed_image, image_bytes)
        except Exception as exc:
            log.error("embed_failed", error=str(exc))
            await _write_log(chat_id, msg_id, "failed", f"embedding error: {exc}")
            return

    async with AsyncSessionLocal() as session:
        wholesaler_id = await _get_wholesaler_id(
            session,
            source_platform,
            sender_id,
            sender_username=payload.get("sender_username"),
            sender_name=payload.get("sender_name"),
            chat_title=payload.get("chat_title") or payload.get("chat_name"),
        )

    if vector is not None and wholesaler_id is not None:
        is_dup = await _check_duplicate(vector, wholesaler_id, source_platform)
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
                message_id=msg_id,
                name=name,
                raw_caption=caption or None,
                price=price,
                image_url=image_url,
                image_key=image_key,
                source_platform=source_platform,
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
                                "source_platform": source_platform,
                                "price": price,
                                "chat_name": payload.get("chat_title")
                                or payload.get("chat_name", ""),
                                "received_at": received_at.timestamp(),
                                "status": "active",
                            },
                        )
                    ],
                )

            log_entry = IngestionLog(
                chat_id=chat_id,
                message_id=msg_id,
                status="processed",
                product_id=product_id,
            )
            session.add(log_entry)
            await session.commit()
            log.info(
                "product_persisted",
                product_id=str(product_id),
                platform=source_platform,
                has_image=has_image,
            )
            try:
                await redis.setex(idem_key, 86400 * 30, "1")
            except Exception as redis_exc:
                log.warning("redis_setex_failed", error=str(redis_exc))

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


async def _write_log(chat_id: str, msg_id: str, status: str, reason: str | None = None) -> None:
    from app.models.ingestion_log import IngestionLog

    async with AsyncSessionLocal() as session:
        session.add(
            IngestionLog(
                chat_id=chat_id,
                message_id=msg_id,
                status=status,
                reason=reason,
            )
        )
        await session.commit()
