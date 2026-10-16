#!/bin/bash
set -e

TOKEN=$(curl -s -X POST http://127.0.0.1:9000/api/auth/login/password \
  -H 'Content-Type: application/json' \
  -d @/tmp/login.json | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

TASK_ID="7ec1ddb9-6560-42fc-8ebd-b51f35b4f9cf"
echo "=== GET /api/tasks/$TASK_ID - checking collected field ==="
curl -s -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8000/api/tasks/$TASK_ID" | python3 -c '
import sys, json
d = json.load(sys.stdin)
collected_count = 0
for seg in d.get("segments", []):
    idx = seg["seq_index"]
    col = seg.get("collected", "MISSING")
    txt = seg["german_text"][:50]
    if col:
        collected_count += 1
        print("  seg %d: collected=%s text=%s  *** COLLECTED ***" % (idx, col, txt))
print("Total collected: %d / %d" % (collected_count, len(d.get("segments", []))))
'

echo ""
echo "=== Done ==="
