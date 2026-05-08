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


# ── Auth proxy (admin API → ingestion service) ────────────────────────────────
#
# The Pyrogram client used during the login flow must keep a single connection
# alive between send_code and sign_in. The admin API runs with multiple workers,
# so we host that state inside the singleton ingestion process instead.


async def auth_send_code_via_ingestion(phone: str) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{settings.ingestion_internal_url}/auth/send-code",
            json={"phone": phone},
        )
        return _unwrap(resp)


async def auth_verify_code_via_ingestion(login_id: str, code: str) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{settings.ingestion_internal_url}/auth/verify-code",
            json={"login_id": login_id, "code": code},
        )
        return _unwrap(resp)


async def auth_verify_password_via_ingestion(login_id: str, password: str) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{settings.ingestion_internal_url}/auth/verify-password",
            json={"login_id": login_id, "password": password},
        )
        return _unwrap(resp)


async def session_reload_via_ingestion() -> None:
    """Trigger a graceful exit — supervisor restarts the process and it
    picks up the newly-saved active session from the DB."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(f"{settings.ingestion_internal_url}/session/reload")
    except Exception as exc:
        log.warning("ingestion_session_reload_failed", error=str(exc))


async def health_via_ingestion() -> dict:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{settings.ingestion_internal_url}/health")
            resp.raise_for_status()
            return resp.json()
    except Exception:
        return {"status": "unreachable", "connected": False}


def _unwrap(resp: httpx.Response) -> dict:
    """Translate ingestion-side error envelopes to exceptions the API layer
    can turn into HTTP responses."""
    try:
        body = resp.json()
    except Exception:
        body = {}
    if resp.status_code >= 400:
        err = body.get("error", "ingestion_error") if isinstance(body, dict) else "ingestion_error"
        raise IngestionAuthError(err, resp.status_code, body if isinstance(body, dict) else {})
    return body


class IngestionAuthError(Exception):
    def __init__(self, code: str, http_status: int, payload: dict):
        super().__init__(code)
        self.code = code
        self.http_status = http_status
        self.payload = payload
