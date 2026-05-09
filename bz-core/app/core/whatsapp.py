"""HTTP client for the WA Listener internal API (Node.js Baileys service).

FastAPI uses this to proxy admin actions to the listener and to push
whitelist / auth state changes without restarting containers.
"""

from __future__ import annotations

import httpx
import structlog

from app.config import get_settings

settings = get_settings()
log = structlog.get_logger(__name__)

_HEADERS = {"X-Internal-Secret": settings.wa_internal_secret}


async def _get(path: str, **params) -> dict:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{settings.wa_listener_url}{path}", params=params, headers=_HEADERS
        )
        resp.raise_for_status()
        return resp.json()


async def _post(path: str, body: dict | None = None) -> dict:
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            f"{settings.wa_listener_url}{path}",
            json=body or {},
            headers=_HEADERS,
        )
        resp.raise_for_status()
        return resp.json()


async def get_status() -> dict:
    try:
        return await _get("/wa-internal/status")
    except Exception:
        return {"state": "unreachable", "connected": False}


async def request_pair_code(phone: str) -> dict:
    return await _post("/wa-internal/pair", {"phone": phone})


async def get_joined_chats(query: str = "") -> list[dict]:
    return await _get("/wa-internal/joined", q=query)


async def resolve_invite_link(url: str) -> dict:
    return await _post("/wa-internal/resolve-link", {"url": url})


async def reload_whitelist() -> None:
    try:
        await _post("/wa-internal/whitelist/reload")
    except Exception as exc:
        log.warning("wa_whitelist_reload_failed", error=str(exc))


async def subscribe_newsletter(jid: str) -> None:
    try:
        await _post("/wa-internal/subscribe-newsletter", {"jid": jid})
    except Exception as exc:
        log.warning("wa_subscribe_newsletter_failed", jid=jid, error=str(exc))


async def reset_session() -> None:
    await _post("/wa-internal/reset")


class WAListenerError(Exception):
    def __init__(self, code: str, http_status: int, payload: dict):
        super().__init__(code)
        self.code = code
        self.http_status = http_status
        self.payload = payload
