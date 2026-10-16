import hashlib
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth_client import admin_add_credits
from app.config import settings
from app.database import get_db
from app.deps import get_admin_user, get_current_user
from app.models import BillingRecord, RechargeRequest, User

router = APIRouter(prefix="/recharge", tags=["recharge"])
bearer_scheme = HTTPBearer()

RECHARGE_DIR = os.path.join(settings.UPLOAD_DIR, "recharge")
QR_DIR = os.path.join(RECHARGE_DIR, "qr")
PROOF_DIR = os.path.join(RECHARGE_DIR, "proof")
COEFFICIENT = Decimal("10")  # 1元 = 10积分


def _ensure_dirs():
    for d in [RECHARGE_DIR, QR_DIR, PROOF_DIR]:
        os.makedirs(d, exist_ok=True)


_ensure_dirs()


@router.get("/info")
async def recharge_info():
    return {"coefficient": float(COEFFICIENT), "description": f"1元 = {int(COEFFICIENT)}积分"}


@router.get("/payment-qr")
async def get_payment_qr():
    """Get the admin-uploaded payment QR code image."""
    qr_files = [f for f in os.listdir(QR_DIR) if f.lower().endswith((".png", ".jpg", ".jpeg"))]
    if not qr_files:
        raise HTTPException(status_code=404, detail="收款码未上传")
    qr_files.sort(key=lambda f: os.path.getmtime(os.path.join(QR_DIR, f)), reverse=True)
    return FileResponse(os.path.join(QR_DIR, qr_files[0]))


@router.post("/submit")
async def submit_recharge(
    amount: Decimal = Form(..., gt=0),
    payment_image: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """User submits a recharge request with payment proof."""
    # Check for pending duplicate
    pending = await db.execute(
        select(RechargeRequest).where(
            RechargeRequest.user_id == user.id,
            RechargeRequest.status == "pending",
        )
    )
    if pending.scalar_one_or_none():
        raise HTTPException(status_code=429, detail="您已有待审核的充值申请，请等待管理员处理")

    # Save payment image
    ext = os.path.splitext(payment_image.filename or "image.png")[1] or ".png"
    filename = f"{user.id}_{uuid.uuid4().hex[:8]}{ext}"
    filepath = os.path.join(PROOF_DIR, filename)
    content = await payment_image.read()
    with open(filepath, "wb") as f:
        f.write(content)

    image_hash = hashlib.sha256(content).hexdigest()

    credits_amount = amount * COEFFICIENT

    req = RechargeRequest(
        user_id=user.id,
        amount=amount,
        credits_amount=credits_amount,
        coefficient=COEFFICIENT,
        payment_image=filename,
        image_hash=image_hash,
    )
    db.add(req)
    await db.commit()
    await db.refresh(req)

    return {
        "id": str(req.id),
        "amount": float(req.amount),
        "credits_amount": float(req.credits_amount),
        "status": req.status,
        "message": "充值申请已提交，请等待管理员审核",
    }


@router.get("/my-requests")
async def my_recharge_requests(
    page: int = 1,
    per_page: int = 20,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(RechargeRequest).where(RechargeRequest.user_id == user.id)
    count_query = select(func.count()).select_from(RechargeRequest).where(RechargeRequest.user_id == user.id)

    total = (await db.execute(count_query)).scalar()
    query = query.order_by(RechargeRequest.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    requests = result.scalars().all()

    return {
        "items": [
            {
                "id": str(r.id),
                "amount": float(r.amount),
                "credits_amount": float(r.credits_amount),
                "status": r.status,
                "admin_note": r.admin_note,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
            }
            for r in requests
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.get("/proof/{filename}")
async def get_proof_image(
    filename: str,
    token: str = None,
    db: AsyncSession = Depends(get_db),
):
    """Get a payment proof image. Supports auth via query param token for img tags."""
    from app.deps import get_optional_user, bearer_scheme
    from fastapi.security import HTTPAuthorizationCredentials

    user = None
    # Try header auth first
    try:
        from fastapi import Request
    except ImportError:
        pass

    # Try query param token
    if token:
        try:
            from app.auth_client import verify_token, get_user_info
            verify_result = await verify_token(token)
            if verify_result and verify_result.get("is_active", True):
                user_info = await get_user_info(token)
                if user_info:
                    from app.deps import _sync_local_user
                    from uuid import UUID
                    auth_user = {
                        "user_id": verify_result["user_id"],
                        "email": user_info.get("email"),
                        "phone": user_info.get("phone"),
                        "display_name": user_info.get("display_name"),
                        "role": user_info.get("role", "user"),
                        "is_active": user_info.get("is_active", True),
                    }
                    credits = user_info.get("credits")
                    credits_reserved = user_info.get("credits_reserved")
                    user = await _sync_local_user(db, auth_user, credits, credits_reserved)
        except Exception:
            pass

    if user is None:
        raise HTTPException(status_code=401, detail="未认证")

    if user.role != "admin":
        if not filename.startswith(str(user.id)):
            raise HTTPException(status_code=403, detail="无权访问")
    filepath = os.path.join(PROOF_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(filepath)


# ─── Admin endpoints ──────────────────────────────────────────────────


@router.post("/admin/upload-qr")
async def admin_upload_qr(
    qr_image: UploadFile = File(...),
    admin: User = Depends(get_admin_user),
):
    """Admin uploads payment QR code image."""
    ext = os.path.splitext(qr_image.filename or "qr.png")[1] or ".png"
    filename = f"payment_qr{ext}"
    filepath = os.path.join(QR_DIR, filename)
    content = await qr_image.read()
    with open(filepath, "wb") as f:
        f.write(content)
    return {"message": "收款码已上传", "filename": filename}


@router.get("/admin/requests")
async def admin_list_requests(
    status_filter: str = None,
    page: int = 1,
    per_page: int = 20,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(RechargeRequest)
    count_query = select(func.count()).select_from(RechargeRequest)

    if status_filter:
        query = query.where(RechargeRequest.status == status_filter)
        count_query = count_query.where(RechargeRequest.status == status_filter)

    total = (await db.execute(count_query)).scalar()
    query = query.order_by(RechargeRequest.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    requests = result.scalars().all()

    return {
        "items": [
            {
                "id": str(r.id),
                "user_id": str(r.user_id),
                "user_email": r.user.email if r.user else None,
                "user_display_name": r.user.display_name if r.user else None,
                "amount": float(r.amount),
                "credits_amount": float(r.credits_amount),
                "payment_image": r.payment_image,
                "status": r.status,
                "admin_note": r.admin_note,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
            }
            for r in requests
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.post("/admin/review/{request_id}")
async def admin_review_request(
    request_id: uuid.UUID,
    action: str = Form(...),  # "approved" or "rejected"
    admin_note: str = Form(""),
    admin: User = Depends(get_admin_user),
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    """Admin approves or rejects a recharge request."""
    result = await db.execute(select(RechargeRequest).where(RechargeRequest.id == request_id))
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="充值申请不存在")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail="该申请已处理")

    if action == "approved":
        # Add credits via auth-service
        auth_result = await admin_add_credits(
            credentials.credentials,
            req.user_id,
            req.credits_amount,
            f"充值审核通过: {req.amount}元 → {req.credits_amount}积分",
        )
        if auth_result is None:
            raise HTTPException(status_code=502, detail="积分充值失败，请重试")

        new_credits = Decimal(auth_result.get("new_credits", "0"))

        # Update local user credits
        user_result = await db.execute(select(User).where(User.id == req.user_id))
        target_user = user_result.scalar_one_or_none()
        if target_user:
            target_user.credits = new_credits
            target_user.updated_at = datetime.now(timezone.utc)

        # Create billing record
        record = BillingRecord(
            user_id=req.user_id,
            action="topup",
            amount=req.credits_amount,
            balance_after=new_credits,
            description=f"充值: {req.amount}元 → {req.credits_amount}积分",
        )
        db.add(record)

        req.status = "approved"
    elif action == "rejected":
        req.status = "rejected"
    else:
        raise HTTPException(status_code=400, detail="无效的操作，请使用 approved 或 rejected")

    req.admin_note = admin_note
    req.reviewed_at = datetime.now(timezone.utc)
    await db.commit()

    return {"status": req.status, "message": "操作成功"}
