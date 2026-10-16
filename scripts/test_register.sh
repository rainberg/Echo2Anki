#!/bin/bash
curl -s -X POST http://127.0.0.1:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@anki.app","password":"admin123456","display_name":"Admin"}' 2>&1

echo ""
echo "---LOG---"
cat /tmp/anki-api.log 2>/dev/null || echo "no log file"
