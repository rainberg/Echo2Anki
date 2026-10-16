"""Email service - delegates to auth-service internal API."""
import logging
import httpx

logger = logging.getLogger(__name__)

AUTH_SERVICE_URL = "http://127.0.0.1:9000"
SERVICE_KEY = "anki-svc-key-2026-secure"


async def send_email_code(to_email: str, purpose: str = "register") -> tuple[bool, str]:
    """Send email verification code via auth-service internal endpoint.
    Returns (success, message)."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{AUTH_SERVICE_URL}/api/auth/email/send-internal",
                json={
                    "email": to_email,
                    "purpose": purpose,
                    "service_key": SERVICE_KEY,
                },
            )
            data = resp.json()
            if resp.status_code == 200:
                return True, data.get("message", "验证码已发送")
            else:
                detail = data.get("detail", "邮件发送失败")
                return False, detail
    except Exception as e:
        logger.error("Failed to call auth-service email send: %s", e)
        return False, "邮件服务暂时不可用"


async def verify_email_code(email: str, code: str) -> bool:
    """Verify email code via auth-service internal endpoint."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{AUTH_SERVICE_URL}/api/auth/email/verify-internal",
                json={
                    "email": email,
                    "code": code,
                    "service_key": SERVICE_KEY,
                },
            )
            data = resp.json()
            return data.get("valid", False)
    except Exception as e:
        logger.error("Failed to call auth-service email verify: %s", e)
        return False
