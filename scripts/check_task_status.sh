#!/bin/bash
LOGIN=$(curl -s -X POST http://127.0.0.1:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@anki.app","password":"admin123456"}')
TOKEN=$(echo "$LOGIN" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "=== Task Status ==="
curl -s http://127.0.0.1:8000/api/tasks -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
echo ""
echo "=== API Logs (last 20) ==="
sudo journalctl -u anki-api.service --no-pager -n 20
