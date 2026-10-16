#!/bin/bash
pkill -f 'uvicorn app.main' 2>/dev/null
sleep 1
cd /opt/anki-app/backend
nohup /opt/anki-venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 > /tmp/anki-api.log 2>&1 &
sleep 3
echo "=== Health ==="
curl -s http://127.0.0.1:8000/api/health
echo ""
echo "=== Register ==="
curl -s -X POST http://127.0.0.1:8000/api/auth/register -H "Content-Type: application/json" -d '{"email":"test@example.com","password":"test123456"}'
echo ""
echo "=== Login ==="
curl -s -X POST http://127.0.0.1:8000/api/auth/login -H "Content-Type: application/json" -d '{"email":"admin@anki.app","password":"admin123456"}'
echo ""
