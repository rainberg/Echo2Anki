#!/bin/bash
TOKEN=$(curl -s -X POST http://127.0.0.1:9000/api/auth/login/password \
  -H 'Content-Type: application/json' \
  -d @/tmp/login.json | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

echo "=== 1. GET /api/collections (through Cloudflare) ==="
curl -s -H "Authorization: Bearer $TOKEN" https://anki.3mudi.com/api/collections

echo ""
echo ""
echo "=== 2. GET /api/collections (direct backend) ==="
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/collections

echo ""
echo ""
echo "=== 3. Check index.html content ==="
curl -s https://anki.3mudi.com/index.html | head -15

echo ""
echo ""
echo "=== 4. Check JS file loaded ==="
curl -sI https://anki.3mudi.com/assets/CollectionsView-CfbwLvVL.js | head -5

echo ""
echo ""
echo "=== 5. Check latest nginx access log for collections ==="
sudo tail -20 /var/log/nginx/access.log 2>/dev/null | grep -i collection

echo ""
echo ""
echo "=== Done ==="
