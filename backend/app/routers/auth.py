from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth_client import admin_add_credits, admin_toggle_active
from app.database import get_db
from app.deps import get_admin_user, get_current_user
from app.models import BillingRecord, User
from app.schemas import (
    AdminTopup,
    AdminUpdateEngines,
    AdminUpdatePushConfigLimit,
    AdminUpdateStatus,
    AdminUserListResponse,
    AdminUserResponse,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])
bearer_scheme = HTTPBearer()


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    return UserResponse.model_validate(user)


admin_router = APIRouter(prefix="/admin", tags=["admin"])


@admin_router.get("/users", response_model=AdminUserListResponse)
async def list_users(
    page: int = 1,
    per_page: int = 20,
    search: str = None,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(User)
    count_query = select(func.count()).select_from(User)
    if search:
        query = query.where(
            (User.email.ilike(f"%{search}%")) | (User.phone.ilike(f"%{search}%")) | (User.display_name.ilike(f"%{search}%"))
        )
        count_query = count_query.where(
            (User.email.ilike(f"%{search}%")) | (User.phone.ilike(f"%{search}%")) | (User.display_name.ilike(f"%{search}%"))
        )

    total = (await db.execute(count_query)).scalar()
    query = query.order_by(User.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    users = result.scalars().all()

    return AdminUserListResponse(
        items=[AdminUserResponse.model_validate(u) for u in users],
        total=total,
        page=page,
        per_page=per_page,
    )


@admin_router.post("/users/{user_id}/topup")
async def topup_user(
    user_id: UUID,
    body: AdminTopup,
    admin: User = Depends(get_admin_user),
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    auth_result = await admin_add_credits(
        credentials.credentials, user_id, body.amount, body.description or f"Admin topup: {body.amount} credits"
    )
    if auth_result is None:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to add credits via Auth Service")

    new_credits = Decimal(auth_result.get("new_credits", str(user.credits + body.amount)))
    record = BillingRecord(
        user_id=user.id,
        action="topup",
        amount=body.amount,
        balance_after=new_credits,
        description=body.description or f"Admin topup: {body.amount} credits",
    )
    db.add(record)
    user.credits = new_credits
    user.updated_at = datetime.now(timezone.utc)
    await db.commit()

    return {"credits": float(user.credits), "billing_record_id": str(record.id)}


@admin_router.put("/users/{user_id}/engines")
async def update_user_engines(
    user_id: UUID,
    body: AdminUpdateEngines,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.allowed_engines = body.allowed_engines
    user.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"allowed_engines": user.allowed_engines}


@admin_router.put("/users/{user_id}/status")
async def update_user_status(
    user_id: UUID,
    body: AdminUpdateStatus,
    admin: User = Depends(get_admin_user),
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if body.is_active != user.is_active:
        auth_result = await admin_toggle_active(credentials.credentials, user_id)
        if auth_result is None:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to toggle user status via Auth Service")

    user.is_active = body.is_active
    user.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"is_active": user.is_active}


@admin_router.put("/users/{user_id}/push-config-limit")
async def update_user_push_config_limit(
    user_id: UUID,
    body: AdminUpdatePushConfigLimit,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.max_push_configs = body.max_push_configs
    user.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"max_push_configs": user.max_push_configs}
