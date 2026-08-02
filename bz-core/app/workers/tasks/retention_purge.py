from app.services.retention import run_retention_purge


async def retention_purge(ctx: dict) -> None:
    """ARQ cron task — daily, deletes products (and dependents) older than
    settings.retention_days, keeping a rolling window of recent data intact.
    """
    await run_retention_purge()
