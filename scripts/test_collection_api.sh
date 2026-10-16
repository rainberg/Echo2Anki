#!/bin/bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"ooJerry@gmail.com","password":"Guangrui2026"}' | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")

echo "=== List collections ==="
curl -s http://127.0.0.1:8000/api/collections -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys,json
d=json.load(sys.stdin)
items = d if isinstance(d, list) else d.get('items', d.get('data', []))
print(f'Type: {type(d).__name__}')
print(f'Keys: {list(d.keys()) if isinstance(d, dict) else \"list\"}')
for c in (items if isinstance(items, list) else []):
    print(f'  id={c.get(\"id\",\"?\")} name={c.get(\"name\",\"?\")} count={c.get(\"item_count\",\"?\")}')
"

echo ""
echo "=== Create collection test ==="
curl -s -X POST http://127.0.0.1:8000/api/collections \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name":"测试收藏集"}' | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f'Response keys: {list(d.keys())}')
print(f'ID type: {type(d.get(\"id\")).__name__}')
print(f'ID value: {d.get(\"id\",\"?\")}')
print(f'Name: {d.get(\"name\",\"?\")}')
"
