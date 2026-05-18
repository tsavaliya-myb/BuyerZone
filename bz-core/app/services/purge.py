"""Weekly purge service.

Drops ALL product data from every storage layer:
  - PostgreSQL  : ingestion_logs → products → wholesalers  (FK order)
  - Qdrant      : delete every point in the collection (then re-create)
  - Redis       : flush all  buyerzone:*  keys
                  (ARQ result / queue keys are intentionally left intact)
  - iDrive E2   : delete all objects under the  products/  prefix

Runs every Sunday at midnight IST (Saturday 18:30 UTC) via the ARQ cron.
"""

from __future__ import annotations

import asyncio

import structlog
from sqlalchemy import delete

from app.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.qdrant import get_qdrant_client
from app.core.redis import get_redis
from app.models.ingestion_log import IngestionLog
from app.models.product import Product
from app.models.wholesaler import Wholesaler
from app.services.storage import _get_client as _get_s3_client

log = structlog.get_logger(__name__)
settings = get_settings()


async def run_weekly_purge() -> dict[str, int | str]:
    """Purge all product data from Postgres, Qdrant, and Redis.

    Returns a summary dict suitable for structured logging.
    """
    summary: dict[str, int | str] = {}

    # ── 1. PostgreSQL ──────────────────────────────────────────────────────────
    async with AsyncSessionLocal() as session:
        # ingestion_logs first — FK references products.id
        result_logs = await session.execute(delete(IngestionLog))
        summary["pg_ingestion_logs_deleted"] = result_logs.rowcount

        result_products = await session.execute(delete(Product))
        summary["pg_products_deleted"] = result_products.rowcount

        result_wholesalers = await session.execute(delete(Wholesaler))
        summary["pg_wholesalers_deleted"] = result_wholesalers.rowcount

        await session.commit()

    log.info(
        "weekly_purge_postgres_done",
        ingestion_logs=summary["pg_ingestion_logs_deleted"],
        products=summary["pg_products_deleted"],
        wholesalers=summary["pg_wholesalers_deleted"],
    )

    # ── 2. Qdrant ─────────────────────────────────────────────────────────────
    qdrant = get_qdrant_client()
    try:
        await qdrant.delete_collection(settings.qdrant_collection)
        summary["qdrant_collection_wiped"] = True
        # Re-create collection + payload indexes immediately so search works
        # without waiting for a worker restart.
        from app.core.qdrant import ensure_collection
        await ensure_collection()
        log.info("weekly_purge_qdrant_done", collection=settings.qdrant_collection)
    except Exception as exc:
        summary["qdrant_error"] = str(exc)
        log.error("weekly_purge_qdrant_failed", error=str(exc))

    # ── 3. Redis — buyerzone:* namespace only ─────────────────────────────────
    redis = get_redis()
    try:
        pattern = "buyerzone:*"
        deleted_keys = 0
        # Use SCAN to avoid blocking on large keyspaces
        async for key in redis.scan_iter(match=pattern, count=500):
            await redis.delete(key)
            deleted_keys += 1
        summary["redis_keys_deleted"] = deleted_keys
        log.info("weekly_purge_redis_done", keys_deleted=deleted_keys, pattern=pattern)
    except Exception as exc:
        summary["redis_error"] = str(exc)
        log.error("weekly_purge_redis_failed", error=str(exc))

    # ── 4. iDrive E2 — delete all objects under products/ ────────────────────
    # boto3 is synchronous; run in a thread so the event loop stays free.
    def _purge_s3() -> int:
        s3 = _get_s3_client()
        bucket = settings.s3_bucket_name
        prefix = "products/"
        total_deleted = 0
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            objects = page.get("Contents", [])
            if not objects:
                continue
            # S3 delete_objects accepts at most 1 000 keys per call
            delete_payload = {"Objects": [{"Key": obj["Key"]} for obj in objects]}
            resp = s3.delete_objects(Bucket=bucket, Delete=delete_payload)
            total_deleted += len(resp.get("Deleted", []))
        return total_deleted

    try:
        s3_deleted = await asyncio.to_thread(_purge_s3)
        summary["s3_objects_deleted"] = s3_deleted
        log.info("weekly_purge_s3_done", objects_deleted=s3_deleted, bucket=settings.s3_bucket_name)
    except Exception as exc:
        summary["s3_error"] = str(exc)
        log.error("weekly_purge_s3_failed", error=str(exc))

    log.info("weekly_purge_complete", **summary)
    return summary
