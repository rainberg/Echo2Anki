#!/bin/bash

echo "=== Full System Verification ==="

echo "[1] Health Check"
curl -s http://localhost:8000/api/health
echo ""

echo "[2] Login"
LOGIN_RESP=$(curl -s -X POST http://localhost:8000/api/auth/login -H 'Content-Type: application/json' -d '{"email":"admin@anki.app","password":"admin123456"}')
TOKEN=$(echo "$LOGIN_RESP" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["access_token"])')
echo "Token: obtained"

echo "[3] Balance"
curl -s http://localhost:8000/api/auth/billing/balance -H "Authorization: Bearer $TOKEN"
echo ""

echo "[4] Tasks"
curl -s 'http://localhost:8000/api/tasks?page=1&per_page=5' -H "Authorization: Bearer $TOKEN" | python3 -c 'import sys,json; d=json.load(sys.stdin); t=d["total"]; print(f"Tasks: {t} total")'

echo "[5] Admin Users"
curl -s 'http://localhost:8000/api/admin/users?per_page=3' -H "Authorization: Bearer $TOKEN" | python3 -c 'import sys,json; d=json.load(sys.stdin); t=d["total"]; print(f"Users: {t} total")'

echo "[6] Billing Engines"
curl -s http://localhost:8000/api/billing/engines -H "Authorization: Bearer $TOKEN"
echo ""

echo "[7] System Engines"
curl -s http://localhost:8000/api/system/engines
echo ""

echo "[8] Collections"
curl -s http://localhost:8000/api/collections -H "Authorization: Bearer $TOKEN"
echo ""

echo "[9] Public Tasks"
curl -s 'http://localhost:8000/api/public/tasks?per_page=3'
echo ""

echo "[10] Frontend Routes"
for path in / /login /tasks /billing /public /anki /admin; do
    CODE=$(curl -s -o /dev/null -w '%{http_code}' http://localhost/$path)
    echo "  $path -> $CODE"
done

echo ""
echo "=== Verification Complete ==="
