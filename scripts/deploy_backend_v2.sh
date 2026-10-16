#!/bin/bash
set -e

echo "=== Deploying Backend Files ==="

echo "[1/7] Copying models.py..."
sudo cp /tmp/models.py /opt/anki-app/backend/app/models.py

echo "[2/7] Copying billing.py..."
sudo cp /tmp/billing.py /opt/anki-app/backend/app/billing.py

echo "[3/7] Copying worker.py..."
sudo cp /tmp/worker.py /opt/anki-app/backend/app/worker.py

echo "[4/7] Copying main.py..."
sudo cp /tmp/main.py /opt/anki-app/backend/app/main.py

echo "[5/7] Copying routers..."
sudo cp /tmp/tasks.py /opt/anki-app/backend/app/routers/tasks.py
sudo cp /tmp/public.py /opt/anki-app/backend/app/routers/public.py
sudo cp /tmp/ws.py /opt/anki-app/backend/app/routers/ws.py

echo "[6/7] Creating alembic directories..."
sudo mkdir -p /opt/anki-app/backend/alembic/versions

echo "[7/7] Verifying files..."
ls -la /opt/anki-app/backend/app/models.py
ls -la /opt/anki-app/backend/app/billing.py
ls -la /opt/anki-app/backend/app/worker.py
ls -la /opt/anki-app/backend/app/main.py
ls -la /opt/anki-app/backend/app/routers/ws.py

echo ""
echo "=== Backend files deployed ==="
