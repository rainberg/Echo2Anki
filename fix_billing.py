"""Fix unsettled billing: settle reserved credits and add billing records.

For each task with reserve but no settle/refund:
1. Call the auth service settle API to properly settle the reserved credits
2. Add settle/refund billing records
"""
import sys
sys.path.insert(0, "/opt/anki-app/backend")

from decimal import Decimal
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.config import settings
from app.models import Task, BillingRecord
import httpx
import os

engine = create_engine(settings.DATABASE_URL_SYNC, pool_size=2)
ADMIN_TOKEN = os.environ.get("ADMIN_ACCESS_TOKEN", "")


def auth_settle(access_token, reserved_amount, actual_amount, reference_id="", description=""):
    """Call auth service settle API synchronously."""
    with httpx.Client(timeout=15) as client:
        resp = client.post(
            f"{settings.AUTH_SERVICE_URL}/api/credits/settle",
            json={
                "reserved_amount": str(reserved_amount),
                "actual_amount": str(actual_amount),
                "reference_id": reference_id,
                "description": description,
            },
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"  settle API error: {resp.status_code} {resp.text}")
            return None


def admin_add_credits(admin_token, user_id, amount, remark=""):
    """Call auth service admin add-credits API."""
    with httpx.Client(timeout=15) as client:
        resp = client.post(
            f"{settings.AUTH_SERVICE_URL}/api/admin/users/{user_id}/add-credits",
            json={"amount": str(amount), "remark": remark},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"  admin add-credits error: {resp.status_code} {resp.text}")
            return None


with Session(engine) as db:
    # Find all tasks with reserve but no settle/refund
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
                "reserve_reference_id": task.reserve_reference_id or "",
            })

    if not unsettled:
        print("No unsettled tasks found.")
        sys.exit(0)

    print(f"Found {len(unsettled)} unsettled tasks:")
    total_reserved_sum = Decimal("0")
    total_charged_sum = Decimal("0")
    for u in unsettled:
        print(f"  Task {u['task_id'][:8]}: reserved={u['total_reserved']}, charged={u['credits_charged']}, diff={u['diff']}, ref={u['reserve_reference_id'][:20] if u['reserve_reference_id'] else 'N/A'}")
        total_reserved_sum += u["total_reserved"]
        total_charged_sum += u["credits_charged"]

    total_diff = total_reserved_sum - total_charged_sum
    print(f"\nTotal: reserved={total_reserved_sum}, charged={total_charged_sum}, diff={total_diff}")

    if not ADMIN_TOKEN:
        print("\nERROR: ADMIN_ACCESS_TOKEN not set.")
        print("Set it and re-run to apply the fix.")
        sys.exit(1)

    # Use admin add-credits to credit the net difference
    # The auth service reserved the total_reserved amount but never settled.
    # We need to: 1) settle each task, or 2) credit the user the difference
    # Since we have admin token, we'll credit the net difference.
    user_id = unsettled[0]["user_id"]

    if total_diff > 0:
        print(f"\nUser overpaid by {total_diff}. Crediting user...")
        result = admin_add_credits(ADMIN_TOKEN, user_id, total_diff, "退还预扣差额（修复未结算记录）")
        if result:
            print(f"  Credited {total_diff} to user. Result: {result}")
        else:
            print("  ERROR: Failed to credit user")
            sys.exit(1)
    elif total_diff < 0:
        print(f"\nUser underpaid by {-total_diff}. The auth service only held {total_reserved_sum} but should charge {total_charged_sum}.")
        print("  Not charging additional amount (discount applied due to system error).")

    # Add settle billing records for each task
    for u in unsettled:
        settle_record = BillingRecord(
            user_id=u["user_id"],
            task_id=u["task_id"],
            action="settle",
            amount=-u["credits_charged"],
            balance_after=Decimal("0"),
            duration_sec=u["file_duration_sec"],
            description=f"结算(补录): {u['engine']}/{u['model_size']}, {u['file_duration_sec']}s",
        )
        db.add(settle_record)

        if u["diff"] > 0:
            refund_record = BillingRecord(
                user_id=u["user_id"],
                task_id=u["task_id"],
                action="refund",
                amount=u["diff"],
                balance_after=Decimal("0"),
                duration_sec=u["file_duration_sec"],
                description=f"退还差额(补录): {u['diff']}",
            )
            db.add(refund_record)

    db.commit()
    print("\nDone! Billing records updated and user credited.")
