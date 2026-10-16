#!/bin/bash
echo "=== Full System Test ==="

echo "[1] Health..."
curl -s https://anki.3mudi.com/api/health
echo ""

echo "[2] Login..."
LOGIN=$(curl -s -X POST https://anki.3mudi.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@anki.app","password":"admin123456"}')
TOKEN=$(echo "$LOGIN" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null)
echo "Token: ${TOKEN:0:20}..."

echo "[3] Tasks API..."
curl -s https://anki.3mudi.com/api/tasks -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Tasks: {d[\"total\"]} total')"
echo ""

echo "[4] Collections API..."
curl -s https://anki.3mudi.com/api/collections -H "Authorization: Bearer $TOKEN"
echo ""

echo "[5] Tags API..."
curl -s https://anki.3mudi.com/api/tags -H "Authorization: Bearer $TOKEN"
echo ""

echo "[6] Billing balance..."
curl -s https://anki.3mudi.com/api/billing/balance -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
echo ""

echo "[7] Billing engines..."
curl -s https://anki.3mudi.com/api/billing/engines -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
echo ""

echo "[8] Public library..."
curl -s "https://anki.3mudi.com/api/public/tasks" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Public tasks: {len(d)}')"
echo ""

echo "[9] Anki configs..."
curl -s https://anki.3mudi.com/api/anki/configs -H "Authorization: Bearer $TOKEN"
echo ""

echo "[10] System engines..."
curl -s https://anki.3mudi.com/api/system/engines -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
echo ""

echo "[11] Admin users..."
curl -s "https://anki.3mudi.com/api/admin/users?page=1&per_page=5" -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Users: {d[\"total\"]} total')"
echo ""

echo "[12] Vue SPA routes..."
for route in / /login /register /tasks /collections /billing /public /anki; do
  CODE=$(curl -s -o /dev/null -w '%{http_code}' "https://anki.3mudi.com$route")
  echo "  $route -> HTTP $CODE"
done

echo ""
echo "=== All tests complete ==="
