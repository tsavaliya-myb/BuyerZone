from pydantic import BaseModel, Field


class SendCodeRequest(BaseModel):
    phone: str = Field(
        ...,
        description="Digits only with country code, no '+', e.g. '919876543210'",
    )


class SendCodeResponse(BaseModel):
    login_id: str
    expires_in: int


class VerifyCodeRequest(BaseModel):
    login_id: str
    code: str


class VerifyPasswordRequest(BaseModel):
    login_id: str
    password: str


class VerifyResponse(BaseModel):
    status: str  # 'success' | 'requires_2fa'
    session_id: str | None = None
    phone: str | None = None
    display_name: str | None = None


class TelegramAuthStatus(BaseModel):
    connected: bool
    phone: str | None = None
    display_name: str | None = None
    session_id: str | None = None
