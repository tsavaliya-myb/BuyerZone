"""HTTP client for the ingestion service internal API (port 8001).

The admin API uses this instead of opening a second Pyrogram session.
"""

import httpx
import structlog

from app.config import get_settings

settings = get_settings()
log = structlog.get_logger(__name__)


async def search_dialogs_via_ingestion(name: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            f"{settings.ingestion_internal_url}/dialogs/search",
            params={"name": name},
        )
        resp.raise_for_status()
        return resp.json()


async def resolve_dialog_via_ingestion(name: str) -> dict | None:
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            f"{settings.ingestion_internal_url}/dialogs/resolve",
            params={"name": name},
        )
        resp.raise_for_status()
        data = resp.json()
        return data if data else None


async def reload_whitelist_via_ingestion() -> None:
    """Tell the ingestion service to immediately reload its in-memory whitelist
    from PostgreSQL. Failures are swallowed — the periodic background refresher
    in the ingestion service will catch up within WHITELIST_REFRESH_INTERVAL."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{settings.ingestion_internal_url}/whitelist/reload",
            )
            resp.raise_for_status()
    except Exception as exc:
        log.warning("whitelist_reload_push_failed", error=str(exc))
