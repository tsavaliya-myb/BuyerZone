"""ARQ worker entrypoint.

Run with:  python -m arq app.workers.arq_worker.WorkerSettings
"""

import structlog
from arq import cron

from app.config import get_settings
from app.core.logging_config import configure_logging
from app.workers.tasks.process_message import process_message
from app.workers.tasks.retention_purge import retention_purge

configure_logging()

log = structlog.get_logger(__name__)
settings = get_settings()


async def startup(ctx: dict) -> None:
    """Preload CLIP model and ensure Qdrant collection + indexes exist."""
    log.info("worker_startup_clip_load")
    from app.core.clip import _load

    _load()
    log.info("worker_startup_clip_ready")

    from app.core.qdrant import ensure_collection

    await ensure_collection()
    log.info("worker_startup_qdrant_ready")


class WorkerSettings:
    functions = [process_message]
    cron_jobs = [
        # Daily retention purge, 18:29 UTC = 23:59 IST.
        # Deletes products (+ dependent ingestion_logs, orphaned wholesalers,
        # Qdrant points, S3 images) older than settings.retention_days.
        cron(retention_purge, hour={18}, minute={29}, name="retention_purge"),
    ]
    on_startup = startup
    redis_settings = settings.arq_redis_settings
    max_jobs = 5  # pipeline is mixed CPU (CLIP) + I/O (R2, Qdrant, DB) — overlap is key to throughput
    job_timeout = 600  # 10 minutes — CLIP inference + DB writes on slow hardware
    keep_result = 3600  # keep job results for 1 hour
