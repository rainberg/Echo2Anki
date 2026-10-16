#!/bin/bash
echo "=== Verify Migration ==="

echo ""
echo "--- Tasks for Guangrui ---"
sudo -u postgres psql -d anki -c "SELECT id, upload_name, file_duration_sec, stage, segment_count, engine, model_size, created_at FROM tasks WHERE user_id = 'fa98f9c1-8e5f-47d6-b77a-d73fdef2a54f' ORDER BY created_at;"

echo ""
echo "--- Segments count per task ---"
sudo -u postgres psql -d anki -c "SELECT t.upload_name, COUNT(s.id) as seg_count FROM tasks t LEFT JOIN segments s ON s.task_id = t.id WHERE t.user_id = 'fa98f9c1-8e5f-47d6-b77a-d73fdef2a54f' GROUP BY t.upload_name ORDER BY t.upload_name;"

echo ""
echo "--- Total segments for Guangrui ---"
sudo -u postgres psql -d anki -c "SELECT COUNT(*) FROM segments s JOIN tasks t ON s.task_id = t.id WHERE t.user_id = 'fa98f9c1-8e5f-47d6-b77a-d73fdef2a54f';"

echo ""
echo "--- Sample segment data ---"
sudo -u postgres psql -d anki -c "SELECT s.german_text, s.chinese_text, s.start_time, s.end_time, s.clip_path FROM segments s JOIN tasks t ON s.task_id = t.id WHERE t.user_id = 'fa98f9c1-8e5f-47d6-b77a-d73fdef2a54f' LIMIT 3;"

echo ""
echo "--- File system check ---"
echo "Uploads:"
sudo ls -la /var/lib/anki/uploads/fa98f9c1-8e5f-47d6-b77a-d73fdef2a54f/ 2>/dev/null
echo ""
echo "Task dirs:"
sudo ls -la /var/lib/anki/tasks/fa98f9c1-8e5f-47d6-b77a-d73fdef2a54f/ 2>/dev/null | head -10
echo ""
echo "Sample clips dir:"
FIRST_TASK=$(sudo ls /var/lib/anki/tasks/fa98f9c1-8e5f-47d6-b77a-d73fdef2a54f/ 2>/dev/null | head -1)
sudo ls /var/lib/anki/tasks/fa98f9c1-8e5f-47d6-b77a-d73fdef2a54f/$FIRST_TASK/clips/ 2>/dev/null | head -5
echo "..."
sudo ls /var/lib/anki/tasks/fa98f9c1-8e5f-47d6-b77a-d73fdef2a54f/$FIRST_TASK/clips/ 2>/dev/null | wc -l

echo ""
echo "--- API test: login as Guangrui ---"
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"ooJerry@gmail.com","password":"admin123456"}' | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('access_token',''))" 2>/dev/null)

if [ -z "$TOKEN" ]; then
  echo "WARNING: Could not login as Guangrui (may need password reset)"
else
  echo "Login OK"
  echo ""
  echo "--- API test: list tasks ---"
  curl -s http://127.0.0.1:8000/api/tasks -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f'Total tasks: {d.get(\"total\",0)}')
for t in d.get('items',[]):
    print(f'  {t[\"upload_name\"]}: stage={t[\"stage\"]}, segments={t[\"segment_count\"]}, duration={t.get(\"file_duration_sec\",\"?\")}s')
"
fi
