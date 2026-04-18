"""HTTP client for the ingestion service internal API (port 8001).

The admin API uses this instead of opening a second Pyrogram session.
"""

import httpx

from app.config import get_settings

settings = get_settings()


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
