"""
Fix remaining reserved credits - settle all remaining reserves.
Usage: /opt/anki-venv/bin/python3 fix_remaining_reserves.py <user_access_token>
"""
import sys
import os
import uuid

sys.path.insert(0, "/opt/anki-app/backend")
os.chdir("/opt/anki-app/backend")

import asyncio
from decimal import Decimal

from app.auth_client import get_credits_balance, settle_credits, refund_credits


async def fix_remaining(access_token: str):
    # Check current balance
    balance = await get_credits_balance(access_token)
    if balance:
        print(f"Current balance: {balance}")
        print(f"  credits: {balance.get('credits')}")
        print(f"  credits_reserved: {balance.get('credits_reserved')}")
    else:
        print("Failed to get balance")
        return

    reserved = Decimal(str(balance.get("credits_reserved", "0")))
    if reserved <= 0:
        print("No reserved credits to settle")
        return

    print(f"\nSettling {reserved} reserved credits...")

    # Settle all reserved credits with actual=reserved (no refund)
    ref_id = f"fix-settle-remaining-{uuid.uuid4().hex[:8]}"
    result = await settle_credits(access_token, reserved, reserved, ref_id, "结算剩余预扣(修复)")
    if result:
        print(f"SETTLE OK: {result}")
    else:
        print("SETTLE FAILED - trying refund instead")
        ref_id2 = f"fix-refund-remaining-{uuid.uuid4().hex[:8]}"
        result2 = await refund_credits(access_token, reserved, ref_id2, "退还剩余预扣(修复)")
        if result2:
            print(f"REFUND OK: {result2}")
        else:
            print("REFUND ALSO FAILED")

    # Check final balance
    balance2 = await get_credits_balance(access_token)
    if balance2:
        print(f"\nFinal balance: {balance2}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python fix_remaining_reserves.py <user_access_token>")
        sys.exit(1)

    token = sys.argv[1]
    asyncio.run(fix_remaining(token))
