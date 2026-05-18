"""WA chat resolve logic — wraps the WA Listener internal API calls."""

from __future__ import annotations

import structlog

from app.core import whatsapp as wa

log = structlog.get_logger(__name__)


def _parse_phone(query: str) -> str | None:
    """Return normalised digits if *query* looks like a phone number, else None."""
    cleaned = query.strip().lstrip("+").replace(" ", "").replace("-", "")
    if cleaned.isdigit() and 7 <= len(cleaned) <= 15:
        return cleaned
    return None


async def resolve_query(query: str) -> list[dict] | dict:
    """Resolve a name fragment, invite URL, or plain phone number.

    - Path A — name fragment   → list of matching joined chats
    - Path B — invite URL      → single chat dict from the invite link
    - Path C — phone number    → synthetic wa_contact result (no listener call)
    """
    raw = query.strip()

    # Path B: invite link
    if raw.startswith("http"):
        return await wa.resolve_invite_link(raw)

    # Path C: plain phone number → build JID directly
    phone = _parse_phone(raw)
    if phone:
        jid = f"{phone}@s.whatsapp.net"
        return [
            {
                "jid": jid,
                "name": f"+{phone}",
                "type": "wa_contact",
                "participant_count": None,
                "already_monitored": False,
            }
        ]

    # Path A: name / keyword search
    return await wa.get_joined_chats(raw)
