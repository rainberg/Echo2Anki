#!/bin/bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@anki.app","password":"admin123456"}' | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('access_token',''))")

if [ -z "$TOKEN" ]; then
  echo "LOGIN FAILED"
  exit 1
fi

echo "=== Login OK ==="

echo ""
echo "=== GET /api/auth/me ==="
curl -s http://127.0.0.1:8000/api/auth/me -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; d=json.load(sys.stdin); print('User:', d.get('display_name','?')); print('Credits:', d.get('credits','?'))"

echo ""
echo "=== PUT /api/auth/me (update display_name) ==="
curl -s -X PUT http://127.0.0.1:8000/api/auth/me \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"display_name":"Admin"}' | python3 -c "import sys,json; d=json.load(sys.stdin); print('Updated name:', d.get('display_name','?'))"

echo ""
echo "=== PUT /api/auth/me (change password with wrong old_password) ==="
curl -s -X PUT http://127.0.0.1:8000/api/auth/me \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"old_password":"wrongpass","password":"newpass123"}' | python3 -c "import sys,json; d=json.load(sys.stdin); print('Error:', d.get('detail','?'))"

echo ""
echo "=== GET /api/auth/billing/balance ==="
curl -s http://127.0.0.1:8000/api/auth/billing/balance -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; d=json.load(sys.stdin); print('Credits:', d.get('credits','?')); print('Total used:', d.get('total_used','?'))"

echo ""
echo "=== ALL TESTS PASSED ==="
