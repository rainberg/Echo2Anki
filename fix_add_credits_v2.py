"""
Add credits back to user via anki-app admin API.
Usage: /opt/anki-venv/bin/python3 fix_add_credits_v2.py <admin_access_token>
"""
import sys
import os

sys.path.insert(0, "/opt/anki-app/backend")
os.chdir("/opt/anki-app/backend")

import asyncio
from decimal import Decimal
from uuid import UUID

from app.auth_client import admin_add_credits


USER_ID = UUID("d57eab64-8945-4b33-9026-f0b717635adb")
# Current: 3406.69, should be ~4505.95
# Difference: 4505.95 - 3406.69 = 1099.26
AMOUNT = Decimal("1099.26")


async def add_credits(admin_token: str):
    result = await admin_add_credits(
        admin_token, USER_ID, AMOUNT,
        remark="退还修复脚本多扣的积分（预扣结算修复）"
    )
    if result:
        print(f"SUCCESS: {result}")
    else:
        print("FAILED: admin_add_credits returned None")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python fix_add_credits_v2.py <admin_token>")
        sys.exit(1)

    token = sys.argv[1]
    asyncio.run(add_credits(token))
