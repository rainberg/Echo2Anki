"""
修复孤儿 reserve：查找所有已结束但仍有 credits_reserved > 0 的任务，
通过 Auth Service API 退还冻结的积分。

用法（在服务器上）：
    cd /opt/anki-app/backend
    python -m scripts.fix_orphan_reserves [--dry-run]

需要先设置环境变量或确保 .env 文件存在。
"""

import argparse
import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
os.chdir(_PROJECT_ROOT)

from decimal import Decimal

import httpx
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Task


def _get_auth_token(email: str, password: str) -> str:
    resp = httpx.post(
        f"{settings.AUTH_SERVICE_URL}/api/auth/login",
        json={"account": email, "password": password, "app": "anki"},
        timeout=settings.AUTH_SERVICE_TIMEOUT,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Login failed: {resp.status_code} {resp.text}")
    return resp.json()["access_token"]


def _refund_via_auth(access_token: str, reserved_amount: Decimal, reference_id: str) -> dict | None:
    try:
        resp = httpx.post(
            f"{settings.AUTH_SERVICE_URL}/api/credits/settle",
            json={
                "reserved_amount": str(reserved_amount),
                "actual_amount": "0",
                "reference_id": reference_id,
                "description": "修复孤儿reserve - 全额退还",
            },
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=settings.AUTH_SERVICE_TIMEOUT,
        )
        if resp.status_code == 200:
            return resp.json()
        print(f"  [ERROR] Auth settle failed: {resp.status_code} {resp.text}")
        return None
    except Exception as e:
        print(f"  [ERROR] Auth service unreachable: {e}")
        return None


def _get_user_token_for_task(engine_db, user_id, admin_email, admin_password):
    result = engine_db.execute(text("SELECT email FROM users WHERE id = :uid"), {"uid": str(user_id)})
    row = result.fetchone()
    if not row or not row[0]:
        return None
    try:
        return _get_auth_token(row[0], admin_password)
    except Exception as e:
        print(f"  [WARN] Cannot get token for user {user_id}: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Fix orphan reserves")
    parser.add_argument("--dry-run", action="store_true", help="Only show what would be done")
    parser.add_argument("--email", default="ooJerry@gmail.com", help="Admin email for auth")
    parser.add_argument("--password", default="", help="Admin password for auth")
    args = parser.parse_args()

    engine = create_engine(settings.DATABASE_URL_SYNC, pool_size=5)
    total_refunded = Decimal("0")
    fixed_count = 0

    with Session(engine) as db:
        result = db.execute(
            select(Task).where(
                Task.credits_reserved > 0,
                Task.stage.in_(["done", "failed", "cancelled"]),
            )
        )
        orphan_tasks = result.scalars().all()

        if not orphan_tasks:
            print("No orphan reserves found.")
            return

        print(f"Found {len(orphan_tasks)} orphan reserve(s):\n")

        for task in orphan_tasks:
            print(f"Task {task.id}:")
            print(f"  stage={task.stage}, credits_reserved={task.credits_reserved}")
            print(f"  engine={task.engine}, model_size={task.model_size}")
            print(f"  reserve_reference_id={task.reserve_reference_id}")

            if args.dry_run:
                print(f"  [DRY-RUN] Would refund {task.credits_reserved} credits")
                continue

            access_token = _get_user_token_for_task(db, task.user_id, args.email, args.password)
            if not access_token:
                print(f"  [SKIP] Cannot get access token for user {task.user_id}")
                continue

            ref_id = task.reserve_reference_id or f"task:{task.id}:orphan-fix"
            auth_result = _refund_via_auth(access_token, task.credits_reserved, ref_id)

            if auth_result is not None:
                refund_amount = task.credits_reserved
                task.credits_reserved = Decimal("0")
                task.reserve_reference_id = None
                db.commit()
                total_refunded += refund_amount
                fixed_count += 1
                new_credits = auth_result.get("credits", "?")
                print(f"  [FIXED] Refunded {refund_amount}, new balance={new_credits}")
            else:
                print(f"  [FAILED] Could not refund via Auth Service")

    print(f"\nSummary: fixed {fixed_count}/{len(orphan_tasks)} orphan reserves, total refunded={total_refunded}")


if __name__ == "__main__":
    main()
