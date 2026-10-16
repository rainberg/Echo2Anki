"""
Fix unsettled reserve records - v2.
Strategy: settle(reserved, reserved=0) to refund all, then charge actual amount.
Usage: /opt/anki-venv/bin/python3 fix_unsettled_billing_v2.py <user_access_token>
"""
import sys
import os

sys.path.insert(0, "/opt/anki-app/backend")
os.chdir("/opt/anki-app/backend")

import asyncio
from decimal import Decimal
from uuid import UUID

from app.auth_client import settle_credits, refund_credits, charge_credits
from app.models import BillingRecord, Task

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


# Unsettled tasks: (task_id, reserve_amount, actual_charged, engine, model_size, actual_duration_sec)
UNSETTLED_DONE = [
    ("eb551a51-68c7-4fff-a7ba-3fc932219a42", Decimal("55.08"), Decimal("60.02"), "local_whisper", "medium", Decimal("1800.12")),
    ("2062e846-5303-4c06-ba1d-545fd966446b", Decimal("47.58"), Decimal("51.92"), "local_whisper", "medium", Decimal("1557.33")),
    ("58ab42d6-01f3-4038-937e-a6cd6f9c4812", Decimal("36.64"), Decimal("39.90"), "local_whisper", "medium", Decimal("1196.47")),
    ("9acefbb9-e596-4d40-9616-6a2c9f6f35dc", Decimal("66.28"), Decimal("72.12"), "local_whisper", "large", Decimal("1081.35")),
    ("ad141a2d-dfab-46a9-bec8-7266d6ead30e", Decimal("108.04"), Decimal("120.04"), "local_whisper", "large", Decimal("1800.12")),
    ("f773c387-8000-4415-8f01-3bcb1ae2f95b", Decimal("108.04"), Decimal("120.04"), "local_whisper", "large", Decimal("1800.12")),
    # f63d2645: first reserve of 27.01, actual 30.01
    ("f63d2645-57b4-41dc-adc1-92c6f5b1f836", Decimal("27.01"), Decimal("30.01"), "cohere", "default", Decimal("1800.12")),
]

# f63d2645 already refunded the second reserve in v1 run, skip it


async def fix_unsettled(access_token: str):
    from app.config import settings
    db_engine = create_async_engine(settings.DATABASE_URL)

    async with AsyncSession(db_engine) as db:
        for task_id_str, reserved, actual, engine_name, model_size, actual_dur in UNSETTLED_DONE:
            task_id = UUID(task_id_str)
            task = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
            if not task:
                print(f"SKIP: Task {task_id_str[:8]} not found")
                continue

            user_id = task.user_id
            print(f"\n--- Task {task_id_str[:8]} ---")
            print(f"  Reserved: {reserved}, Actual: {actual}")

            # Step 1: Refund all reserved (settle with actual=0)
            ref_id = f"task:{task_id_str}:settle:fix"
            desc = f"退还预扣(修复): {reserved}"
            result = await settle_credits(access_token, reserved, Decimal("0"), ref_id, desc)
            if result:
                print(f"  REFUND OK: {result}")
                record = BillingRecord(
                    user_id=user_id,
                    task_id=task_id,
                    action="refund",
                    amount=reserved,
                    balance_after=Decimal(str(result.get("credits", "0"))),
                    description=desc,
                )
                db.add(record)
                await db.commit()
            else:
                print(f"  REFUND FAILED")
                continue

            # Step 2: Charge actual amount
            charge_ref_id = f"task:{task_id_str}:charge:fix"
            charge_desc = f"扣费(修复): {engine_name}/{model_size}, {actual_dur}s"
            charge_result = await charge_credits(access_token, actual, charge_ref_id, charge_desc)
            if charge_result:
                print(f"  CHARGE OK: {charge_result}")
                record = BillingRecord(
                    user_id=user_id,
                    task_id=task_id,
                    action="charge",
                    amount=-actual,
                    balance_after=Decimal(str(charge_result.get("credits", "0"))),
                    duration_sec=actual_dur,
                    description=charge_desc,
                )
                db.add(record)
                await db.commit()
            else:
                print(f"  CHARGE FAILED")

    await db_engine.dispose()
    print("\n\nDone!")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python fix_unsettled_billing_v2.py <user_access_token>")
        sys.exit(1)

    token = sys.argv[1]
    asyncio.run(fix_unsettled(token))
