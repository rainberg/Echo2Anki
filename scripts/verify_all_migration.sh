#!/bin/bash
echo "=== Final Verification: All Tasks for Guangrui ==="

echo ""
echo "--- DB: All tasks ---"
sudo -u postgres psql -d anki -c "SELECT upload_name, file_duration_sec, stage, segment_count, stage_message FROM tasks WHERE user_id = 'fa98f9c1-8e5f-47d6-b77a-d73fdef2a54f' ORDER BY created_at;"

echo ""
echo "--- DB: Total counts ---"
sudo -u postgres psql -d anki -c "SELECT COUNT(*) as total_tasks, SUM(segment_count) as total_segments, COALESCE(SUM(file_duration_sec),0) as total_duration_sec FROM tasks WHERE user_id = 'fa98f9c1-8e5f-47d6-b77a-d73fdef2a54f';"

echo ""
echo "--- API: Login and list tasks ---"
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"ooJerry@gmail.com","password":"Guangrui2026"}' | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('access_token',''))")

if [ -z "$TOKEN" ]; then
  echo "LOGIN FAILED!"
  exit 1
fi
echo "Login OK"

echo ""
curl -s http://127.0.0.1:8000/api/tasks -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f'Total tasks: {d.get(\"total\",0)}')
for t in d.get('items',[]):
    dur = t.get('file_duration_sec')
    dur_min = round(float(dur)/60,1) if dur else '?'
    print(f'  {t[\"upload_name\"]}: stage={t[\"stage\"]}, segs={t[\"segment_count\"]}, dur={dur_min}min, note={t.get(\"stage_message\",\"\")}')
"

echo ""
echo "--- API: Billing balance ---"
curl -s http://127.0.0.1:8000/api/auth/billing/balance -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys,json
d=json.load(sys.stdin)
dur = float(d.get('total_duration_sec',0))
print(f'Credits: {d.get(\"credits\",\"?\")} min')
print(f'Total tasks: {d.get(\"total_tasks\",\"?\")}')
print(f'Total duration: {round(dur/60,1)} min ({round(dur/3600,1)} hours)')
"

echo ""
echo "--- API: Test audio access ---"
FIRST_TASK_ID=$(curl -s http://127.0.0.1:8000/api/tasks -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['items'][0]['id'] if d.get('items') else '')")
if [ -n "$FIRST_TASK_ID" ]; then
  AUDIO_URL="http://127.0.0.1:8000/api/audio/fa98f9c1-8e5f-47d6-b77a-d73fdef2a54f/$FIRST_TASK_ID/clips/clip_001.mp3"
  STATUS=$(curl -sI "$AUDIO_URL" | head -1)
  echo "Audio test ($FIRST_TASK_ID/clip_001.mp3): $STATUS"
fi

echo ""
echo "=== VERIFICATION COMPLETE ==="
