#!/bin/bash
set -e

TOKEN=$(curl -s -X POST http://127.0.0.1:9000/api/auth/login/password \
  -H 'Content-Type: application/json' \
  -d @/tmp/login.json | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

echo "=== Checking collection items ==="
COLL_ID="7ef7d43d-fc78-46a8-9d61-d8e35de27540"
curl -s -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8000/api/collections/$COLL_ID" | python3 -c '
import sys, json
d = json.load(sys.stdin)
for item in d.get("items", []):
    seg = item.get("segment") or {}
    tid = seg.get("task_id", "NONE")
    sid = item.get("segment_id", "NONE")
    txt = seg.get("german_text", "")[:50]
    print("  item_id=%s seg_id=%s task_id=%s text=%s" % (item["id"][:8], sid[:8], tid[:8], txt))
'

echo ""
echo "=== Check for duplicate text in collection ==="
curl -s -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8000/api/collections/$COLL_ID" | python3 -c '
import sys, json
d = json.load(sys.stdin)
texts = []
for item in d.get("items", []):
    seg = item.get("segment") or {}
    texts.append(seg.get("german_text", ""))
seen = set()
for t in texts:
    if t in seen:
        print("  DUPLICATE: %s" % t[:60])
    else:
        seen.add(t)
if len(texts) == len(seen):
    print("  No duplicates found")
'

echo ""
echo "=== Done ==="
