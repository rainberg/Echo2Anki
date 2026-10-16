#!/bin/bash
echo "=== Full API Chain Test ==="

echo "[1] Health check..."
curl -s https://anki.3mudi.com/api/health
echo ""

echo "[2] Register new user..."
REGISTER_RESULT=$(curl -s -X POST https://anki.3mudi.com/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"chain_test@example.com","password":"test123456"}')
echo "$REGISTER_RESULT"
echo ""

echo "[3] Login as admin..."
LOGIN_RESULT=$(curl -s -X POST https://anki.3mudi.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@anki.app","password":"admin123456"}')
echo "$LOGIN_RESULT"
echo ""

ACCESS_TOKEN=$(echo "$LOGIN_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null)

if [ -n "$ACCESS_TOKEN" ]; then
  echo "[4] Get current user..."
  curl -s https://anki.3mudi.com/api/auth/me \
    -H "Authorization: Bearer $ACCESS_TOKEN"
  echo ""

  echo "[5] Get billing balance..."
  curl -s https://anki.3mudi.com/api/auth/billing/balance \
    -H "Authorization: Bearer $ACCESS_TOKEN"
  echo ""

  echo "[6] Get engines..."
  curl -s https://anki.3mudi.com/api/system/engines \
    -H "Authorization: Bearer $ACCESS_TOKEN"
  echo ""

  echo "[7] Admin - list users..."
  curl -s https://anki.3mudi.com/api/admin/users \
    -H "Authorization: Bearer $ACCESS_TOKEN"
  echo ""
else
  echo "Login failed, skipping authenticated tests"
fi

echo ""
echo "=== All chain tests complete ==="
