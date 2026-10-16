from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth_client import admin_add_credits
from app.database import get_db
from app.deps import get_admin_user, get_current_user
from app.models import BillingRecord, EnginePricing, User
from app.schemas import (
    AdminTopup,
    BillingBalance,
    BillingRecordListResponse,
    BillingRecordResponse,
    EngineInfo,
)

router = APIRouter(prefix="/billing", tags=["billing"])
bearer_scheme = HTTPBearer()


@router.get("/balance", response_model=BillingBalance)
async def get_balance(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    total_used_result = await db.execute(
        select(func.coalesce(func.sum(BillingRecord.amount), 0)).where(
            BillingRecord.user_id == user.id,
            BillingRecord.amount < 0,
        )
    )
    total_used = abs(total_used_result.scalar() or 0)

    total_tasks_result = await db.execute(
        select(func.count()).select_from(BillingRecord).where(
            BillingRecord.user_id == user.id,
            BillingRecord.action == "settle",
        )
    )
    total_tasks = total_tasks_result.scalar() or 0

    total_dur_result = await db.execute(
        select(func.coalesce(func.sum(BillingRecord.duration_sec), 0)).where(
            BillingRecord.user_id == user.id,
            BillingRecord.action == "settle",
        )
    )
    total_duration_sec = total_dur_result.scalar() or Decimal("0")

    return BillingBalance(
        credits=user.credits,
        total_used=Decimal(str(total_used)),
        total_tasks=total_tasks,
        total_duration_sec=total_duration_sec,
    )


@router.get("/records", response_model=BillingRecordListResponse)
async def get_records(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(BillingRecord).where(BillingRecord.user_id == user.id)
    count_query = select(func.count()).select_from(BillingRecord).where(BillingRecord.user_id == user.id)

    total = (await db.execute(count_query)).scalar()
    query = query.order_by(BillingRecord.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    records = result.scalars().all()

    return BillingRecordListResponse(
        items=[BillingRecordResponse.model_validate(r) for r in records],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/engines", response_model=list[EngineInfo])
async def list_engine_pricing(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(EnginePricing).where(EnginePricing.is_active == True))
    pricings = result.scalars().all()

    engine_map = {}
    for p in pricings:
        if p.engine_key not in engine_map:
            engine_map[p.engine_key] = EngineInfo(
                engine_key=p.engine_key,
                engine_name=p.engine_name,
                credits_per_minute=p.credits_per_minute,
                model_sizes=[],
            )
        if p.model_size:
            engine_map[p.engine_key].model_sizes.append(p.model_size)

    return list(engine_map.values())


@router.post("/topup/{user_id}")
async def admin_topup(
    user_id: UUID,
    body: AdminTopup,
    admin: User = Depends(get_admin_user),
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    auth_result = await admin_add_credits(
        credentials.credentials, user_id, body.amount, body.description or f"Admin topup: {body.amount} credits"
    )
    if auth_result is None:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to add credits via Auth Service")

    new_credits = Decimal(auth_result.get("new_credits", str(target.credits + body.amount)))
    record = BillingRecord(
        user_id=target.id,
        action="topup",
        amount=body.amount,
        balance_after=new_credits,
        description=body.description or f"Admin topup: {body.amount} credits",
    )
    db.add(record)
    target.credits = new_credits
    target.updated_at = datetime.now(timezone.utc)
    await db.commit()

    return {"status": "ok", "credits": float(target.credits)}
