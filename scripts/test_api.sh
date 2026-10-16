#!/bin/bash
set -x

echo "=== Test Register ==="
curl -sv -X POST http://127.0.0.1:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@anki.app","password":"admin123456","display_name":"Admin"}'

echo ""
echo "=== Test Login ==="
curl -s -X POST http://127.0.0.1:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@anki.app","password":"admin123456"}'

echo ""
echo "=== Test Health ==="
curl -s http://127.0.0.1:8000/api/health

echo ""
