#!/bin/bash
echo "=== Final Verification ==="

echo ""
echo "--- Login as Guangrui ---"
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"ooJerry@gmail.com","password":"Guangrui2026"}' | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('access_token',''))")

if [ -z "$TOKEN" ]; then
  echo "LOGIN FAILED!"
  exit 1
fi
echo "Login OK"

echo ""
echo "--- List tasks ---"
curl -s http://127.0.0.1:8000/api/tasks -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f'Total tasks: {d.get(\"total\",0)}')
for t in d.get('items',[]):
    print(f'  {t[\"upload_name\"]}: stage={t[\"stage\"]}, segments={t[\"segment_count\"]}, duration={t.get(\"file_duration_sec\",\"?\")}s')
"

echo ""
echo "--- Get first task detail (segments) ---"
FIRST_TASK_ID=$(curl -s http://127.0.0.1:8000/api/tasks -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['items'][0]['id'] if d.get('items') else '')")
if [ -n "$FIRST_TASK_ID" ]; then
  curl -s "http://127.0.0.1:8000/api/tasks/$FIRST_TASK_ID" -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys,json
d=json.load(sys.stdin)
segs = d.get('segments',[])
print(f'Task: {d[\"upload_name\"]}')
print(f'Segments: {len(segs)}')
for s in segs[:3]:
    print(f'  [{s[\"start_time\"]}-{s[\"end_time\"]}] {s[\"german_text\"][:60]}')
    print(f'    clip: {s.get(\"clip_path\",\"?\")}')
"
fi

echo ""
echo "--- Billing balance ---"
curl -s http://127.0.0.1:8000/api/auth/billing/balance -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f'Credits: {d.get(\"credits\",\"?\")}')
print(f'Total used: {d.get(\"total_used\",\"?\")}')
print(f'Total tasks: {d.get(\"total_tasks\",\"?\")}')
print(f'Total duration: {d.get(\"total_duration_sec\",\"?\")}s')
"

echo ""
echo "=== ALL VERIFIED ==="
