#!/bin/bash
echo "=== guangrui 的最近计费记录 ==="
echo "SELECT id, task_id, action, amount, balance_after, duration_sec, left(description,60) as desc, created_at FROM billing_records WHERE user_id = 'd57eab64-8945-4b33-9026-f0b717635adb' ORDER BY created_at DESC LIMIT 25;" | sudo -u postgres psql -d anki
echo ""
echo "=== 用户的 credits 和 credits_reserved ==="
echo "SELECT id, email, credits, credits_reserved FROM users WHERE id = 'd57eab64-8945-4b33-9026-f0b717635adb';" | sudo -u postgres psql -d anki
echo ""
echo "=== 有预扣但未结算的任务 ==="
echo "SELECT t.id, t.upload_name, t.engine, t.stage, t.credits_reserved, t.credits_charged, t.reserve_reference_id, t.file_duration_sec, t.finished_at FROM tasks t WHERE t.user_id = 'd57eab64-8945-4b33-9026-f0b717635adb' AND t.credits_reserved > 0 ORDER BY t.created_at DESC;" | sudo -u postgres psql -d anki
