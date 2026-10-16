"""
Fix unsettled reserve records by calling auth service settle/refund API.
Usage: /opt/anki-venv/bin/python3 fix_unsettled_billing.py <user_access_token>
"""
import sys
import os

sys.path.insert(0, "/opt/anki-app/backend")
os.chdir("/opt/anki-app/backend")

import asyncio
from decimal import Decimal
from uuid import UUID

from app.auth_client import settle_credits, refund_credits
from app.models import BillingRecord, Task

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


# Unsettled tasks: (task_id, reserve_amount, actual_charged)
# For done tasks: settle(reserved, actual) -> charges actual, refunds difference
UNSETTLED_DONE = [
    ("eb551a51-68c7-4fff-a7ba-3fc932219a42", Decimal("55.08"), Decimal("60.02")),
    ("2062e846-5303-4c06-ba1d-545fd966446b", Decimal("47.58"), Decimal("51.92")),
    ("58ab42d6-01f3-4038-937e-a6cd6f9c4812", Decimal("36.64"), Decimal("39.90")),
    ("9acefbb9-e596-4d40-9616-6a2c9f6f35dc", Decimal("66.28"), Decimal("72.12")),
    ("ad141a2d-dfab-46a9-bec8-7266d6ead30e", Decimal("108.04"), Decimal("120.04")),
    ("f773c387-8000-4415-8f01-3bcb1ae2f95b", Decimal("108.04"), Decimal("120.04")),
    # f63d2645: first reserve of 27.01, settle with actual 30.01
    ("f63d2645-57b4-41dc-adc1-92c6f5b1f836", Decimal("27.01"), Decimal("30.01")),
]

# f63d2645 has a SECOND reserve of 27.01 that needs to be refunded
EXTRA_REFUND = [
    ("f63d2645-57b4-41dc-adc1-92c6f5b1f836", Decimal("27.01")),
]


async def fix_unsettled(access_token: str):
    from app.config import settings
    db_engine = create_async_engine(settings.DATABASE_URL)

    async with AsyncSession(db_engine) as db:
        for task_id_str, reserved, actual in UNSETTLED_DONE:
            task_id = UUID(task_id_str)
            task = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
            if not task:
                print(f"SKIP: Task {task_id_str[:8]} not found")
                continue

            user_id = task.user_id
            print(f"\n--- Task {task_id_str[:8]} ---")
            print(f"  Reserved: {reserved}, Actual: {actual}")

            reference_id = f"task:{task_id_str}:settle:fix"
            description = f"结算(修复): reserved={reserved}, actual={actual}"

            result = await settle_credits(
                access_token, reserved, actual, reference_id, description
            )
            if result:
                print(f"  SETTLE OK: {result}")
                record = BillingRecord(
                    user_id=user_id,
                    task_id=task_id,
                    action="settle",
                    amount=-actual,
                    balance_after=Decimal(str(result.get("credits", "0"))),
                    description=description,
                )
                db.add(record)
                if result.get("refund") and Decimal(result["refund"]) > 0:
                    refund_record = BillingRecord(
                        user_id=user_id,
                        task_id=task_id,
                        action="refund",
                        amount=Decimal(result["refund"]),
                        balance_after=Decimal(str(result.get("credits", "0"))),
                        description=f"退还差额(修复): {result['refund']}",
                    )
                    db.add(refund_record)
                    print(f"  REFUND: {result['refund']}")
                await db.commit()
            else:
                print(f"  SETTLE FAILED: auth service returned None")

        # Handle extra refund for f63d2645
        for task_id_str, refund_amount in EXTRA_REFUND:
            task_id = UUID(task_id_str)
            task = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
            if not task:
                print(f"SKIP: Task {task_id_str[:8]} not found")
                continue

            user_id = task.user_id
            print(f"\n--- Extra refund for {task_id_str[:8]} ---")
            print(f"  Refund amount: {refund_amount}")

            reference_id = f"task:{task_id_str}:refund:fix"
            description = "退还重复预扣(修复)"

            result = await refund_credits(
                access_token, refund_amount, reference_id, description
            )
            if result:
                print(f"  REFUND OK: {result}")
                record = BillingRecord(
                    user_id=user_id,
                    task_id=task_id,
                    action="refund",
                    amount=refund_amount,
                    balance_after=Decimal(str(result.get("credits", "0"))),
                    description=description,
                )
                db.add(record)
                await db.commit()
            else:
                print(f"  REFUND FAILED: auth service returned None")

    await db_engine.dispose()
    print("\n\nDone! All unsettled records have been processed.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python fix_unsettled_billing.py <user_access_token>")
        sys.exit(1)

    token = sys.argv[1]
    asyncio.run(fix_unsettled(token))
