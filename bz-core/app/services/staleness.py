"""Cron job — marks products older than STALENESS_DAYS as stale."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import update

from app.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.qdrant import get_qdrant_client
from app.models.product import Product

log = structlog.get_logger(__name__)
settings = get_settings()


async def run_staleness_check() -> int:
    """Mark active products older than staleness_days as stale. Returns count updated."""
    cutoff = datetime.now(UTC) - timedelta(days=settings.staleness_days)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            update(Product)
            .where(Product.status == "active", Product.received_at < cutoff)
            .values(status="stale")
            .returning(Product.id, Product.qdrant_id)
        )
        rows = result.fetchall()
        await session.commit()

    if not rows:
        log.info("staleness_check_done", updated=0)
        return 0

    # Mirror status update to Qdrant payload
    qdrant_client = get_qdrant_client()
    qdrant_ids = [str(row.qdrant_id) for row in rows]

    await qdrant_client.set_payload(
        collection_name=settings.qdrant_collection,
        payload={"status": "stale"},
        points=qdrant_ids,
    )

    log.info("staleness_check_done", updated=len(rows))
    return len(rows)
