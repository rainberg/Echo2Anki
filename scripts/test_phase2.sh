#!/bin/bash
echo "=== Phase 2 API Test ==="

echo "[1] Health check..."
curl -s https://anki.3mudi.com/api/health
echo ""

echo "[2] Login as admin..."
LOGIN=$(curl -s -X POST https://anki.3mudi.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@anki.app","password":"admin123456"}')
TOKEN=$(echo "$LOGIN" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null)
echo "Token: ${TOKEN:0:20}..."

echo "[3] List tasks (empty)..."
curl -s https://anki.3mudi.com/api/tasks \
  -H "Authorization: Bearer $TOKEN"
echo ""

echo "[4] Create task (upload)..."
dd if=/dev/urandom bs=1024 count=10 of=/tmp/test_audio.mp3 2>/dev/null
RESULT=$(curl -s -X POST https://anki.3mudi.com/api/tasks \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/tmp/test_audio.mp3" \
  -F "engine=local_whisper" \
  -F "model_size=tiny")
echo "$RESULT"
echo ""

TASK_ID=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
echo "Task ID: $TASK_ID"

if [ -n "$TASK_ID" ]; then
  echo "[5] Get task detail..."
  curl -s "https://anki.3mudi.com/api/tasks/$TASK_ID" \
    -H "Authorization: Bearer $TOKEN"
  echo ""
fi

echo "[6] List tasks..."
curl -s https://anki.3mudi.com/api/tasks \
  -H "Authorization: Bearer $TOKEN"
echo ""

echo "=== Phase 2 API Test Complete ==="
