from app.services.staleness import run_staleness_check


async def staleness_check(ctx: dict) -> None:
    """Periodic ARQ cron task — marks old products as stale."""
    await run_staleness_check()
