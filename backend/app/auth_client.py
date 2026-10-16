import logging
from decimal import Decimal
from typing import Optional
from uuid import UUID

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_http_client: Optional[httpx.AsyncClient] = None


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=settings.AUTH_SERVICE_TIMEOUT)
    return _http_client


async def verify_token(access_token: str) -> Optional[dict]:
    client = _get_http_client()
    try:
        resp = await client.get(
            f"{settings.AUTH_SERVICE_URL}/api/auth/verify",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if resp.status_code == 200:
            return resp.json()
        logger.debug("Auth verify failed: status=%d body=%s", resp.status_code, resp.text)
        return None
    except httpx.RequestError as exc:
        logger.error("Auth service unreachable: %s", exc)
        return None


async def get_user_info(access_token: str) -> Optional[dict]:
    client = _get_http_client()
    try:
        resp = await client.get(
            f"{settings.AUTH_SERVICE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if resp.status_code == 200:
            return resp.json()
        logger.debug("Auth get_user_info failed: status=%d body=%s", resp.status_code, resp.text)
        return None
    except httpx.RequestError as exc:
        logger.error("Auth service unreachable: %s", exc)
        return None


async def reserve_credits(access_token: str, amount: Decimal, reference_id: str = "", description: str = "") -> Optional[dict]:
    client = _get_http_client()
    try:
        payload = {"amount": str(amount)}
        if reference_id:
            payload["reference_id"] = reference_id
        if description:
            payload["description"] = description
        resp = await client.post(
            f"{settings.AUTH_SERVICE_URL}/api/credits/reserve",
            json=payload,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 402:
            try:
                body = resp.json()
                return {"success": False, "detail": body.get("detail", "余额不足，请先充值")}
            except Exception:
                return {"success": False, "detail": "余额不足，请先充值"}
        try:
            body = resp.json()
            return {"success": False, "detail": body.get("detail", f"预扣失败 (HTTP {resp.status_code})")}
        except Exception:
            return {"success": False, "detail": f"预扣失败 (HTTP {resp.status_code})"}
    except httpx.RequestError as exc:
        logger.error("Auth service unreachable: %s", exc)
        return None


async def settle_credits(access_token: str, reserved_amount: Decimal, actual_amount: Decimal, reference_id: str = "", description: str = "") -> Optional[dict]:
    client = _get_http_client()
    try:
        payload = {"reserved_amount": str(reserved_amount), "actual_amount": str(actual_amount)}
        if reference_id:
            payload["reference_id"] = reference_id
        if description:
            payload["description"] = description
        resp = await client.post(
            f"{settings.AUTH_SERVICE_URL}/api/credits/settle",
            json=payload,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if resp.status_code == 200:
            return resp.json()
        logger.error("Auth settle_credits failed: status=%d body=%s", resp.status_code, resp.text)
        return None
    except httpx.RequestError as exc:
        logger.error("Auth service unreachable: %s", exc)
        return None


async def refund_credits(access_token: str, amount: Decimal, reference_id: str = "", description: str = "") -> Optional[dict]:
    client = _get_http_client()
    try:
        payload = {"amount": str(amount)}
        if reference_id:
            payload["reference_id"] = reference_id
        if description:
            payload["description"] = description
        resp = await client.post(
            f"{settings.AUTH_SERVICE_URL}/api/credits/refund",
            json=payload,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if resp.status_code == 200:
            return resp.json()
        logger.error("Auth refund_credits failed: status=%d body=%s", resp.status_code, resp.text)
        return None
    except httpx.RequestError as exc:
        logger.error("Auth service unreachable: %s", exc)
        return None


def reserve_credits_sync(access_token: str, amount: Decimal, reference_id: str = "", description: str = "") -> Optional[dict]:
    payload = {"amount": str(amount)}
    if reference_id:
        payload["reference_id"] = reference_id
    if description:
        payload["description"] = description
    with httpx.Client(timeout=settings.AUTH_SERVICE_TIMEOUT) as client:
        resp = client.post(
            f"{settings.AUTH_SERVICE_URL}/api/credits/reserve",
            json=payload,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 402:
            try:
                body = resp.json()
                return {"success": False, "detail": body.get("detail", "余额不足，请先充值")}
            except Exception:
                return {"success": False, "detail": "余额不足，请先充值"}
        try:
            body = resp.json()
            return {"success": False, "detail": body.get("detail", f"预扣失败 (HTTP {resp.status_code})")}
        except Exception:
            return {"success": False, "detail": f"预扣失败 (HTTP {resp.status_code})"}


def settle_credits_sync(access_token: str, reserved_amount: Decimal, actual_amount: Decimal, reference_id: str = "", description: str = "") -> Optional[dict]:
    payload = {"reserved_amount": str(reserved_amount), "actual_amount": str(actual_amount)}
    if reference_id:
        payload["reference_id"] = reference_id
    if description:
        payload["description"] = description
    with httpx.Client(timeout=settings.AUTH_SERVICE_TIMEOUT) as client:
        resp = client.post(
            f"{settings.AUTH_SERVICE_URL}/api/credits/settle",
            json=payload,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if resp.status_code == 200:
            return resp.json()
        logger.error("Auth settle_credits_sync failed: status=%d body=%s", resp.status_code, resp.text)
        return None


def refund_credits_sync(access_token: str, amount: Decimal, reference_id: str = "", description: str = "") -> Optional[dict]:
    payload = {"amount": str(amount)}
    if reference_id:
        payload["reference_id"] = reference_id
    if description:
        payload["description"] = description
    with httpx.Client(timeout=settings.AUTH_SERVICE_TIMEOUT) as client:
        resp = client.post(
            f"{settings.AUTH_SERVICE_URL}/api/credits/refund",
            json=payload,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if resp.status_code == 200:
            return resp.json()
        logger.error("Auth refund_credits_sync failed: status=%d body=%s", resp.status_code, resp.text)
        return None


async def admin_add_credits(admin_token: str, user_id: UUID, amount: Decimal, remark: str = "") -> Optional[dict]:
    client = _get_http_client()
    try:
        payload = {"amount": str(amount)}
        if remark:
            payload["remark"] = remark
        resp = await client.post(
            f"{settings.AUTH_SERVICE_URL}/api/admin/users/{user_id}/add-credits",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        if resp.status_code == 200:
            return resp.json()
        logger.error("Auth admin_add_credits failed: status=%d body=%s", resp.status_code, resp.text)
        return None
    except httpx.RequestError as exc:
        logger.error("Auth service unreachable: %s", exc)
        return None


async def admin_toggle_active(admin_token: str, user_id: UUID) -> Optional[dict]:
    client = _get_http_client()
    try:
        resp = await client.put(
            f"{settings.AUTH_SERVICE_URL}/api/admin/users/{user_id}/toggle-active",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        if resp.status_code == 200:
            return resp.json()
        logger.error("Auth admin_toggle_active failed: status=%d body=%s", resp.status_code, resp.text)
        return None
    except httpx.RequestError as exc:
        logger.error("Auth service unreachable: %s", exc)
        return None


async def charge_credits(access_token: str, amount: Decimal, reference_id: str = "", description: str = "") -> Optional[dict]:
    """Directly charge credits: reserve then immediately settle with same amount."""
    result = await reserve_credits(access_token, amount, reference_id, description or "扣费")
    if result is None:
        return None
    if not result.get("success"):
        return result
    # Settle with actual_amount == reserved_amount (no refund)
    # Use a different reference_id for settle to avoid UNIQUE constraint conflict on credit_logs
    settle_ref = f"{reference_id}-settle" if reference_id else ""
    settle_result = await settle_credits(access_token, amount, amount, settle_ref, description or "扣费")
    return settle_result


def charge_credits_sync(access_token: str, amount: Decimal, reference_id: str = "", description: str = "") -> Optional[dict]:
    """Directly charge credits (sync): reserve then immediately settle with same amount."""
    result = reserve_credits_sync(access_token, amount, reference_id, description or "扣费")
    if result is None:
        return None
    if not result.get("success"):
        return result
    # Settle with actual_amount == reserved_amount (no refund)
    # Use a different reference_id for settle to avoid UNIQUE constraint conflict on credit_logs
    settle_ref = f"{reference_id}-settle" if reference_id else ""
    settle_result = settle_credits_sync(access_token, amount, amount, settle_ref, description or "扣费")
    return settle_result


async def get_credits_balance(access_token: str) -> Optional[dict]:
    client = _get_http_client()
    try:
        resp = await client.get(
            f"{settings.AUTH_SERVICE_URL}/api/credits/balance",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if resp.status_code == 200:
            return resp.json()
        logger.error("Auth get_credits_balance failed: status=%d body=%s", resp.status_code, resp.text)
        return None
    except httpx.RequestError as exc:
        logger.error("Auth service unreachable: %s", exc)
        return None


async def close_http_client():
    global _http_client
    if _http_client and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None


async def reset_password(user_id: UUID, new_password: str) -> Optional[dict]:
    client = _get_http_client()
    try:
        resp = await client.post(
            f"{settings.AUTH_SERVICE_URL}/api/admin/users/{user_id}/reset-password",
            json={"new_password": new_password},
        )
        if resp.status_code == 200:
            return resp.json()
        logger.error("Auth reset_password failed: status=%d body=%s", resp.status_code, resp.text)
        return None
    except httpx.RequestError as exc:
        logger.error("Auth service unreachable: %s", exc)
        return None
