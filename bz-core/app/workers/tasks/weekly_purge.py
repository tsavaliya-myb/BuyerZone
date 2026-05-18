from app.services.purge import run_weekly_purge


async def weekly_purge(ctx: dict) -> None:
    """ARQ cron task — purges all product data every Sunday at midnight IST.

    Clears: Postgres (ingestion_logs / products / wholesalers),
            Qdrant (all vectors), Redis (buyerzone:* keys),
            iDrive E2 S3 (products/ prefix).
    """
    await run_weekly_purge()
