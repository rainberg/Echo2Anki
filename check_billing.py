"""Check unsettled billing records - read only, no token needed."""
import sys
sys.path.insert(0, "/opt/anki-app/backend")

from decimal import Decimal
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.config import settings
from app.models import Task, BillingRecord

engine = create_engine(settings.DATABASE_URL_SYNC, pool_size=2)

with Session(engine) as db:
    unsettled = []
    tasks = db.execute(
        select(Task).where(
            Task.credits_reserved == 0,
            Task.credits_charged > 0,
        )
    ).scalars().all()

    for task in tasks:
        reserved_records = db.execute(
            select(BillingRecord).where(
                BillingRecord.task_id == task.id,
                BillingRecord.action == "reserve"
            )
        ).scalars().all()

        settle_records = db.execute(
            select(BillingRecord).where(
                BillingRecord.task_id == task.id,
                BillingRecord.action.in_(["settle", "refund"])
            )
        ).scalars().all()

        if reserved_records and not settle_records:
            total_reserved = sum(-r.amount for r in reserved_records)
            unsettled.append({
                "task_id": str(task.id),
                "user_id": str(task.user_id),
                "engine": task.engine,
                "model_size": task.model_size,
                "file_duration_sec": task.file_duration_sec or Decimal("0"),
                "total_reserved": total_reserved,
                "credits_charged": task.credits_charged,
                "diff": total_reserved - task.credits_charged,
            })

    if not unsettled:
        print("No unsettled tasks found.")
        sys.exit(0)

    print(f"Found {len(unsettled)} unsettled tasks:")
    total_reserved_sum = Decimal("0")
    total_charged_sum = Decimal("0")
    for u in unsettled:
        print(f"  Task {u['task_id'][:8]}: reserved={u['total_reserved']}, charged={u['credits_charged']}, diff={u['diff']}")
        total_reserved_sum += u["total_reserved"]
        total_charged_sum += u["credits_charged"]

    total_diff = total_reserved_sum - total_charged_sum
    print(f"\nTotal: reserved={total_reserved_sum}, charged={total_charged_sum}, diff={total_diff}")
    print(f"User ID: {unsettled[0]['user_id']}")
    if total_diff > 0:
        print(f"User overpaid by {total_diff} - needs refund")
    elif total_diff < 0:
        print(f"User underpaid by {-total_diff} - auth service only held reserved amount")
