"""Admin endpoints for Telegram session authentication (UI-driven OTP flow).

The actual Pyrogram login state machine lives in the ingestion service —
this router proxies into it and persists the resulting session string in
the platform_sessions table.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_admin
from app.core.telegram import (
    IngestionAuthError,
    auth_send_code_via_ingestion,
    auth_verify_code_via_ingestion,
    auth_verify_password_via_ingestion,
    health_via_ingestion,
    session_reload_via_ingestion,
)
from app.models.platform_session import PlatformSession
from app.schemas.telegram_auth import (
    SendCodeRequest,
    SendCodeResponse,
    TelegramAuthStatus,
    VerifyCodeRequest,
    VerifyPasswordRequest,
    VerifyResponse,
)

router = APIRouter(prefix="/admin/telegram/auth", tags=["telegram-auth"])


# Map ingestion-side error codes → admin-facing HTTP responses.
_ERROR_HTTP = {
    "invalid_phone": (400, "Invalid phone number"),
    "flood_wait": (429, "Telegram is rate-limiting this number, retry later"),
    "login_not_found": (404, "Login session not found or expired — restart the flow"),
    "invalid_code": (400, "Invalid verification code"),
    "code_expired": (400, "Verification code expired — request a new one"),
    "invalid_password": (400, "Invalid 2FA password"),
}


def _http_from_auth_error(exc: IngestionAuthError) -> HTTPException:
    status, msg = _ERROR_HTTP.get(exc.code, (exc.http_status or 500, exc.code))
    return HTTPException(status_code=status, detail=msg)


def _normalize_phone(raw: str) -> str:
    phone = raw.strip().lstrip("+").replace(" ", "").replace("-", "")
    if not phone.isdigit() or not (7 <= len(phone) <= 15):
        raise HTTPException(
            status_code=400,
            detail="Invalid phone — digits only, 7-15 chars, country code included",
        )
    return phone


@router.post("/send-code", response_model=SendCodeResponse)
async def send_code(body: SendCodeRequest, _=Depends(require_admin)):
    phone = _normalize_phone(body.phone)
    try:
        result = await auth_send_code_via_ingestion(phone)
    except IngestionAuthError as exc:
        raise _http_from_auth_error(exc) from exc
    return SendCodeResponse(**result)


@router.post("/verify-code", response_model=VerifyResponse)
async def verify_code(
    body: VerifyCodeRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_admin),
):
    try:
        result = await auth_verify_code_via_ingestion(body.login_id, body.code)
    except IngestionAuthError as exc:
        raise _http_from_auth_error(exc) from exc

    if result.get("status") == "requires_2fa":
        return VerifyResponse(status="requires_2fa")
    return await _persist_and_reload(db, uuid.UUID(admin["sub"]), result)


@router.post("/verify-password", response_model=VerifyResponse)
async def verify_password(
    body: VerifyPasswordRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_admin),
):
    try:
        result = await auth_verify_password_via_ingestion(body.login_id, body.password)
    except IngestionAuthError as exc:
        raise _http_from_auth_error(exc) from exc
    return await _persist_and_reload(db, uuid.UUID(admin["sub"]), result)


@router.get("/status", response_model=TelegramAuthStatus)
async def status_endpoint(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    q = await db.execute(
        select(PlatformSession).where(
            PlatformSession.platform == "telegram",
            PlatformSession.status == "active",
        )
    )
    sess = q.scalar_one_or_none()
    health = await health_via_ingestion()
    return TelegramAuthStatus(
        connected=bool(health.get("connected")),
        phone=sess.phone_number if sess else None,
        display_name=sess.display_name if sess else None,
        session_id=str(sess.id) if sess else None,
    )


@router.delete("", status_code=204)
async def revoke_active(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    await db.execute(
        update(PlatformSession)
        .where(
            PlatformSession.platform == "telegram",
            PlatformSession.status == "active",
        )
        .values(status="revoked", updated_at=datetime.utcnow())
    )
    await db.commit()
    await session_reload_via_ingestion()


async def _persist_and_reload(
    db: AsyncSession,
    admin_id: uuid.UUID,
    result: dict,
) -> VerifyResponse:
    session_string = result.get("session_string")
    phone = result.get("phone")
    display_name = result.get("display_name")
    if not session_string or not phone:
        raise HTTPException(status_code=502, detail="Ingestion did not return a session")

    # Revoke the previous active session before inserting the new one — the
    # partial unique index forbids two active rows for the same platform.
    await db.execute(
        update(PlatformSession)
        .where(
            PlatformSession.platform == "telegram",
            PlatformSession.status == "active",
        )
        .values(status="revoked", updated_at=datetime.utcnow())
    )

    existing_q = await db.execute(
        select(PlatformSession).where(
            PlatformSession.platform == "telegram",
            PlatformSession.phone_number == phone,
        )
    )
    existing = existing_q.scalar_one_or_none()
    if existing:
        existing.session_data = session_string
        existing.status = "active"
        existing.display_name = display_name
        existing.created_by = admin_id
        sess = existing
    else:
        sess = PlatformSession(
            platform="telegram",
            phone_number=phone,
            session_data=session_string,
            status="active",
            display_name=display_name,
            created_by=admin_id,
        )
        db.add(sess)

    await db.flush()
    await db.commit()
    await db.refresh(sess)

    # Bounce the ingestion process so it boots with the new DB session.
    await session_reload_via_ingestion()

    return VerifyResponse(
        status="success",
        session_id=str(sess.id),
        phone=phone,
        display_name=display_name,
    )
