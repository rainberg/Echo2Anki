#!/bin/bash
echo "=== Check V1 Streamlit service ==="
sudo systemctl list-units --type=service | grep -i stream
echo ""

echo "=== Check V1 Streamlit app ==="
sudo ls -la /opt/anki-app/app*.py 2>/dev/null
echo ""

echo "=== Check V1 task data dir ==="
sudo ls -la /var/lib/anki/tasks/ 2>/dev/null
echo ""
sudo find /var/lib/anki -maxdepth 3 -type d 2>/dev/null
echo ""

echo "=== Check V1 database ==="
sudo -u postgres psql -l 2>/dev/null | grep -v template | grep -v postgres
echo ""

echo "=== Check sqlite databases ==="
sudo find /opt/anki-app /var/lib/anki /home -name "*.db" -not -path "*/node_modules/*" -not -path "*/.git/*" -not -path "*/pki/*" -not -path "*/.pki/*" -not -path "*/.hermes/*" -not -path "*/.config/*" -not -path "*/.local/*" 2>/dev/null
echo ""

echo "=== Check V1 streamlit config ==="
sudo cat /etc/systemd/system/anki-streamlit*.service 2>/dev/null
echo ""

echo "=== Check /var/lib/anki-v2 full structure ==="
sudo find /var/lib/anki-v2 -maxdepth 1 -type d 2>/dev/null
echo ""

echo "=== Check /var/lib/anki full structure ==="
sudo find /var/lib/anki -maxdepth 2 -type d 2>/dev/null
echo ""

echo "=== Check deutsch-lernen-app ==="
sudo ls -la /home/deutsch-lernen-app/ 2>/dev/null | head -20
sudo ls -la /home/deutsch-lernen-app/data/ 2>/dev/null | head -20
