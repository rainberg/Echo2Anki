import logging
import time
from decimal import Decimal, ROUND_UP
from typing import Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.auth_client import (
    charge_credits as _auth_charge,
    charge_credits_sync as _auth_charge_sync,
    get_credits_balance as _auth_get_balance,
    refund_credits as _auth_refund,
    refund_credits_sync as _auth_refund_sync,
    reserve_credits as _auth_reserve,
    reserve_credits_sync as _auth_reserve_sync,
    settle_credits as _auth_settle,
    settle_credits_sync as _auth_settle_sync,
)
from app.models import BillingRecord, EnginePricing

logger = logging.getLogger(__name__)


async def get_credits_per_minute(db: AsyncSession, engine: str, model_size: str) -> Decimal:
    result = await db.execute(
        select(EnginePricing).where(
            EnginePricing.engine_key == engine,
            EnginePricing.model_size == model_size,
            EnginePricing.is_active == True,
        )
    )
    pricing = result.scalar_one_or_none()
    if pricing:
        return pricing.credits_per_minute
    return Decimal("1.0")


def get_credits_per_minute_sync(db: Session, engine: str, model_size: str) -> Decimal:
    result = db.execute(
        select(EnginePricing).where(
            EnginePricing.engine_key == engine,
            EnginePricing.model_size == model_size,
            EnginePricing.is_active == True,
        )
    )
    pricing = result.scalar_one_or_none()
    if pricing:
        return pricing.credits_per_minute
    return Decimal("1.0")


def _calc_amount(duration_sec: Decimal, cpm: Decimal) -> Decimal:
    minutes = (duration_sec / Decimal("60")).quantize(Decimal("0.01"), rounding=ROUND_UP)
    return (minutes * cpm).quantize(Decimal("0.01"), rounding=ROUND_UP)


async def reserve_credits(
    db: AsyncSession,
    user_id: UUID,
    task_id: UUID,
    duration_sec: Decimal,
    engine: str,
    model_size: str,
    access_token: str,
) -> Tuple[Decimal, str]:
    cpm = await get_credits_per_minute(db, engine, model_size)
    amount = _calc_amount(duration_sec, cpm)
    reference_id = f"task:{task_id}:{int(time.time())}"
    description = f"预扣: {engine}/{model_size}, {duration_sec}s"

    result = await _auth_reserve(access_token, amount, reference_id, description)
    if result is None:
        raise ValueError("计费服务暂时不可用，请稍后重试")

    if not result.get("success"):
        detail = result.get("detail", "")
        if "余额不足" in detail or "insufficient" in detail.lower():
            raise ValueError("余额不足，请先充值后再提交任务")
        if "已存在" in detail:
            raise ValueError("该任务已预扣费用，请稍后重试")
        raise ValueError(f"预扣费用失败：{detail}")

    record = BillingRecord(
        user_id=user_id,
        task_id=task_id,
        action="reserve",
        amount=-amount,
        balance_after=Decimal(result.get("credits", "0")),
        duration_sec=duration_sec,
        description=description,
    )
    db.add(record)
    await db.commit()
    return amount, reference_id


async def settle_credits(
    db: AsyncSession,
    user_id: UUID,
    task_id: UUID,
    actual_duration_sec: Decimal,
    engine: str,
    model_size: str,
    reserved_amount: Decimal,
    access_token: str,
    reserve_reference_id: str = "",
) -> Decimal:
    cpm = await get_credits_per_minute(db, engine, model_size)
    actual_amount = _calc_amount(actual_duration_sec, cpm)
    reference_id = reserve_reference_id or f"task:{task_id}:settle:{int(time.time())}"
    description = f"结算: {engine}/{model_size}, {actual_duration_sec}s"

    result = await _auth_settle(access_token, reserved_amount, actual_amount, reference_id, description)
    if result is None:
        logger.error("Settle credits via Auth Service failed for user %s task %s ref_id=%s", user_id, task_id, reference_id)
        return actual_amount

    record = BillingRecord(
        user_id=user_id,
        task_id=task_id,
        action="settle",
        amount=-actual_amount,
        balance_after=Decimal(result.get("credits", "0")),
        duration_sec=actual_duration_sec,
        description=description,
    )
    db.add(record)
    if result.get("refund") and Decimal(result["refund"]) > 0:
        refund_record = BillingRecord(
            user_id=user_id,
            task_id=task_id,
            action="refund",
            amount=Decimal(result["refund"]),
            balance_after=Decimal(result.get("credits", "0")),
            duration_sec=actual_duration_sec,
            description=f"退还差额: {result['refund']}",
        )
        db.add(refund_record)
    await db.commit()
    return actual_amount


async def refund_all_reserved(
    db: AsyncSession,
    user_id: UUID,
    task_id: UUID,
    reserved_amount: Decimal,
    access_token: str,
    reserve_reference_id: str = "",
):
    if not reserved_amount or reserved_amount <= 0:
        return

    reference_id = reserve_reference_id or f"task:{task_id}:refund:{int(time.time())}"
    description = "全额退还（任务失败/取消）"

    result = await _auth_settle(access_token, reserved_amount, Decimal("0"), reference_id, description)
    if result is None:
        logger.error("Refund credits via Auth Service failed for user %s task %s ref_id=%s", user_id, task_id, reference_id)
        return

    record = BillingRecord(
        user_id=user_id,
        task_id=task_id,
        action="refund",
        amount=reserved_amount,
        balance_after=Decimal(result.get("credits", "0")),
        description=description,
    )
    db.add(record)
    await db.commit()


def reserve_credits_sync(
    db: Session,
    user_id: UUID,
    task_id: UUID,
    duration_sec: Decimal,
    engine: str,
    model_size: str,
    access_token: str,
) -> Tuple[Decimal, str]:
    cpm = get_credits_per_minute_sync(db, engine, model_size)
    amount = _calc_amount(duration_sec, cpm)
    reference_id = f"task:{task_id}:{int(time.time())}"
    description = f"预扣: {engine}/{model_size}, {duration_sec}s"

    result = _auth_reserve_sync(access_token, amount, reference_id, description)
    if result is None:
        raise ValueError("计费服务暂时不可用，请稍后重试")

    if not result.get("success"):
        detail = result.get("detail", "")
        if "余额不足" in detail or "insufficient" in detail.lower():
            raise ValueError("余额不足，请先充值后再提交任务")
        if "已存在" in detail:
            raise ValueError("该任务已预扣费用，请稍后重试")
        raise ValueError(f"预扣费用失败：{detail}")

    record = BillingRecord(
        user_id=user_id,
        task_id=task_id,
        action="reserve",
        amount=-amount,
        balance_after=Decimal(result.get("credits", "0")),
        duration_sec=duration_sec,
        description=description,
    )
    db.add(record)
    db.commit()
    return amount, reference_id


def settle_credits_sync(
    db: Session,
    user_id: UUID,
    task_id: UUID,
    actual_duration_sec: Decimal,
    engine: str,
    model_size: str,
    reserved_amount: Decimal,
    access_token: str,
    reserve_reference_id: str = "",
) -> Decimal:
    cpm = get_credits_per_minute_sync(db, engine, model_size)
    actual_amount = _calc_amount(actual_duration_sec, cpm)
    reference_id = reserve_reference_id or f"task:{task_id}:settle:{int(time.time())}"
    description = f"结算: {engine}/{model_size}, {actual_duration_sec}s"

    result = _auth_settle_sync(access_token, reserved_amount, actual_amount, reference_id, description)
    if result is None:
        logger.error("Settle credits via Auth Service failed for user %s task %s ref_id=%s", user_id, task_id, reference_id)
        return actual_amount

    record = BillingRecord(
        user_id=user_id,
        task_id=task_id,
        action="settle",
        amount=-actual_amount,
        balance_after=Decimal(result.get("credits", "0")),
        duration_sec=actual_duration_sec,
        description=description,
    )
    db.add(record)
    if result.get("refund") and Decimal(result["refund"]) > 0:
        refund_record = BillingRecord(
            user_id=user_id,
            task_id=task_id,
            action="refund",
            amount=Decimal(result["refund"]),
            balance_after=Decimal(result.get("credits", "0")),
            duration_sec=actual_duration_sec,
            description=f"退还差额: {result['refund']}",
        )
        db.add(refund_record)
    db.commit()
    return actual_amount


def refund_all_reserved_sync(
    db: Session,
    user_id: UUID,
    task_id: UUID,
    reserved_amount: Decimal,
    access_token: str,
    reserve_reference_id: str = "",
) -> bool:
    """Refund all reserved credits. Returns True on success, False on failure."""
    if not reserved_amount or reserved_amount <= 0:
        return True

    reference_id = reserve_reference_id or f"task:{task_id}:refund:{int(time.time())}"
    description = "全额退还（任务失败/取消）"

    result = _auth_settle_sync(access_token, reserved_amount, Decimal("0"), reference_id, description)
    if result is None:
        logger.error("Refund credits via Auth Service failed for user %s task %s ref_id=%s", user_id, task_id, reference_id)
        return False

    record = BillingRecord(
        user_id=user_id,
        task_id=task_id,
        action="refund",
        amount=reserved_amount,
        balance_after=Decimal(result.get("credits", "0")),
        description=description,
    )
    db.add(record)
    db.commit()
    return True


# ── New billing model: pre-check + post-charge ──────────────────────────


async def check_balance(
    access_token: str,
    required_amount: Decimal,
) -> None:
    """Check if user has enough credits. Raises ValueError if insufficient."""
    result = await _auth_get_balance(access_token)
    if result is None:
        raise ValueError("计费服务暂时不可用，请稍后重试")
    balance = Decimal(str(result.get("credits", 0)))
    if balance < required_amount:
        raise ValueError(f"余额不足（当前 {balance} 积分，需要 {required_amount} 积分），请先充值后再提交任务")


async def estimate_cost(
    db: AsyncSession,
    duration_sec: Decimal,
    engine: str,
    model_size: str,
) -> Decimal:
    """Estimate cost for a task based on duration, engine, model_size."""
    cpm = await get_credits_per_minute(db, engine, model_size)
    return _calc_amount(duration_sec, cpm)


def estimate_cost_sync(
    db: Session,
    duration_sec: Decimal,
    engine: str,
    model_size: str,
) -> Decimal:
    """Estimate cost for a task (sync version)."""
    cpm = get_credits_per_minute_sync(db, engine, model_size)
    return _calc_amount(duration_sec, cpm)


async def charge_credits(
    db: AsyncSession,
    user_id: UUID,
    task_id: UUID,
    actual_duration_sec: Decimal,
    engine: str,
    model_size: str,
    access_token: str,
) -> Decimal:
    """Charge credits after task completion. Uses reserve+settle to deduct actual cost."""
    cpm = await get_credits_per_minute(db, engine, model_size)
    actual_amount = _calc_amount(actual_duration_sec, cpm)
    reference_id = f"task:{task_id}:{int(time.time())}"
    description = f"扣费: {engine}/{model_size}, {actual_duration_sec}s"

    result = await _auth_charge(access_token, actual_amount, reference_id, description)
    if result is None:
        logger.error("Charge credits via Auth Service failed for user %s task %s", user_id, task_id)
        return actual_amount

    record = BillingRecord(
        user_id=user_id,
        task_id=task_id,
        action="charge",
        amount=-actual_amount,
        balance_after=Decimal(result.get("credits", "0")),
        duration_sec=actual_duration_sec,
        description=description,
    )
    db.add(record)
    await db.commit()
    return actual_amount


def charge_credits_sync(
    db: Session,
    user_id: UUID,
    task_id: UUID,
    actual_duration_sec: Decimal,
    engine: str,
    model_size: str,
    access_token: str,
) -> Decimal:
    """Charge credits after task completion (sync version)."""
    cpm = get_credits_per_minute_sync(db, engine, model_size)
    actual_amount = _calc_amount(actual_duration_sec, cpm)
    reference_id = f"task:{task_id}:{int(time.time())}"
    description = f"扣费: {engine}/{model_size}, {actual_duration_sec}s"

    result = _auth_charge_sync(access_token, actual_amount, reference_id, description)
    if result is None:
        logger.error("Charge credits via Auth Service failed for user %s task %s", user_id, task_id)
        return actual_amount

    record = BillingRecord(
        user_id=user_id,
        task_id=task_id,
        action="charge",
        amount=-actual_amount,
        balance_after=Decimal(result.get("credits", "0")),
        duration_sec=actual_duration_sec,
        description=description,
    )
    db.add(record)
    db.commit()
    return actual_amount
