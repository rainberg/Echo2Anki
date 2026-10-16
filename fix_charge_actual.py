"""
Fix unsettled - Step 2: Charge actual amounts after refund.
Usage: /opt/anki-venv/bin/python3 fix_charge_actual.py <user_access_token>
"""
import sys
import os
import time

sys.path.insert(0, "/opt/anki-app/backend")
os.chdir("/opt/anki-app/backend")

import asyncio
from decimal import Decimal
from uuid import UUID

from app.auth_client import charge_credits
from app.models import BillingRecord, Task

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


UNSETTLED_DONE = [
    ("eb551a51-68c7-4fff-a7ba-3fc932219a42", Decimal("60.02"), "local_whisper", "medium", Decimal("1800.12")),
    ("2062e846-5303-4c06-ba1d-545fd966446b", Decimal("51.92"), "local_whisper", "medium", Decimal("1557.33")),
    ("58ab42d6-01f3-4038-937e-a6cd6f9c4812", Decimal("39.90"), "local_whisper", "medium", Decimal("1196.47")),
    ("9acefbb9-e596-4d40-9616-6a2c9f6f35dc", Decimal("72.12"), "local_whisper", "large", Decimal("1081.35")),
    ("ad141a2d-dfab-46a9-bec8-7266d6ead30e", Decimal("120.04"), "local_whisper", "large", Decimal("1800.12")),
    ("f773c387-8000-4415-8f01-3bcb1ae2f95b", Decimal("120.04"), "local_whisper", "large", Decimal("1800.12")),
    ("f63d2645-57b4-41dc-adc1-92c6f5b1f836", Decimal("30.01"), "cohere", "default", Decimal("1800.12")),
]


async def fix_charge(access_token: str):
    from app.config import settings
    db_engine = create_async_engine(settings.DATABASE_URL)

    async with AsyncSession(db_engine) as db:
        for task_id_str, actual, engine_name, model_size, actual_dur in UNSETTLED_DONE:
            task_id = UUID(task_id_str)
            task = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
            if not task:
                print(f"SKIP: Task {task_id_str[:8]} not found")
                continue

            user_id = task.user_id
            print(f"\n--- Task {task_id_str[:8]} ---")
            print(f"  Charging: {actual}")

            ref_id = f"task:{task_id_str}:charge:fix:{int(time.time())}"
            desc = f"扣费(修复): {engine_name}/{model_size}, {actual_dur}s"

            result = await charge_credits(access_token, actual, ref_id, desc)
            if result:
                print(f"  CHARGE OK: {result}")
                record = BillingRecord(
                    user_id=user_id,
                    task_id=task_id,
                    action="charge",
                    amount=-actual,
                    balance_after=Decimal(str(result.get("credits", "0"))),
                    duration_sec=actual_dur,
                    description=desc,
                )
                db.add(record)
                await db.commit()
            else:
                print(f"  CHARGE FAILED")

    await db_engine.dispose()
    print("\nDone!")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python fix_charge_actual.py <user_access_token>")
        sys.exit(1)

    token = sys.argv[1]
    asyncio.run(fix_charge(token))
