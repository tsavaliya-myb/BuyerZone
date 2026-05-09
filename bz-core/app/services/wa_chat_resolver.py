"""WA chat resolve logic — wraps the WA Listener internal API calls."""

from __future__ import annotations

import structlog

from app.core import whatsapp as wa

log = structlog.get_logger(__name__)


async def resolve_query(query: str) -> list[dict] | dict:
    """Resolve a name fragment or invite URL.

    Returns a list of matching chats (Path A — name search) or a single
    chat dict (Path B — invite link). Raises on listener errors.
    """
    if query.strip().startswith("http"):
        return await wa.resolve_invite_link(query.strip())
    else:
        return await wa.get_joined_chats(query.strip())
