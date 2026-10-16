from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_admin_user, get_current_user
from app.models import EnginePricing, SystemSetting, User
from app.schemas import EngineInfo

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/engines", response_model=list[EngineInfo])
async def list_engines(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(EnginePricing).where(EnginePricing.is_active == True).order_by(EnginePricing.sort_order)
    )
    engines = result.scalars().all()

    allowed = set(user.allowed_engines or [])

    engine_map = {}
    for e in engines:
        if user.role != "admin" and e.engine_key not in allowed:
            continue
        if e.engine_key not in engine_map:
            engine_map[e.engine_key] = EngineInfo(
                engine_key=e.engine_key,
                engine_name=e.engine_name,
                credits_per_minute=e.credits_per_minute,
                model_sizes=[],
            )
        engine_map[e.engine_key].model_sizes.append(e.model_size)

    return list(engine_map.values())


@router.get("/engines/all")
async def list_all_engines(admin: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db)):
    """Admin: list all engine pricing entries including disabled ones."""
    result = await db.execute(select(EnginePricing).order_by(EnginePricing.sort_order))
    engines = result.scalars().all()
    return [
        {
            "engine_key": e.engine_key,
            "model_size": e.model_size,
            "engine_name": e.engine_name,
            "credits_per_minute": float(e.credits_per_minute),
            "is_active": e.is_active,
            "sort_order": e.sort_order,
            "description": e.description,
        }
        for e in engines
    ]


@router.put("/engines/{engine_key}/{model_size}")
async def update_engine(
    engine_key: str,
    model_size: str,
    data: dict,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin: update engine pricing and availability."""
    result = await db.execute(
        select(EnginePricing).where(
            EnginePricing.engine_key == engine_key,
            EnginePricing.model_size == model_size,
        )
    )
    engine = result.scalar_one_or_none()
    if not engine:
        raise HTTPException(status_code=404, detail="引擎不存在")

    if "credits_per_minute" in data:
        engine.credits_per_minute = Decimal(str(data["credits_per_minute"]))
    if "is_active" in data:
        engine.is_active = bool(data["is_active"])
    if "engine_name" in data:
        engine.engine_name = data["engine_name"]
    if "sort_order" in data:
        engine.sort_order = int(data["sort_order"])
    if "description" in data:
        engine.description = data["description"]

    await db.commit()
    await db.refresh(engine)

    return {
        "engine_key": engine.engine_key,
        "model_size": engine.model_size,
        "engine_name": engine.engine_name,
        "credits_per_minute": float(engine.credits_per_minute),
        "is_active": engine.is_active,
    }


@router.get("/health")
async def health_check():
    return {"status": "ok", "version": "2.0.0"}


# ─── System Settings (Admin) ─────────────────────────────────────────

@router.get("/settings")
async def list_settings(admin: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SystemSetting))
    settings = result.scalars().all()
    return {s.key: s.value for s in settings}


@router.put("/settings/{key}")
async def update_setting(
    key: str,
    data: dict,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SystemSetting).where(SystemSetting.key == key))
    setting = result.scalar_one_or_none()
    value = data.get("value", "")
    if setting:
        setting.value = value
    else:
        setting = SystemSetting(key=key, value=value)
        db.add(setting)
    await db.commit()
    return {"key": key, "value": value}


@router.get("/settings/openai_key_configured")
async def openai_key_configured(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Check if system OpenAI key is configured (for non-admin users)."""
    result = await db.execute(
        select(SystemSetting).where(SystemSetting.key == "openai_api_key")
    )
    setting = result.scalar_one_or_none()
    return {"configured": bool(setting and setting.value)}
