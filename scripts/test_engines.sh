#!/bin/bash
sudo systemctl restart anki-api.service
sleep 3
echo "Health: $(curl -s http://127.0.0.1:8000/api/health)"

LOGIN=$(curl -s -X POST http://127.0.0.1:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@anki.app","password":"admin123456"}')
TOKEN=$(echo "$LOGIN" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

echo "=== Engines ==="
curl -s http://127.0.0.1:8000/api/system/engines -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

echo ""
echo "=== Billing Engines ==="
curl -s http://127.0.0.1:8000/api/billing/engines -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
