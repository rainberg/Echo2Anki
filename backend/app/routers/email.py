"""Email verification code routes - delegates to auth-service."""
import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.email_service import send_email_code, verify_email_code

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/email", tags=["email"])


class SendCodeRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    purpose: str = Field(default="register", max_length=30)

    @field_validator("purpose")
    @classmethod
    def validate_purpose(cls, v: str) -> str:
        allowed = {"register", "reset_password", "change_email"}
        if v not in allowed:
            raise ValueError(f"无效的用途，允许: {allowed}")
        return v

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if "@" not in v:
            raise ValueError("无效的邮箱地址")
        return v


class VerifyCodeRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    code: str = Field(min_length=4, max_length=6)
    purpose: str = Field(default="register", max_length=30)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if "@" not in v:
            raise ValueError("无效的邮箱地址")
        return v


class SendCodeResponse(BaseModel):
    success: bool
    message: str


class VerifyCodeResponse(BaseModel):
    success: bool
    message: str


@router.post("/send-code", response_model=SendCodeResponse)
async def handle_send_code(body: SendCodeRequest):
    """Send email verification code via auth-service."""
    success, message = await send_email_code(body.email, body.purpose)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS if "频繁" in message else status.HTTP_502_BAD_GATEWAY,
            detail=message,
        )
    return SendCodeResponse(success=True, message=message)


@router.post("/verify-code", response_model=VerifyCodeResponse)
async def handle_verify_code(body: VerifyCodeRequest):
    """Verify email verification code via auth-service."""
    valid = await verify_email_code(body.email, body.code)
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="验证码错误或已过期",
        )
    return VerifyCodeResponse(success=True, message="验证成功")
