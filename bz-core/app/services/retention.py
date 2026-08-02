"""Retention purge service.

Deletes only data older than RETENTION_DAYS, keeping a rolling window
of recent products intact (unlike the old weekly full-wipe):
  - PostgreSQL  : ingestion_logs (orphan + linked to expired products) → products
                  → orphaned wholesalers (no products left)
  - Qdrant      : delete points with received_at < cutoff (payload range filter)
  - iDrive E2   : delete only the image objects belonging to expired products

Runs daily via the ARQ cron (see app/workers/arq_worker.py).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import structlog
from qdrant_client.models import FieldCondition, Filter, Range
from sqlalchemy import delete, func, select

from app.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.qdrant import get_qdrant_client
from app.models.ingestion_log import IngestionLog
from app.models.product import Product
from app.models.wholesaler import Wholesaler
from app.services.storage import delete_image

log = structlog.get_logger(__name__)
settings = get_settings()

BATCH_SIZE = 500


async def run_retention_purge() -> dict[str, int | str]:
    """Delete products (and dependents) older than settings.retention_days.

    Returns a summary dict suitable for structured logging.
    """
    cutoff = (datetime.now(UTC) - timedelta(days=settings.retention_days)).replace(tzinfo=None)
    summary: dict[str, int | str] = {
        "pg_products_deleted": 0,
        "pg_ingestion_logs_deleted": 0,
        "pg_wholesalers_deleted": 0,
        "s3_objects_deleted": 0,
    }

    # ── 1. PostgreSQL — expired products, batched ──────────────────────────────
    async with AsyncSessionLocal() as session:
        while True:
            rows = (
                await session.execute(
                    select(Product.id, Product.image_key)
                    .where(Product.received_at < cutoff)
                    .limit(BATCH_SIZE)
                )
            ).all()
            if not rows:
                break

            batch_ids = [row.id for row in rows]

            result_logs = await session.execute(
                delete(IngestionLog).where(IngestionLog.product_id.in_(batch_ids))
            )
            summary["pg_ingestion_logs_deleted"] += result_logs.rowcount

            result_products = await session.execute(
                delete(Product).where(Product.id.in_(batch_ids))
            )
            summary["pg_products_deleted"] += result_products.rowcount
            await session.commit()

            # Best-effort S3 cleanup for this batch — don't fail the loop on one bad key.
            for row in rows:
                if not row.image_key:
                    continue
                try:
                    await asyncio.to_thread(delete_image, row.image_key)
                    summary["s3_objects_deleted"] += 1
                except Exception as exc:
                    log.warning("retention_purge_s3_delete_failed", key=row.image_key, error=str(exc))

        # Orphan ingestion_logs — skipped/failed/duplicate entries never tied to
        # a product, aged out independently by their own timestamp.
        result_orphan_logs = await session.execute(
            delete(IngestionLog).where(
                IngestionLog.product_id.is_(None), IngestionLog.processed_at < cutoff
            )
        )
        summary["pg_ingestion_logs_deleted"] += result_orphan_logs.rowcount
        await session.commit()

        # Wholesalers with no remaining products.
        result_wholesalers = await session.execute(
            delete(Wholesaler).where(
                ~select(Product.id)
                .where(Product.wholesaler_id == Wholesaler.id)
                .exists()
            )
        )
        summary["pg_wholesalers_deleted"] = result_wholesalers.rowcount
        await session.commit()

    log.info("retention_purge_postgres_done", **{k: v for k, v in summary.items() if k.startswith("pg_")})

    # ── 2. Qdrant — delete points older than cutoff via payload filter ────────
    qdrant = get_qdrant_client()
    try:
        await qdrant.delete(
            collection_name=settings.qdrant_collection,
            points_selector=Filter(
                must=[FieldCondition(key="received_at", range=Range(lt=cutoff.timestamp()))]
            ),
        )
        log.info("retention_purge_qdrant_done", collection=settings.qdrant_collection, cutoff=cutoff.isoformat())
    except Exception as exc:
        summary["qdrant_error"] = str(exc)
        log.error("retention_purge_qdrant_failed", error=str(exc))

    log.info("retention_purge_complete", **summary)
    return summary
