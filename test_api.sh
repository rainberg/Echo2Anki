#!/bin/bash
set -e

TOKEN=$(curl -s -X POST http://127.0.0.1:9000/api/auth/login/password \
  -H 'Content-Type: application/json' \
  -d @/tmp/login.json | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

echo "=== Token obtained ==="

echo ""
echo "=== GET /api/collections ==="
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/collections | python3 -m json.tool

echo ""
echo "=== GET /api/tasks (first task) ==="
TASK_ID=$(curl -s -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8000/api/tasks?per_page=1" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["items"][0]["id"] if d["items"] else "NONE")')
echo "Task ID: $TASK_ID"

if [ "$TASK_ID" != "NONE" ]; then
  echo ""
  echo "=== GET /api/tasks/{id} - checking collected field ==="
  curl -s -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8000/api/tasks/$TASK_ID" | python3 -c '
import sys, json
d = json.load(sys.stdin)
for seg in d.get("segments", [])[:5]:
    idx = seg["seq_index"]
    col = seg.get("collected", "MISSING")
    txt = seg["german_text"][:40]
    print("  seg %d: collected=%s text=%s" % (idx, col, txt))
'
fi

echo ""
echo "=== Done ==="
